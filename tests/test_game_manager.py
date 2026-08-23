"""Tests pour src/core/game_manager.py"""

import sys
from unittest.mock import patch

import pytest

from src.core.config import Config
from src.core.game_data import GameData, GameVersion, Catalog
from src.core.game_manager import GameManager, GameState, _is_safe_relative
from src.core.pre_launch import apply_ini_patches, create_pre_launch_files, unblock_game_dlls
from src.core.system_checks import check_vcredist_x86, check_d3d11_feature_level


# ── Helpers ──

GAME_DICT = {
    "id": "hp_test",
    "name": "HP Test",
    "year": 2001,
    "description": "Desc",
    "developer": "Dev",
    "executable": "HPTest/System/Game.exe",
    "cover_image": "test.jpg",
    "latest_version": "1.0",
    "recommended_version": "1.0",
    "versions": [{
        "version": "1.0", "date": "2026-01-01",
        "download_url": "https://example.com/game.7z",
        "download_parts": None, "size_mb": 100, "changes": [],
    }],
    "post_install": {"registry": []},
}


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path):
    """Empêche les tests d'écrire dans le vrai config.json."""
    with patch("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json"):
        yield


def _make_manager(tmp_path, games=None):
    """Crée un GameManager avec un catalogue custom et un dossier temp."""
    if games is None:
        games = [GameData.from_dict(GAME_DICT)]
    catalog = Catalog(catalog_version="1.0", catalog_url="", games=tuple(games))
    config = Config(install_path=tmp_path, cache_path=tmp_path / ".cache")
    with patch("src.core.game_manager.load_catalog", return_value=catalog):
        return GameManager(config)


# ── Tests _is_safe_relative ──

class TestIsSafeRelative:
    def test_normal_path(self):
        assert _is_safe_relative("HP1/System/Game.exe") is True

    def test_backslash(self):
        assert _is_safe_relative("HP1\\System\\Game.exe") is True

    def test_traversal(self):
        assert _is_safe_relative("../evil.exe") is False

    def test_absolute(self):
        assert _is_safe_relative("/usr/bin/evil") is False
        assert _is_safe_relative("C:\\Windows\\System32\\evil.exe") is False

    def test_hidden_traversal(self):
        assert _is_safe_relative("HP1/../../evil.exe") is False

    def test_single_file(self):
        assert _is_safe_relative("game.exe") is True


# ── Tests GameManager ──

class TestGameManager:
    def test_init(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert len(mgr.get_games()) == 1
        assert mgr.get_state("hp_test") == GameState.NOT_INSTALLED

    def test_detect_installed(self, tmp_path):
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("fake")
        mgr = _make_manager(tmp_path)
        assert mgr.get_state("hp_test") == GameState.INSTALLED

    def test_get_game_by_id(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.get_game_by_id("hp_test") is not None
        assert mgr.get_game_by_id("nonexistent") is None

    def test_get_game_path(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.get_game_path("hp_test") == tmp_path / "HPTest"

    def test_installed_version(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.installed_version("hp_test") is None
        mgr.save_installed_version("hp_test", "1.0")
        assert mgr.installed_version("hp_test") == "1.0"

    def test_has_update(self, tmp_path):
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("fake")
        mgr = _make_manager(tmp_path)
        mgr.save_installed_version("hp_test", "0.9")
        assert mgr.has_update("hp_test") is True
        mgr.save_installed_version("hp_test", "1.0")
        assert mgr.has_update("hp_test") is False

    def test_backfill_installed_without_version(self, tmp_path):
        """Régression d'audit : un jeu installé SANS version enregistrée (config
        réinitialisée, dossier préexistant) ne recevait JAMAIS de notification
        de mise à jour — has_update exige une version connue."""
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("fake")
        mgr = _make_manager(tmp_path)  # config vierge, jeu détecté sur disque
        # Backfillée à la version recommandée (même convention que l'import)
        assert mgr.installed_version("hp_test") == "1.0"

        # …et au prochain bump du catalogue, la mise à jour est bien signalée
        new_game = GameData.from_dict({**GAME_DICT, "recommended_version": "2.0"})
        mgr.reload_catalog(Catalog(catalog_version="2.0", catalog_url="", games=(new_game,)))
        assert mgr.has_update("hp_test") is True

    def test_backfill_after_install_path_change(self, tmp_path):
        """Changement d'install_path vers un dossier déjà peuplé : refresh_states
        détecte le jeu ET lui enregistre une version."""
        other = tmp_path / "ailleurs"
        exe = other / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("fake")
        mgr = _make_manager(tmp_path)  # install_path initial : vide
        assert mgr.installed_version("hp_test") is None

        mgr.config.install_path = other
        mgr.refresh_states()
        assert mgr.get_state("hp_test") == GameState.INSTALLED
        assert mgr.installed_version("hp_test") == "1.0"

    def test_set_game_state(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.set_game_state("hp_test", GameState.DOWNLOADING)
        assert mgr.get_state("hp_test") == GameState.DOWNLOADING

    def test_set_state_unknown_game(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.set_game_state("unknown", GameState.INSTALLED)
        assert mgr.get_state("unknown") == GameState.NOT_INSTALLED

    def test_reload_catalog(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.set_game_state("hp_test", GameState.DOWNLOADING)

        new_game = GameData.from_dict({**GAME_DICT, "recommended_version": "2.0"})
        new_catalog = Catalog(catalog_version="2.0", catalog_url="", games=(new_game,))
        mgr.reload_catalog(new_catalog)

        # State should be preserved
        assert mgr.get_state("hp_test") == GameState.DOWNLOADING
        assert mgr.catalog.catalog_version == "2.0"

    def test_refresh_states_detects_removed_game(self, tmp_path):
        """Régression : après changement d'install_path, les états doivent être re-détectés."""
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("fake")
        mgr = _make_manager(tmp_path)
        assert mgr.get_state("hp_test") == GameState.INSTALLED

        mgr.config.install_path = tmp_path / "nouveau_dossier"
        mgr.refresh_states()
        assert mgr.get_state("hp_test") == GameState.NOT_INSTALLED

    def test_refresh_states_preserves_transient(self, tmp_path):
        """Un téléchargement en cours ne doit pas être écrasé par la re-détection."""
        mgr = _make_manager(tmp_path)
        mgr.set_game_state("hp_test", GameState.DOWNLOADING)
        mgr.refresh_states()
        assert mgr.get_state("hp_test") == GameState.DOWNLOADING

    def test_redetect_state_single_game(self, tmp_path):
        """redetect_state force la détection disque (utilisé après annulation/erreur).

        Cas réel : mise à jour annulée — l'ancienne version est toujours là,
        l'état doit revenir à INSTALLED, pas NOT_INSTALLED.
        """
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("fake")
        mgr = _make_manager(tmp_path)
        mgr.set_game_state("hp_test", GameState.DOWNLOADING)  # update en cours
        mgr.redetect_state("hp_test")  # annulation → re-détection
        assert mgr.get_state("hp_test") == GameState.INSTALLED

    def test_playtime_tracking(self, tmp_path):
        """add_playtime cumule, date la dernière session, ignore les jeux inconnus."""
        mgr = _make_manager(tmp_path)
        assert mgr.get_playtime("hp_test") == 0
        assert mgr.last_played("hp_test") is None

        mgr.add_playtime("hp_test", 120)
        mgr.add_playtime("hp_test", 60)
        assert mgr.get_playtime("hp_test") == 180
        assert mgr.last_played("hp_test") is not None

        mgr.add_playtime("inconnu", 60)
        assert mgr.get_playtime("inconnu") == 0
        mgr.add_playtime("hp_test", 0)  # durée nulle ignorée
        assert mgr.get_playtime("hp_test") == 180

    def test_last_played_game_id(self, tmp_path):
        """Hero dynamique : jeu joué le plus récemment, ids retirés du catalogue ignorés."""
        mgr = _make_manager(tmp_path)
        assert mgr.last_played_game_id() is None

        mgr.config.last_played["hp_test"] = "2026-06-01"
        mgr.config.last_played["disparu"] = "2026-06-10"  # plus dans le catalogue
        assert mgr.last_played_game_id() == "hp_test"

    def test_new_game_badge_lifecycle(self, tmp_path):
        """is_new/mark_seen : badge posé au reload du catalogue, retiré à la sélection."""
        mgr = _make_manager(tmp_path)
        assert mgr.is_new("hp_test") is False

        new_game = GameData.from_dict({**GAME_DICT, "id": "hp_new", "name": "HP New"})
        old_game = GameData.from_dict(GAME_DICT)
        catalog = Catalog(catalog_version="2.0", catalog_url="", games=(old_game, new_game))
        mgr.reload_catalog(catalog)

        assert mgr.is_new("hp_new") is True
        assert mgr.is_new("hp_test") is False  # déjà connu
        mgr.mark_seen("hp_new")
        assert mgr.is_new("hp_new") is False

    def test_uninstall(self, tmp_path):
        game_dir = tmp_path / "HPTest" / "System"
        game_dir.mkdir(parents=True)
        (game_dir / "Game.exe").write_text("fake")
        (game_dir / "Data.dll").write_text("fake")
        mgr = _make_manager(tmp_path)
        mgr.save_installed_version("hp_test", "1.0")

        assert mgr.uninstall_game("hp_test") is True
        assert not (tmp_path / "HPTest").exists()
        assert mgr.get_state("hp_test") == GameState.NOT_INSTALLED
        assert mgr.installed_version("hp_test") is None

    def test_uninstall_readonly_files(self, tmp_path):
        game_dir = tmp_path / "HPTest" / "System"
        game_dir.mkdir(parents=True)
        exe = game_dir / "Game.exe"
        exe.write_text("fake")
        readonly = game_dir / "ReadOnly.ini"
        readonly.write_text("data")
        readonly.chmod(0o444)

        mgr = _make_manager(tmp_path)
        assert mgr.uninstall_game("hp_test") is True
        assert not (tmp_path / "HPTest").exists()

    def test_launch_missing_exe(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.launch_game("hp_test")
        assert result is None

    def test_unsafe_executable_rejected_at_parse(self):
        """Validation early : path traversal refusé au parsing du catalog."""
        bad_dict = {**GAME_DICT, "executable": "../../../evil.exe"}
        with pytest.raises(ValueError, match="executable non"):
            GameData.from_dict(bad_dict)
        with pytest.raises(ValueError, match="executable non"):
            GameData.from_dict({**GAME_DICT, "executable": "/etc/passwd"})
        with pytest.raises(ValueError, match="executable non"):
            GameData.from_dict({**GAME_DICT, "executable": "C:\\Windows\\evil.exe"})


# ── Tests DLL unblock ──

class TestUnblockDlls:
    def test_unblock_removes_zone_identifier(self, tmp_path):
        dll = tmp_path / "test.dll"
        dll.write_text("fake dll")
        # Créer un faux Zone.Identifier (NTFS alternate data stream)
        # On ne peut pas facilement tester les ADS hors NTFS,
        # mais on vérifie que la méthode ne crashe pas
        unblock_game_dlls(tmp_path)
        # Pas de crash = OK


# ── Tests pre-launch ──

class TestPreLaunch:
    def test_create_files(self, tmp_path):
        game_dict = {
            **GAME_DICT,
            "pre_launch": {
                "create_files": [str(tmp_path / "TestDir" / "Running.ini")],
            },
        }
        game = GameData.from_dict(game_dict)
        mgr = _make_manager(tmp_path, games=[game])
        # Patch get_documents_dir to return tmp_path
        with patch("src.core.pre_launch.get_documents_dir", return_value=tmp_path):
            create_pre_launch_files(game, mgr.config)
        assert (tmp_path / "TestDir" / "Running.ini").exists()

    def test_apply_ini_patches(self, tmp_path):
        ini_file = tmp_path / "Game.ini"
        ini_file.write_text("[Engine.Engine]\nGameRenderDevice=OldValue\n", encoding="utf-8")

        game_dict = {
            **GAME_DICT,
            "pre_launch": {
                "ini_patches": [{
                    "file": str(ini_file),
                    "section": "Engine.Engine",
                    "key": "GameRenderDevice",
                    "value": "NewValue",
                }],
            },
        }
        game = GameData.from_dict(game_dict)
        mgr = _make_manager(tmp_path, games=[game])
        with patch("src.core.pre_launch.get_documents_dir", return_value=tmp_path):
            apply_ini_patches(game, mgr.config)

        content = ini_file.read_text(encoding="utf-8")
        assert "GameRenderDevice=NewValue" in content

    def test_ini_patch_adds_missing_key(self, tmp_path):
        ini_file = tmp_path / "Game.ini"
        ini_file.write_text("[Engine.Engine]\nExisting=Yes\n", encoding="utf-8")

        game_dict = {
            **GAME_DICT,
            "pre_launch": {
                "ini_patches": [{
                    "file": str(ini_file),
                    "section": "Engine.Engine",
                    "key": "NewKey",
                    "value": "NewValue",
                }],
            },
        }
        game = GameData.from_dict(game_dict)
        mgr = _make_manager(tmp_path, games=[game])
        with patch("src.core.pre_launch.get_documents_dir", return_value=tmp_path):
            apply_ini_patches(game, mgr.config)

        content = ini_file.read_text(encoding="utf-8")
        assert "NewKey=NewValue" in content

    def test_ini_patch_adds_missing_section(self, tmp_path):
        ini_file = tmp_path / "Game.ini"
        ini_file.write_text("[OtherSection]\nFoo=Bar\n", encoding="utf-8")

        game_dict = {
            **GAME_DICT,
            "pre_launch": {
                "ini_patches": [{
                    "file": str(ini_file),
                    "section": "NewSection",
                    "key": "Key",
                    "value": "Value",
                }],
            },
        }
        game = GameData.from_dict(game_dict)
        mgr = _make_manager(tmp_path, games=[game])
        with patch("src.core.pre_launch.get_documents_dir", return_value=tmp_path):
            apply_ini_patches(game, mgr.config)

        content = ini_file.read_text(encoding="utf-8")
        assert "[NewSection]" in content
        assert "Key=Value" in content


# ── Tests system checks ──

class TestSystemChecks:
    def test_vcredist_non_windows(self):
        with patch.object(sys, "platform", "linux"):
            assert check_vcredist_x86() is True

    def test_d3d11_non_windows(self):
        with patch.object(sys, "platform", "linux"):
            assert check_d3d11_feature_level() is False


class TestExpectedHashes:
    """Résolution des empreintes : catalogue d'abord, sinon celles de GitHub.

    L'enjeu est qu'une empreinte OUBLIÉE dans games.json ne laisse pas la
    vérification d'intégrité dormante — GitHub publie déjà la sienne.
    """

    A = "aa" * 32
    B = "bb" * 32
    C = "cc" * 32

    @staticmethod
    def _version(**kw):
        data = {"version": "1.0", "date": "2026-01-01", "size_mb": 100,
                "changes": [], "download_url": "https://x/game.7z"}
        data.update(kw)
        return GameVersion.from_dict(data)

    def test_catalogue_prioritaire(self, tmp_path):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/game.7z": self.B})
        sha, parts = m.expected_hashes(self._version(sha256=self.A))
        assert sha == self.A and parts == []

    def test_repli_sur_github(self, tmp_path):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/game.7z": self.B})
        sha, parts = m.expected_hashes(self._version())
        assert sha == self.B and parts == []

    def test_aucune_source(self, tmp_path):
        m = _make_manager(tmp_path)
        sha, parts = m.expected_hashes(self._version())
        assert sha is None and parts == []

    def test_url_inconnue_de_github(self, tmp_path):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://autre/ailleurs.7z": self.B})
        sha, parts = m.expected_hashes(self._version())
        assert sha is None and parts == []

    def test_desaccord_journalise_mais_catalogue_gagne(self, tmp_path, caplog):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/game.7z": self.B})
        with caplog.at_level("WARNING"):
            sha, _ = m.expected_hashes(self._version(sha256=self.A))
        assert sha == self.A
        assert any("diff" in r.message.lower() or "GitHub" in r.message
                   for r in caplog.records)

    # ── multi-parts ──

    def test_parts_depuis_github(self, tmp_path):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/a.001": self.A, "https://x/a.002": self.B})
        v = self._version(download_url=None,
                          download_parts=["https://x/a.001", "https://x/a.002"])
        sha, parts = m.expected_hashes(v)
        assert sha is None and parts == [self.A, self.B]

    def test_parts_catalogue_prioritaire(self, tmp_path):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/a.001": self.A, "https://x/a.002": self.B})
        v = self._version(download_url=None,
                          download_parts=["https://x/a.001", "https://x/a.002"],
                          sha256_parts=[self.C, self.C])
        sha, parts = m.expected_hashes(v)
        assert sha is None and parts == [self.C, self.C]

    def test_parts_partielles_rejetees(self, tmp_path):
        """Une liste trouée décalerait les empreintes d'un cran et ferait
        échouer une archive pourtant saine — tout ou rien."""
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/a.001": self.A})  # .002 manquant
        v = self._version(download_url=None,
                          download_parts=["https://x/a.001", "https://x/a.002"])
        sha, parts = m.expected_hashes(v)
        assert sha is None and parts == []

    def test_parts_catalogue_incomplet_retombe_sur_github(self, tmp_path):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/a.001": self.A, "https://x/a.002": self.B})
        v = self._version(download_url=None,
                          download_parts=["https://x/a.001", "https://x/a.002"],
                          sha256_parts=[self.C])  # une seule sur deux
        sha, parts = m.expected_hashes(v)
        assert parts == [self.A, self.B]

    # ── casse des noms d'assets ──

    def test_casse_differente_trouvee(self, tmp_path):
        """Cas réel hp6 : le catalogue dit « hp6.7z.001 », l'asset « HP6.7z.001 ».

        GitHub sert les deux formes mais n'en publie qu'une : sans recherche
        insensible à la casse, ces versions perdraient leur vérification.
        """
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/HP6.7z.001": self.A,
                             "https://x/HP6.7z.002": self.B})
        v = self._version(download_url=None,
                          download_parts=["https://x/hp6.7z.001", "https://x/hp6.7z.002"])
        sha, parts = m.expected_hashes(v)
        assert parts == [self.A, self.B]

    def test_casse_differente_simple(self, tmp_path):
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/GAME.7z": self.A})
        sha, _ = m.expected_hashes(self._version(download_url="https://x/game.7z"))
        assert sha == self.A

    def test_ambiguite_de_casse_ignoree(self, tmp_path):
        """Deux assets ne différant que par la casse, empreintes distinctes :
        ne pas vérifier vaut mieux que vérifier contre la mauvaise."""
        m = _make_manager(tmp_path)
        m.set_asset_digests({"https://x/Game.7z": self.A, "https://x/game.7z": self.B})
        # L'URL exacte reste servie…
        sha, _ = m.expected_hashes(self._version(download_url="https://x/game.7z"))
        assert sha == self.B
        # …mais une variante de casse non listée n'est plus devinable.
        sha, _ = m.expected_hashes(self._version(download_url="https://x/GAME.7z"))
        assert sha is None


# ── Langue de jeu (registre) ──

_LANG_BLOCK = {
    "root": "HKLM",
    "view": 32,
    "key": "SOFTWARE" + chr(92) + "Electronic Arts" + chr(92) + "Jeu",
    "languages": {
        "fr": {"label": "Français", "values": {"Language": "French", "Locale": "fr_FR"}},
        "en": {"label": "English", "values": {"Language": "English", "Locale": "en_US"}},
        "de": {"label": "Deutsch", "values": {"Language": "German", "Locale": "de_DE"}},
    },
}


def _jeu_multilingue():
    return GameData.from_dict({**GAME_DICT, "id": "hp7a", "language_registry": _LANG_BLOCK})


class TestLangueDeJeu:
    """La langue est une PRÉFÉRENCE, pas un fait d'installation.

    Aucun défaut figé ne peut convenir — « English » bloque un francophone, la
    langue système bloque un francophone qui veut jouer en anglais. Ce qui
    bloquait tout le monde, c'était l'absence de bascule.
    """

    def test_aucune_langue_pour_un_jeu_qui_n_en_declare_pas(self, tmp_path):
        m = _make_manager(tmp_path)
        assert m.game_language(m.get_games()[0].game) is None

    def test_defaut_sur_la_langue_de_l_interface(self, tmp_path):
        from src.core.i18n import set_language
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        set_language("en")
        try:
            assert m.game_language(jeu) == "en"
        finally:
            set_language("fr")
        assert m.game_language(jeu) == "fr"

    def test_repli_sur_la_premiere_si_l_interface_n_est_pas_proposee(self, tmp_path):
        from src.core.i18n import set_language
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        set_language("es")   # le jeu ne propose pas l'espagnol
        try:
            assert m.game_language(jeu) == "fr"
        finally:
            set_language("fr")

    def test_le_choix_explicite_prime(self, tmp_path):
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        m.set_game_language("hp7a", "de")
        assert m.game_language(jeu) == "de"
        assert m.config.game_language["hp7a"] == "de"

    def test_une_langue_non_proposee_est_ignoree(self, tmp_path):
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        m.set_game_language("hp7a", "ja")
        assert "hp7a" not in m.config.game_language
        assert m.game_language(jeu) == "fr"

    def test_un_choix_devenu_invalide_retombe_sur_le_defaut(self, tmp_path):
        """Le catalogue peut retirer une langue : le choix stocké ne doit pas
        rendre le jeu inutilisable pour autant."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        m.config.game_language["hp7a"] = "ja"
        assert m.game_language(jeu) == "fr"

    def test_apply_ecrit_les_valeurs_de_la_langue_choisie(self, tmp_path):
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        m.set_game_language("hp7a", "en")
        vus = []
        with patch("src.core.game_manager.registre.ecrire_valeurs",
                   side_effect=lambda *a, **k: vus.append(a) or True):
            assert m.apply_game_language(jeu) is True
        assert vus[0][0] == "HKLM"
        assert vus[0][2] == {"Language": "English", "Locale": "en_US"}
        assert vus[0][3] == 32

    def test_apply_ne_fait_rien_sans_bloc_de_langue(self, tmp_path):
        m = _make_manager(tmp_path)
        with patch("src.core.game_manager.registre.ecrire_valeurs") as ecrire:
            assert m.apply_game_language(m.get_games()[0].game) is True
        ecrire.assert_not_called()

    def test_un_echec_de_registre_ne_bloque_pas_le_lancement(self, tmp_path, monkeypatch):
        """UAC refusé : le jeu démarre dans la langue déjà en place, ce qui vaut
        mieux que de ne pas démarrer du tout."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        monkeypatch.setattr("src.core.game_manager.prerequis_manquants", lambda _r: [])
        monkeypatch.setattr("src.core.game_manager.unblock_game_dlls", lambda _p: None)
        monkeypatch.setattr("src.core.game_manager.delete_pre_launch_files", lambda *a: None)
        monkeypatch.setattr("src.core.game_manager.create_pre_launch_files", lambda *a: None)
        monkeypatch.setattr("src.core.game_manager.apply_ini_patches", lambda *a: None)
        monkeypatch.setattr("src.core.game_manager.registre.ecrire_valeurs",
                            lambda *a, **k: False)
        lances = []
        monkeypatch.setattr("src.core.game_manager.subprocess.Popen",
                            lambda *a, **k: lances.append(a) or object())
        assert m.launch_game("hp7a") is not None
        assert len(lances) == 1

    def _jeu_pret_a_lancer(self, tmp_path, monkeypatch, ecriture_ok):
        """Un jeu lançable, avec toute la plomberie de pré-lancement neutralisée."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        for nom in ("unblock_game_dlls", "delete_pre_launch_files",
                    "create_pre_launch_files", "apply_ini_patches"):
            monkeypatch.setattr("src.core.game_manager." + nom, lambda *a: None)
        monkeypatch.setattr("src.core.game_manager.prerequis_manquants", lambda _r: [])
        monkeypatch.setattr("src.core.game_manager.registre.ecrire_valeurs",
                            lambda *a, **k: ecriture_ok)
        monkeypatch.setattr("src.core.game_manager.subprocess.Popen",
                            lambda *a, **k: object())
        return m

    def test_un_echec_de_registre_est_signale_a_l_appelant(self, tmp_path, monkeypatch):
        """Le jeu démarre quand même, mais on ne se tait pas.

        Sur HP7 partie 2, un `Locale` resté à `fr_FR` donne un jeu qui refuse
        de se lancer : sans ce signal, l'utilisateur voit une fenêtre se
        fermer et rien ne relie ça à l'invite qu'il vient de voir passer.
        """
        m = self._jeu_pret_a_lancer(tmp_path, monkeypatch, ecriture_ok=False)
        avertis = []
        assert m.launch_game("hp7a", avertir=lambda: avertis.append(1)) is not None
        assert avertis == [1]

    def test_rien_a_signaler_quand_le_registre_a_pris(self, tmp_path, monkeypatch):
        """Un lancement normal ne doit produire AUCUN message : c'est le cas
        courant, dès le deuxième démarrage."""
        m = self._jeu_pret_a_lancer(tmp_path, monkeypatch, ecriture_ok=True)
        avertis = []
        assert m.launch_game("hp7a", avertir=lambda: avertis.append(1)) is not None
        assert avertis == []

    def test_l_absence_de_rappel_ne_casse_rien(self, tmp_path, monkeypatch):
        """`avertir` est optionnel : les appelants qui l'ignorent doivent
        continuer à lancer sans lever."""
        m = self._jeu_pret_a_lancer(tmp_path, monkeypatch, ecriture_ok=False)
        assert m.launch_game("hp7a") is not None


class TestDetectionDeLaLangue:
    """La ligne meta doit dire ce que le registre porte VRAIMENT.

    Sinon elle annonce une langue que le jeu n'a pas, et le lancement veut
    « corriger » le registre — donc demander une elevation — alors que
    l'utilisateur n'a rien demande.
    """

    def test_detecte_la_langue_posee(self, tmp_path):
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        with patch("src.core.game_manager.registre.lire_valeurs",
                   return_value={"Language": "German", "Locale": "de_DE"}):
            assert m.detect_game_language(jeu) == "de"

    def test_none_si_la_cle_est_absente(self, tmp_path):
        """Cas d'un jeu installe par le launcher : l'installeur EA n'a jamais
        tourne, la cle n'existe pas."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        with patch("src.core.game_manager.registre.lire_valeurs", return_value={}):
            assert m.detect_game_language(jeu) is None

    def test_none_si_les_valeurs_ne_correspondent_a_aucune_langue(self, tmp_path):
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        with patch("src.core.game_manager.registre.lire_valeurs",
                   return_value={"Language": "Klingon", "Locale": "tlh"}):
            assert m.detect_game_language(jeu) is None

    def test_une_correspondance_PARTIELLE_ne_compte_pas(self, tmp_path):
        """Toutes les valeurs de la langue doivent coller, sinon on ne sait pas
        dans quel etat est le jeu — et pretendre le savoir serait pire."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        with patch("src.core.game_manager.registre.lire_valeurs",
                   return_value={"Language": "German", "Locale": "fr_FR"}):
            assert m.detect_game_language(jeu) is None

    def test_la_detection_prime_sur_la_langue_d_interface(self, tmp_path):
        from src.core.i18n import set_language
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        set_language("en")
        try:
            with patch("src.core.game_manager.registre.lire_valeurs",
                       return_value={"Language": "German", "Locale": "de_DE"}):
                assert m.game_language(jeu) == "de"
        finally:
            set_language("fr")

    def test_le_choix_explicite_prime_sur_la_detection(self, tmp_path):
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        m.set_game_language("hp7a", "en")
        with patch("src.core.game_manager.registre.lire_valeurs",
                   return_value={"Language": "German", "Locale": "de_DE"}):
            assert m.game_language(jeu) == "en"

    def test_rien_a_ecrire_quand_le_registre_est_deja_bon(self, tmp_path):
        """Le point entier : aucune invite UAC sur un jeu qu'on n'a pas touche."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        with patch("src.core.game_manager.registre.lire_valeurs",
                   return_value={"Language": "German", "Locale": "de_DE"}),              patch("src.core.game_manager.registre.ecrire_valeurs") as ecrire:
            ecrire.return_value = True
            assert m.apply_game_language(jeu) is True
            # `ecrire_valeurs` est appelee, mais avec les valeurs DEJA en place :
            # c'est elle qui court-circuite (deja_a_jour) sans elever.
            assert ecrire.call_args[0][2] == {"Language": "German", "Locale": "de_DE"}

    def test_apply_accepte_un_code_explicite(self, tmp_path):
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        with patch("src.core.game_manager.registre.ecrire_valeurs",
                   return_value=True) as ecrire:
            m.apply_game_language(jeu, "en")
        assert ecrire.call_args[0][2] == {"Language": "English", "Locale": "en_US"}


class TestLanguesReellementInstallees:
    """Le registre SELECTIONNE une langue ; il ne l'installe pas.

    Deux guides communautaires le disent : « you also have to copy the language
    file from the DVD to your installation path ». Un jeu installe en francais
    n'a que les fichiers francais — proposer l'anglais promettrait quelque chose
    de faux. Le catalogue declare donc, par langue, un fichier temoin.
    """

    @staticmethod
    def _jeu_avec_temoins():
        bloc = dict(_LANG_BLOCK)
        bloc["languages"] = {
            "fr": {"label": "Francais", "values": {"Language": "French"},
                   "requires_file": "HPTest/fr.big"},
            "en": {"label": "English", "values": {"Language": "English"},
                   "requires_file": "HPTest/en.big"},
            "de": {"label": "Deutsch", "values": {"Language": "German"}},
        }
        return GameData.from_dict({**GAME_DICT, "id": "hp7a",
                                   "language_registry": bloc})

    def test_seules_les_langues_presentes_sur_le_disque(self, tmp_path):
        jeu = self._jeu_avec_temoins()
        m = _make_manager(tmp_path, [jeu])
        (tmp_path / "HPTest").mkdir(parents=True, exist_ok=True)
        (tmp_path / "HPTest" / "fr.big").write_bytes(b"")
        codes = [lg.code for lg in m.langues_disponibles(jeu)]
        # « de » n'a pas de temoin declare : toujours propose.
        assert codes == ["fr", "de"]

    def test_toutes_quand_rien_n_est_declare(self, tmp_path):
        """Le controle est une OPTION du catalogue, pas une obligation."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        assert [lg.code for lg in m.langues_disponibles(jeu)] == ["fr", "en", "de"]

    def test_aucune_pour_un_jeu_sans_bloc(self, tmp_path):
        m = _make_manager(tmp_path)
        assert m.langues_disponibles(m.get_games()[0].game) == ()

    def test_le_defaut_evite_une_langue_non_installee(self, tmp_path):
        """L'interface est en anglais mais seul le francais est installe : le
        defaut doit tomber sur ce qui existe."""
        from src.core.i18n import set_language
        jeu = self._jeu_avec_temoins()
        m = _make_manager(tmp_path, [jeu])
        (tmp_path / "HPTest").mkdir(parents=True, exist_ok=True)
        (tmp_path / "HPTest" / "fr.big").write_bytes(b"")
        set_language("en")
        try:
            with patch("src.core.game_manager.registre.lire_valeurs", return_value={}):
                assert m.game_language(jeu) == "fr"
        finally:
            set_language("fr")

    def test_le_registre_prime_meme_sur_une_langue_absente(self, tmp_path):
        """Si le registre annonce l'allemand, on l'AFFICHE — mieux vaut dire la
        verite que masquer l'etat reel du jeu."""
        jeu = self._jeu_avec_temoins()
        m = _make_manager(tmp_path, [jeu])
        with patch("src.core.game_manager.registre.lire_valeurs",
                   return_value={"Language": "German"}):
            assert m.game_language(jeu) == "de"


class TestValeursCommunes:
    """Certaines valeurs de la clé ne dépendent PAS de la langue.

    HP7 lit « Install Dir » pour retrouver ses données (relevé dans hp7.exe et
    hp8.exe le 2026-08-22) ; sans elle il ne démarre pas, et c'est normalement
    l'installeur EA qui l'écrit — il n'a jamais tourné quand le jeu vient du
    launcher. Elles partent avec la langue, dans la MÊME écriture : même clé,
    donc une seule invite UAC au lieu de deux à la suite.
    """

    _BLOC = {
        **_LANG_BLOCK,
        "values": {"Install Dir": "%INSTALL_DIR%" + chr(92)},
    }

    def _jeu(self):
        return GameData.from_dict({**GAME_DICT, "id": "hp7a",
                                   "language_registry": self._BLOC})

    def test_les_communes_accompagnent_la_langue(self, tmp_path):
        jeu = self._jeu()
        m = _make_manager(tmp_path, [jeu])
        m.set_game_language("hp7a", "en")
        valeurs = m.valeurs_registre(jeu)
        assert valeurs["Language"] == "English"     # la langue choisie
        assert "Install Dir" in valeurs             # ET la commune

    def test_install_dir_est_substitue(self, tmp_path):
        """`%INSTALL_DIR%` doit devenir un VRAI chemin : c'est ce que le jeu
        suivra pour trouver ses fichiers."""
        jeu = self._jeu()
        m = _make_manager(tmp_path, [jeu])
        valeurs = m.valeurs_registre(jeu)
        dossier_jeu = jeu.executable.replace(chr(92), "/").split("/")[0]
        attendu = str(tmp_path / dossier_jeu) + chr(92)
        assert valeurs["Install Dir"] == attendu
        assert "%INSTALL_DIR%" not in valeurs["Install Dir"]

    def test_la_langue_l_emporte_sur_une_commune_de_meme_nom(self, tmp_path):
        """Plus spécifique gagne — sinon une commune mal placée figerait la
        langue et le sélecteur n'aurait plus aucun effet."""
        bloc = {**self._BLOC, "values": {"Locale": "zz_ZZ"}}
        jeu = GameData.from_dict({**GAME_DICT, "id": "hp7a",
                                  "language_registry": bloc})
        m = _make_manager(tmp_path, [jeu])
        m.set_game_language("hp7a", "fr")
        assert m.valeurs_registre(jeu)["Locale"] == "fr_FR"

    def test_une_seule_ecriture_pour_les_deux(self, tmp_path):
        """Deux écritures = deux invites UAC de suite : le meilleur moyen de
        faire refuser la seconde."""
        jeu = self._jeu()
        m = _make_manager(tmp_path, [jeu])
        appels = []
        with patch("src.core.game_manager.registre.ecrire_valeurs",
                   side_effect=lambda *a, **k: appels.append(a) or True):
            assert m.apply_game_language(jeu) is True
        assert len(appels) == 1
        assert set(appels[0][2]) == {"Install Dir", "Language", "Locale"}

    def test_le_rappel_de_prevenance_est_transmis(self, tmp_path):
        """`launch_game` doit pouvoir prévenir l'utilisateur : si le rappel
        n'arrive pas jusqu'à `ecrire_valeurs`, l'écriture est silencieuse."""
        jeu = self._jeu()
        m = _make_manager(tmp_path, [jeu])
        recus = {}
        with patch("src.core.game_manager.registre.ecrire_valeurs",
                   side_effect=lambda *a, **k: recus.update(k) or True):
            m.apply_game_language(jeu, confirmer="sentinelle")
        assert recus.get("confirmer") == "sentinelle"

    def test_sans_communes_rien_ne_change(self, tmp_path):
        """Le champ est OPTIONNEL : les sept autres jeux n'en ont pas."""
        jeu = _jeu_multilingue()
        m = _make_manager(tmp_path, [jeu])
        assert set(m.valeurs_registre(jeu)) == {"Language", "Locale"}

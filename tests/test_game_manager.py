"""Tests pour src/core/game_manager.py"""

import sys
from unittest.mock import patch

import pytest

from src.core.config import Config
from src.core.game_data import GameData, Catalog
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

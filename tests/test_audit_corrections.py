"""Filets de non-régression des corrections de l'audit du 2026-08-20.

Chaque test ici a été écrit APRÈS avoir reproduit le défaut : il échoue sur le
code d'avant et passe sur celui d'après. Les défauts couverts avaient tous en
commun d'être invisibles à la suite existante — c'est ce qui les rendait chers.
"""

import json
import sys
import types
from pathlib import Path

import src.core.config as cfgmod
import src.core.self_update as self_update
from src.core.config import Config
from src.core.game_data import GameData, _parse_catalog
from src.core.updater import UpdateChecker, aggregate_download_counts
from src.core.version_utils import compare_versions, update_disponible

JEU_MINIMAL = {
    "id": "x", "name": "Jeu", "year": 2001, "description": "d",
    "developer": "dev", "executable": "X/x.exe", "cover_image": "c.png",
}


# ───────────────────────── B2 · le .bat et les accents ─────────────────────

class TestScriptDeRelanceEtLesAccents:
    """`C:\\Users\\Frédéric\\` devenait `C:\\Users\\Fr?d?ric\\`.

    Le .bat était écrit en `ascii` avec `errors="replace"` ; `move` et `start`
    échouaient donc sur un chemin inexistant, et l'auto-update comme les deux
    boutons « Redémarrer » s'arrêtaient sans un mot.
    """

    @staticmethod
    def _capture(monkeypatch, tmp_path):
        vu = {}
        bat = tmp_path / "t.bat"

        def faux_popen(*a, **kw):
            vu["contenu"] = bat.read_bytes()
            vu["env"] = kw.get("env")
            return object()

        def faux_mkstemp(**kw):
            import os
            return os.open(str(bat), os.O_RDWR | os.O_CREAT), str(bat)

        monkeypatch.setattr(self_update.subprocess, "Popen", faux_popen)
        monkeypatch.setattr(self_update.tempfile, "mkstemp", faux_mkstemp)
        return vu

    def test_les_chemins_passent_par_l_environnement(self, tmp_path, monkeypatch):
        vu = self._capture(monkeypatch, tmp_path)
        accentue = "C:\\Users\\Fr\u00e9d\u00e9ric\\AccioLauncher.exe"

        ok = self_update._spawn_after_exit_bat(
            'start "" "%ACCIO_EXE%"\r\n', prefix="t_",
            variables={"ACCIO_EXE": accentue})

        assert ok is True
        # Le corps reste en ASCII pur…
        assert b"?" not in vu["contenu"], "un chemin a été mutilé dans le .bat"
        assert b"ACCIO_EXE" in vu["contenu"]
        # …et le chemin accentué voyage INTACT par le bloc d'environnement,
        # transmis en Unicode par CreateProcessW.
        assert vu["env"]["ACCIO_EXE"] == accentue

    def test_un_corps_non_ascii_est_refuse_franchement(self, tmp_path, monkeypatch):
        """Plutôt qu'un « ? » silencieux qui produit un chemin inexistant."""
        self._capture(monkeypatch, tmp_path)
        assert self_update._spawn_after_exit_bat(
            'start "" "C:\\Fr\u00e9d\u00e9ric.exe"\r\n', prefix="t_") is False

    def test_aucun_chemin_en_dur_dans_les_corps_de_script(self):
        """Garde d'architecture : les deux appelants doivent utiliser %VAR%."""
        import inspect
        for fonction in (self_update.apply_update_and_restart,
                         self_update.relaunch_after_exit):
            src = inspect.getsource(fonction)
            assert "%ACCIO_" in src, (
                f"{fonction.__name__} doit passer ses chemins par `variables`")


# ───────────────────── I2 · réponses GitHub malformées ─────────────────────

class TestReponsesGitHubMalformees:
    """Une `AttributeError` sortant d'un `QThread.run()` affiche un RAPPORT DE
    PLANTAGE à l'utilisateur — vérifié. Une réponse HTTP inattendue (portail
    captif, proxy, page d'erreur) ne doit jamais en arriver là."""

    def test_release_nulle(self):
        assert aggregate_download_counts([None], {"hp1": [["u"]]}) == {}

    def test_asset_non_objet(self):
        assert aggregate_download_counts(
            [{"assets": [None, "texte"]}], {"hp1": [["u"]]}) == {}

    def test_compteur_non_numerique(self):
        totaux = aggregate_download_counts(
            [{"assets": [{"browser_download_url": "u", "download_count": "beaucoup"}]}],
            {"hp1": [["u"]]})
        assert totaux == {}

    def test_check_launcher_sur_une_reponse_liste(self, monkeypatch):
        """`resp.json()` peut rendre une liste : `data.get` levait alors."""
        mod = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class Timeout:
            def __init__(self, *a, **kw):
                pass

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return ["pas un objet"]

        class Client:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url):
                return _Resp()

        mod.HTTPError, mod.Timeout, mod.Client = HTTPError, Timeout, Client
        mod.TransportError = type("TransportError", (HTTPError,), {})
        monkeypatch.setitem(sys.modules, "httpx", mod)

        checker = UpdateChecker("", "0", {})
        checker._check_launcher()   # ne doit pas lever


# ──────────────────── I5 · « mise à jour disponible » ──────────────────────

class TestRegleDeMiseAJour:
    """La règle était écrite deux fois, et comparait des CHAÎNES."""

    def test_versions_numeriquement_egales(self):
        """« 1.0 » et « 1.0.0 » : textuellement différentes, donc une mise à
        jour fantôme s'affichait en permanence."""
        assert update_disponible("1.0", "1.0.0") is False
        assert update_disponible("1.0.0", "1.0") is False

    def test_vraie_mise_a_jour(self):
        assert update_disponible("1.0", "1.1") is True

    def test_retour_en_arriere_du_catalogue(self):
        """Recommandée PLUS ANCIENNE que l'installée : ce n'est pas une mise à
        jour, et le lien proposait pourtant de « mettre à jour » vers l'ancienne."""
        assert update_disponible("1.1", "1.0") is False

    def test_sans_version_connue(self):
        assert update_disponible(None, "1.0") is False
        assert update_disponible("", "1.0") is False

    def test_composant_non_numerique_ne_decale_plus(self):
        """Supprimer un composant illisible décalait les suivants : « 1.beta.5 »
        se réduisait à [1, 5] et ressortait donc PLUS RÉCENT que « 1.0.5 »
        (mesuré : +5). Il vaut désormais 0, ce qui aligne les rangs."""
        assert compare_versions("1.beta.5", "1.0.5") == 0
        # Et le rang des composants suivants est bien conservé.
        assert compare_versions("1.beta.9", "1.0.5") > 0
        assert compare_versions("1.beta.1", "1.0.5") < 0
        assert update_disponible("1.0.5", "1.beta.5") is False


# ─────────────────────── I6 · config mal typée ─────────────────────────────

class TestConfigMalTypee:
    """`Config.load()` promet de retomber sur les valeurs par défaut. Elle
    laissait pourtant passer des valeurs qui explosaient bien plus loin."""

    @staticmethod
    def _charge(tmp_path, monkeypatch, brut: dict) -> Config:
        f = tmp_path / "config.json"
        f.write_text(json.dumps(brut), encoding="utf-8")
        monkeypatch.setattr(cfgmod, "CONFIG_FILE_PATH", f)
        return Config.load()

    def test_champs_texte_coerces(self, tmp_path, monkeypatch):
        c = self._charge(tmp_path, monkeypatch,
                         {"langue": 42, "theme": ["x"], "season": None,
                          "dismissed_launcher_version": 7})
        assert c.langue == cfgmod.DEFAULT_LANGUAGE
        assert c.theme == "poudlard"
        assert c.season == "auto"
        assert c.dismissed_launcher_version == ""

    def test_booleens_coerces(self, tmp_path, monkeypatch):
        c = self._charge(tmp_path, monkeypatch,
                         {"delete_archives": "oui", "mute_videos": 3})
        assert c.delete_archives is True
        assert c.mute_videos is True

    def test_valeurs_de_dictionnaires_filtrees(self, tmp_path, monkeypatch):
        """`last_played_game_id()` tourne AU DÉMARRAGE : un mélange str/int y
        levait `TypeError`, donc un rapport de plantage à l'ouverture."""
        c = self._charge(tmp_path, monkeypatch, {
            "last_played": {"hp1": "2026-08-01", "hp2": 3},
            "playtime_seconds": {"hp1": 60, "hp2": "beaucoup"},
            "installed_versions": {"hp1": "1.0", "hp2": 2},
        })
        assert c.last_played == {"hp1": "2026-08-01"}
        assert c.playtime_seconds == {"hp1": 60}
        assert c.installed_versions == {"hp1": "1.0"}

    def test_vitesse_aberrante(self, tmp_path, monkeypatch):
        assert self._charge(tmp_path, monkeypatch,
                            {"last_download_speed": -5}).last_download_speed == 0.0
        assert self._charge(tmp_path, monkeypatch,
                            {"last_download_speed": "vite"}).last_download_speed == 0.0


# ──────────────── A3 / A4 · durcissement du catalogue ──────────────────────

class TestCatalogueDurci:
    def test_taille_negative_ne_leve_plus_le_plafond(self):
        """`size_mb` négatif rendait `needed_space_mb` négatif (le contrôle
        d'espace passait toujours) ET mettait le plafond du téléchargeur à 0,
        c'est-à-dire DÉSACTIVÉ."""
        from src.core.downloader import Downloader
        from src.core.system_checks import needed_space_mb

        cat = _parse_catalog({"catalog_version": "1", "games": [dict(
            JEU_MINIMAL, versions=[{"version": "1.0", "size_mb": -9999,
                                    "download_url": "https://x/a.7z"}])]})
        version = cat.games[0].versions[0]
        assert version.size_mb == 0
        assert needed_space_mb(version.size_mb) == 0
        # size_mb == 0 signifie « taille inconnue » : le plafond est désactivé,
        # mais plus par une valeur NÉGATIVE qui se déguisait en taille valide.
        assert Downloader("https://x/a.7z", Path("x"),
                          expected_size_mb=version.size_mb)._max_total_bytes == 0

    def test_empreinte_mal_formee_ignoree(self):
        """Une empreinte non-hex levait `AttributeError` sur `.lower()`."""
        cat = _parse_catalog({"catalog_version": "1", "games": [dict(
            JEU_MINIMAL, versions=[{"version": "1.0", "sha256": 12345,
                                    "download_url": "https://x/a.7z"}])]})
        assert cat.games[0].versions[0].sha256 is None

    def test_empreinte_valide_normalisee(self):
        cat = _parse_catalog({"catalog_version": "1", "games": [dict(
            JEU_MINIMAL, versions=[{"version": "1.0", "sha256": "AB" * 32,
                                    "download_url": "https://x/a.7z"}])]})
        assert cat.games[0].versions[0].sha256 == "ab" * 32

    def test_traduction_vide_retombe_sur_le_francais(self):
        """Le nom français est validé non vide ; une traduction vide passait
        derrière et donnait une fiche de jeu SANS TITRE."""
        import src.core.i18n as i18n
        ancien = i18n._lang
        i18n._lang = "en"
        try:
            jeu = GameData.from_dict(dict(
                JEU_MINIMAL, i18n={"en": {"name": "   ", "description": ""}}))
            assert jeu.name == "Jeu"
            assert jeu.description == "d"
        finally:
            i18n._lang = ancien


# ─────────────────── Prérequis runtimes (HP7) ──────────────────────────────

class TestPrerequisRuntimes:
    """HP7 partie 1 réclame Visual C++ 2005, partie 2 Visual C++ 2008 —
    deux runtimes distincts du 2015-2022 vérifié pour tous les jeux."""

    def test_le_catalogue_embarque_declare_les_deux(self):
        catalogue = json.loads(
            (Path(__file__).resolve().parents[1] / "src/data/games.json")
            .read_text(encoding="utf-8"))
        par_id = {g["id"]: g for g in catalogue["games"]}
        assert par_id["hp7a"].get("requires") == ["vcredist2005_x86"]
        assert par_id["hp7b"].get("requires") == ["vcredist2008_x86"]

    def test_requires_parse(self):
        jeu = GameData.from_dict(dict(JEU_MINIMAL, requires=["vcredist2005_x86", 42]))
        assert jeu.requires == ("vcredist2005_x86",)

    def test_identifiant_inconnu_jamais_bloquant(self):
        """Un catalogue en avance sur le launcher ne doit pas verrouiller un jeu."""
        from src.core.system_checks import prerequis_manquants
        assert prerequis_manquants(("runtime_du_futur",)) == []

    def test_detection_par_assembly_winsxs(self, tmp_path):
        from src.core.system_checks import crt_x86_present
        jeton = "1fc8b3b9a1e18e3b"
        assert crt_x86_present(tmp_path, "vc80") is False

        assembly = tmp_path / f"x86_microsoft.vc80.crt_{jeton}_8.0.50727.9680_none_abc"
        assembly.mkdir()
        (assembly / "msvcr80.dll").write_bytes(b"MZ")
        assert crt_x86_present(tmp_path, "vc80") is True
        # Le 2008 est un runtime DISTINCT : sa présence ne s'en déduit pas.
        assert crt_x86_present(tmp_path, "vc90") is False

    def test_le_manquant_remonte_avec_son_identifiant(self, monkeypatch):
        """C'est lui qui permet d'ouvrir la BONNE page de téléchargement."""
        from src.core.system_checks import prerequis_manquants
        monkeypatch.setattr("src.core.system_checks.check_vcredist_2008_x86",
                            lambda: False)
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: True)
        assert prerequis_manquants(
            ("vcredist_x86", "vcredist2008_x86")) == ["vcredist2008_x86"]

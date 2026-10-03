"""La taille de fenêtre de HP1/HP2 : celle de l'écran, ou celle choisie.

Documents est celui du conftest. Le jeu est FABRIQUÉ (règle 78 : aucun test
ne dépend du contenu de games.json).
"""
from types import SimpleNamespace

import pytest

from src.core import resolution_jeu as rj
from src.core.catalogue_blocs import Resolution, _parse_resolution
from src.core.config import Config

GAME_INI = (
    "[Engine.Engine]\r\nGameRenderDevice=D3D11Drv.D3D11RenderDevice\r\n"
    "[WinDrv.WindowsClient]\r\nWindowedViewportX=1024\r\nWindowedViewportY=768\r\n"
    "StartupFullscreen=False\r\n"
    "[SDLDrv.SDLClient]\r\nWindowedViewportX=640\r\nWindowedViewportY=480\r\n"
)
BLOC = {"file": "%DOCUMENTS%\\Harry Potter II\\Game.ini", "section": "WinDrv.WindowsClient",
        "width": "WindowedViewportX", "height": "WindowedViewportY"}


@pytest.fixture
def jeu(tmp_path):
    ini = tmp_path / "Documents" / "Harry Potter II" / "Game.ini"
    ini.parent.mkdir(parents=True)
    ini.write_bytes(GAME_INI.encode("cp1252"))
    game = SimpleNamespace(id="hp2", name="Harry Potter II", executable="HP2/system/Game.exe",
                           resolution=_parse_resolution(BLOC))
    config = Config(install_path=tmp_path / "Jeux")
    return game, config, ini


class TestChoix:
    def test_lire(self):
        assert rj.lire("2560x1440") == (2560, 1440)
        for douteux in ("", "2560", "800x600", "2560x1440x2", "99999x1080", None, "abcxdef"):
            assert rj.lire(douteux) is None

    def test_par_defaut_l_ecran(self):
        assert rj.voulue("", (2560, 1440)) == (2560, 1440)

    def test_le_choix_s_il_tient(self):
        assert rj.voulue("1920x1080", (2560, 1440)) == (1920, 1080)

    def test_un_choix_trop_grand_replie_sur_l_ecran(self):
        """Choisi sur un écran 4K, relu sur un portable 1080p."""
        assert rj.voulue("3840x2160", (1920, 1080)) == (1920, 1080)

    def test_ni_choix_ni_ecran_rien(self):
        assert rj.voulue("", None) is None

    def test_proposees_tiennent_dans_l_ecran_sans_le_repeter(self):
        tailles = rj.proposees((2560, 1440))
        assert (2560, 1440) not in tailles and (1920, 1080) in tailles
        assert all(w <= 2560 and h <= 1440 for w, h in tailles)


class TestCatalogue:
    def test_bloc_valable(self):
        assert _parse_resolution(BLOC) == Resolution(**BLOC)

    @pytest.mark.parametrize("douteux", [
        None, "x", {}, {**BLOC, "section": "WinDrv]\n[Autre"}, {**BLOC, "width": "A=B"},
        {**BLOC, "height": BLOC["width"]}, {**BLOC, "file": 42},
    ])
    def test_bloc_douteux_ignore(self, douteux):
        assert _parse_resolution(douteux) is None


class TestAppliquer:
    def test_l_ecran_est_ecrit_dans_la_bonne_section(self, jeu):
        game, config, ini = jeu
        assert rj.appliquer(game, config, (2560, 1440)) == (2560, 1440)
        texte = ini.read_bytes().decode("cp1252")
        assert "[WinDrv.WindowsClient]\r\nWindowedViewportX=2560\r\nWindowedViewportY=1440\r\n" in texte
        # L'autre section qui porte les mêmes clés n'est pas touchée,
        # et le plein écran jamais allumé.
        assert "[SDLDrv.SDLClient]\r\nWindowedViewportX=640\r\nWindowedViewportY=480" in texte
        assert "StartupFullscreen=False" in texte and "StartupFullscreen=True" not in texte

    def test_le_choix_de_la_personne_l_emporte(self, jeu):
        game, config, ini = jeu
        config.resolution_jeu["hp2"] = "1600x900"
        rj.appliquer(game, config, (2560, 1440))
        assert "WindowedViewportX=1600\r\nWindowedViewportY=900" in ini.read_bytes().decode("cp1252")

    def test_un_alt_entree_est_defait_au_lancement_suivant(self, jeu):
        """HP2 écrit 2560×1440 dans Game.ini sur Alt+Entrée (2026-10-01)."""
        game, config, ini = jeu
        config.resolution_jeu["hp2"] = "1920x1080"
        ini.write_bytes(ini.read_bytes().replace(b"=1024", b"=2560").replace(b"=768", b"=1440"))
        rj.appliquer(game, config, (2560, 1440))
        assert "WindowedViewportX=1920\r\nWindowedViewportY=1080" in ini.read_bytes().decode("cp1252")

    def test_jeu_sans_bloc_ou_ecran_inconnu_rien_n_est_ecrit(self, jeu):
        game, config, ini = jeu
        avant = ini.read_bytes()
        assert rj.appliquer(SimpleNamespace(id="hp5", resolution=None), config, (2560, 1440)) is None
        assert rj.appliquer(game, config, None) is None
        assert ini.read_bytes() == avant

    def test_config_aller_retour(self, tmp_path):
        config = Config(install_path=tmp_path)
        config.resolution_jeu["hp1"] = "1920x1080"
        config.save()
        assert Config.load().resolution_jeu == {"hp1": "1920x1080"}


class TestLancement:
    def test_launch_game_ecrit_la_resolution(self, jeu, monkeypatch):
        """Câblage : l'étape tourne au lancement, après les patchs."""
        from src.core import game_manager as gm
        game, config, _ini = jeu
        appels = []
        monkeypatch.setattr(gm.resolution_jeu, "appliquer",
                            lambda g, c, e: appels.append((g.id, e)))
        monkeypatch.setattr(gm.resolution_jeu, "ecran_principal", lambda: (1920, 1200))
        source = __import__("inspect").getsource(gm.GameManager.launch_game)
        assert source.index("apply_ini_patches(") < source.index("resolution_jeu.appliquer(")
        gm.resolution_jeu.appliquer(game, config, gm.resolution_jeu.ecran_principal())
        assert appels == [("hp2", (1920, 1200))]


class TestFenetre:
    """La rubrique « Affichage » de la fenêtre de réglages."""

    def _dialogue(self, qtbot, game, config, monkeypatch, ecran=(2560, 1440)):
        from src.ui import game_settings_dialog as gsd
        from src.ui import reglages_rubriques as rr
        monkeypatch.setattr(rr.resolution_jeu, "ecran_principal", lambda: ecran)
        manager = SimpleNamespace(config=config, game_language=lambda _g: None)
        dlg = gsd.GameSettingsDialog(game, manager, appliquer_langue=lambda _c: True)
        qtbot.addWidget(dlg)
        return dlg

    def _jeu_complet(self, game):
        from src.core.game_data import GameData
        return GameData(id=game.id, name=game.name, year=2002, description="", developer="",
                        executable=game.executable, cover_image="", latest_version="1.0",
                        recommended_version="1.0", resolution=game.resolution,
                        display_locked=True)

    def test_l_ecran_par_defaut_et_le_choix_enregistre(self, qtbot, jeu, monkeypatch):
        game, config, _ = jeu
        dlg = self._dialogue(qtbot, self._jeu_complet(game), config, monkeypatch)
        choix = dlg._choix_resolution
        assert choix.currentText() == "Celle de l'écran (2560 × 1440)"
        choix.setCurrentIndex(choix.findData("1920x1080"))
        assert config.resolution_jeu == {"hp2": "1920x1080"}
        choix.setCurrentIndex(0)
        assert config.resolution_jeu == {}

    def test_un_choix_plus_grand_que_l_ecran_reste_montre(self, qtbot, jeu, monkeypatch):
        game, config, _ = jeu
        config.resolution_jeu["hp2"] = "3840x2160"
        dlg = self._dialogue(qtbot, self._jeu_complet(game), config, monkeypatch, (1920, 1080))
        assert dlg._choix_resolution.currentText() == "3840 × 2160 (plus grande que cet écran)"

    def test_pas_de_liste_pour_un_jeu_sans_bloc(self, qtbot, jeu, monkeypatch):
        game, config, _ = jeu
        sans = self._jeu_complet(SimpleNamespace(id="hp3", name="HP3", executable="HP3/x.exe",
                                                 resolution=None))
        dlg = self._dialogue(qtbot, sans, config, monkeypatch)
        assert dlg._choix_resolution is None

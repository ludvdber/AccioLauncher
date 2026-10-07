"""Captures d'écran : un dossier par jeu, hors du dossier du jeu.

Désinstaller ou réparer un jeu emportait ses captures (le correctif les posait
à côté de l'exe, Unreal dans `System\\`). Elles vivent maintenant dans
`Images/Accio Launcher/<nom du jeu>` — la garde `_captures_hors_des_vraies_images`
de conftest redirige ce dossier pour chaque test.
"""
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtGui import QColor, QImage

from src.core import captures
from src.core.game_data import GameData

INI_V2 = "[Accio.Window]\r\nWindowed=1\r\nScreenshotKey=123\r\n\r\n[Accio.Game]\r\nFOV=1.0\r\n"


def _jeu(**extra) -> GameData:
    base = {"id": "hp4", "name": "Harry Potter et la Coupe de feu", "year": 2005, "description": "d",
            "developer": "d", "executable": "HP4/gof_f.exe", "cover_image": "c.jpg",
            "i18n": {"en": {"name": "Harry Potter and the Goblet of Fire"}}}
    base.update(extra)
    return GameData.from_dict(base)


def _bmp(chemin: Path, couleur="red") -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(8, 4, QImage.Format.Format_RGB32)
    image.fill(QColor(couleur))
    assert image.save(str(chemin), "BMP")
    return chemin


class TestCatalogue:
    def test_bloc_complet(self):
        jeu = _jeu(screenshots={"key": "F12", "collect": ["HP4/screenshots/*.png"]})
        assert jeu.touche_capture == "F12"
        assert jeu.captures == ("HP4/screenshots/*.png",)

    def test_tous_les_noms(self):
        assert _jeu().noms == ("Harry Potter et la Coupe de feu", "Harry Potter and the Goblet of Fire")

    @pytest.mark.parametrize("motifs", [
        ["*.bmp"],                          # la racine des jeux : on y DÉPLACERAIT tout
        ["../HP4/*.png"], ["C:/x/*.png"], ["HP4/**/*.png"], ["/HP4/*.png"],
        "HP4/*.png",                        # une chaîne seule
        ["HP4/a.png"] * 9,                  # plus de huit
    ])
    def test_motif_douteux_tout_est_refuse(self, motifs):
        assert _jeu(screenshots={"collect": motifs}).captures == ()

    def test_un_seul_mauvais_motif_refuse_le_bloc(self):
        assert _jeu(screenshots={"collect": ["HP4/ok/*.png", "../x"]}).captures == ()

    @pytest.mark.parametrize("touche", ["", "x" * 25, "F12\n", "<b>F12</b>", 12])
    def test_touche_douteuse(self, touche):
        assert _jeu(screenshots={"key": touche}).touche_capture == ""

    def test_ancien_format_liste_ignore(self):
        assert _jeu(screenshots=["HP4/screenshots/*.png"]).captures == ()


class TestDossier:
    def test_nom_lisible_et_valable_partout(self):
        assert captures.nom_de_dossier('Harry Potter: "Reliques"? 1.') == "Harry Potter Reliques 1"
        assert captures.nom_de_dossier("À l'école des sorciers") == "À l'école des sorciers"
        assert captures.nom_de_dossier("???") == "Jeu"

    def test_hors_du_dossier_du_jeu(self, tmp_path):
        assert captures.dossier(_jeu()) == captures.racine() / "Harry Potter et la Coupe de feu"
        assert "AccioLauncher" not in captures.dossier(_jeu()).parts

    def test_changer_de_langue_retrouve_le_meme_dossier(self):
        """Créé en anglais, retrouvé depuis un lanceur en français."""
        anglais = captures.racine() / "Harry Potter and the Goblet of Fire"
        anglais.mkdir(parents=True)
        assert captures.dossier(_jeu()) == anglais


class TestRamasser:
    def _jeu_ue1(self):
        return _jeu(id="hp1", executable="HP1/System/HP.exe",
                    screenshots={"key": "F12", "collect": ["HP1/System/Shot*.bmp"]})

    def test_bmp_devient_png_et_quitte_le_jeu(self, tmp_path):
        jeux = tmp_path / "jeux"
        source = _bmp(jeux / "HP1" / "System" / "Shot0000.bmp")
        assert captures.ramasser(self._jeu_ue1(), jeux) == 1
        assert not source.exists()
        (png,) = captures.images(captures.dossier(self._jeu_ue1()))
        assert png.suffix == ".png"
        assert QImage(str(png)).pixelColor(0, 0) == QColor("red")

    def test_nom_date_d_apres_le_fichier(self, tmp_path):
        jeux = tmp_path / "jeux"
        source = _bmp(jeux / "HP1" / "System" / "Shot0001.bmp")
        quand = time.mktime((2026, 9, 27, 3, 14, 15, 0, 0, -1))
        os.utime(source, (quand, quand))
        captures.ramasser(self._jeu_ue1(), jeux)
        assert [p.name for p in captures.images(captures.dossier(self._jeu_ue1()))] == [
            "2026-09-27_03-14-15.png"]

    def test_jamais_d_ecrasement(self, tmp_path):
        jeux = tmp_path / "jeux"
        quand = time.mktime((2026, 9, 27, 3, 14, 15, 0, 0, -1))
        for i, couleur in enumerate(("red", "blue")):
            s = _bmp(jeux / "HP1" / "System" / f"Shot000{i}.bmp", couleur)
            os.utime(s, (quand, quand))
        assert captures.ramasser(self._jeu_ue1(), jeux) == 2
        noms = sorted(p.name for p in captures.images(captures.dossier(self._jeu_ue1())))
        assert noms == ["2026-09-27_03-14-15.png", "2026-09-27_03-14-15_2.png"]

    def test_ne_touche_qu_aux_motifs(self, tmp_path):
        jeux = tmp_path / "jeux"
        autre = _bmp(jeux / "HP1" / "System" / "Splash.bmp")
        texture = _bmp(jeux / "HP1" / "Textures" / "Shot0000.bmp")
        assert captures.ramasser(self._jeu_ue1(), jeux) == 0
        assert autre.exists() and texture.exists()

    def test_png_deplace_tel_quel(self, tmp_path):
        jeux = tmp_path / "jeux"
        source = jeux / "HP4" / "screenshots" / "gof_f_2026.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"\x89PNG faux mais intact")
        jeu = _jeu(screenshots={"key": "F12", "collect": ["HP4/screenshots/*.png"]})
        assert captures.ramasser(jeu, jeux) == 1
        (copie,) = captures.images(captures.dossier(jeu))
        assert copie.read_bytes() == b"\x89PNG faux mais intact"

    def test_bmp_illisible_deplace_sans_conversion(self, tmp_path):
        jeux = tmp_path / "jeux"
        source = jeux / "HP1" / "System" / "Shot0002.bmp"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"pas une image")
        assert captures.ramasser(self._jeu_ue1(), jeux) == 1
        (copie,) = captures.images(captures.dossier(self._jeu_ue1()))
        assert copie.suffix == ".bmp" and copie.read_bytes() == b"pas une image"

    def test_sans_bloc_rien(self, tmp_path):
        assert captures.ramasser(_jeu(), tmp_path) == 0
        assert not captures.dossier(_jeu()).exists()


class TestPreparer:
    def _poser_ini(self, tmp_path, texte=INI_V2) -> Path:
        ini = tmp_path / "HP4" / "d3d9.ini"
        ini.parent.mkdir(parents=True)
        ini.write_bytes(texte.encode("utf-8"))
        return ini

    def test_le_correctif_recoit_le_dossier(self, tmp_path):
        ini = self._poser_ini(tmp_path)
        assert captures.preparer(_jeu(), tmp_path) is True
        texte = ini.read_bytes().decode("utf-8")
        cible = captures.dossier(_jeu())
        # Le chemin tel que le JEU le lit : natif sous Windows, `Z:\…` sous Linux (le jeu
        # tourne sous Wine). Attendre `cible` telle quelle cassait le job Linux de la CI.
        assert f"ScreenshotFolder={captures.chemin_pour_le_jeu(cible)}\r\n" in texte
        assert texte.index("ScreenshotFolder") < texte.index("[Accio.Game]")
        assert cible.is_dir()

    def test_le_reste_du_fichier_ne_bouge_pas(self, tmp_path):
        ini = self._poser_ini(tmp_path)
        captures.preparer(_jeu(), tmp_path)
        lignes = ini.read_bytes().decode("utf-8").split("\r\n")
        assert "ScreenshotKey=123" in lignes and "FOV=1.0" in lignes

    def test_pas_de_reecriture_inutile(self, tmp_path):
        ini = self._poser_ini(tmp_path)
        captures.preparer(_jeu(), tmp_path)
        avant = ini.stat().st_mtime_ns
        os.utime(ini, ns=(avant - 10**9, avant - 10**9))
        captures.preparer(_jeu(), tmp_path)
        assert ini.stat().st_mtime_ns == avant - 10**9

    def test_ancien_correctif_intouche(self, tmp_path):
        ini = self._poser_ini(tmp_path, "[MAIN]\r\nForceWindowedMode=1\r\n")
        assert captures.preparer(_jeu(), tmp_path) is False
        assert ini.read_bytes() == b"[MAIN]\r\nForceWindowedMode=1\r\n"

    def test_sans_ini_rien(self, tmp_path):
        assert captures.preparer(_jeu(), tmp_path) is False

    def test_sous_wine_le_chemin_que_lit_le_jeu(self, tmp_path, monkeypatch):
        self._poser_ini(tmp_path)
        monkeypatch.setattr(captures.sys, "platform", "linux")
        monkeypatch.setattr("src.core.compat.chemin_windows", lambda p: r"Z:\home\ludo\Images\x")
        captures.preparer(_jeu(), tmp_path)
        assert r"ScreenshotFolder=Z:\home\ludo\Images\x" in (tmp_path / "HP4" / "d3d9.ini").read_text()


class TestToucheDuCorrectif:
    """La touche se lit dans l'ini : seul le nouveau correctif en a une, et elle se change."""

    def _ini(self, tmp_path, texte):
        ini = tmp_path / "d3d9.ini"
        ini.write_bytes(texte.encode("utf-8"))
        return ini

    @pytest.mark.parametrize("ligne, attendu", [
        ("ScreenshotKey=123", "F12"), ("ScreenshotKey=112", "F1"), ("ScreenshotKey=44", "Impr. écran"),
        ("ScreenshotKey=80", "P"), ("ScreenshotKey=0", ""), ("", "F12"), ("ScreenshotKey=abc", ""),
    ])
    def test_nom_de_la_touche(self, tmp_path, ligne, attendu):
        from src.core import reglages_correctif
        ini = self._ini(tmp_path, f"[Accio.Window]\r\n{ligne}\r\n")
        assert reglages_correctif.touche_capture(ini) == attendu

    def test_ancien_correctif_aucune_touche(self, tmp_path):
        from src.core import reglages_correctif
        assert reglages_correctif.touche_capture(self._ini(tmp_path, "[MAIN]\r\nScreenshotKey=123\r\n")) == ""

    def test_la_fenetre_montre_la_touche_du_correctif(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QLabel

        from src.ui.game_settings_dialog import GameSettingsDialog
        (tmp_path / "HP4").mkdir()
        (tmp_path / "HP4" / "d3d9.ini").write_bytes(b"[Accio.Window]\r\nScreenshotKey=120\r\n")
        manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                                  config=SimpleNamespace(install_path=tmp_path))
        dlg = GameSettingsDialog(_jeu(screenshots={"collect": ["HP4/screenshots/*.png"]}), manager, lambda c: True)
        qtbot.addWidget(dlg)
        assert any("F9" in lbl.text() for lbl in dlg.findChildren(QLabel))


class TestFenetre:
    def _dialogue(self, qtbot, jeu, tmp_path):
        from src.ui.game_settings_dialog import GameSettingsDialog
        manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                                  config=SimpleNamespace(install_path=tmp_path))
        dlg = GameSettingsDialog(jeu, manager, lambda code: True)
        qtbot.addWidget(dlg)
        return dlg

    def test_rubrique_absente_sans_capture_possible(self, qtbot, tmp_path):
        dlg = self._dialogue(qtbot, _jeu(), tmp_path)
        assert dlg._compte_captures is None

    def test_rubrique_et_touche(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QLabel
        dlg = self._dialogue(qtbot, _jeu(screenshots={"key": "F12"}), tmp_path)
        assert dlg._compte_captures is not None and dlg._compte_captures.text() == ""
        assert any("F12" in lbl.text() for lbl in dlg.findChildren(QLabel))

    def test_ancien_correctif_la_rubrique_le_dit(self, qtbot, tmp_path):
        """Captures déclarées, aucune touche connue (ancien correctif), aucune capture : la rubrique
        disparaissait sans un mot et le bouton annoncé restait introuvable (Ludo, 2026-09-27)."""
        from PyQt6.QtWidgets import QLabel, QPushButton
        (tmp_path / "HP4").mkdir()
        (tmp_path / "HP4" / "d3d9.ini").write_bytes(b"[MAIN]\r\nScreenshotKey=123\r\n")
        dlg = self._dialogue(qtbot, _jeu(screenshots={"collect": ["HP4/screenshots/*.png"]}), tmp_path)
        textes = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))
        assert "Captures d'écran" in textes and "prochaine version" in textes
        assert not any("captures" in b.text() for b in dlg.findChildren(QPushButton))

    def test_un_jeu_desinstalle_garde_l_acces_a_ses_captures(self, qtbot, tmp_path):
        dossier = captures.dossier(_jeu())
        dossier.mkdir(parents=True)
        (dossier / "a.png").write_bytes(b"x")
        dlg = self._dialogue(qtbot, _jeu(), tmp_path)
        assert dlg._compte_captures.text() == "1 capture"

    def test_ouvrir_range_puis_ouvre(self, qtbot, tmp_path, monkeypatch):
        ouverts = []
        monkeypatch.setattr("src.ui.reglages_rubriques.open_local_path", ouverts.append)
        jeu = _jeu(id="hp1", executable="HP1/System/HP.exe",
                   screenshots={"key": "F12", "collect": ["HP1/System/Shot*.bmp"]})
        _bmp(tmp_path / "HP1" / "System" / "Shot0000.bmp")
        _bmp(tmp_path / "HP1" / "System" / "Shot0001.bmp")
        dlg = self._dialogue(qtbot, jeu, tmp_path)
        dlg._ouvrir_captures()
        assert ouverts == [str(captures.dossier(jeu))]
        assert dlg._compte_captures.text() == "2 captures"


class TestFinDePartie:
    def test_la_fin_de_partie_range_les_captures(self, tmp_path, qtbot):
        from unittest.mock import patch

        from src.core.config import Config
        from src.core.game_data import Catalog
        from src.core.game_manager import GameManager
        from src.ui.game_session import GameSession

        jeu = _jeu(id="hp1", executable="HP1/System/HP.exe",
                   screenshots={"key": "F12", "collect": ["HP1/System/Shot*.bmp"]})
        catalog = Catalog(catalog_version="1.0", catalog_url="", games=(jeu,))
        with patch("src.core.game_manager.load_catalog", return_value=catalog):
            manager = GameManager(Config(install_path=tmp_path, cache_path=tmp_path / ".cache"))
        session = GameSession(manager)
        session._monitor.start = lambda proc, nom: None
        session.demarrer(SimpleNamespace(pid=1), jeu.name, "hp1")
        _bmp(tmp_path / "HP1" / "System" / "Shot0000.bmp")
        session._on_game_exited(jeu.name, 0, 600.0)
        assert len(captures.images(captures.dossier(jeu))) == 1
        assert not (tmp_path / "HP1" / "System" / "Shot0000.bmp").exists()

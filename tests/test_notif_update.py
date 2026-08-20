"""Bandeau de mise à jour du launcher — visibilité, persistance, vitesse.

Trois défauts signalés sur une même capture d'écran :
① le bouton ⚙ recouvrait la croix de fermeture du bandeau (invisible et
incliquable) ; ② le bandeau s'effaçait au bout de 30 s, donc on le ratait ;
③ le téléchargement de la mise à jour n'affichait qu'un pourcentage, sans
vitesse ni temps restant, impossible de savoir s'il avançait.
"""

import time

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QPushButton  # noqa: E402

import src.ui.main_window as mw  # noqa: E402

URL = "https://github.com/ludvdber/AccioLauncher/releases"
ASSET = "https://github.com/ludvdber/AccioLauncher/releases/download/v9/A.exe"


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    import src.core.config as cfgmod
    monkeypatch.setattr(cfgmod, "CONFIG_FILE_PATH", tmp_path / "config.json")
    from src.core.config import Config
    Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "jeux" / ".cache",
           langue="fr", autoplay_videos=False).save()
    monkeypatch.setattr(mw.MainWindow, "_start_update_check", lambda self: None)
    # Pas de neutralisation du verrou d'instance unique : il vit dans main.py,
    # MainWindow ne le touche jamais.

    w = mw.MainWindow()
    qtbot.addWidget(w)
    w.resize(1280, 860)
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()
    w._launcher_update_asked = True     # on n'ouvre pas le dialogue ici
    return w


def _croix(fenetre):
    return [b for b in fenetre._notif_bar.findChildren(QPushButton)
            if b.text() == "\u2715"][0]


class TestLeBandeauResteAtteignable:
    def test_le_bouton_parametres_ne_recouvre_pas_le_bandeau(self, qtbot, fenetre):
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        qtbot.wait(10)
        assert fenetre._notif_bar.isVisible()
        engrenage = fenetre._btn_settings.geometry()
        assert not engrenage.intersects(fenetre._notif_bar.geometry()), (
            "le bouton ⚙ est posé par-dessus le bandeau : il en masque la croix")

    def test_le_bouton_parametres_ne_recouvre_pas_la_croix(self, qtbot, fenetre):
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        qtbot.wait(10)
        croix = _croix(fenetre)
        barre = fenetre._notif_bar
        zone = croix.geometry().translated(barre.mapTo(fenetre, croix.pos())
                                           - croix.pos())
        assert not fenetre._btn_settings.geometry().intersects(zone)

    def test_le_bouton_parametres_remonte_quand_le_bandeau_part(self, qtbot, fenetre):
        haut_initial = fenetre._btn_settings.geometry().top()
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        qtbot.wait(10)
        assert fenetre._btn_settings.geometry().top() > haut_initial
        fenetre._dismiss_notif()
        qtbot.wait(10)
        assert fenetre._btn_settings.geometry().top() == haut_initial


class TestLeBandeauNeSEffacePas:
    def test_il_reste_visible(self, qtbot, fenetre):
        """Il disparaissait au bout de 30 s : on le ratait, et plus rien ne
        rappelait qu'une mise à jour attendait."""
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        qtbot.wait(120)
        assert fenetre._notif_bar.isVisible()

    def test_aucun_effacement_automatique_dans_le_code(self):
        assert not hasattr(mw.MainWindow, "_auto_hide_notif"), (
            "l'effacement automatique du bandeau est revenu")

    def test_la_croix_ecarte_la_version_pour_de_bon(self, qtbot, fenetre):
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        fenetre._dismiss_notif()
        assert fenetre.config.dismissed_launcher_version == "9.9.9"
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        assert not fenetre._notif_bar.isVisible()


class TestDialogue:
    def test_pose_une_seule_fois_par_session(self, qtbot, fenetre, monkeypatch):
        appels = []

        class FausseBoite:
            def __init__(self, parent=None):
                appels.append(1)
                self._boutons = []

            def setWindowTitle(self, *a): pass
            def setIcon(self, *a): pass
            def setText(self, *a): pass
            def setInformativeText(self, *a): pass
            def setDefaultButton(self, *a): pass

            def addButton(self, texte, role):
                self._boutons.append(texte)
                return texte

            def exec(self): return 0
            def clickedButton(self): return None

        FausseBoite.Icon = mw.QMessageBox.Icon
        FausseBoite.ButtonRole = mw.QMessageBox.ButtonRole
        monkeypatch.setattr(mw, "QMessageBox", FausseBoite)

        fenetre._launcher_update_asked = False
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        fenetre._updates.version = "9.9.9"
        fenetre._propose_launcher_update()
        assert len(appels) == 1, (
            "le dialogue se rouvrirait à chaque contrôle de mise à jour")


class TestVitesseAffichee:
    def test_la_ligne_montre_la_vitesse_et_le_volume(self, qtbot, fenetre):
        fenetre._on_launcher_update("9.9.9", URL, ASSET, "")
        # La progression est calculée par le dispatcher et POSÉE dans le
        # bandeau par un signal : on exerce la chaîne complète.
        fenetre._updates._speed.reset()
        fenetre._updates._on_progress(5_000_000, 40_000_000)
        time.sleep(0.05)
        fenetre._updates._on_progress(40_000_000, 40_000_000)
        texte = fenetre._notif_bar.message()
        assert "%" in texte, texte
        assert "/s" in texte, f"pas de vitesse dans « {texte} »"
        assert "Mo" in texte or "MB" in texte, texte

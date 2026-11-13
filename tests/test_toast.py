"""Le toast ne couvre jamais la rangée JOUER et tient dans la fenêtre (`src/ui/toast.py`).

Audit du 2026-11-13, reproduit par un vérificateur : à 980×660 (taille
d'ouverture sur un écran 1366×768), le toast « … n'a pas démarré », posé à
200 px fixes du bas, couvrait JOUER pendant 12 s ; un clic pour relancer le
jeu copiait le rapport et ouvrait Discord. Et un texte long sortait de la
fenêtre des deux côtés (1 173 px dans 980). Mesure : rectangles réels.
Contre-épreuve : ces tests échouent sur l'ancien code.
"""

import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QWidget

from src.ui.toast import Toast

_LONG = ("Harry Potter et les Reliques de la Mort – Partie 2 s'est fermé aussitôt : "
         "le jeu n'a pas démarré. Besoin d'aide ? Cliquez ici pour copier le rapport.")


def _rect(widget, dans):
    return QRect(widget.mapTo(dans, QPoint(0, 0)), widget.size())


@pytest.mark.parametrize("y_rangee", [380, 400, 420, 440])
def test_le_toast_se_pose_hors_de_la_rangee_jouer(qtbot, y_rangee):
    fenetre = QWidget()
    qtbot.addWidget(fenetre)
    fenetre.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    fenetre.resize(980, 660)
    rangee = QWidget(fenetre)
    rangee.setGeometry(51, y_rangee, 545, 46)
    toast = Toast(fenetre, a_eviter=lambda: rangee)
    fenetre.show()
    toast.show_message(_LONG, duration_ms=12000, on_click=lambda: None)
    assert not toast.geometry().intersects(_rect(rangee, fenetre)), (toast.geometry(), y_rangee)


@pytest.mark.parametrize("taille", [(980, 660), (1280, 800), (1920, 1080)])
def test_dans_la_vraie_fenetre(make_window, qtbot, taille):
    win = make_window()
    win.show()
    win.resize(*taille)
    qtbot.wait(30)
    win._toast.show_message(_LONG, duration_ms=12000, on_click=lambda: None)
    geo = win._toast.geometry()
    assert not geo.intersects(_rect(win._detail.zone_d_action, win)), geo
    assert geo.left() >= 0 and geo.right() < win.width(), (geo, win.width())

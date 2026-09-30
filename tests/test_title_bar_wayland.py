"""Déplacer la fenêtre sans cadre sous Wayland.

Sous Wayland, `QWidget.move()` est ignoré : seul le compositeur déplace une
fenêtre. La barre de titre suivait la souris par `move()`, donc la fenêtre ne
bougeait pas du tout sur Bazzite (2026-09-30). Elle passe d'abord par
`startSystemMove`, et ne suit la souris elle-même que s'il refuse.
"""
import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPointF, Qt, QEvent  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from src.ui.title_bar import TitleBar  # noqa: E402


class _Poignee:
    def __init__(self, accepte: bool) -> None:
        self.accepte = accepte
        self.appels = 0

    def startSystemMove(self) -> bool:
        self.appels += 1
        return self.accepte


def _evenement(barre: TitleBar, genre: QEvent.Type, x: float) -> QMouseEvent:
    p = QPointF(x, 10)
    return QMouseEvent(genre, p, barre.mapToGlobal(p),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


@pytest.mark.parametrize("accepte", [True, False])
def test_le_compositeur_deplace_la_fenetre(qtbot, accepte):
    fenetre = QWidget()
    qtbot.addWidget(fenetre)
    barre = TitleBar(fenetre)
    poignee = _Poignee(accepte)
    fenetre.windowHandle = lambda: poignee    # sur l'INSTANCE (règle 12)
    barre.mousePressEvent(_evenement(barre, QEvent.Type.MouseButtonPress, 50))
    # L'appui seul ne passe pas la main : sous Windows, il avalerait le double-clic.
    assert poignee.appels == 0
    barre.mouseMoveEvent(_evenement(barre, QEvent.Type.MouseMove, 60))
    assert poignee.appels == 1
    # Accepté : aucun suivi manuel. Refusé : repli sur `move()`.
    assert (barre._drag_pos is None) is accepte

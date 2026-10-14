"""La molette fait défiler la page, jamais le réglage sous le curseur.

Ludo, 2026-10-14 : en faisant défiler les réglages graphiques, une liste
fermée passait sous le curseur et changeait de valeur, écrite aussitôt.
"""

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from src.ui.utils import liste_deroulante, zone_defilable


def _molette(widget, vers_le_bas=True):
    centre = QPointF(widget.rect().center())
    evenement = QWheelEvent(centre, QPointF(widget.mapToGlobal(centre.toPoint())), QPoint(),
                            QPoint(0, -120 if vers_le_bas else 120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, evenement)


def test_la_liste_ne_change_pas_et_la_page_defile(qtbot):
    page = QWidget()
    lay = QVBoxLayout(page)
    liste = liste_deroulante()
    liste.addItems(["Aucun", "2x", "4x", "8x"])
    lay.addWidget(liste)
    lay.addSpacing(2000)
    zone = zone_defilable(page)
    zone.resize(300, 200)
    qtbot.addWidget(zone)
    zone.show()
    qtbot.waitExposed(zone)

    _molette(liste)

    assert liste.currentIndex() == 0
    assert zone.verticalScrollBar().value() > 0


def test_meme_avec_le_focus(qtbot):
    """Après un choix, la liste garde le focus : la molette suivante non plus."""
    liste = liste_deroulante()
    liste.addItems(["a", "b", "c"])
    qtbot.addWidget(liste)
    liste.show()
    liste.setFocus()
    _molette(liste)
    assert liste.currentIndex() == 0

"""ClickableLabel — label cliquable ET focusable clavier (A11Y).

Remplace le monkey-patching `label.mousePressEvent = lambda …` qui rendait
les pseudo-liens invisibles à la navigation clavier. L'outline doré
`QLabel:focus` du stylesheet global s'applique automatiquement.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QLabel, QWidget


class ClickableLabel(QLabel):
    """QLabel émettant `clicked` au clic gauche, sur Entrée ou sur Espace."""

    clicked = pyqtSignal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

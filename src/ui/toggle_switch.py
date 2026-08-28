"""Interrupteur animé ON/OFF réutilisable."""

from PyQt6.QtCore import Qt, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.ui.focus_visible import PROPRIETE as _FOCUS_CLAVIER
from src.ui.theme import accent_qcolor, current as current_theme


class ToggleSwitch(QWidget):
    """Interrupteur animé ON/OFF."""

    toggled = pyqtSignal(bool)

    _TRACK_W = 40
    _TRACK_H = 22
    _KNOB_R = 8   # rayon du cercle

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._knob_x = float(self._TRACK_W - 12 if checked else 12)
        self.setFixedSize(self._TRACK_W, self._TRACK_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Sans ceci l'interrupteur était `NoFocus` : SEPT réglages ne
        # s'atteignaient qu'à la souris — lecture automatique des vidéos, son,
        # présence Discord, suppression des archives, plus trois de l'assistant
        # de premier lancement. Un utilisateur au clavier ne pouvait ni couper
        # une bande-annonce ni refuser Discord. Mesuré le 2026-08-28.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._anim = QPropertyAnimation(self, b"knob_x")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    # -- Propriété animable --
    def _get_knob_x(self) -> float:
        return self._knob_x

    def _set_knob_x(self, val: float) -> None:
        self._knob_x = val
        self.update()

    knob_x = pyqtProperty(float, _get_knob_x, _set_knob_x)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool) -> None:
        if val == self._checked:
            return
        self._checked = val
        self._animate()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._basculer()

    def keyPressEvent(self, event) -> None:
        """Espace et Entrée basculent, comme sur n'importe quelle case à cocher.

        Les deux, et pas seulement Espace : c'est la convention d'une case
        (Espace) ET celle d'un bouton (Entrée), et l'interrupteur ressemble
        assez aux deux pour qu'on essaie l'une ou l'autre.
        """
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._basculer()
            return
        super().keyPressEvent(event)

    def _basculer(self) -> None:
        self._checked = not self._checked
        self._animate()
        self.toggled.emit(self._checked)

    def _animate(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(float(self._TRACK_W - 12 if self._checked else 12))
        self._anim.start()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Piste
        # Piste off = bordure forte du thème (bleu nuit en Poudlard, teinte maison sinon)
        track_color = accent_qcolor() if self._checked else QColor(current_theme().border_strong)
        p.setBrush(QBrush(track_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, self._TRACK_W, self._TRACK_H), 11, 11)
        # Cercle
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QRectF(self._knob_x - self._KNOB_R, (self._TRACK_H - 2 * self._KNOB_R) / 2,
                              2 * self._KNOB_R, 2 * self._KNOB_R))
        # Anneau de focus réservé au CLAVIER (cf. focus_visible) : un widget
        # PEINT n'est pas atteint par la règle `:focus` du stylesheet, il doit
        # donc le dessiner lui-même — sinon l'utilisateur au clavier peut
        # atteindre l'interrupteur sans jamais voir lequel est sélectionné.
        if self.property(_FOCUS_CLAVIER):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(accent_qcolor(210), 1.2))
            p.drawRoundedRect(
                QRectF(0, 0, self._TRACK_W, self._TRACK_H).adjusted(0.6, 0.6, -0.6, -0.6),
                11, 11)
        p.end()


def toggle_row(label_text: str, checked: bool) -> tuple[QWidget, ToggleSwitch]:
    """Crée une ligne [toggle] [label] et renvoie le widget-ligne + le toggle."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(12)
    toggle = ToggleSwitch(checked)
    # Le libellé est à CÔTÉ, pas dedans : sans nom accessible, une aide
    # technique n'annonce qu'« interrupteur », sans dire de quoi.
    toggle.setAccessibleName(label_text)
    toggle.setToolTip(label_text)
    lay.addWidget(toggle)
    lbl = QLabel(label_text)
    lbl.setStyleSheet("color: #ffffff; font-size: 13px; background: transparent;")
    lay.addWidget(lbl, stretch=1)
    return row, toggle

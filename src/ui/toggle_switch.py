"""Interrupteur animé ON/OFF réutilisable."""

from PyQt6.QtCore import Qt, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


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
        track_color = QColor("#d4a017") if self._checked else QColor("#2c3e6b")
        p.setBrush(QBrush(track_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, self._TRACK_W, self._TRACK_H), 11, 11)
        # Cercle
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QRectF(self._knob_x - self._KNOB_R, (self._TRACK_H - 2 * self._KNOB_R) / 2,
                              2 * self._KNOB_R, 2 * self._KNOB_R))
        p.end()


def toggle_row(label_text: str, checked: bool) -> tuple[QWidget, ToggleSwitch]:
    """Crée une ligne [toggle] [label] et renvoie le widget-ligne + le toggle."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(12)
    toggle = ToggleSwitch(checked)
    lay.addWidget(toggle)
    lbl = QLabel(label_text)
    lbl.setStyleSheet("color: #ffffff; font-size: 13px; background: transparent;")
    lay.addWidget(lbl, stretch=1)
    return row, toggle

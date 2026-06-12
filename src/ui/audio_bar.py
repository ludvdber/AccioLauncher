"""Barre audio (mute + volume) du lecteur vidéo de la vue détail."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QWidget

from src.ui.theme import themed

_MUTE_ON = "\U0001f507"
_MUTE_OFF = "\U0001f50a"


class AudioBar(QWidget):
    """Mini-barre flottante avec bouton mute et slider de volume.

    Émet `mute_toggled` (bool) et `volume_changed` (int 0-100). Le contrôleur
    est responsable de propager au lecteur média et de mettre à jour l'icône.
    """

    mute_toggled = pyqtSignal()
    volume_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("QWidget { background: rgba(0,0,0,0.55); border-radius: 14px; }")
        self.setFixedSize(160, 32)
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self._btn_mute = QPushButton(_MUTE_OFF)
        self._btn_mute.setFixedSize(26, 26)
        self._btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mute.setAccessibleName("Couper le son de la vidéo")
        self._btn_mute.setStyleSheet(themed(
            "QPushButton { background: transparent; color: #eaeaea; border: none; font-size: 15px; }"
            "QPushButton:hover { color: #d4a017; }"
        ))
        self._btn_mute.clicked.connect(self.mute_toggled.emit)
        layout.addWidget(self._btn_mute)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(25)
        self._volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._volume_slider.setAccessibleName("Volume de la vidéo")
        self._volume_slider.setStyleSheet(themed(
            "QSlider::groove:horizontal { background: rgba(255,255,255,0.12); height: 4px; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #d4a017; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: rgba(212,160,23,0.5); border-radius: 2px; }"
        ))
        self._volume_slider.valueChanged.connect(self.volume_changed.emit)
        layout.addWidget(self._volume_slider)

    def set_muted_icon(self, muted: bool) -> None:
        self._btn_mute.setText(_MUTE_ON if muted else _MUTE_OFF)

    def volume(self) -> int:
        return self._volume_slider.value()

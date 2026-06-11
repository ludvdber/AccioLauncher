"""Toast — notification éphémère non bloquante affichée au-dessus du contenu.

Une seule instance par fenêtre, réutilisée : un nouveau message remplace
l'ancien et relance le timer. Fade-in/out via QGraphicsOpacityEffect.
"""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from src.ui.fonts import body_font

_DEFAULT_DURATION_MS = 3500


class Toast(QLabel):
    """Bandeau doré discret, centré en bas de la fenêtre parente."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFont(body_font(13))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "QLabel { background: rgba(13, 13, 26, 0.94); color: #e8c547;"
            " border: 1px solid rgba(212, 160, 23, 0.45); border-radius: 8px;"
            " padding: 10px 22px; }"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, duration_ms: int = _DEFAULT_DURATION_MS) -> None:
        """Affiche (ou remplace) le toast pendant `duration_ms`."""
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(1.0)
        self._anim.setDuration(180)
        self._anim.start()
        self._hide_timer.start(duration_ms)

    def reposition(self) -> None:
        """Centre le toast en bas de la fenêtre parente (au-dessus du carrousel)."""
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 200
        self.move(x, max(y, 0))

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(0.0)
        self._anim.setDuration(300)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        if self._opacity.opacity() < 0.05:
            self.hide()

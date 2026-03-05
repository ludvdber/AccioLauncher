"""Barre de titre custom pour fenêtre sans cadre."""

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QLabel, QWidget

from src.ui.fonts import cinzel


class TitleBar(QWidget):
    """Barre de titre draggable avec boutons min/max/close."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._window = parent
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(38)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(0)

        # Titre — Cinzel Decorative, doré
        self._title = QLabel("\u26a1 Accio Launcher")
        self._title.setFont(cinzel(13, bold=True))
        self._title.setStyleSheet("color: #d4a017; background: transparent;")
        layout.addWidget(self._title)

        layout.addStretch()

        # Boutons minimalistes
        for text, slot, hover_bg in (
            ("\u2500", self._on_minimize, "rgba(255,255,255,0.08)"),
            ("\u25a1", self._on_maximize, "rgba(255,255,255,0.08)"),
            ("\u2715", self._on_close, "#c0392b"),
        ):
            btn = QPushButton(text)
            btn.setFixedSize(44, 38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: #8a8aaa; border: none;"
                f" font-size: 13px; }}"
                f"QPushButton:hover {{ background: {hover_bg}; color: #eaeaea; }}"
            )
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def _on_minimize(self) -> None:
        self._window.showMinimized()

    def _on_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def _on_close(self) -> None:
        self._window.close()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(6, 6, 17, 217))  # rgba(6,6,17,0.85)
        # Séparateur doré subtil
        p.setPen(QPen(QColor(212, 160, 23, 25), 1.0))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    # ── Drag de la fenêtre ──

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._on_maximize()

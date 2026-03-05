import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QIcon, QKeyEvent, QMouseEvent, QPixmap, QPainter, QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core.config import APP_VERSION, Config, DEFAULT_INSTALL_PATH
from src.core.game_manager import GameManager
from src.ui.carousel import Carousel
from src.ui.fonts import load_fonts
from src.ui.game_detail import GameDetailView
from src.ui.particles import ParticleOverlay
from src.ui.settings_panel import SettingsDialog
from src.ui.styles import MAIN_STYLE
from src.ui.title_bar import TitleBar


def _make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(QFont("Segoe UI Emoji", 40))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "\u26a1")
    painter.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    """Fenêtre principale d'Accio Launcher — style launcher AAA."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Accio Launcher")
        self.resize(1200, 800)
        self.setWindowIcon(_make_icon())

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(MAIN_STYLE)

        self.setMouseTracking(True)

        load_fonts()

        self.config = self._first_launch_or_load()
        self.manager = GameManager(self.config)
        self._build_ui()

    @staticmethod
    def _first_launch_or_load() -> Config:
        if Config.exists():
            return Config.load()

        QMessageBox.information(
            None,
            "Bienvenue dans Accio Launcher !",
            "Bienvenue dans Accio Launcher !\n\n"
            "Veuillez choisir le dossier o\u00f9 les jeux seront install\u00e9s.",
        )
        chosen = QFileDialog.getExistingDirectory(
            None, "Dossier d'installation des jeux", str(DEFAULT_INSTALL_PATH),
        )
        install_path = Path(chosen) if chosen else DEFAULT_INSTALL_PATH
        config = Config(install_path=install_path, cache_path=install_path / ".cache")
        config.save()
        return config

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralContainer")
        central.setMouseTracking(True)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._title_bar = TitleBar(self)
        root_layout.addWidget(self._title_bar)

        games = [entry["game"] for entry in self.manager.get_games()]

        self._detail = GameDetailView(self.manager, self)
        self._detail.setMouseTracking(True)
        self._detail.status_message.connect(self._show_status)
        self._detail.state_changed.connect(self._on_state_changed)
        root_layout.addWidget(self._detail, stretch=1)

        self._carousel = Carousel(games, self.manager, self)
        self._carousel.game_selected.connect(self._on_carousel_select)
        root_layout.addWidget(self._carousel)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Pr\u00eat")

        # Overlay particules
        self._particles = ParticleOverlay(self)
        self._particles.raise_()

        # Settings button
        self._btn_settings = QPushButton("\u2699", self)
        self._btn_settings.setFixedSize(36, 36)
        self._btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_settings.setStyleSheet(
            "QPushButton { background: rgba(0,0,0,0.4); color: #8a8aaa; border: none;"
            " border-radius: 18px; font-size: 18px; }"
            "QPushButton:hover { color: #d4a017; background: rgba(0,0,0,0.6); }"
        )
        self._btn_settings.clicked.connect(self._on_settings)
        self._btn_settings.raise_()

        # Event filter on QApplication for global mouse tracking
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)

        if games:
            self._detail.set_game(games[0])

    def _show_status(self, msg: str) -> None:
        self._status_bar.showMessage(msg)

    def _on_carousel_select(self, index: int) -> None:
        games = [entry["game"] for entry in self.manager.get_games()]
        if 0 <= index < len(games):
            self._detail.set_game(games[index])

    def _on_state_changed(self) -> None:
        self._carousel.refresh_indicators()

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.manager, self)
        dlg.exec()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_btn_settings"):
            self._btn_settings.move(self.width() - 52, 42)
            self._btn_settings.raise_()
        if hasattr(self, "_particles"):
            self._particles.setGeometry(self.centralWidget().geometry())
            self._particles.raise_()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseMove:
            try:
                global_pos = event.globalPosition()
                local = self.mapFromGlobal(global_pos.toPoint())
                pos = QPointF(local.x(), local.y())
                if hasattr(self, "_detail"):
                    self._detail.handle_mouse_move(pos)
            except (AttributeError, RuntimeError):
                pass
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if hasattr(self, "_detail"):
            self._detail.handle_mouse_move(QPointF(pos.x(), pos.y()))
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        match event.key():
            case Qt.Key.Key_Left:
                self._carousel.select_prev()
            case Qt.Key.Key_Right:
                self._carousel.select_next()
            case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                self._detail.trigger_primary_action()
            case _:
                super().keyPressEvent(event)

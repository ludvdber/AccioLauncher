import logging
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QPointF, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeyEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from src.core.config import ASSETS_DIR, Config, DEFAULT_INSTALL_PATH
from src.core.game_manager import GameManager
from src.ui.carousel import Carousel
from src.ui.fonts import load_fonts
from src.ui.game_detail import GameDetailView
from src.ui.particles import ParticleOverlay
from src.ui.settings_panel import SettingsDialog
from src.ui.styles import MAIN_STYLE
from src.ui.title_bar import TitleBar

log = logging.getLogger(__name__)

_PROCESS_POLL_MS = 2000  # Vérification toutes les 2 secondes

_ICON_PATH = ASSETS_DIR / "accio_launcher.png"


def _load_app_icon() -> QIcon:
    """Charge l'icône de l'application depuis le fichier PNG."""
    icon_path = str(_ICON_PATH)
    return QIcon(icon_path)


class MainWindow(QMainWindow):
    """Fenêtre principale d'Accio Launcher — style launcher AAA."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Accio Launcher")
        self.resize(1200, 800)
        self.setWindowIcon(_load_app_icon())

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(MAIN_STYLE)

        self.setMouseTracking(True)

        load_fonts()

        self.config = self._first_launch_or_load()
        self.manager = GameManager(self.config)

        # État du processus de jeu surveillé
        self._game_process: subprocess.Popen | None = None
        self._game_name: str = ""

        self._build_ui()
        self._build_tray()
        self._build_process_monitor()

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

    # ──────────────────── Construction UI ────────────────────

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
        self._detail.game_launched.connect(self._on_game_launched)
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

    # ──────────────────── System Tray ────────────────────

    def _build_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(_load_app_icon())
        self._tray.setToolTip("Accio Launcher")

        tray_menu = QMenu()
        act_restore = QAction("Restaurer Accio Launcher", self)
        act_restore.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(act_restore)

        tray_menu.addSeparator()

        act_quit = QAction("Quitter", self)
        act_quit.triggered.connect(self._quit_app)
        tray_menu.addAction(act_quit)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)

    def _build_process_monitor(self) -> None:
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_PROCESS_POLL_MS)
        self._poll_timer.timeout.connect(self._poll_game_process)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _minimize_to_tray(self) -> None:
        """Cache la fenêtre dans le system tray et pause tous les effets."""
        self.hide()
        self._tray.show()
        self.pause_all_effects()
        log.info("Launcher minimisé dans le tray — en jeu : %s", self._game_name)

    def _restore_from_tray(self) -> None:
        """Restaure la fenêtre et reprend les effets."""
        self.showNormal()
        self.activateWindow()
        self._tray.hide()
        self.resume_all_effects()
        log.info("Launcher restauré depuis le tray")

    def _quit_app(self) -> None:
        """Quitte proprement l'application."""
        self._tray.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    # ──────────────────── Pause / Resume effets ────────────────────

    def pause_all_effects(self) -> None:
        """Met en pause TOUS les timers et animations pour consommation CPU ~0."""
        if hasattr(self, "_particles"):
            self._particles.pause()
        if hasattr(self, "_detail") and hasattr(self._detail, "_bg"):
            self._detail._bg.pause()
        if hasattr(self, "_carousel"):
            self._carousel.pause()
        log.debug("Tous les effets sont en pause")

    def resume_all_effects(self) -> None:
        """Reprend tous les timers et animations."""
        if hasattr(self, "_particles"):
            self._particles.resume()
        if hasattr(self, "_detail") and hasattr(self._detail, "_bg"):
            self._detail._bg.resume()
        if hasattr(self, "_carousel"):
            self._carousel.resume()
        log.debug("Tous les effets sont repris")

    # ──────────────────── Surveillance du processus de jeu ────────────────────

    def _on_game_launched(self, process: subprocess.Popen, game_name: str) -> None:
        """Appelé quand un jeu est lancé — minimise et surveille."""
        self._game_process = process
        self._game_name = game_name
        self._tray.setToolTip(f"Accio Launcher \u2014 En jeu : {game_name}")
        self._minimize_to_tray()
        self._poll_timer.start()

    def _poll_game_process(self) -> None:
        """Vérifie si le jeu tourne encore (toutes les 2s)."""
        if self._game_process is None:
            self._poll_timer.stop()
            return

        ret = self._game_process.poll()
        if ret is not None:
            # Le jeu s'est fermé
            game_name = self._game_name
            self._game_process = None
            self._game_name = ""
            self._poll_timer.stop()
            self._tray.setToolTip("Accio Launcher")

            log.info("Jeu terminé : %s (code retour %s)", game_name, ret)

            self._restore_from_tray()
            self._status_bar.showMessage(f"Retour de {game_name} \u2014 Bon jeu !")

    # ──────────────────── Slots UI ────────────────────

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
        dlg.config_changed.connect(self._on_state_changed)
        dlg.exec()

    # ──────────────────── Événements ────────────────────

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

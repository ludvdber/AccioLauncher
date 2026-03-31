import logging
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QPointF, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
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
from src.core.updater import UpdateChecker
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
        self._game_exe_name: str = ""  # nom de l'exe pour détecter un redémarrage
        self._exe_grace_until: float = 0.0  # timestamp jusqu'auquel on attend le redémarrage

        self._update_checker: UpdateChecker | None = None
        self._launcher_update_version: str = ""
        self._launcher_update_url: str = ""

        self._build_ui()
        self._build_tray()
        self._build_process_monitor()
        self._start_update_check()

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

        # Notification bar (cachée par défaut)
        self._notif_bar = self._build_notif_bar()
        root_layout.addWidget(self._notif_bar)
        self._notif_bar.hide()

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

    def _build_notif_bar(self) -> QWidget:
        """Construit la barre de notification dorée pour les updates launcher."""
        bar = QWidget()
        bar.setFixedHeight(35)
        bar.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 rgba(212,160,23,0.15), stop:0.5 rgba(212,160,23,0.25),"
            "stop:1 rgba(212,160,23,0.15)); }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(10)

        self._notif_label = QLabel()
        self._notif_label.setStyleSheet("color: #d4a017; font-size: 12px; background: transparent;")
        layout.addWidget(self._notif_label, stretch=1)

        self._notif_btn = QPushButton("Télécharger")
        self._notif_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notif_btn.setStyleSheet(
            "QPushButton { background: rgba(212,160,23,0.2); color: #d4a017;"
            " border: 1px solid rgba(212,160,23,0.4); border-radius: 4px;"
            " padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(212,160,23,0.35); color: #e8c547; }"
        )
        self._notif_btn.clicked.connect(self._on_notif_download)
        layout.addWidget(self._notif_btn)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; color: #d4a017; border: none; font-size: 14px; }"
            "QPushButton:hover { color: #e8c547; }"
        )
        btn_close.clicked.connect(self._dismiss_notif)
        layout.addWidget(btn_close)

        return bar

    # ──────────────────── Update checker ────────────────────

    def _start_update_check(self) -> None:
        """Lance la vérification des mises à jour en arrière-plan."""
        if not self.config.check_updates:
            return
        catalog = self.manager.catalog
        self._update_checker = UpdateChecker(
            catalog_url=catalog.catalog_url,
            current_catalog_version=catalog.catalog_version,
            installed_versions=self.config.installed_versions,
            parent=self,
        )
        self._update_checker.catalog_updated.connect(self._on_catalog_updated)
        self._update_checker.launcher_update.connect(self._on_launcher_update)
        self._update_checker.update_counts.connect(self._on_update_counts)
        self._update_checker.start()

    def _on_catalog_updated(self, catalog) -> None:
        """Le catalogue distant est plus récent — recharger."""
        self.manager.reload_catalog(catalog)
        # Rafraîchir l'UI
        games = [entry["game"] for entry in self.manager.get_games()]
        self._carousel.refresh_indicators()
        # Mettre à jour la vue détaillée si le jeu courant a changé
        if self._detail.game:
            updated = self.manager.get_game_by_id(self._detail.game.id)
            if updated:
                self._detail.update_game_data(updated)
        log.info("UI rafraîchie après mise à jour du catalogue")

    def _on_launcher_update(self, version: str, url: str) -> None:
        """Nouvelle version du launcher disponible."""
        if self.config.dismissed_launcher_version == version:
            return
        self._launcher_update_version = version
        self._launcher_update_url = url
        self._notif_label.setText(f"Accio Launcher v{version} est disponible !")
        self._notif_bar.show()
        QTimer.singleShot(30_000, self._auto_hide_notif)

    def _on_update_counts(self, count: int) -> None:
        """Affiche le nombre de mises à jour disponibles dans la status bar."""
        self._status_bar.showMessage(
            f"{count} mise(s) à jour disponible(s)" if count > 0 else "Prêt"
        )

    def _on_notif_download(self) -> None:
        if self._launcher_update_url:
            self._open_url(self._launcher_update_url)

    def _dismiss_notif(self) -> None:
        """Ferme la notification et sauvegarde la version ignorée."""
        self._notif_bar.hide()
        if self._launcher_update_version:
            self.config.dismissed_launcher_version = self._launcher_update_version
            self.config.save()

    def _auto_hide_notif(self) -> None:
        if self._notif_bar.isVisible():
            self._notif_bar.hide()

    @staticmethod
    def _open_url(url: str) -> None:
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

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
        self._particles.pause()
        self._detail.pause()
        self._carousel.pause()
        log.debug("Tous les effets sont en pause")

    def resume_all_effects(self) -> None:
        """Reprend tous les timers et animations."""
        self._particles.resume()
        self._detail.resume()
        self._carousel.resume()
        log.debug("Tous les effets sont repris")

    # ──────────────────── Surveillance du processus de jeu ────────────────────

    def _on_game_launched(self, process: subprocess.Popen, game_name: str) -> None:
        """Appelé quand un jeu est lancé — minimise et surveille."""
        self._game_process = process
        self._game_name = game_name
        # Extraire le nom de l'exe pour détecter un redémarrage du processus
        try:
            self._game_exe_name = Path(process.args[0]).name.lower()
        except (IndexError, TypeError):
            self._game_exe_name = ""
        self._tray.setToolTip(f"Accio Launcher \u2014 En jeu : {game_name}")
        self._minimize_to_tray()
        self._poll_timer.start()

    @staticmethod
    def _is_exe_still_running(exe_name: str) -> bool:
        """Vérifie si un processus avec ce nom d'exe tourne encore."""
        if not exe_name:
            return False
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return exe_name.lower() in result.stdout.lower()
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _poll_game_process(self) -> None:
        """Vérifie si le jeu tourne encore (toutes les 2s).

        Deux modes de surveillance :
        1. Par Popen.poll() — tant que le processus initial tourne
        2. Par nom d'exe (tasklist) — si le jeu a redémarré son processus
           (ex: UE1 redémarre quand on charge une partie depuis le wizard)
        """
        import time

        if self._game_process is not None:
            ret = self._game_process.poll()
            if ret is None:
                return  # processus initial tourne encore
            # Le processus initial s'est fermé — accorder 10s de grâce
            # pour laisser le jeu redémarrer (UE1 wizard → jeu)
            log.info("Process initial terminé (code %s), grâce de 10s…", ret)
            self._game_process = None
            self._exe_grace_until = time.monotonic() + 10.0
            return  # ne pas vérifier tout de suite

        # Mode surveillance par nom d'exe
        if self._game_exe_name and self._is_exe_still_running(self._game_exe_name):
            return  # le jeu tourne encore (process redémarré)

        # Pendant la période de grâce, ne pas restaurer même si l'exe est introuvable
        if time.monotonic() < self._exe_grace_until:
            return

        # Le jeu est vraiment fermé
        game_name = self._game_name
        self._game_name = ""
        self._game_exe_name = ""
        self._poll_timer.stop()
        self._tray.setToolTip("Accio Launcher")

        log.info("Jeu terminé : %s", game_name)

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
        dlg.force_catalog_refresh.connect(lambda: self._force_update_check(dlg, catalog_only=True))
        dlg.force_launcher_check.connect(lambda: self._force_update_check(dlg, catalog_only=False))
        dlg.exec()

    def _force_update_check(self, dlg: SettingsDialog, *, catalog_only: bool) -> None:
        """Lance une vérification forcée (catalogue et/ou launcher)."""
        catalog = self.manager.catalog
        checker = UpdateChecker(
            catalog_url=catalog.catalog_url,
            current_catalog_version="0",  # version "0" → force le fetch
            installed_versions=self.config.installed_versions,
            parent=self,
        )
        state = {"catalog_updated": False}

        def on_catalog(new_catalog):
            state["catalog_updated"] = True
            self._on_catalog_updated(new_catalog)
            dlg.update_catalog_version(new_catalog.catalog_version)

        def on_launcher(version, url):
            self._launcher_update_version = version
            self._launcher_update_url = url
            self._notif_label.setText(f"Accio Launcher v{version} est disponible !")
            self._notif_bar.show()
            dlg.show_update_status(f"Launcher v{version} disponible !")

        def on_finished():
            if not state["catalog_updated"]:
                dlg.show_update_status("Catalogue déjà à jour")
            if catalog_only:
                return
            if not self._launcher_update_url:
                dlg.show_update_status("Tout est à jour")

        checker.catalog_updated.connect(on_catalog)
        if not catalog_only:
            checker.launcher_update.connect(on_launcher)
        checker.finished.connect(on_finished)
        checker.start()

    # ──────────────────── Événements ────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._btn_settings.move(self.width() - 52, 42)
        self._btn_settings.raise_()
        self._particles.setGeometry(self.centralWidget().geometry())
        self._particles.raise_()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseMove:
            try:
                global_pos = event.globalPosition()
                local = self.mapFromGlobal(global_pos.toPoint())
                self._detail.handle_mouse_move(QPointF(local.x(), local.y()))
            except (AttributeError, RuntimeError):
                pass
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self._detail.handle_mouse_move(QPointF(pos.x(), pos.y()))
        super().mouseMoveEvent(event)

    def closeEvent(self, event) -> None:
        """Attend la fin des threads avant de fermer."""
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().removeEventFilter(self)

        if self._update_checker is not None and self._update_checker.isRunning():
            self._update_checker.wait(3000)
        # Arrêter un éventuel téléchargement/installation en cours
        if self._detail._downloader is not None:
            self._detail._downloader.cancel()
            self._detail._downloader.wait(3000)
        if self._detail._installer is not None:
            self._detail._installer.cancel()
            self._detail._installer.wait(3000)
        self._tray.hide()
        super().closeEvent(event)

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

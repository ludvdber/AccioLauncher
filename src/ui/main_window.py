import logging
import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QPointF, QTimer
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core.config import ASSETS_DIR, Config, DEFAULT_INSTALL_PATH
from src.core.discord_presence import DiscordPresence
from src.core.downloader import Downloader
from src.core.game_manager import GameManager, GameState
from src.core.i18n import tr
from src.core.self_update import apply_update_and_restart, can_self_update
from src.core.updater import UpdateChecker
from src.core.win_taskbar import TaskbarProgress
from src.ui.carousel import Carousel
from src.ui.download_bar import DownloadBar
from src.ui.fonts import load_fonts
from src.ui.game_detail import GameDetailView
from src.ui.particles import ParticleOverlay
from src.ui.process_monitor import ProcessMonitor
from src.ui.settings_panel import SettingsDialog
from src.ui.styles import MAIN_STYLE
from src.ui.ticker import Ticker
from src.ui.title_bar import TitleBar
from src.ui.toast import Toast
from src.ui.tray_manager import TrayManager
from src.ui.utils import open_url

log = logging.getLogger(__name__)

_ICON_PATH = ASSETS_DIR / "accio_launcher.png"


def _load_app_icon() -> QIcon:
    """Charge l'icône de l'application depuis le fichier PNG."""
    icon_path = str(_ICON_PATH)
    return QIcon(icon_path)


class MainWindow(QMainWindow):
    """Fenêtre principale d'Accio Launcher — style launcher AAA."""

    RESIZE_MARGIN = 6  # zone de saisie des bords pour redimensionner (px)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Accio Launcher")
        self.resize(1200, 800)
        self.setMinimumSize(980, 660)
        self.setWindowIcon(_load_app_icon())

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(MAIN_STYLE)

        self.setMouseTracking(True)
        self._edge_cursor_active = False  # override-cursor de resize posé ?

        load_fonts()

        self.config = self._first_launch_or_load()
        # La langue doit être active AVANT la construction des widgets (chaînes tr()
        # posées à la construction ; changement de langue = redémarrage).
        from src.core.i18n import set_language
        set_language(self.config.langue)
        self.manager = GameManager(self.config)

        self._update_checker: UpdateChecker | None = None
        self._extra_checkers: list[UpdateChecker] = []
        self._launcher_update_version: str = ""
        self._launcher_update_url: str = ""
        self._launcher_update_asset: str = ""
        self._launcher_dl: Downloader | None = None  # téléchargement auto-update en cours
        self._taskbar: TaskbarProgress | None = None  # créé paresseusement (winId après show)
        self._presence = DiscordPresence()  # no-op tant que DISCORD_CLIENT_ID est vide
        # Session de jeu en cours (stats de temps de jeu)
        self._session_game_id: str = ""
        self._session_start: float = 0.0

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
        install_path = MainWindow._prompt_writable_dir()
        config = Config(install_path=install_path, cache_path=install_path / ".cache")
        config.save()
        return config

    @staticmethod
    def _prompt_writable_dir() -> Path:
        """Demande un dossier au user, retry tant qu'il n'est pas inscriptible.

        Le user peut annuler \u00e0 tout moment \u2192 on tombe sur DEFAULT_INSTALL_PATH (cr\u00e9able).
        """
        while True:
            chosen = QFileDialog.getExistingDirectory(
                None, "Dossier d'installation des jeux", str(DEFAULT_INSTALL_PATH),
            )
            candidate = Path(chosen) if chosen else DEFAULT_INSTALL_PATH
            if MainWindow._is_writable(candidate):
                return candidate
            reply = QMessageBox.warning(
                None, "Dossier non inscriptible",
                f"Impossible d'\u00e9crire dans :\n{candidate}\n\n"
                "Choisissez un autre dossier ou annulez pour utiliser :\n"
                f"{DEFAULT_INSTALL_PATH}",
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Retry,
            )
            if reply != QMessageBox.StandardButton.Retry:
                # Fallback DEFAULT_INSTALL_PATH (toujours cr\u00e9able sous le home).
                DEFAULT_INSTALL_PATH.mkdir(parents=True, exist_ok=True)
                return DEFAULT_INSTALL_PATH

    @staticmethod
    def _is_writable(path: Path) -> bool:
        """Cr\u00e9e le dossier si n\u00e9cessaire et v\u00e9rifie qu'on peut y \u00e9crire."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".accio_write_test"
            probe.write_bytes(b"")
            probe.unlink()
            return True
        except OSError:
            return False

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

        games = [entry.game for entry in self.manager.get_games()]

        self._detail = GameDetailView(self.manager, self)
        self._detail.setMouseTracking(True)
        self._detail.status_message.connect(self._show_status)
        self._detail.state_changed.connect(self._on_state_changed)
        self._detail.game_launched.connect(self._on_game_launched)
        root_layout.addWidget(self._detail, stretch=1)

        # Barre de téléchargement persistante (visible pendant download/install)
        self._download_bar = DownloadBar(self)
        root_layout.addWidget(self._download_bar)
        self._wire_download_bar()

        self._carousel = Carousel(games, self.manager, self)
        self._carousel.game_selected.connect(self._on_carousel_select)
        root_layout.addWidget(self._carousel)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(tr("Prêt"))

        # Overlay particules
        self._particles = ParticleOverlay(self)
        self._particles.raise_()

        # Toast (notifications éphémères)
        self._toast = Toast(self)
        self._detail.ops.operation_finished.connect(self._notify_operation_finished)

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
        self._tray = TrayManager(_load_app_icon(), self)
        self._tray.restore_requested.connect(self._restore_from_tray)
        self._tray.quit_requested.connect(self._quit_app)

    def _wire_download_bar(self) -> None:
        """Connecte la barre de téléchargement aux signaux du GameOperations."""
        ops = self._detail.ops
        ops.download_progress.connect(self._download_bar.update_download_progress)
        ops.install_progress.connect(self._download_bar.update_install_progress)
        ops.part_info.connect(self._download_bar.update_part_info)
        ops.state_changed.connect(self._on_ops_state_changed)
        self._download_bar.cancel_clicked.connect(ops.cancel_download)
        # Progression sur l'icône de la barre des tâches Windows
        ops.download_progress.connect(self._on_taskbar_download_progress)
        ops.install_progress.connect(self._on_taskbar_install_progress)

    def _get_taskbar(self) -> TaskbarProgress:
        if self._taskbar is None:
            self._taskbar = TaskbarProgress(int(self.winId()))
        return self._taskbar

    def _on_taskbar_download_progress(self, downloaded: int, total: int,
                                      _speed: float, _eta: float) -> None:
        self._get_taskbar().set_progress(downloaded, max(total, 1))

    def _on_taskbar_install_progress(self, pct: int) -> None:
        self._get_taskbar().set_progress(pct, 100)

    def _notify_operation_finished(self, game) -> None:
        """Fin d'installation : toast, et notification système si on n'est pas devant."""
        self._toast.show_message(tr("{} installé avec succès ✓").format(game.name))
        if self.isHidden():
            # Minimisé dans le tray (souvent : en jeu) → vraie notification Windows
            self._tray.show_notification(
                tr("Téléchargement terminé"), tr("{} est prêt à jouer !").format(game.name)
            )
        elif not self.isActiveWindow():
            from PyQt6.QtWidgets import QApplication
            QApplication.alert(self)  # fait clignoter l'icône taskbar

    def _on_ops_state_changed(self) -> None:
        """Affiche/cache la barre de téléchargement selon l'état des opérations."""
        ops = self._detail.ops
        if ops.is_busy and ops.active_game is not None:
            game = ops.active_game
            state = self.manager.get_state(game.id)
            if state in (GameState.DOWNLOADING, GameState.INSTALLING):
                self._download_bar.show_for_game(game, state)
                return
        self._download_bar.hide_bar()
        self._get_taskbar().clear()

    def _build_process_monitor(self) -> None:
        self._monitor = ProcessMonitor(self)
        self._monitor.game_exited.connect(self._on_game_exited)

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

        self._notif_btn = QPushButton(tr("Télécharger"))
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
        if self._update_checker is not None and self._update_checker.isRunning():
            self._update_checker.requestInterruption()
            self._update_checker.wait(1000)
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
        games = [entry.game for entry in self.manager.get_games()]
        self._carousel.set_games(games)
        # Vue détaillée : conserver le jeu si encore présent, sinon premier jeu
        current_id = self._detail.game.id if self._detail.game else None
        updated = self.manager.get_game_by_id(current_id) if current_id else None
        if updated is not None:
            self._detail.set_game(updated)
        elif games:
            self._detail.set_game(games[0])
        self._toast.show_message(tr("Catalogue mis à jour (v{})").format(catalog.catalog_version))
        log.info("UI rafraîchie après mise à jour du catalogue")

    def _on_launcher_update(self, version: str, url: str, asset_url: str = "") -> None:
        """Nouvelle version du launcher disponible."""
        if self.config.dismissed_launcher_version == version:
            return
        self._launcher_update_version = version
        self._launcher_update_url = url
        self._launcher_update_asset = asset_url
        self._notif_label.setText(tr("Accio Launcher v{} est disponible !").format(version))
        self._notif_btn.setText(tr("Mettre à jour") if asset_url and can_self_update() else tr("Télécharger"))
        self._notif_bar.show()
        QTimer.singleShot(30_000, self._auto_hide_notif)

    def _on_update_counts(self, count: int) -> None:
        """Affiche le nombre de mises à jour disponibles dans la status bar."""
        if self._detail.ops.is_busy:
            return  # ne pas écraser le statut d'un téléchargement en cours
        self._status_bar.showMessage(
            tr("{} mise(s) à jour disponible(s)").format(count) if count > 0 else tr("Prêt")
        )

    def _on_notif_download(self) -> None:
        """Auto-update en un clic si possible, sinon ouverture de la page release."""
        if self._launcher_dl is not None:
            return  # téléchargement déjà en cours
        if not self._launcher_update_asset or not can_self_update():
            if self._launcher_update_url:
                open_url(self._launcher_update_url)
            return
        dest = self.config.cache_path / f"AccioLauncher_v{self._launcher_update_version}.exe"
        dest.unlink(missing_ok=True)
        self._notif_btn.setEnabled(False)
        self._notif_label.setText(tr("Téléchargement de la mise à jour…"))
        self._launcher_dl = Downloader(
            url=self._launcher_update_asset, destination=dest, parent=self,
        )
        self._launcher_dl.progress.connect(self._on_launcher_dl_progress)
        self._launcher_dl.download_finished.connect(self._on_launcher_dl_finished)
        self._launcher_dl.error.connect(self._on_launcher_dl_error)
        self._launcher_dl.start()

    def _on_launcher_dl_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self._notif_label.setText(
                tr("Téléchargement de la mise à jour… {}%").format(downloaded * 100 // total)
            )

    def _on_launcher_dl_finished(self, path_str: str) -> None:
        self._launcher_dl = None
        self._notif_btn.setEnabled(True)
        if apply_update_and_restart(Path(path_str)):
            self._notif_label.setText(tr("Redémarrage…"))
            log.info("Fermeture pour mise à jour vers v%s", self._launcher_update_version)
            self.close()
        else:
            # Mode dev / échec du script : retomber sur la page release
            if self._launcher_update_url:
                open_url(self._launcher_update_url)

    def _on_launcher_dl_error(self, message: str) -> None:
        log.warning("Échec du téléchargement de la mise à jour : %s", message)
        self._launcher_dl = None
        self._notif_btn.setEnabled(True)
        self._notif_label.setText(tr("Échec du téléchargement — ouverture de la page de release"))
        if self._launcher_update_url:
            open_url(self._launcher_update_url)

    def _dismiss_notif(self) -> None:
        """Ferme la notification et sauvegarde la version ignorée."""
        self._notif_bar.hide()
        if self._launcher_update_version:
            self.config.dismissed_launcher_version = self._launcher_update_version
            self.config.save()

    def _auto_hide_notif(self) -> None:
        if self._notif_bar.isVisible():
            self._notif_bar.hide()

    def _minimize_to_tray(self) -> None:
        """Cache la fenêtre dans le system tray et pause tous les effets."""
        self.hide()
        self._tray.show()
        self.pause_all_effects()
        log.info("Launcher minimisé dans le tray — en jeu : %s", self._monitor.game_name)

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

    def bring_to_front(self) -> None:
        """Remet la fenêtre au premier plan (second lancement → instance unique)."""
        if self.isHidden():
            self._restore_from_tray()
            return
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # ──────────────────── Pause / Resume effets ────────────────────

    def pause_all_effects(self) -> None:
        """Met en pause TOUS les timers et animations pour consommation CPU ~0."""
        Ticker.instance().pause()
        self._particles.pause()
        self._detail.pause()
        self._carousel.pause()
        log.debug("Tous les effets sont en pause")

    def resume_all_effects(self) -> None:
        """Reprend tous les timers et animations."""
        Ticker.instance().resume()
        self._particles.resume()
        self._detail.resume()
        self._carousel.resume()
        log.debug("Tous les effets sont repris")

    def changeEvent(self, event) -> None:
        """Fenêtre désactivée (derrière une autre) → pause des effets décoratifs.

        La vidéo continue (l'utilisateur peut regarder un trailer en arrière-plan) ;
        seuls particules, étoiles, glow et zoom s'arrêtent — CPU/GPU quasi nul.
        """
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                Ticker.instance().resume()
                self._detail.resume_effects()
            elif self.isVisible():  # pas via le tray (géré par pause_all_effects)
                Ticker.instance().pause()
                self._detail.pause_effects()
        super().changeEvent(event)

    # ──────────────────── Surveillance du processus de jeu ────────────────────

    def _on_game_launched(self, process: subprocess.Popen, game_name: str, game_id: str) -> None:
        """Appelé quand un jeu est lancé — minimise, surveille, présence Discord, stats."""
        self._session_game_id = game_id
        self._session_start = time.monotonic()
        self._tray.set_tooltip(tr("Accio Launcher — En jeu : {}").format(game_name))
        self._minimize_to_tray()
        self._monitor.start(process, game_name)
        if self.config.discord_presence:
            self._presence.set_playing(game_name)

    def _on_game_exited(self, game_name: str) -> None:
        """Le ProcessMonitor a détecté la fin du jeu (avec grâce de redémarrage)."""
        # Stats : cumuler la session (les sessions < 10 s sont des faux lancements)
        elapsed = time.monotonic() - self._session_start if self._session_start else 0.0
        if self._session_game_id and elapsed >= 10:
            self.manager.add_playtime(self._session_game_id, int(elapsed))
        self._session_game_id = ""
        self._session_start = 0.0

        self._presence.clear()
        self._tray.set_tooltip("Accio Launcher")
        self._restore_from_tray()
        self._status_bar.showMessage(tr("Retour de {} — Bon jeu !").format(game_name))
        # Rafraîchir la ligne stats du jeu affiché (set_game même id = refresh sans transition)
        if self._detail.game is not None:
            self._detail.set_game(self._detail.game)

    # ──────────────────── Slots UI ────────────────────

    def _show_status(self, msg: str) -> None:
        self._status_bar.showMessage(msg)

    def _on_carousel_select(self, index: int) -> None:
        games = [entry.game for entry in self.manager.get_games()]
        if 0 <= index < len(games):
            self._detail.set_game(games[index])

    def _on_state_changed(self) -> None:
        self._carousel.refresh_indicators()

    def _on_config_changed(self) -> None:
        """Config modifiée (ex: dossier d'installation) — re-détecter les états.

        Sans re-détection, un jeu installé dans l'ancien dossier resterait
        affiché INSTALLED et « JOUER » échouerait silencieusement.
        """
        self.manager.refresh_states()
        self._detail.refresh_actions()
        self._carousel.refresh_indicators()

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.manager, self)
        dlg.config_changed.connect(self._on_config_changed)
        dlg.force_catalog_refresh.connect(lambda: self._force_update_check(dlg, catalog_only=True))
        dlg.force_launcher_check.connect(lambda: self._force_update_check(dlg, catalog_only=False))
        dlg.exec()

    def _force_update_check(self, dlg: SettingsDialog, *, catalog_only: bool) -> None:
        """Lance une vérification forcée (catalogue et/ou launcher).

        Protégé contre dlg détruit avant la fin du checker : chaque slot vérifie
        que le dialog est encore vivant via _dlg_alive.
        """
        catalog = self.manager.catalog
        checker = UpdateChecker(
            catalog_url=catalog.catalog_url,
            current_catalog_version="0",  # version "0" → force le fetch
            installed_versions=self.config.installed_versions,
            parent=self,
        )
        self._extra_checkers.append(checker)
        state = {"catalog_updated": False, "dlg_alive": True}

        def _dlg_alive() -> bool:
            if not state["dlg_alive"]:
                return False
            try:
                dlg.isVisible()
                return True
            except RuntimeError:
                state["dlg_alive"] = False
                return False

        dlg.destroyed.connect(lambda *_: state.update(dlg_alive=False))

        def on_catalog(new_catalog):
            state["catalog_updated"] = True
            self._on_catalog_updated(new_catalog)
            if _dlg_alive():
                dlg.update_catalog_version(new_catalog.catalog_version)

        def on_launcher(version, url, asset_url=""):
            self.config.dismissed_launcher_version = ""  # check forcé → toujours montrer
            self._on_launcher_update(version, url, asset_url)
            if _dlg_alive():
                dlg.show_update_status(tr("Launcher v{} disponible !").format(version))

        def on_finished():
            if _dlg_alive():
                if not state["catalog_updated"]:
                    dlg.show_update_status(tr("Catalogue déjà à jour"))
                elif not catalog_only and not self._launcher_update_url:
                    dlg.show_update_status(tr("Tout est à jour"))
            if checker in self._extra_checkers:
                self._extra_checkers.remove(checker)

        checker.catalog_updated.connect(on_catalog)
        checker.update_counts.connect(self._on_update_counts)
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
        self._toast.reposition()

    # ──────────────────── Redimensionnement fenêtre frameless ────────────────────

    def _edges_at(self, pos) -> Qt.Edge:
        """Bords de la fenêtre sous `pos` (coordonnées locales), zone de 6 px."""
        m = self.RESIZE_MARGIN
        edges = Qt.Edge(0)
        if pos.x() <= m:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - m:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= m:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _update_resize_cursor(self, edges: Qt.Edge) -> None:
        """Affiche/retire le curseur de redimensionnement (override global)."""
        from PyQt6.QtGui import QCursor, QGuiApplication
        E = Qt.Edge
        if (edges & E.LeftEdge and edges & E.TopEdge) or (edges & E.RightEdge and edges & E.BottomEdge):
            shape = Qt.CursorShape.SizeFDiagCursor
        elif (edges & E.RightEdge and edges & E.TopEdge) or (edges & E.LeftEdge and edges & E.BottomEdge):
            shape = Qt.CursorShape.SizeBDiagCursor
        elif edges & (E.LeftEdge | E.RightEdge):
            shape = Qt.CursorShape.SizeHorCursor
        elif edges & (E.TopEdge | E.BottomEdge):
            shape = Qt.CursorShape.SizeVerCursor
        else:
            if self._edge_cursor_active:
                QGuiApplication.restoreOverrideCursor()
                self._edge_cursor_active = False
            return
        if self._edge_cursor_active:
            QGuiApplication.changeOverrideCursor(QCursor(shape))
        else:
            QGuiApplication.setOverrideCursor(QCursor(shape))
            self._edge_cursor_active = True

    def eventFilter(self, obj, event) -> bool:
        # Couvre les MouseMove sur tous les widgets enfants (l'override mouseMoveEvent
        # ne firerait que sur la surface bare de MainWindow → redondant et incomplet).
        if event.type() == QEvent.Type.MouseMove:
            try:
                global_pos = event.globalPosition()
                local = self.mapFromGlobal(global_pos.toPoint())
                self._detail.handle_mouse_move(QPointF(local.x(), local.y()))
                # Curseur de resize sur les bords (fenêtre frameless)
                if not self.isMaximized() and self.isActiveWindow():
                    self._update_resize_cursor(self._edges_at(local))
            except (AttributeError, RuntimeError) as exc:
                log.debug("eventFilter mouseMove failed: %s", exc)
        elif event.type() == QEvent.Type.MouseButtonPress and not self.isMaximized():
            # Saisie d'un bord → resize natif (uniquement pour NOS widgets)
            try:
                from PyQt6.QtWidgets import QWidget
                if (event.button() == Qt.MouseButton.LeftButton
                        and isinstance(obj, QWidget) and obj.window() is self):
                    local = self.mapFromGlobal(event.globalPosition().toPoint())
                    edges = self._edges_at(local)
                    if edges and self.windowHandle() is not None:
                        self.windowHandle().startSystemResize(edges)
                        return True
            except (AttributeError, RuntimeError) as exc:
                log.debug("eventFilter resize failed: %s", exc)
        elif event.type() == QEvent.Type.Leave:
            # Souris sortie de la fenêtre → ne pas laisser un curseur de resize collé
            if self._edge_cursor_active and not self.underMouse():
                from PyQt6.QtGui import QGuiApplication
                QGuiApplication.restoreOverrideCursor()
                self._edge_cursor_active = False
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        """Attend la fin des threads avant de fermer."""
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().removeEventFilter(self)

        if self._update_checker is not None and self._update_checker.isRunning():
            self._update_checker.wait(3000)
        for checker in list(self._extra_checkers):
            if checker.isRunning():
                checker.wait(3000)
        self._extra_checkers.clear()
        if self._launcher_dl is not None:
            self._launcher_dl.cancel()
            self._launcher_dl.wait(3000)
            self._launcher_dl = None
        self._presence.shutdown()
        self._detail.cancel_operations()
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

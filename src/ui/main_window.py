import logging
import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QPointF, QTimer
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core.config import ASSETS_DIR, Config
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
from src.ui.season import resolve as resolve_season
from src.ui.settings_panel import SettingsDialog
from src.ui.styles import MAIN_STYLE
from src.ui.theme import set_theme, themed
from src.ui.ticker import Ticker
from src.ui.title_bar import TitleBar
from src.ui.toast import Toast
from src.ui.tray_manager import TrayManager
from src.ui.utils import open_url

log = logging.getLogger(__name__)

_ICON_PATH = ASSETS_DIR / "accio_launcher.ico"
# Repli hors Windows : le .ico est un format Windows, et le portage Linux est
# un objectif déclaré. Qt sait lire les deux, mais autant ne pas en dépendre.
_ICON_FALLBACK = ASSETS_DIR / "accio_launcher.png"

# Délai avant de re-tester le réseau quand plus rien ne répond. Assez court pour
# qu'un câble rebranché se voie tout de suite, assez long pour ne pas marteler
# l'API GitHub — et de toute façon sans coût quand on est réellement hors ligne
# (les requêtes échouent au premier DNS).
_OFFLINE_RETRY_MS = 45_000

# Checkers encore actifs à la fermeture : déparentés de la MainWindow et gardés
# vivants ici jusqu'à leur fin réelle. Sans ça, un QThread bloqué sur un read
# réseau était détruit avec sa fenêtre parente → « QThread: Destroyed while
# thread is still running » et abandon du process (le launcher « plante quand
# on le ferme »). Même contrat que GameOperations._zombies.
_orphaned_checkers: list[UpdateChecker] = []


def _reap_checker(checker: UpdateChecker) -> None:
    """Libère un checker orphelin une fois son thread réellement terminé."""
    if checker in _orphaned_checkers:
        _orphaned_checkers.remove(checker)
    checker.deleteLater()


def _load_app_icon() -> QIcon:
    """Icône de l'application — le .ico multi-résolution en priorité.

    Il embarque les tailles 16 à 256 dessinées pour chacune : la barre des
    tâches et la fenêtre y piochent la bonne au lieu de réduire un seul PNG,
    ce qui rend les petites tailles nettement plus nettes. Repli sur le PNG si
    le .ico manque (ou hors Windows).
    """
    if _ICON_PATH.exists():
        return QIcon(str(_ICON_PATH))
    return QIcon(str(_ICON_FALLBACK))


class MainWindow(QMainWindow):
    """Fenêtre principale d'Accio Launcher — style launcher AAA."""

    RESIZE_MARGIN = 6  # zone de saisie des bords pour redimensionner (px)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Accio Launcher")
        self.setMinimumSize(980, 660)
        self._apply_default_geometry()
        self.setWindowIcon(_load_app_icon())

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.setMouseTracking(True)
        self._edge_cursor_active = False  # override-cursor de resize posé ?

        load_fonts()

        self.config = self._first_launch_or_load()
        # Langue et thème doivent être actifs AVANT la construction des widgets
        # (chaînes tr() et couleurs posées à la construction ; changement = redémarrage).
        from src.core.i18n import set_language
        set_language(self.config.langue)
        set_theme(self.config.theme)
        self.setStyleSheet(themed(MAIN_STYLE))
        self.manager = GameManager(self.config)

        self._update_checker: UpdateChecker | None = None
        self._extra_checkers: list[UpdateChecker] = []
        self._launcher_update_version: str = ""
        self._launcher_update_url: str = ""
        self._launcher_update_asset: str = ""
        self._launcher_update_sha256: str = ""
        self._launcher_dl: Downloader | None = None  # téléchargement auto-update en cours
        self._taskbar: TaskbarProgress | None = None  # créé paresseusement (winId après show)
        self._presence = DiscordPresence()  # no-op tant que DISCORD_CLIENT_ID est vide
        # Session de jeu en cours (stats de temps de jeu)
        self._session_game_id: str = ""
        self._session_start: float = 0.0
        # État réseau — optimiste au départ : on n'affiche « hors ligne » que
        # sur une preuve, jamais par défaut (cf. UpdateChecker.is_online).
        self._online = True
        self._offline_retry = QTimer(self)
        self._offline_retry.setSingleShot(True)
        self._offline_retry.timeout.connect(self._start_update_check)

        self._build_ui()
        self._build_tray()
        self._build_process_monitor()
        self._start_update_check()

    @staticmethod
    def _first_launch_or_load() -> Config:
        if Config.exists():
            return Config.load()
        # Premier lancement : assistant 3 écrans (dossier, import en masse,
        # langue/thème — appliqués dès la suite de la construction).
        from src.ui.onboarding import run_onboarding
        return run_onboarding()

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

        # Overlay particules (+ saison décorative, changeable en direct dans Paramètres)
        self._particles = ParticleOverlay(self)
        self._particles.apply_season(resolve_season(self.config.season))
        self._particles.raise_()

        # Toast (notifications éphémères)
        self._toast = Toast(self)
        self._detail.ops.operation_finished.connect(self._notify_operation_finished)
        # Ce qui informait par dialogue modal passe par le toast : rien à
        # décider, donc rien qui justifie d'arrêter l'utilisateur.
        self._detail.notify.connect(self._toast.show_message)
        self._detail.settings_requested.connect(self._on_settings)

        # Settings button
        self._btn_settings = QPushButton("⚙", self)
        self._btn_settings.setFixedSize(36, 36)
        self._btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_settings.setStyleSheet(themed(
            "QPushButton { background: rgba(0,0,0,0.4); color: #8a8aaa; border: none;"
            " border-radius: 18px; font-size: 18px; }"
            "QPushButton:hover { color: #d4a017; background: rgba(0,0,0,0.6); }"
        ))
        self._btn_settings.clicked.connect(self._on_settings)
        self._btn_settings.raise_()

        # Event filter on QApplication for global mouse tracking
        QApplication.instance().installEventFilter(self)

        if games:
            # Hero dynamique : ouvrir sur le dernier jeu joué plutôt que toujours HP1.
            last_id = self.manager.last_played_game_id()
            idx = next((i for i, g in enumerate(games) if g.id == last_id), 0)
            if idx > 0:
                self._carousel.select(idx)  # émet game_selected → set_game
            else:
                self._detail.set_game(games[0])

        # Notification VISIBLE des mises à jour de jeux (recompte local, différé
        # après le fade-in). La status bar seule passait inaperçue — retour Ludo.
        QTimer.singleShot(2500, self._notify_game_updates)

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
        ops.phase_changed.connect(self._download_bar.set_phase)
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
        bar.setStyleSheet(themed(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 rgba(212,160,23,0.15), stop:0.5 rgba(212,160,23,0.25),"
            "stop:1 rgba(212,160,23,0.15)); }"
        ))
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(10)

        self._notif_label = QLabel()
        self._notif_label.setStyleSheet(themed("color: #d4a017; font-size: 12px; background: transparent;"))
        layout.addWidget(self._notif_label, stretch=1)

        self._notif_btn = QPushButton(tr("Télécharger"))
        self._notif_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notif_btn.setStyleSheet(themed(
            "QPushButton { background: rgba(212,160,23,0.2); color: #d4a017;"
            " border: 1px solid rgba(212,160,23,0.4); border-radius: 4px;"
            " padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(212,160,23,0.35); color: #e8c547; }"
        ))
        self._notif_btn.clicked.connect(self._on_notif_download)
        layout.addWidget(self._notif_btn)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(themed(
            "QPushButton { background: transparent; color: #d4a017; border: none; font-size: 14px; }"
            "QPushButton:hover { color: #e8c547; }"
        ))
        btn_close.clicked.connect(self._dismiss_notif)
        layout.addWidget(btn_close)

        return bar

    # ──────────────────── Update checker ────────────────────

    def _games_asset_urls(self) -> dict[str, list[list[str]]]:
        """Snapshot game_id → versions → URLs d'assets (compteur ⬇, thread-safe)."""
        return {
            entry.game.id: [
                [v.download_url or ""] + list(v.download_parts or [])
                for v in entry.game.versions
            ]
            for entry in self.manager.get_games()
        }

    def _apply_default_geometry(self) -> None:
        """Taille d'ouverture proportionnée à l'écran, fenêtre centrée.

        L'ancienne valeur fixe (1200x800) ne tenait pas sur un portable
        1366x768, où il ne reste que ~728 px une fois la barre des tâches
        déduite : la fenêtre débordait par le bas. À l'inverse elle paraissait
        étriquée sur un grand écran. On prend donc une fraction de la zone
        disponible, bornée des deux côtés.
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:  # sans écran (tests offscreen) : valeur historique
            self.resize(1200, 800)
            return
        avail = screen.availableGeometry()
        # 62 % et non 72 % : le catalogue tient en huit jaquettes, soit ~900 px.
        # Plus large, le carrousel flotte au milieu de deux grandes marges vides
        # et le panneau d'info laisse une moitié droite déserte.
        width = max(980, min(1320, int(avail.width() * 0.62)))
        height = max(660, min(880, int(avail.height() * 0.76)))
        # Jamais plus grand que l'écran, même si les bornes basses l'imposaient.
        width = min(width, avail.width())
        height = min(height, avail.height())
        self.resize(width, height)
        self.move(avail.x() + (avail.width() - width) // 2,
                  avail.y() + (avail.height() - height) // 2)

    def _start_update_check(self) -> None:
        """Lance la vérification des mises à jour en arrière-plan.

        Toujours lancée : sans réseau, ou si GitHub répond mal, chaque étape
        échoue proprement et le launcher garde ce qu'il a déjà — le catalogue
        embarqué ou le dernier téléchargé (`load_catalog` prend le plus récent
        des deux). Il n'y a donc rien à gagner à ne pas essayer, et un réglage
        « ne pas vérifier » ne faisait que priver l'utilisateur des empreintes
        SHA-256 qui vérifient ses téléchargements.
        """
        if self._update_checker is not None:
            # Même traitement qu'à la fermeture : jamais de thread remplacé
            # pendant qu'il tourne encore (il resterait enfant de la fenêtre
            # et mourrait avec elle).
            self._shutdown_checker(self._update_checker)
        catalog = self.manager.catalog
        self._update_checker = UpdateChecker(
            catalog_url=catalog.catalog_url,
            current_catalog_version=catalog.catalog_version,
            installed_versions=self.config.installed_versions,
            games_asset_urls=self._games_asset_urls(),
            parent=self,
        )
        self._update_checker.catalog_updated.connect(self._on_catalog_updated)
        self._update_checker.launcher_update.connect(self._on_launcher_update)
        self._update_checker.update_counts.connect(self._on_update_counts)
        self._update_checker.download_counts.connect(self._on_download_counts)
        self._update_checker.asset_digests.connect(self._on_asset_digests)
        self._update_checker.network_status.connect(self._on_network_status)
        self._update_checker.start()

    def _on_network_status(self, online: bool) -> None:
        """Aucun serveur joignable → le dire, et re-tester tout seul.

        Sans re-tentative, rebrancher son câble laisserait « Télécharger »
        grisé jusqu'au prochain démarrage : l'utilisateur croirait le launcher
        en panne. Le timer est ré-armé à CHAQUE échec, pas seulement à la
        transition, sinon un seul essai serait fait.
        """
        if online:
            self._offline_retry.stop()
        else:
            self._offline_retry.start(_OFFLINE_RETRY_MS)
        if online == self._online:
            return
        self._online = online
        self._detail.set_online(online)
        log.info("État réseau : %s", "en ligne" if online else "hors ligne")
        # Recompte local plutôt que `_notify_game_updates` : on veut remettre le
        # bon message ambiant, pas re-jouer un toast déjà vu.
        pending = sum(1 for entry in self.manager.get_games()
                      if self.manager.has_update(entry.game.id))
        self._on_update_counts(pending)

    def _on_asset_digests(self, digests: dict) -> None:
        """Empreintes SHA-256 publiées par GitHub, pour vérifier les archives.

        Reçues dans la même réponse que les compteurs ⬇ : aucune requête
        supplémentaire. Voir `GameManager.expected_hashes`.
        """
        self.manager.set_asset_digests(digests)

    def _on_download_counts(self, counts: dict) -> None:
        """Compteurs ⬇ reçus — rafraîchir la fiche affichée (même id = pas de transition)."""
        self.manager.set_download_counts(counts)
        if self._detail.game is not None:
            self._detail.set_game(self._detail.game)

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
        # Le toast « mise à jour de jeu dispo » (actionnable) prime sur le toast
        # « catalogue mis à jour » (informatif) — un seul Toast à la fois.
        if not self._notify_game_updates():
            self._toast.show_message(tr("Catalogue mis à jour (v{})").format(catalog.catalog_version))
        log.info("UI rafraîchie après mise à jour du catalogue")

    def _on_launcher_update(self, version: str, url: str, asset_url: str = "",
                            asset_sha256: str = "") -> None:
        """Nouvelle version du launcher disponible."""
        if self.config.dismissed_launcher_version == version:
            return
        self._launcher_update_version = version
        self._launcher_update_url = url
        self._launcher_update_asset = asset_url
        self._launcher_update_sha256 = asset_sha256
        self._notif_label.setText(tr("Accio Launcher v{} est disponible !").format(version))
        self._notif_btn.setText(tr("Mettre à jour") if asset_url and can_self_update() else tr("Télécharger"))
        self._notif_bar.show()
        QTimer.singleShot(30_000, self._auto_hide_notif)

    def _on_update_counts(self, count: int) -> None:
        """Message ambiant de la status bar : mises à jour, hors ligne, ou « Prêt »."""
        if self._detail.ops.is_busy:
            return  # ne pas écraser le statut d'un téléchargement en cours
        if count > 0:
            self._status_bar.showMessage(tr("{} mise(s) à jour disponible(s)").format(count))
        elif not self._online:
            # Dire ce qui change vraiment pour l'utilisateur : sa bibliothèque
            # reste jouable, seuls les nouveaux téléchargements attendent.
            self._status_bar.showMessage(tr("Hors ligne — les jeux installés restent jouables."))
        else:
            self._status_bar.showMessage(tr("Prêt"))

    def _notify_game_updates(self) -> bool:
        """Toast cliquable si des jeux installés ont une mise à jour. Recompte LOCAL :
        contrairement au signal `update_counts` du checker (qui ne compte que si le
        catalogue DISTANT est plus récent), ceci couvre aussi un catalogue embarqué
        déjà à jour livré par une mise à jour du launcher. Retourne True si toast."""
        games = [entry.game for entry in self.manager.get_games()]
        pending = [(i, g) for i, g in enumerate(games) if self.manager.has_update(g.id)]
        self._on_update_counts(len(pending))
        if not pending:
            return False
        first_idx = pending[0][0]
        if len(pending) == 1:
            msg = tr("Mise à jour disponible pour {}").format(pending[0][1].name)
        else:
            msg = tr("{} jeux ont une mise à jour disponible").format(len(pending))
        # Clic → sélectionner le premier jeu concerné (son lien « Mettre à jour »
        # et le marqueur carrousel deviennent visibles immédiatement).
        self._toast.show_message(msg, duration_ms=6000,
                                 on_click=lambda: self._carousel.select(first_idx))
        return True

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
        # L'empreinte vient de l'API GitHub (cf. UpdateChecker._check_launcher).
        # Vide → téléchargement non vérifié, comme avant : on ne bloque pas une
        # mise à jour parce que GitHub n'a pas publié de digest.
        self._launcher_dl = Downloader(
            url=self._launcher_update_asset, destination=dest,
            expected_sha256=self._launcher_update_sha256 or None,
            parent=self,
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
                # Retour d'une installation de prérequis lancée depuis le
                # bandeau d'avertissement (no-op le reste du temps).
                self._detail.recheck_prerequisites()
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
        self._maybe_thank_milestone()

    def _maybe_thank_milestone(self) -> None:
        """Un seul remerciement Ko-fi dans la vie du launcher, au cap des 10 h de jeu.

        Moment de joie (retour de jeu), jamais de répétition, jamais de
        culpabilisation — voir la stratégie « pas de nag » du projet.
        """
        if self.config.kofi_milestone_thanked:
            return
        if sum(self.config.playtime_seconds.values()) < 10 * 3600:
            return
        self.config.kofi_milestone_thanked = True
        self.config.save()
        self._toast.show_message(
            tr("Déjà 10 h de magie retrouvée. Si le launcher te plaît, un café fait plaisir — clique ici."),
            duration_ms=9000,
            on_click=lambda: open_url("https://ko-fi.com/ludovic01"),
        )

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
        self._detail.apply_audio_config()  # mute/unmute la vidéo en cours (live)
        self._carousel.refresh_indicators()

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.manager, self)
        dlg.config_changed.connect(self._on_config_changed)
        dlg.force_catalog_refresh.connect(lambda: self._force_update_check(dlg, catalog_only=True))
        dlg.force_launcher_check.connect(lambda: self._force_update_check(dlg, catalog_only=False))
        dlg.season_changed.connect(self._particles.apply_season)
        dlg.restart_requested.connect(lambda: self._restart_launcher(dlg))
        dlg.exec()

    def _restart_launcher(self, dlg: SettingsDialog | None = None) -> None:
        """« Redémarrer maintenant » (thème/langue) : relance programmée puis fermeture propre."""
        from src.core.self_update import relaunch_after_exit
        if relaunch_after_exit():
            if dlg is not None:
                dlg.accept()
            self.close()
        else:
            self._show_status(tr("Relance automatique impossible — redémarrez manuellement."))

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
            # Sans ça, un utilisateur ayant désactivé la vérif au démarrage
            # n'obtiendrait jamais les compteurs ⬇ même en forçant la vérif.
            games_asset_urls=self._games_asset_urls(),
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
        checker.download_counts.connect(self._on_download_counts)
        checker.network_status.connect(self._on_network_status)
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
        # Fenêtre basse : le carrousel se compacte pour rendre sa hauteur à la
        # fiche de jeu, qui devait sinon défiler.
        self._carousel.set_compact(self.height() < 780)

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
        elif event.type() == QEvent.Type.KeyPress:
            if self._handle_global_key(event):
                return True
        return super().eventFilter(obj, event)

    def _handle_global_key(self, event) -> bool:
        """←/→ naviguent le carrousel même quand un bouton a le focus (A11Y).

        Sans ce filtre, le premier clic sur un bouton lui donnait le focus et
        les flèches devenaient muettes (Qt les consomme pour déplacer le focus).
        Jamais actif quand un dialog modal est ouvert ni quand le focus est sur
        un widget d'édition (slider de volume, combo, champ texte).
        """
        if event.key() not in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            return False
        from PyQt6.QtWidgets import (
            QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QSlider,
        )
        if QApplication.activeModalWidget() is not None or not self.isActiveWindow():
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QComboBox, QSlider, QAbstractSpinBox)):
            return False
        if event.key() == Qt.Key.Key_Left:
            self._carousel.select_prev()
        else:
            self._carousel.select_next()
        return True

    @staticmethod
    def _shutdown_checker(checker: UpdateChecker) -> None:
        """Arrête un UpdateChecker sans jamais le détruire pendant qu'il tourne.

        Demande l'interruption (honorée entre les étapes réseau de `run()`),
        attend, et si le thread est encore bloqué sur une requête en vol, le
        déparente pour qu'il survive à la destruction de la fenêtre — son
        `finished` natif s'occupe du nettoyage.
        """
        if not checker.isRunning():
            return
        checker.requestInterruption()
        if checker.wait(3000):
            return
        log.warning("UpdateChecker encore actif à la fermeture — nettoyage différé")
        checker.setParent(None)
        _orphaned_checkers.append(checker)
        checker.finished.connect(lambda: _reap_checker(checker))

    def closeEvent(self, event) -> None:
        """Attend la fin des threads avant de fermer."""
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().removeEventFilter(self)

        # Avant tout : sinon le timer hors-ligne ressuscite un checker pendant
        # qu'on attend justement la fin des threads.
        self._offline_retry.stop()
        if self._update_checker is not None:
            self._shutdown_checker(self._update_checker)
        for checker in list(self._extra_checkers):
            self._shutdown_checker(checker)
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

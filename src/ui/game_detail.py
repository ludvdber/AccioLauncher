"""Vue détaillée d'un jeu — zone centrale avec fond, infos et actions."""

import logging
import shutil
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QUrl, pyqtSignal, QPointF,
)
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.background_widget import BackgroundWidget
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel, cinzel_decorative, body_font
from src.ui.glow_button import GlowButton
from src.ui.speed_tracker import SpeedTracker, format_size, format_bytes, format_speed, format_eta

from src.core.downloader import Downloader
from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.core.installer import Installer

log = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"

# Nombre de caractères affichés avant troncature
_DESC_TRUNCATE = 160


class GameDetailView(QWidget):
    """Zone centrale : fond + voile gauche + infos + boutons d'action."""

    status_message = pyqtSignal(str)
    state_changed = pyqtSignal()

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.game: GameData | None = None
        self._downloader: Downloader | None = None
        self._installer: Installer | None = None
        self._speed_tracker = SpeedTracker()

        self._video_player = None
        self._video_widget = None
        self._video_muted = True

        self._desc_expanded = False
        self._full_desc = ""

        self._build_ui()

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ──────────────────── Construction UI ────────────────────

    def _build_ui(self) -> None:
        self._bg = BackgroundWidget(self)

        # ── Info labels over the left veil gradient ──
        self._info_container = QWidget(self)
        self._info_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._info_container.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(self._info_container)
        info_layout.setContentsMargins(50, 0, 30, 0)
        info_layout.setSpacing(0)

        # Title
        self._title = QLabel()
        self._title.setObjectName("gameTitle")
        self._title.setFont(cinzel_decorative(36))
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(600)
        self._title.setStyleSheet("QLabel { color: #eaeaea; background: transparent; }")
        info_layout.addWidget(self._title)

        info_layout.addSpacing(8)

        # Metadata
        self._meta = QLabel()
        self._meta.setObjectName("gameMeta")
        self._meta.setFont(cinzel(14))
        self._meta.setTextFormat(Qt.TextFormat.RichText)
        self._meta.setStyleSheet("QLabel { color: #8a8aaa; background: transparent; }")
        info_layout.addWidget(self._meta)

        info_layout.addSpacing(14)

        # Gold separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setFixedWidth(60)
        sep.setStyleSheet("background: rgba(212, 160, 23, 0.30);")
        info_layout.addWidget(sep)

        info_layout.addSpacing(14)

        # Description
        self._desc = QLabel()
        self._desc.setObjectName("gameDescription")
        self._desc.setFont(body_font(15))
        self._desc.setWordWrap(True)
        self._desc.setMaximumWidth(520)
        self._desc.setStyleSheet(
            "QLabel { color: rgba(176, 176, 200, 0.75); background: transparent;"
            " line-height: 1.5; }"
        )
        info_layout.addWidget(self._desc)

        # "Lire la suite..." / "Réduire" toggle
        self._btn_expand = QLabel()
        self._btn_expand.setFont(body_font(13))
        self._btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_expand.setStyleSheet(
            "QLabel { color: #d4a017; background: transparent; padding-top: 4px; }"
            "QLabel:hover { color: #e8c547; }"
        )
        self._btn_expand.setVisible(False)
        self._btn_expand.mousePressEvent = lambda _: self._toggle_desc()
        info_layout.addWidget(self._btn_expand)

        info_layout.addSpacing(10)

        # Tags
        self._tags_container = QWidget()
        self._tags_container.setStyleSheet("background: transparent;")
        self._tags_container.setMaximumHeight(80)
        self._tags_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._tags_layout = FlowLayout(self._tags_container, spacing=8)
        info_layout.addWidget(self._tags_container)

        info_layout.addSpacing(20)

        # Action buttons
        self._action_container = QWidget()
        self._action_container.setStyleSheet("background: transparent;")
        self._action_container.setMaximumHeight(60)
        self._action_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._action_layout = QHBoxLayout(self._action_container)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(14)
        self._action_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._action_container)

        info_layout.addStretch()

        self._btn_mute = QPushButton("\U0001f507", self)
        self._btn_mute.setObjectName("btnMute")
        self._btn_mute.setFixedSize(28, 28)
        self._btn_mute.clicked.connect(self._toggle_mute)
        self._btn_mute.hide()

        # Fade — background
        self._fade_anim = QPropertyAnimation(self._bg, b"bg_opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Fade — info text
        self._info_opacity = QGraphicsOpacityEffect(self._info_container)
        self._info_opacity.setOpacity(1.0)
        self._info_container.setGraphicsEffect(self._info_opacity)
        self._info_fade = QPropertyAnimation(self._info_opacity, b"opacity")
        self._info_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ──────────────────── Description expand/collapse ────────────────────

    def _set_desc_text(self, text: str) -> None:
        """Store full text and show truncated or full based on state."""
        self._full_desc = text
        self._desc_expanded = False
        if len(text) > _DESC_TRUNCATE:
            self._desc.setText(text[:_DESC_TRUNCATE].rstrip() + "…")
            self._btn_expand.setText("Lire la suite…")
            self._btn_expand.setVisible(True)
        else:
            self._desc.setText(text)
            self._btn_expand.setVisible(False)

    def _toggle_desc(self) -> None:
        self._desc_expanded = not self._desc_expanded
        if self._desc_expanded:
            self._desc.setText(self._full_desc)
            self._btn_expand.setText("Réduire")
        else:
            self._desc.setText(self._full_desc[:_DESC_TRUNCATE].rstrip() + "…")
            self._btn_expand.setText("Lire la suite…")

    # ──────────────────── Positionnement ────────────────────

    def _position_info(self) -> None:
        w, h = self.width(), self.height()
        info_w = min(650, int(w * 0.50))
        info_top = int(h * 0.22)
        info_h = h - info_top - 20
        self._info_container.setGeometry(0, info_top, info_w, info_h)

    def resizeEvent(self, event) -> None:
        self._bg.setGeometry(self.rect())
        self._bg._prepared = None
        self._position_info()
        if self._video_widget:
            self._video_widget.setGeometry(self.rect())
        self._btn_mute.move(self.width() - 40, 12)

    # ──────────────────── Changement de jeu ────────────────────

    def set_game(self, game: GameData) -> None:
        if self.game and self.game.id == game.id:
            self._refresh_action()
            return

        self._stop_video()

        # Fade out info
        self._info_fade.stop()
        self._info_opacity.setOpacity(0.0)

        # Fade out background
        self._fade_anim.stop()
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        try:
            self._fade_anim.finished.disconnect()
        except TypeError:
            pass
        self._fade_anim.finished.connect(lambda g=game: self._apply_game(g))
        self._fade_anim.start()

    def _apply_game(self, game: GameData) -> None:
        try:
            self._fade_anim.finished.disconnect()
        except TypeError:
            pass

        self.game = game
        self._title.setText(game.name)

        # Metadata
        gold = "#d4a017"
        sep = f'<span style="color:{gold}; margin: 0 6px;"> \u25c6 </span>'
        self._meta.setText(
            f'<span style="text-transform:uppercase; letter-spacing:2px;">'
            f'{game.year}{sep}{game.developer}{sep}{format_size(game.archive_size_mb)}'
            f'</span>'
        )

        # Description (truncated + expand)
        self._set_desc_text(game.description)

        # Tags
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            if (w := item.widget()) is not None:
                w.deleteLater()
        for tag in game.tags:
            badge = QLabel(tag.upper())
            badge.setFont(cinzel(10, bold=True))
            badge.setStyleSheet(
                "QLabel {"
                "  background: rgba(212, 160, 23, 0.05);"
                "  color: #d4a017;"
                "  border: 1px solid rgba(212, 160, 23, 0.3);"
                "  border-radius: 12px;"
                "  padding: 4px 14px;"
                "  letter-spacing: 2px;"
                "}"
            )
            self._tags_layout.addWidget(badge)
        self._tags_container.updateGeometry()

        # Background
        bg_path = ASSETS_DIR / "backgrounds" / f"{game.id}_bg.jpg"
        self._bg.set_image(bg_path)

        if self.manager.config.autoplay_videos:
            self._try_play_video(game.id)

        self._refresh_action()

        # Fade-in background (400ms) + zoom loop
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setDuration(400)
        self._fade_anim.start()
        self._bg.start_zoom_loop()

        # Fade-in info (500ms)
        self._info_container.show()
        self._position_info()
        self._info_fade.stop()
        self._info_fade.setStartValue(0.0)
        self._info_fade.setEndValue(1.0)
        self._info_fade.setDuration(500)
        self._info_fade.start()

    # ──────────────────── Parallaxe ────────────────────

    def handle_mouse_move(self, pos: QPointF) -> None:
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return
        self._bg.set_parallax_target(pos.x(), pos.y(), float(w), float(h))

    # ──────────────────── Vidéo ────────────────────

    def _try_play_video(self, game_id: str) -> None:
        video_path = ASSETS_DIR / "videos" / f"{game_id}_video.mp4"
        if not video_path.exists():
            self._btn_mute.hide()
            return
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PyQt6.QtMultimediaWidgets import QVideoWidget

            if self._video_widget is None:
                self._video_widget = QVideoWidget(self)
                self._video_widget.setGeometry(self.rect())
                self._video_widget.stackUnder(self._bg)
                self._audio_output = QAudioOutput()
                self._audio_output.setVolume(0.0)
                self._video_player = QMediaPlayer()
                self._video_player.setVideoOutput(self._video_widget)
                self._video_player.setAudioOutput(self._audio_output)
                self._video_player.mediaStatusChanged.connect(self._on_media_status)

            self._video_widget.setGeometry(self.rect())
            self._video_widget.show()
            self._video_player.setSource(QUrl.fromLocalFile(str(video_path)))
            self._video_player.play()
            self._video_muted = self.manager.config.mute_videos
            self._audio_output.setVolume(0.0 if self._video_muted else 0.5)
            self._btn_mute.setText("\U0001f507" if self._video_muted else "\U0001f50a")
            self._btn_mute.show()
            self._btn_mute.raise_()
        except ImportError:
            log.debug("PyQt6-Multimedia non disponible")

    def _on_media_status(self, status) -> None:
        try:
            from PyQt6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                self._video_player.setPosition(0)
                self._video_player.play()
        except ImportError:
            pass

    def _stop_video(self) -> None:
        if self._video_player:
            self._video_player.stop()
        if self._video_widget:
            self._video_widget.hide()
        self._btn_mute.hide()

    def _toggle_mute(self) -> None:
        if not hasattr(self, "_audio_output"):
            return
        self._video_muted = not self._video_muted
        self._audio_output.setVolume(0.0 if self._video_muted else 0.5)
        self._btn_mute.setText("\U0001f507" if self._video_muted else "\U0001f50a")

    # ──────────────────── Actions ────────────────────

    def _current_state(self) -> GameState:
        if self.game is None:
            return GameState.NOT_INSTALLED
        for entry in self.manager.get_games():
            if entry["game"].id == self.game.id:
                return entry["state"]
        return GameState.NOT_INSTALLED

    def _refresh_action(self) -> None:
        while self._action_layout.count():
            item = self._action_layout.takeAt(0)
            if (w := item.widget()) is not None:
                w.deleteLater()
        self._action_layout.setDirection(QHBoxLayout.Direction.LeftToRight)

        if self.game is None:
            return

        match self._current_state():
            case GameState.NOT_INSTALLED:
                self._build_not_installed()
            case GameState.DOWNLOADING:
                self._build_downloading()
            case GameState.INSTALLING:
                self._build_installing()
            case GameState.INSTALLED:
                self._build_installed()

    def _build_not_installed(self) -> None:
        size = format_size(self.game.archive_size_mb)
        btn = GlowButton(
            f"T\u00c9L\u00c9CHARGER  \u2014  {size}",
            glow_color="#d4a017",
            style="outline",
        )
        btn.setObjectName("btnDownload")
        btn.setFont(cinzel(13, bold=True))
        btn.setFixedSize(300, 46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_download)
        self._action_layout.addWidget(btn)

    def _build_downloading(self) -> None:
        self._action_layout.setDirection(QHBoxLayout.Direction.TopToBottom)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(400)
        self._action_layout.addWidget(self._progress_bar)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        self._download_label = QLabel("T\u00e9l\u00e9chargement : 0%")
        self._download_label.setObjectName("downloadLabel")
        self._download_label.setMinimumWidth(500)
        row_layout.addWidget(self._download_label)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self._on_cancel_download)
        row_layout.addWidget(btn_cancel)

        self._action_layout.addWidget(row)

    def _build_installing(self) -> None:
        self._action_layout.setDirection(QHBoxLayout.Direction.TopToBottom)
        self._install_bar = QProgressBar()
        self._install_bar.setRange(0, 100)
        self._install_bar.setValue(0)
        self._install_bar.setFormat("Installation\u2026 %p%")
        self._install_bar.setFixedWidth(400)
        self._action_layout.addWidget(self._install_bar)

    def _build_installed(self) -> None:
        btn_play = GlowButton(
            "JOUER",
            glow_color="#2ecc71",
            style="filled",
            bg_stops=("#2ecc71", "#27ae60", "#1a9c54"),
            text_color="#ffffff",
        )
        btn_play.setObjectName("btnPlay")
        btn_play.setFont(cinzel(15, bold=True))
        btn_play.setFixedSize(200, 48)
        btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_play.clicked.connect(self._on_play)
        self._action_layout.addWidget(btn_play)

        btn_uninstall = GlowButton(
            "D\u00c9SINSTALLER",
            glow_color="#8a8aaa",
            style="outline",
            text_color="#8a8aaa",
        )
        btn_uninstall.setObjectName("btnUninstall")
        btn_uninstall.setFont(cinzel(10, bold=True))
        btn_uninstall.setFixedSize(160, 36)
        btn_uninstall.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_uninstall.clicked.connect(self._on_uninstall)
        self._action_layout.addWidget(btn_uninstall)

    # ──────────────────── Téléchargement ────────────────────

    def _check_disk_space(self) -> bool:
        needed_mb = self.game.archive_size_mb * 2
        try:
            usage = shutil.disk_usage(self.manager.config.install_path)
            free_mb = usage.free // (1024 * 1024)
        except OSError:
            return True

        if free_mb < needed_mb:
            QMessageBox.warning(
                self,
                "Espace disque insuffisant",
                f"Espace disque insuffisant.\n"
                f"Il faut environ {format_size(needed_mb)} d'espace libre.\n"
                f"Actuellement {format_size(int(free_mb))} disponibles sur le lecteur.",
            )
            return False
        return True

    def _on_download(self) -> None:
        if not self._check_disk_space():
            return

        self.manager.set_game_state(self.game.id, GameState.DOWNLOADING)
        self._refresh_action()
        self._speed_tracker.reset()
        self.status_message.emit(f"T\u00e9l\u00e9chargement de {self.game.name}\u2026")

        dest = self.manager.config.cache_path / self.game.archive_name
        self._downloader = Downloader(self.game.download_url, dest, parent=self)
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)
        self._downloader.start()

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            return
        self._speed_tracker.update(downloaded)
        if not self._speed_tracker.should_update_ui():
            return

        pct = downloaded * 100 // total
        dl_str = format_bytes(downloaded)
        total_str = format_bytes(total)
        speed_str = format_speed(self._speed_tracker.speed)
        eta = self._speed_tracker.eta(downloaded, total)
        eta_str = format_eta(eta)

        parts = [f"T\u00e9l\u00e9chargement : {pct}%", f"{dl_str} / {total_str}", speed_str]
        if eta_str:
            parts.append(eta_str)

        if hasattr(self, "_progress_bar"):
            self._progress_bar.setValue(pct)
        if hasattr(self, "_download_label"):
            self._download_label.setText(" \u2014 ".join(parts))

    def _on_download_finished(self, archive_path_str: str) -> None:
        self._downloader = None
        self.status_message.emit(f"Installation de {self.game.name}\u2026")
        self._start_install(Path(archive_path_str), delete_archive=self.manager.config.delete_archives)

    def _on_download_error(self, message: str) -> None:
        self._downloader = None
        self.manager.set_game_state(self.game.id, GameState.NOT_INSTALLED)
        self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit(f"Erreur : {message}")
        QMessageBox.warning(
            self, "\u00c9chec du t\u00e9l\u00e9chargement",
            "Le t\u00e9l\u00e9chargement a \u00e9chou\u00e9.\nV\u00e9rifiez votre connexion internet et r\u00e9essayez.",
        )

    def _on_cancel_download(self) -> None:
        if self._downloader is not None:
            self._downloader.cancel()
            self._downloader = None
        self.manager.set_game_state(self.game.id, GameState.NOT_INSTALLED)
        self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit("T\u00e9l\u00e9chargement annul\u00e9.")

    # ──────────────────── Installation ────────────────────

    def _start_install(self, archive_path: Path, *, delete_archive: bool = True) -> None:
        self.manager.set_game_state(self.game.id, GameState.INSTALLING)
        self._refresh_action()

        dest = self.manager.config.install_path
        self._installer = Installer(
            archive_path, dest,
            registry_entries=list(self.game.post_install.registry),
            delete_archive=delete_archive, parent=self,
        )
        self._installer.progress.connect(self._on_install_progress)
        self._installer.finished.connect(self._on_install_finished)
        self._installer.error.connect(self._on_install_error)
        self._installer.start()

    def _on_install_progress(self, pct: int) -> None:
        if hasattr(self, "_install_bar"):
            self._install_bar.setValue(pct)

    def _on_install_finished(self, _path: str) -> None:
        self._installer = None
        exe_path = self.manager.config.install_path / self.game.executable
        if not exe_path.exists():
            log.warning("Ex\u00e9cutable introuvable apr\u00e8s extraction : %s", exe_path)
            self.manager.set_game_state(self.game.id, GameState.NOT_INSTALLED)
            self._refresh_action()
            self.state_changed.emit()
            self.status_message.emit("Installation incompl\u00e8te.")
            QMessageBox.warning(
                self, "Installation incompl\u00e8te",
                "L'installation semble incompl\u00e8te : l'ex\u00e9cutable du jeu est introuvable.\n"
                "L'archive est peut-\u00eatre corrompue.",
            )
            return
        self.manager.set_game_state(self.game.id, GameState.INSTALLED)
        self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit(f"{self.game.name} install\u00e9 avec succ\u00e8s !")

    def _on_install_error(self, message: str) -> None:
        self._installer = None
        self.manager.set_game_state(self.game.id, GameState.NOT_INSTALLED)
        self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit(f"Erreur d'installation : {message}")
        QMessageBox.warning(
            self, "\u00c9chec de l'installation",
            "L'installation a \u00e9chou\u00e9.\nL'archive est peut-\u00eatre corrompue. R\u00e9essayez le t\u00e9l\u00e9chargement.",
        )

    # ──────────────────── Jouer / Désinstaller ────────────────────

    def _on_play(self) -> None:
        if self.manager.launch_game(self.game.id):
            self.status_message.emit(f"Lancement de {self.game.name}\u2026")
        else:
            self.status_message.emit("Impossible de lancer le jeu.")

    def _on_uninstall(self) -> None:
        reply = QMessageBox.question(
            self, "Confirmer la d\u00e9sinstallation",
            f"Voulez-vous vraiment d\u00e9sinstaller {self.game.name} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.uninstall_game(self.game.id)
            self._refresh_action()
            self.state_changed.emit()
            self.status_message.emit(f"{self.game.name} d\u00e9sinstall\u00e9.")

    # ──────────────────── Menu contextuel ────────────────────

    def _show_context_menu(self, pos) -> None:
        if self.game is None or self._current_state() != GameState.NOT_INSTALLED:
            return
        menu = QMenu(self)
        act_local = QAction("Installer depuis un fichier local\u2026", self)
        act_local.triggered.connect(self._on_install_local)
        menu.addAction(act_local)
        menu.exec(self.mapToGlobal(pos))

    def _on_install_local(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "S\u00e9lectionner une archive de jeu", "", "Archives (*.7z *.zip)",
        )
        if not path:
            return
        self.status_message.emit(f"Installation de {self.game.name} depuis un fichier local\u2026")
        self._start_install(Path(path), delete_archive=False)

    # ──────────────────── Action principale ────────────────────

    def trigger_primary_action(self) -> None:
        if self.game is None:
            return
        match self._current_state():
            case GameState.NOT_INSTALLED:
                self._on_download()
            case GameState.INSTALLED:
                self._on_play()

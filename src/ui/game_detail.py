"""Vue détaillée d'un jeu — zone centrale avec fond, infos et actions."""

import logging
import shutil
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QUrl, QTimer, pyqtSignal, QPointF,
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
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.ui.background_widget import BackgroundWidget
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel, cinzel_decorative, body_font
from src.ui.glow_button import GlowButton
from src.ui.speed_tracker import SpeedTracker, format_size, format_bytes, format_speed, format_eta

from src.core.config import ASSETS_DIR
from src.core.downloader import Downloader
from src.core.game_data import GameData, GameVersion
from src.core.game_manager import GameManager, GameState
from src.core.installer import Installer
from src.ui.versions_dialog import VersionsDialog

log = logging.getLogger(__name__)

# Nombre de caractères affichés avant troncature
_DESC_TRUNCATE = 160


class GameDetailView(QWidget):
    """Zone centrale : fond + voile gauche + infos + boutons d'action."""

    status_message = pyqtSignal(str)
    state_changed = pyqtSignal()
    game_launched = pyqtSignal(object, str)  # (subprocess.Popen, game_name)

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.game: GameData | None = None
        self._downloader: Downloader | None = None
        self._installer: Installer | None = None
        self._speed_tracker = SpeedTracker()

        self._video_player = None
        self._video_sink = None
        self._audio_output = None
        self._video_muted = False

        self._target_version: GameVersion | None = None
        self._active_game: GameData | None = None  # jeu en cours de téléchargement/installation
        self._desc_expanded = False
        self._full_desc = ""

        # Widgets créés dynamiquement par _build_downloading / _build_installing
        self._progress_bar: QProgressBar | None = None
        self._download_label: QLabel | None = None
        self._install_bar: QProgressBar | None = None

        self._build_ui()

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ──────────────────── Construction UI ────────────────────

    def _build_ui(self) -> None:
        self._bg = BackgroundWidget(self)

        # ── Info labels over the left veil gradient ──
        self._info_container = QScrollArea(self)
        self._info_container.setWidgetResizable(True)
        self._info_container.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._info_container.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._info_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._info_container.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "  background: transparent; width: 4px; border: none;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(212,160,23,0.3); border-radius: 2px; min-height: 20px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        _info_widget = QWidget()
        _info_widget.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(_info_widget)
        info_layout.setContentsMargins(50, 0, 30, 0)
        info_layout.setSpacing(0)
        self._info_container.setWidget(_info_widget)

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

        info_layout.addSpacing(6)

        # Version + Changelog link
        version_row = QWidget()
        version_row.setStyleSheet("background: transparent;")
        version_layout = QHBoxLayout(version_row)
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(10)
        version_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._version_label = QLabel()
        self._version_label.setFont(body_font(12))
        self._version_label.setStyleSheet(
            "QLabel { color: rgba(212, 160, 23, 0.70); background: transparent; }"
        )
        version_layout.addWidget(self._version_label)

        self._btn_versions = QLabel("Versions et changelog")
        self._btn_versions.setFont(body_font(12))
        self._btn_versions.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_versions.setStyleSheet(
            "QLabel { color: rgba(212, 160, 23, 0.70); background: transparent; }"
            "QLabel:hover { color: #e8c547; text-decoration: underline; }"
        )
        self._btn_versions.mousePressEvent = lambda e: self._on_versions_clicked(e) if e.button() == Qt.MouseButton.LeftButton else None
        version_layout.addWidget(self._btn_versions)

        info_layout.addWidget(version_row)

        info_layout.addSpacing(10)

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
        self._btn_expand.mousePressEvent = lambda e: self._on_expand_clicked(e) if e.button() == Qt.MouseButton.LeftButton else None
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
        self._action_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._action_layout = QHBoxLayout(self._action_container)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(14)
        self._action_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._action_container)

        # Ligne de mise à jour (sous les boutons d'action)
        self._update_row = QWidget()
        self._update_row.setStyleSheet("background: transparent;")
        self._update_row.hide()
        self._update_row_layout = QHBoxLayout(self._update_row)
        self._update_row_layout.setContentsMargins(0, 0, 0, 0)
        self._update_row_layout.setSpacing(8)
        self._update_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._update_row)

        info_layout.addStretch()

        # ── Contrôle audio (mute + slider volume) ──
        self._audio_bar = QWidget(self)
        self._audio_bar.setStyleSheet(
            "QWidget { background: rgba(0,0,0,0.55); border-radius: 14px; }"
        )
        self._audio_bar.setFixedSize(160, 32)
        self._audio_bar.hide()
        ab_layout = QHBoxLayout(self._audio_bar)
        ab_layout.setContentsMargins(8, 0, 8, 0)
        ab_layout.setSpacing(6)

        self._btn_mute = QPushButton("\U0001f50a")
        self._btn_mute.setFixedSize(26, 26)
        self._btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mute.setStyleSheet(
            "QPushButton { background: transparent; color: #eaeaea; border: none;"
            " font-size: 15px; }"
            "QPushButton:hover { color: #d4a017; }"
        )
        self._btn_mute.clicked.connect(self._toggle_mute)
        ab_layout.addWidget(self._btn_mute)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(25)
        self._volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._volume_slider.setStyleSheet(
            "QSlider::groove:horizontal {"
            "  background: rgba(255,255,255,0.12); height: 4px; border-radius: 2px;"
            "}"
            "QSlider::handle:horizontal {"
            "  background: #d4a017; width: 12px; height: 12px; margin: -4px 0;"
            "  border-radius: 6px;"
            "}"
            "QSlider::sub-page:horizontal {"
            "  background: rgba(212,160,23,0.5); border-radius: 2px;"
            "}"
        )
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        ab_layout.addWidget(self._volume_slider)

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

    def _on_expand_clicked(self, _event) -> None:
        """Slot pour le clic sur le label expand."""
        self._toggle_desc()

    def _on_versions_clicked(self, _event) -> None:
        """Ouvre le dialog de gestion des versions."""
        if self.game is not None:
            dlg = VersionsDialog(self.game, self.manager, self)
            dlg.install_version.connect(self._on_install_specific_version)
            dlg.exec()

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
        self._bg.invalidate_cache()
        self._position_info()
        self._audio_bar.move(self.width() - 174, self.height() - 46)
        self._audio_bar.raise_()

    # ──────────────────── Changement de jeu ────────────────────

    def update_game_data(self, game: GameData) -> None:
        """Met à jour les données du jeu courant (après un reload catalogue)."""
        self.game = game
        self._refresh_action()

    def set_game(self, game: GameData) -> None:
        if self.game and self.game.id == game.id:
            self._refresh_action()
            return

        self._stop_video()
        self._fade_anim.stop()
        self._info_fade.stop()

        # Pas de fade-out : on coupe net et on fade-in le nouveau jeu.
        # Élimine le ghosting lors de clics rapides dans le carrousel.
        self._bg._set_bg_opacity(0.0)
        self._info_opacity.setOpacity(0.0)
        self._apply_game(game)

    def _apply_game(self, game: GameData) -> None:
        self.game = game
        self._title.setText(game.name)

        # Metadata
        gold = "#d4a017"
        sep = f'<span style="color:{gold}; margin: 0 6px;"> \u25c6 </span>'
        dl = game.current_download
        size_str = format_size(dl.size_mb) if dl else "?"
        self._meta.setText(
            f'<span style="text-transform:uppercase; letter-spacing:2px;">'
            f'{game.year}{sep}{game.developer}{sep}{size_str}'
            f'</span>'
        )

        # Version
        installed_ver = self.manager.installed_version(game.id)
        display_ver = installed_ver or game.recommended_version
        self._version_label.setText(f"Version {display_ver}")

        # Description (truncated + expand)
        self._set_desc_text(game.description)

        # Tags
        self._clear_layout(self._tags_layout)
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

        # Fade-in background + zoom loop
        current = self._bg.bg_opacity
        self._fade_anim.setStartValue(current)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setDuration(max(int(400 * (1.0 - current)), 80))
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
            self._audio_bar.hide()
            return
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

            if self._video_sink is None:
                self._video_sink = QVideoSink(self)
                self._video_sink.videoFrameChanged.connect(self._on_video_frame)
                self._audio_output = QAudioOutput(self)
                self._audio_output.setVolume(0.25)
                self._video_player = QMediaPlayer(self)
                self._video_player.setVideoOutput(self._video_sink)
                self._video_player.setAudioOutput(self._audio_output)
                self._video_player.mediaStatusChanged.connect(self._on_media_status)

            self._video_player.setSource(QUrl.fromLocalFile(str(video_path)))
            self._video_player.play()
            self._video_muted = self.manager.config.mute_videos
            self._audio_output.setVolume(self._volume_slider.value() / 100.0)
            self._audio_output.setMuted(self._video_muted)
            self._btn_mute.setText("\U0001f507" if self._video_muted else "\U0001f50a")
            self._audio_bar.show()
            self._audio_bar.raise_()
        except ImportError:
            log.debug("PyQt6-Multimedia non disponible")

    def _on_video_frame(self, frame) -> None:
        """Reçoit chaque frame vidéo et l'envoie au BackgroundWidget."""
        if frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self._bg.set_video_frame(image)

    def _on_media_status(self, status) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._stop_video()

    def _stop_video(self) -> None:
        if self._video_player is not None:
            self._video_player.stop()
            self._video_player.setSource(QUrl())
            self._video_player.mediaStatusChanged.disconnect(self._on_media_status)
            self._video_sink.videoFrameChanged.disconnect(self._on_video_frame)
            self._video_player.deleteLater()
            self._video_sink.deleteLater()
            self._audio_output.deleteLater()
            self._video_player = None
            self._video_sink = None
            self._audio_output = None
        self._bg.clear_video()
        self._audio_bar.hide()

    def _toggle_mute(self) -> None:
        if self._audio_output is None:
            return
        self._video_muted = not self._video_muted
        self._audio_output.setMuted(self._video_muted)
        self._btn_mute.setText("\U0001f507" if self._video_muted else "\U0001f50a")

    def _on_volume_changed(self, value: int) -> None:
        if self._audio_output is None:
            return
        if self._video_muted:
            self._video_muted = False
            self._audio_output.setMuted(False)
            self._btn_mute.setText("\U0001f50a")
        self._audio_output.setVolume(value / 100.0)

    # ──────────────────── Pause / Resume (API publique) ────────────────────

    def pause(self) -> None:
        """Met en pause tous les effets visuels et la vidéo."""
        self._stop_video()
        self._bg.pause()

    def resume(self) -> None:
        """Reprend les effets visuels (la vidéo ne reprend pas)."""
        self._bg.resume()

    def _deferred_warning(self, title: str, message: str) -> None:
        """Affiche un QMessageBox.warning via QTimer.singleShot(0) de façon sûre."""
        def _show() -> None:
            try:
                self.isVisible()  # test si le C++ object est encore vivant
            except RuntimeError:
                return
            QMessageBox.warning(self, title, message)
        QTimer.singleShot(0, _show)

    # ──────────────────── Actions ────────────────────

    def _current_state(self) -> GameState:
        if self.game is None:
            return GameState.NOT_INSTALLED
        return self.manager.get_state(self.game.id)

    @staticmethod
    def _clear_layout(layout) -> None:
        """Retire et détruit tous les widgets d'un layout immédiatement."""
        while layout.count():
            item = layout.takeAt(0)
            if (w := item.widget()) is not None:
                w.hide()
                w.deleteLater()

    def _refresh_action(self) -> None:
        self._clear_layout(self._action_layout)
        self._progress_bar = None
        self._download_label = None
        self._install_bar = None
        self._action_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        self._clear_layout(self._update_row_layout)
        self._update_row.hide()

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
        dl = self.game.current_download
        size = format_size(dl.size_mb) if dl else "?"
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
        self._action_layout.setDirection(QVBoxLayout.Direction.TopToBottom)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(400)
        self._action_layout.addWidget(self._progress_bar)

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        self._download_label = QLabel("T\u00e9l\u00e9chargement : 0%")
        self._download_label.setObjectName("downloadLabel")
        row_layout.addWidget(self._download_label, stretch=1)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self._on_cancel_download)
        row_layout.addWidget(btn_cancel)

        self._action_layout.addWidget(row)

    def _build_installing(self) -> None:
        self._action_layout.setDirection(QVBoxLayout.Direction.TopToBottom)
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

        # Lien mise à jour si disponible
        if self.manager.has_update(self.game.id):
            installed_ver = self.manager.installed_version(self.game.id) or "?"
            recommended = self.game.recommended_version
            update_label = QLabel(
                f"Mise à jour disponible : v{installed_ver} → v{recommended}"
            )
            update_label.setFont(body_font(12))
            update_label.setStyleSheet("color: #d4a017; background: transparent;")

            update_link = QLabel("Mettre à jour")
            update_link.setFont(body_font(12))
            update_link.setCursor(Qt.CursorShape.PointingHandCursor)
            update_link.setStyleSheet(
                "QLabel { color: #d4a017; background: transparent; text-decoration: underline; }"
                "QLabel:hover { color: #e8c547; }"
            )
            update_link.mousePressEvent = lambda e: self._on_update_clicked(e) if e.button() == Qt.MouseButton.LeftButton else None

            self._update_row_layout.addWidget(update_label)
            self._update_row_layout.addWidget(update_link)
            self._update_row.show()

    # ──────────────────── Téléchargement ────────────────────

    def _check_disk_space(self, version: GameVersion | None = None) -> bool:
        if self.game is None:
            return False
        ver = version or self.game.current_download
        if ver is None:
            return True
        needed_mb = ver.size_mb * 2
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

    def _on_download(self, version: GameVersion | None = None) -> None:
        if self.game is None:
            return
        if self._downloader is not None or self._installer is not None:
            return
        ver = version or self.game.current_download
        if ver is None:
            self.status_message.emit("Aucune version disponible.")
            return
        if not self._check_disk_space(ver):
            return

        self._target_version = ver
        self._active_game = self.game
        self.manager.set_game_state(self.game.id, GameState.DOWNLOADING)
        self._refresh_action()
        self._speed_tracker.reset()
        self.status_message.emit(f"T\u00e9l\u00e9chargement de {self.game.name} v{ver.version}\u2026")

        archive_name = f"{self.game.id}_v{ver.version}.7z"
        dest = self.manager.config.cache_path / archive_name
        self._downloader = Downloader(
            url=ver.download_url, destination=dest,
            parts=ver.download_parts, parent=self,
        )
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)
        if ver.download_parts:
            self._downloader.part_info.connect(self._on_part_info)
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

        if self._progress_bar is not None:
            self._progress_bar.setValue(pct)
        if self._download_label is not None:
            self._download_label.setText(" \u2014 ".join(parts))

    def _on_download_finished(self, archive_path_str: str) -> None:
        self._downloader = None
        game = self._active_game
        if game is None:
            return
        self.status_message.emit(f"Installation de {game.name}\u2026")
        self._start_install(game, Path(archive_path_str), delete_archive=self.manager.config.delete_archives)

    def _on_download_error(self, message: str) -> None:
        self._downloader = None
        game = self._active_game
        self._active_game = None
        if game is None:
            return
        self.manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        if self.game and self.game.id == game.id:
            self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit(f"Erreur : {message}")
        self._deferred_warning(
            "\u00c9chec du t\u00e9l\u00e9chargement",
            "Le t\u00e9l\u00e9chargement a \u00e9chou\u00e9.\nV\u00e9rifiez votre connexion internet et r\u00e9essayez.",
        )

    def _on_cancel_download(self) -> None:
        dest: Path | None = None
        if self._downloader is not None:
            dest = self._downloader.destination
            self._downloader.progress.disconnect(self._on_download_progress)
            self._downloader.finished.disconnect(self._on_download_finished)
            self._downloader.error.disconnect(self._on_download_error)
            try:
                self._downloader.part_info.disconnect(self._on_part_info)
            except TypeError:
                pass
            self._downloader.cancel()
            if not self._downloader.wait(3000):
                log.warning("Le thread de téléchargement n'a pas répondu dans les 3s")
            self._downloader = None
        # Nettoyer le fichier .part résiduel
        if dest is not None:
            part_path = dest.with_suffix(dest.suffix + ".part")
            part_path.unlink(missing_ok=True)
        game = self._active_game
        self._active_game = None
        if game is None:
            return
        self.manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        if self.game and self.game.id == game.id:
            self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit("Téléchargement annulé.")

    def _on_part_info(self, current: int, total: int) -> None:
        """Met à jour l'affichage du numéro de part (multi-parts)."""
        if self._download_label is not None:
            text = self._download_label.text()
            # Ajouter/remplacer l'info de part
            if "partie" in text:
                text = text[:text.index("partie")].rstrip(" — ")
            self._download_label.setText(f"{text} — partie {current}/{total}")

    def _on_update_clicked(self, _event) -> None:
        """Clic sur le lien 'Mettre à jour'."""
        if self.game is None:
            return
        ver = self.game.get_version(self.game.recommended_version)
        if ver is None:
            return

        # Construire le changelog des versions manquées
        installed = self.manager.installed_version(self.game.id) or "?"
        changes_text = "\n".join(f"• {c}" for c in ver.changes)
        reply = QMessageBox.question(
            self, "Mise à jour disponible",
            f"Mettre à jour de v{installed} vers v{ver.version} ?\n\n"
            f"Changements :\n{changes_text}\n\n"
            f"La version actuelle sera supprimée avant l'installation.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._do_version_switch(ver)

    def _on_install_specific_version(self, game_id: str, version: str) -> None:
        """Slot appelé par VersionsDialog pour installer une version spécifique."""
        if self.game is None or self.game.id != game_id:
            return
        ver = self.game.get_version(version)
        if ver is None:
            return
        self._do_version_switch(ver)

    def _do_version_switch(self, ver: GameVersion) -> None:
        """Supprime la version actuelle si installée, puis télécharge la nouvelle."""
        if self.game is None:
            return
        if self._downloader is not None or self._installer is not None:
            self.status_message.emit("Un téléchargement ou installation est déjà en cours.")
            return
        if self.manager.is_installed(self.game.id):
            self.manager.uninstall_game(self.game.id)
        self._on_download(ver)

    # ──────────────────── Installation ────────────────────

    def _start_install(self, game: GameData, archive_path: Path, *, delete_archive: bool = True) -> None:
        self._active_game = game
        self.manager.set_game_state(game.id, GameState.INSTALLING)
        if self.game and self.game.id == game.id:
            self._refresh_action()

        dest = self.manager.config.install_path
        config_files = [
            (cf.source, cf.destination)
            for cf in game.post_install.config_files
        ]
        # Dossier racine du jeu dans l'archive (ex: "HP3" depuis "HP3/system/hppoa.exe")
        game_dir = Path(game.executable).parts[0] if game.executable else None
        self._installer = Installer(
            archive_path, dest,
            registry_entries=list(game.post_install.registry),
            config_files=config_files,
            game_dir=game_dir,
            delete_archive=delete_archive, parent=self,
        )
        self._installer.progress.connect(self._on_install_progress)
        self._installer.finished.connect(self._on_install_finished)
        self._installer.error.connect(self._on_install_error)
        self._installer.start()

    def _on_install_progress(self, pct: int) -> None:
        if self._install_bar is not None:
            self._install_bar.setValue(pct)

    def _on_install_finished(self, _path: str) -> None:
        self._installer = None
        game = self._active_game
        self._active_game = None
        if game is None:
            return
        is_current = self.game and self.game.id == game.id
        exe_path = self.manager.config.install_path / game.executable
        if not exe_path.exists():
            log.warning("Ex\u00e9cutable introuvable apr\u00e8s extraction : %s", exe_path)
            self.manager.set_game_state(game.id, GameState.NOT_INSTALLED)
            if is_current:
                self._refresh_action()
            self.state_changed.emit()
            self.status_message.emit("Installation incompl\u00e8te.")
            self._deferred_warning(
                "Installation incompl\u00e8te",
                "L'installation semble incompl\u00e8te : l'ex\u00e9cutable du jeu est introuvable.\n"
                "L'archive est peut-\u00eatre corrompue.",
            )
            return
        self.manager.set_game_state(game.id, GameState.INSTALLED)
        target_ver = self._target_version
        self.manager.save_installed_version(game.id, target_ver.version if target_ver else None)
        if is_current:
            self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit(f"{game.name} install\u00e9 avec succ\u00e8s !")

    def _on_install_error(self, message: str) -> None:
        self._installer = None
        game = self._active_game
        self._active_game = None
        if game is None:
            return
        self.manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        if self.game and self.game.id == game.id:
            self._refresh_action()
        self.state_changed.emit()
        self.status_message.emit(f"Erreur d'installation : {message}")
        self._deferred_warning(
            "\u00c9chec de l'installation",
            "L'installation a \u00e9chou\u00e9.\nL'archive est peut-\u00eatre corrompue. R\u00e9essayez le t\u00e9l\u00e9chargement.",
        )

    # ──────────────────── Jouer / Désinstaller ────────────────────

    def _on_play(self) -> None:
        if self.game is None:
            return
        self._stop_video()
        try:
            proc = self.manager.launch_game(self.game.id)
        except OSError as exc:
            log.error("Impossible de lancer %s : %s", self.game.name, exc)
            self.status_message.emit("Impossible de lancer le jeu.")
            return
        if proc is not None:
            self.status_message.emit(f"Lancement de {self.game.name}\u2026")
            self.game_launched.emit(proc, self.game.name)
        else:
            self.status_message.emit("Impossible de lancer le jeu.")

    def _on_uninstall(self) -> None:
        if self.game is None:
            return
        reply = QMessageBox.question(
            self, "Confirmer la d\u00e9sinstallation",
            f"Voulez-vous vraiment d\u00e9sinstaller {self.game.name} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            has_config = bool(self.game.post_install.config_files)
            self.manager.uninstall_game(self.game.id)
            self._refresh_action()
            self.state_changed.emit()
            if has_config:
                QMessageBox.information(
                    self, "Sauvegardes conservées",
                    "Les sauvegardes et la configuration dans Mes Documents "
                    "ont été conservées.",
                )
            self.status_message.emit(f"{self.game.name} d\u00e9sinstall\u00e9.")

    # ──────────────────── Menu contextuel ────────────────────

    def _show_context_menu(self, pos) -> None:
        if self.game is None:
            return
        menu = QMenu(self)

        # Toujours proposer "Gérer les versions"
        act_versions = QAction("Gérer les versions", self)
        act_versions.triggered.connect(lambda: self._on_versions_clicked(None))
        menu.addAction(act_versions)

        if self._current_state() == GameState.NOT_INSTALLED:
            act_local = QAction("Installer depuis un fichier local\u2026", self)
            act_local.triggered.connect(self._on_install_local)
            menu.addAction(act_local)

        menu.exec(self.mapToGlobal(pos))

    def _on_install_local(self) -> None:
        if self.game is None:
            return
        if self._downloader is not None or self._installer is not None:
            self.status_message.emit("Un téléchargement ou installation est déjà en cours.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "S\u00e9lectionner une archive de jeu", "", "Archives (*.7z *.zip)",
        )
        if not path:
            return
        self.status_message.emit(f"Installation de {self.game.name} depuis un fichier local\u2026")
        self._start_install(self.game, Path(path), delete_archive=False)

    # ──────────────────── Action principale ────────────────────

    def trigger_primary_action(self) -> None:
        if self.game is None:
            return
        match self._current_state():
            case GameState.NOT_INSTALLED:
                self._on_download()
            case GameState.INSTALLED:
                self._on_play()

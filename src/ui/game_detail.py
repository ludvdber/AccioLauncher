import logging
import math
import shutil
import time
from collections import deque
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QUrl, pyqtSignal,
    QPointF, QRectF, QTimer, pyqtProperty, QSize,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.fonts import cinzel, cinzel_decorative, body_font
from src.ui.glow_button import GlowButton

from src.core.downloader import Downloader
from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.core.installer import Installer

log = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"

SPEED_WINDOW = 5.0
UI_UPDATE_INTERVAL = 0.5


def _format_size(size_mb: int) -> str:
    if size_mb >= 1000:
        return f"{size_mb / 1000:.1f} Go"
    return f"{size_mb} Mo"


def _format_bytes(b: int) -> str:
    mb = b / (1024 * 1024)
    if mb >= 1000:
        return f"{mb / 1000:.1f} Go"
    return f"{mb:.0f} Mo"


def _format_speed(bytes_per_sec: float) -> str:
    mb = bytes_per_sec / (1024 * 1024)
    if mb >= 1.0:
        return f"{mb:.1f} Mo/s"
    kb = bytes_per_sec / 1024
    return f"{kb:.0f} Ko/s"


def _format_eta(seconds: float) -> str:
    if seconds < 0 or seconds > 86400:
        return ""
    if seconds < 60:
        return f"~{int(seconds)}s restantes"
    minutes = seconds / 60
    if minutes < 60:
        return f"~{int(minutes)} min restantes"
    hours = minutes / 60
    return f"~{hours:.1f}h restantes"


# ──────────────────────────────────────────────────────────────
# FlowLayout — wrapping layout for tags
# ──────────────────────────────────────────────────────────────

class FlowLayout(QLayout):
    """Simple flow layout that wraps items to the next line."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRectF(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(QRectF(rect), test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect, test_only=False):
        x = rect.x()
        y = rect.y()
        line_height = 0
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._spacing
                line_height = 0
            if not test_only:
                from PyQt6.QtCore import QRect as QR
                item.setGeometry(QR(int(x), int(y), int(w), int(h)))
            x += w + self._spacing
            line_height = max(line_height, h)
        return int(y + line_height - rect.y())


# ──────────────────────────────────────────────────────────────
# Widget de fond — zoom cinématique continu + parallaxe
# ──────────────────────────────────────────────────────────────

class BackgroundWidget(QWidget):
    """Image de fond avec zoom lent continu, parallaxe souris,
    vignette renforcée, overlay et dégradé bas 75%."""

    PARALLAX_MAX_X = 20  # pixels max de décalage horizontal
    PARALLAX_MAX_Y = 12  # pixels max de décalage vertical
    MAX_SCALE = 1.18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._prepared: QPixmap | None = None
        self._prepared_for: tuple[int, int] = (0, 0)
        self._opacity = 1.0

        # Zoom cinématique continu (1.0 → 1.05 → 1.0, cycle 16s)
        self._zoom = 1.0
        self._zoom_anim = QPropertyAnimation(self, b"zoom_factor")
        self._zoom_anim.setDuration(8000)
        self._zoom_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        # Parallaxe souris — lerp doux
        self._parallax_tx = 0.0
        self._parallax_ty = 0.0
        self._parallax_cx = 0.0
        self._parallax_cy = 0.0
        self._parallax_timer = QTimer(self)
        self._parallax_timer.setInterval(16)  # ~60 FPS
        self._parallax_timer.timeout.connect(self._update_parallax)
        self._parallax_timer.start()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        log.debug("[FX] BackgroundWidget — zoom 16s, parallaxe ±20/±12, gradient 75%%")

    # ── Propriétés Qt animables ──

    def _get_bg_opacity(self) -> float:
        return self._opacity

    def _set_bg_opacity(self, value: float) -> None:
        self._opacity = value
        self.update()

    bg_opacity = pyqtProperty(float, _get_bg_opacity, _set_bg_opacity)

    def _get_zoom(self) -> float:
        return self._zoom

    def _set_zoom(self, value: float) -> None:
        self._zoom = value
        self.update()

    zoom_factor = pyqtProperty(float, _get_zoom, _set_zoom)

    def start_zoom_loop(self) -> None:
        self._zoom = 1.0
        self._zoom_forward = True
        self._run_zoom_leg()

    def _run_zoom_leg(self) -> None:
        self._zoom_anim.stop()
        if self._zoom_forward:
            self._zoom_anim.setStartValue(1.0)
            self._zoom_anim.setEndValue(1.05)
        else:
            self._zoom_anim.setStartValue(1.05)
            self._zoom_anim.setEndValue(1.0)
        self._zoom_forward = not self._zoom_forward
        try:
            self._zoom_anim.finished.disconnect()
        except TypeError:
            pass
        self._zoom_anim.finished.connect(self._run_zoom_leg)
        self._zoom_anim.start()

    def set_parallax_target(self, mouse_x: float, mouse_y: float,
                            win_w: float, win_h: float) -> None:
        """Set parallax from mouse position and window size."""
        if win_w <= 0 or win_h <= 0:
            return
        center_x = win_w / 2
        center_y = win_h / 2
        self._parallax_tx = -(mouse_x - center_x) / win_w * self.PARALLAX_MAX_X
        self._parallax_ty = -(mouse_y - center_y) / win_h * self.PARALLAX_MAX_Y

    def _update_parallax(self) -> None:
        dx = self._parallax_tx - self._parallax_cx
        dy = self._parallax_ty - self._parallax_cy
        if abs(dx) < 0.05 and abs(dy) < 0.05:
            return
        self._parallax_cx += dx * 0.05
        self._parallax_cy += dy * 0.05
        self.update()

    def set_image(self, path: Path | None) -> None:
        if path and path.exists():
            self._pixmap = QPixmap(str(path))
        else:
            self._pixmap = None
        self._prepared = None
        self._prepared_for = (0, 0)
        self.update()

    def _ensure_prepared(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            self._prepared = None
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        if self._prepared and self._prepared_for == (w, h):
            return
        # Image à 108% pour la marge parallaxe
        tw = int(w * self.MAX_SCALE)
        th = int(h * self.MAX_SCALE)
        self._prepared = self._pixmap.scaled(
            tw, th,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._prepared_for = (w, h)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        w, h = rect.width(), rect.height()

        p.fillRect(rect, QColor("#060611"))
        p.setOpacity(self._opacity)

        self._ensure_prepared()
        if self._prepared and w > 0 and h > 0:
            pw, ph = float(self._prepared.width()), float(self._prepared.height())
            widget_ar = w / h
            prep_ar = pw / ph

            if widget_ar > prep_ar:
                base_w = pw
                base_h = pw / widget_ar
            else:
                base_h = ph
                base_w = ph * widget_ar

            ez = 1.08 * self._zoom
            crop_w = base_w / ez
            crop_h = base_h / ez

            scale_x = crop_w / w
            scale_y = crop_h / h
            cx = pw * 0.5 + self._parallax_cx * scale_x
            cy = ph * 0.5 + self._parallax_cy * scale_y

            src_rect = QRectF(cx - crop_w * 0.5, cy - crop_h * 0.5, crop_w, crop_h)
            p.drawPixmap(QRectF(0, 0, w, h), self._prepared, src_rect)

        # Overlay brightness
        p.fillRect(rect, QColor(0, 0, 0, 77))

        # ── Permanent elements (opacity 1.0) ──
        p.setOpacity(1.0)

        # Subtle dark blue overlay
        p.fillRect(rect, QColor(6, 6, 17, 30))

        # Top gradient (title bar area)
        grad_top = QLinearGradient(0, 0, 0, h * 0.08)
        grad_top.setColorAt(0, QColor(6, 6, 17, 160))
        grad_top.setColorAt(1, QColor(6, 6, 17, 0))
        p.fillRect(rect, grad_top)

        # Bottom gradient — 75% height, very strong
        grad = QLinearGradient(0, h * 0.25, 0, h)
        grad.setColorAt(0.0, QColor(6, 6, 17, 0))
        grad.setColorAt(0.35, QColor(6, 6, 17, 38))    # ~15%
        grad.setColorAt(0.55, QColor(6, 6, 17, 128))   # ~50%
        grad.setColorAt(0.75, QColor(6, 6, 17, 217))   # ~85%
        grad.setColorAt(1.0, QColor(6, 6, 17, 247))    # ~97%
        p.fillRect(rect, grad)

        # Radial vignette
        vcx, vcy = w / 2, h / 2
        vradius = max(w, h) * 0.7
        vignette = QRadialGradient(vcx, vcy, vradius)
        vignette.setColorAt(0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.3, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.7, QColor(0, 0, 0, 130))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 230))
        p.fillRect(rect, vignette)

        # ── Voile gauche — simple dégradé horizontal, pas de blur ──
        veil_grad = QLinearGradient(0, 0, w, 0)
        veil_grad.setColorAt(0.0, QColor(6, 6, 17, 200))
        veil_grad.setColorAt(0.25, QColor(6, 6, 17, 150))
        veil_grad.setColorAt(0.40, QColor(6, 6, 17, 80))
        veil_grad.setColorAt(0.55, QColor(6, 6, 17, 20))
        veil_grad.setColorAt(0.72, QColor(6, 6, 17, 0))
        p.fillRect(rect, veil_grad)

        p.end()


# ──────────────────────────────────────────────────────────────
# Tracker de vitesse de téléchargement
# ──────────────────────────────────────────────────────────────

class SpeedTracker:
    """Calcule la vitesse moyenne glissante et le temps restant."""

    def __init__(self, window: float = SPEED_WINDOW) -> None:
        self._window = window
        self._samples: deque[tuple[float, int]] = deque()
        self._last_ui_update = 0.0

    def reset(self) -> None:
        self._samples.clear()
        self._last_ui_update = 0.0

    def update(self, downloaded: int) -> None:
        now = time.monotonic()
        self._samples.append((now, downloaded))
        cutoff = now - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def should_update_ui(self) -> bool:
        now = time.monotonic()
        if now - self._last_ui_update >= UI_UPDATE_INTERVAL:
            self._last_ui_update = now
            return True
        return False

    @property
    def speed(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        oldest_t, oldest_b = self._samples[0]
        newest_t, newest_b = self._samples[-1]
        dt = newest_t - oldest_t
        if dt <= 0:
            return 0.0
        return (newest_b - oldest_b) / dt

    def eta(self, downloaded: int, total: int) -> float:
        s = self.speed
        if s <= 0 or total <= downloaded:
            return -1.0
        return (total - downloaded) / s


# ──────────────────────────────────────────────────────────────
# Vue détaillée d'un jeu (zone centrale complète)
# ──────────────────────────────────────────────────────────────

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

        self._build_ui()

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _build_ui(self) -> None:
        self._bg = BackgroundWidget(self)

        # ── Info labels positioned over the left veil gradient ──
        self._info_container = QWidget(self)
        self._info_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._info_container.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(self._info_container)
        info_layout.setContentsMargins(50, 0, 30, 0)
        info_layout.setSpacing(0)

        # Title — Cinzel Decorative 40px, max 550px wide
        self._title = QLabel()
        self._title.setObjectName("gameTitle")
        self._title.setFont(cinzel_decorative(36))
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(600)
        self._title.setStyleSheet(
            "QLabel { color: #eaeaea; background: transparent; }"
        )
        info_layout.addWidget(self._title)

        info_layout.addSpacing(8)

        # Metadata — Cinzel 14px
        self._meta = QLabel()
        self._meta.setObjectName("gameMeta")
        self._meta.setFont(cinzel(14))
        self._meta.setTextFormat(Qt.TextFormat.RichText)
        self._meta.setStyleSheet("QLabel { color: #8a8aaa; background: transparent; }")
        info_layout.addWidget(self._meta)

        info_layout.addSpacing(14)

        # Gold separator — 60px wide, 30% opacity
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setFixedWidth(60)
        sep.setStyleSheet("background: rgba(212, 160, 23, 0.30);")
        info_layout.addWidget(sep)

        info_layout.addSpacing(14)

        # Description — 15px, max 3 lines, 75% opacity
        self._desc = QLabel()
        self._desc.setObjectName("gameDescription")
        self._desc.setFont(body_font(15))
        self._desc.setWordWrap(True)
        self._desc.setMaximumWidth(520)
        # Limit to ~3 lines: font size 15 * 1.5 line-height * 3 lines ≈ 68px
        self._desc.setMaximumHeight(68)
        self._desc.setStyleSheet(
            "QLabel { color: rgba(176, 176, 200, 0.75); background: transparent;"
            " line-height: 1.5; }"
        )
        info_layout.addWidget(self._desc)

        info_layout.addSpacing(10)

        # Tags — flow layout (no clipping!)
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

        # Absorb remaining vertical space — keeps everything packed at the top
        info_layout.addStretch()

        self._btn_mute = QPushButton("\U0001f507", self)
        self._btn_mute.setObjectName("btnMute")
        self._btn_mute.setFixedSize(28, 28)
        self._btn_mute.clicked.connect(self._toggle_mute)
        self._btn_mute.hide()

        # Fade animation — background
        self._fade_anim = QPropertyAnimation(self._bg, b"bg_opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Fade animation — info text overlay
        self._info_opacity = QGraphicsOpacityEffect(self._info_container)
        self._info_opacity.setOpacity(1.0)
        self._info_container.setGraphicsEffect(self._info_opacity)
        self._info_fade = QPropertyAnimation(self._info_opacity, b"opacity")
        self._info_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        log.debug("[FX] GameDetailView — left veil, fade 400ms, zoom, parallaxe")

    def _position_info(self) -> None:
        """Position the info container over the left veil gradient."""
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

    def set_game(self, game: GameData) -> None:
        if self.game and self.game.id == game.id:
            self._refresh_action()
            return

        self._stop_video()

        # Fade out info text
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

        # Metadata with golden ◆
        gold = "#d4a017"
        sep = f'<span style="color:{gold}; margin: 0 6px;"> \u25c6 </span>'
        meta_html = (
            f'<span style="text-transform:uppercase; letter-spacing:2px;">'
            f'{game.year}{sep}{game.developer}{sep}{_format_size(game.archive_size_mb)}'
            f'</span>'
        )
        self._meta.setText(meta_html)

        self._desc.setText(game.description)

        # Tags — flow layout, complete text
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
        # Force layout recalculation
        self._tags_container.updateGeometry()

        # Background
        bg_path = ASSETS_DIR / "backgrounds" / f"{game.id}_bg.jpg"
        self._bg.set_image(bg_path)

        if self.manager.config.autoplay_videos:
            self._try_play_video(game.id)

        self._refresh_action()

        # Fade-in (400ms) + zoom loop
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setDuration(400)
        self._fade_anim.start()
        self._bg.start_zoom_loop()

        # Fade in info text (slightly delayed, 500ms)
        self._info_container.show()
        self._position_info()
        self._info_fade.stop()
        self._info_fade.setStartValue(0.0)
        self._info_fade.setEndValue(1.0)
        self._info_fade.setDuration(500)
        self._info_fade.start()

    # ──────────────────── Parallaxe ────────────────────

    def handle_mouse_move(self, pos: QPointF) -> None:
        """Appelé par MainWindow avec la position souris."""
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

        # Reset layout direction (downloading sets TopToBottom)
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
        size = _format_size(self.game.archive_size_mb)
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
                f"Il faut environ {_format_size(needed_mb)} d'espace libre.\n"
                f"Actuellement {_format_size(int(free_mb))} disponibles sur le lecteur.",
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
        dl_str = _format_bytes(downloaded)
        total_str = _format_bytes(total)
        speed_str = _format_speed(self._speed_tracker.speed)
        eta = self._speed_tracker.eta(downloaded, total)
        eta_str = _format_eta(eta)

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

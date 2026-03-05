"""Carrousel de jeux avec barre de verre, étoiles scintillantes et transitions animées."""

import logging
import math
import random
import re

log = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, pyqtSignal, QRect, QRectF, QPropertyAnimation, QEasingCurve, QTimer, pyqtProperty
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTransform,
)
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from src.core.config import ASSETS_DIR
from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.ui.fonts import cinzel
THUMB_W = 90
THUMB_H = 125

_ARABIC_TO_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
                     7: "VII", 8: "VIII", 9: "IX", 10: "X"}


def _game_roman(game_id: str) -> str:
    """Extrait le chiffre romain depuis l'id du jeu (ex: 'hp3' → 'III')."""
    m = re.search(r"(\d+)$", game_id)
    if m:
        n = int(m.group(1))
        return _ARABIC_TO_ROMAN.get(n, str(n))
    return game_id.upper()
CAROUSEL_HEIGHT = 160
REFLECTION_RATIO = 0.20
REFLECTION_OPACITY = 0.06

SCALE_SELECTED = 1.1
SCALE_ADJACENT = 1.0
SCALE_FAR = 0.9

OPACITY_SELECTED = 1.0
OPACITY_ADJACENT = 0.65
OPACITY_FAR = 0.45


class CarouselItem(QWidget):
    """Miniature d'un jeu dans le carrousel avec reflet, profondeur et transitions."""

    clicked = pyqtSignal()

    def __init__(self, game: GameData, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        self.manager = manager
        self._selected = False
        self._hovered = False
        self._pixmap: QPixmap | None = None
        self._anim_scale = float(SCALE_FAR)
        self._anim_opacity = float(OPACITY_FAR)

        self._reflection_cache: QPixmap | None = None
        self._reflection_cache_size: tuple[int, int] = (0, 0)
        self._cached_installed: bool = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._scale_anim = QPropertyAnimation(self, b"anim_scale")
        self._scale_anim.setDuration(400)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._opacity_anim = QPropertyAnimation(self, b"anim_opacity")
        self._opacity_anim.setDuration(400)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._update_size()
        self._load_cover()

    def _get_anim_scale(self) -> float:
        return self._anim_scale

    def _set_anim_scale(self, v: float) -> None:
        self._anim_scale = v
        self._update_size()
        self.update()

    anim_scale = pyqtProperty(float, _get_anim_scale, _set_anim_scale)

    def _get_anim_opacity(self) -> float:
        return self._anim_opacity

    def _set_anim_opacity(self, v: float) -> None:
        self._anim_opacity = v
        self.update()

    anim_opacity = pyqtProperty(float, _get_anim_opacity, _set_anim_opacity)

    def _load_cover(self) -> None:
        cover_path = ASSETS_DIR / "covers" / self.game.cover_image
        if cover_path.exists():
            self._pixmap = QPixmap(str(cover_path)).scaled(
                THUMB_W * 2, THUMB_H * 2,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )

    def _update_size(self) -> None:
        w = int(THUMB_W * self._anim_scale)
        h = int(THUMB_H * self._anim_scale)
        ref_h = int(h * REFLECTION_RATIO) + 6
        self.setFixedSize(w + 10, h + ref_h + 10)

    def set_depth(self, scale: float, opacity: float) -> None:
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self._anim_scale)
        self._scale_anim.setEndValue(scale)
        self._scale_anim.start()

        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self._anim_opacity)
        self._opacity_anim.setEndValue(opacity)
        self._opacity_anim.start()

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        self._selected = value
        self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        scale = self._anim_scale
        w = int(THUMB_W * scale)
        h = int(THUMB_H * scale)
        x_off = (self.width() - w) // 2
        y_off = 5
        radius = 6.0

        eff_opacity = self._anim_opacity
        if self._hovered and not self._selected:
            eff_opacity = min(eff_opacity + 0.2, 1.0)

        p.setOpacity(eff_opacity)

        # Shadow if selected
        if self._selected:
            p.save()
            p.setOpacity(0.4)
            for i in range(4):
                spread = (i + 1) * 3
                alpha = 60 - i * 12
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, max(alpha, 5)))
                p.drawRoundedRect(
                    x_off - spread, y_off - spread + 4,
                    w + spread * 2, h + spread * 2,
                    radius + spread, radius + spread,
                )
            p.restore()
            p.setOpacity(eff_opacity)

        # Cover image
        clip = QPainterPath()
        clip.addRoundedRect(float(x_off), float(y_off), float(w), float(h), radius, radius)

        if self._pixmap:
            p.setClipPath(clip)
            p.drawPixmap(x_off, y_off, w, h, self._pixmap)
            p.setClipping(False)
        else:
            grad = QLinearGradient(x_off, y_off, x_off, y_off + h)
            grad.setColorAt(0, QColor("#1a1a3e"))
            grad.setColorAt(1, QColor("#060611"))
            p.setBrush(grad)
            p.setPen(QPen(QColor(212, 160, 23, 60), 1.0))
            p.drawRoundedRect(x_off, y_off, w, h, radius, radius)

            p.setOpacity(1.0)
            p.setPen(QColor(212, 160, 23, 180))
            p.setFont(QFont("Segoe UI Emoji", 20))
            p.drawText(QRect(x_off, y_off - 10, w, h), Qt.AlignmentFlag.AlignCenter, "\u26a1")

            roman = _game_roman(self.game.id)
            p.setPen(QColor(212, 160, 23, 140))
            p.setFont(cinzel(12, bold=True))
            p.drawText(QRect(x_off, y_off + 22, w, h), Qt.AlignmentFlag.AlignCenter, roman)
            p.setOpacity(eff_opacity)

        # Gold border + glow if selected
        if self._selected:
            p.setOpacity(1.0)
            for i in range(3):
                glow = QColor(212, 160, 23, 25 - i * 7)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                off = (i + 1) * 3
                p.drawRoundedRect(x_off - off, y_off - off, w + off * 2, h + off * 2, radius + off, radius + off)

            pen = QPen(QColor("#d4a017"), 2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(x_off + 1, y_off + 1, w - 2, h - 2, radius, radius)

        # Reflection (cached)
        if self._pixmap:
            ref_h = int(h * REFLECTION_RATIO)
            ref_y = y_off + h + 4
            if self._reflection_cache is None or self._reflection_cache_size != (w, h):
                self._reflection_cache = self._pixmap.scaled(
                    w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                ).transformed(QTransform().scale(1, -1))
                self._reflection_cache_size = (w, h)
            flipped = self._reflection_cache

            p.setOpacity(eff_opacity * REFLECTION_OPACITY)
            ref_clip = QPainterPath()
            ref_clip.addRoundedRect(float(x_off), float(ref_y), float(w), float(ref_h), 3, 3)
            p.setClipPath(ref_clip)
            p.drawPixmap(x_off, ref_y, w, h, flipped)
            p.setClipping(False)

            p.setOpacity(1.0)
            fade = QLinearGradient(0, ref_y, 0, ref_y + ref_h)
            fade.setColorAt(0, QColor(6, 6, 17, 80))
            fade.setColorAt(1, QColor(6, 6, 17, 255))
            p.fillRect(x_off, ref_y, w, ref_h, fade)

        # Green dot if installed
        if self._cached_installed:
            p.setOpacity(1.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2ecc71"))
            p.drawEllipse(x_off + w - 14, y_off + h - 14, 10, 10)

            # Version badge
            ver_text = f"v{self.game.version}"
            p.setFont(QFont("Segoe UI", 9))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(ver_text)
            th = fm.height()
            pad_x, pad_y = 4, 2
            bx = x_off + 3
            by = y_off + h - th - pad_y * 2 - 3
            p.setBrush(QColor(0, 0, 0, 153))
            p.drawRoundedRect(QRectF(bx, by, tw + pad_x * 2, th + pad_y * 2), 3, 3)
            p.setPen(QColor(220, 220, 240, 200))
            p.drawText(QRectF(bx + pad_x, by + pad_y, tw, th), Qt.AlignmentFlag.AlignCenter, ver_text)

        p.end()


class Carousel(QWidget):
    """Bande horizontale de miniatures avec dégradé et étoiles."""

    game_selected = pyqtSignal(int)

    def __init__(self, games: list[GameData], manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("carouselBar")
        self.setFixedHeight(CAROUSEL_HEIGHT)
        self._items: list[CarouselItem] = []
        self._current_index = 0

        # ── Twinkling stars ──
        self._stars: list[tuple[float, float, float, int, bool, float]] = []
        self._star_phase = 0.0
        for _ in range(50):
            x = random.random()
            y = random.random()
            size = random.uniform(1.0, 2.2)
            max_alpha = random.randint(15, 55)
            is_gold = random.random() < 0.2
            phase = random.uniform(0, math.tau)
            self._stars.append((x, y, size, max_alpha, is_gold, phase))

        self._star_timer = QTimer(self)
        self._star_timer.setInterval(66)  # ~15 FPS
        self._star_timer.timeout.connect(self._tick_stars)
        self._star_timer.start()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 4)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for i, game in enumerate(games):
            item = CarouselItem(game, manager, self)
            item.clicked.connect(lambda idx=i: self.select(idx))
            layout.addWidget(item, alignment=Qt.AlignmentFlag.AlignBottom)
            self._items.append(item)

        if self._items:
            self._items[0].selected = True
            self._update_depths()
            self.refresh_indicators()

        log.debug(
            "[FX] Carousel — %d items, %d stars",
            len(self._items), len(self._stars),
        )

    def _tick_stars(self) -> None:
        self._star_phase += 0.04
        self.update()

    def paintEvent(self, event) -> None:
        """Dégradé vertical + étoiles scintillantes."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Simple vertical gradient: transparent → dark
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(6, 6, 17, 0))
        grad.setColorAt(0.15, QColor(6, 6, 17, 140))
        grad.setColorAt(0.4, QColor(6, 6, 17, 200))
        grad.setColorAt(1.0, QColor(6, 6, 17, 242))
        p.fillRect(self.rect(), grad)

        # Subtle top border
        p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))
        p.drawLine(0, 0, w, 0)

        # Stars
        p.setPen(Qt.PenStyle.NoPen)
        for sx, sy, size, max_a, is_gold, phase in self._stars:
            twinkle = 0.4 + 0.6 * (math.sin(self._star_phase + phase) * 0.5 + 0.5)
            alpha = int(max_a * twinkle)
            if is_gold:
                p.setBrush(QColor(212, 160, 23, alpha))
            else:
                p.setBrush(QColor(220, 220, 240, alpha))
            px = sx * w
            py = sy * h
            p.drawEllipse(QRectF(px - size * 0.5, py - size * 0.5, size, size))

        p.end()

    @property
    def current_index(self) -> int:
        return self._current_index

    def _update_depths(self) -> None:
        for i, item in enumerate(self._items):
            dist = abs(i - self._current_index)
            if dist == 0:
                item.set_depth(SCALE_SELECTED, OPACITY_SELECTED)
            elif dist == 1:
                item.set_depth(SCALE_ADJACENT, OPACITY_ADJACENT)
            else:
                item.set_depth(SCALE_FAR, OPACITY_FAR)

    def select(self, index: int) -> None:
        if index < 0 or index >= len(self._items):
            return
        if index == self._current_index:
            return
        self._items[self._current_index].selected = False
        self._current_index = index
        self._items[index].selected = True
        self._update_depths()
        self.game_selected.emit(index)

    def select_next(self) -> None:
        if self._items:
            self.select((self._current_index + 1) % len(self._items))

    def select_prev(self) -> None:
        if self._items:
            self.select((self._current_index - 1) % len(self._items))

    def pause(self) -> None:
        self._star_timer.stop()

    def resume(self) -> None:
        self._star_timer.start()

    def refresh_indicators(self) -> None:
        for item in self._items:
            item._cached_installed = item.manager.is_installed(item.game.id)
            item.update()

"""Carrousel de jeux : bande horizontale avec étoiles scintillantes et transitions."""

import logging
import math
import random

from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.ui.carousel_item import CarouselItem
from src.ui.ticker import Ticker

log = logging.getLogger(__name__)

CAROUSEL_HEIGHT = 160

SCALE_SELECTED = 1.1
SCALE_ADJACENT = 1.0
SCALE_FAR = 0.9

OPACITY_SELECTED = 1.0
OPACITY_ADJACENT = 0.65
OPACITY_FAR = 0.45


class Carousel(QWidget):
    """Bande horizontale de miniatures avec dégradé et étoiles."""

    game_selected = pyqtSignal(int)

    def __init__(self, games: list[GameData], manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("carouselBar")
        self.setFixedHeight(CAROUSEL_HEIGHT)
        self._manager = manager
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

        # Ticker partagé à ~30 FPS, mais repaint des étoiles 1 tick sur 2 (~15 FPS)
        self._star_flip = False
        self._ticking = False
        self.resume()

        self._items_layout = QHBoxLayout(self)
        self._items_layout.setContentsMargins(24, 8, 24, 4)
        self._items_layout.setSpacing(14)
        self._items_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.set_games(games)

    def set_games(self, games: list[GameData]) -> None:
        """Reconstruit la liste des items (appelé au reload du catalog)."""
        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items.clear()
        self._current_index = 0

        for i, game in enumerate(games):
            item = CarouselItem(game, self._manager, self)
            item.clicked.connect(lambda idx=i: self.select(idx))
            self._items_layout.addWidget(item, alignment=Qt.AlignmentFlag.AlignBottom)
            self._items.append(item)

        if self._items:
            self._items[0].selected = True
            self._update_depths()
            self.refresh_indicators()

        log.debug("Carousel — %d items, %d stars", len(self._items), len(self._stars))

    def _tick_stars(self) -> None:
        self._star_flip = not self._star_flip
        if self._star_flip:
            return  # 1 tick sur 2 → ~15 FPS visuel pour le scintillement
        self._star_phase += 0.04
        self.update()

    def paintEvent(self, event) -> None:
        """Dégradé vertical + étoiles scintillantes."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(6, 6, 17, 0))
        grad.setColorAt(0.15, QColor(6, 6, 17, 140))
        grad.setColorAt(0.4, QColor(6, 6, 17, 200))
        grad.setColorAt(1.0, QColor(6, 6, 17, 242))
        p.fillRect(self.rect(), grad)

        p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))
        p.drawLine(0, 0, w, 0)

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
        # L'utilisateur a vu le jeu → retirer le badge « NOUVEAU »
        game_id = self._items[index].game.id
        if self._manager.is_new(game_id):
            self._manager.mark_seen(game_id)
            self._items[index].refresh_state()
        self._update_depths()
        self.game_selected.emit(index)

    def select_next(self) -> None:
        if self._items:
            self.select((self._current_index + 1) % len(self._items))

    def select_prev(self) -> None:
        if self._items:
            self.select((self._current_index - 1) % len(self._items))

    def pause(self) -> None:
        if self._ticking:
            Ticker.instance().tick.disconnect(self._tick_stars)
            self._ticking = False

    def resume(self) -> None:
        if not self._ticking:
            Ticker.instance().tick.connect(self._tick_stars)
            self._ticking = True

    def refresh_indicators(self) -> None:
        for item in self._items:
            item.refresh_state()

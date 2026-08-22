"""Carrousel de jeux : bande horizontale avec étoiles scintillantes et transitions."""

import logging
import math
import random

from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.ui.carousel_item import CarouselItem
from src.ui.theme import accent_qcolor
from src.ui.ticker import Ticker
from src.ui import theme

log = logging.getLogger(__name__)

CAROUSEL_HEIGHT = 160
# Version compacte pour les fenêtres basses : 160 px, c'est un quart d'un
# écran de 660 px de haut, pris à la fiche de jeu.
CAROUSEL_HEIGHT_COMPACT = 124

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

    def current_game_id(self) -> str | None:
        """Id du jeu actuellement surligné (None si la bande est vide)."""
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index].game.id
        return None

    def set_games(self, games: list[GameData], selected_id: str | None = None) -> None:
        """Reconstruit la liste des items (appelé au reload du catalog).

        `selected_id` dit sur quel jeu poser la surbrillance ; à défaut on garde
        celui d'avant la reconstruction. Sans ça la bande repartait sur l'item 0
        pendant que la fiche, elle, gardait son jeu : au premier lancement suivi
        d'une mise à jour du catalogue, HP1 était surligné sous HP6 affiché.
        Et comme `select` sort tôt quand l'index ne change pas, cliquer sur HP1
        ne faisait alors plus rien — l'utilisateur était coincé.

        Aucun signal n'est émis, le contrat ne change pas : c'est à l'appelant
        de poser la fiche (voir `MainWindow._on_catalog_updated`).
        """
        vise = selected_id or self.current_game_id()

        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items.clear()

        for i, game in enumerate(games):
            item = CarouselItem(game, self._manager, self)
            item.clicked.connect(lambda idx=i: self.select(idx))
            self._items_layout.addWidget(item, alignment=Qt.AlignmentFlag.AlignBottom)
            self._items.append(item)

        # Le jeu visé peut avoir disparu du catalogue : repli sur le premier.
        self._current_index = next(
            (i for i, game in enumerate(games) if game.id == vise), 0)

        if self._items:
            self._items[self._current_index].selected = True
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

        # Fondu vers le bas, SANS trait de séparation. Un liseré blanc était
        # dessiné sur le bord haut : posé juste là où le dégradé est encore
        # transparent, il ressortait comme une couture nette dès que l'image de
        # fond était claire à cette hauteur (château d'Azkaban, par exemple).
        # Le dégradé sépare déjà les deux zones, en douceur.
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, theme.bg_qcolor(0))
        grad.setColorAt(0.30, theme.bg_qcolor(120))
        grad.setColorAt(0.60, theme.bg_qcolor(205))
        grad.setColorAt(1.0, theme.bg_qcolor(242))
        p.fillRect(self.rect(), grad)

        p.setPen(Qt.PenStyle.NoPen)
        for sx, sy, size, max_a, is_gold, phase in self._stars:
            twinkle = 0.4 + 0.6 * (math.sin(self._star_phase + phase) * 0.5 + 0.5)
            alpha = int(max_a * twinkle)
            if is_gold:
                p.setBrush(accent_qcolor(alpha))
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

    def set_compact(self, compact: bool) -> None:
        """Réduit la hauteur du carrousel quand la fenêtre manque de hauteur."""
        cible = CAROUSEL_HEIGHT_COMPACT if compact else CAROUSEL_HEIGHT
        if self.height() != cible:
            self.setFixedHeight(cible)

    def pause(self) -> None:
        if self._ticking:
            Ticker.detach(self._tick_stars)
            self._ticking = False

    def resume(self) -> None:
        if not self._ticking:
            Ticker.instance().tick.connect(self._tick_stars)
            self._ticking = True

    def refresh_indicators(self) -> None:
        for item in self._items:
            item.refresh_state()

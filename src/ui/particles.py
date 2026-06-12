"""Particules magiques flottantes — style prototype HTML.

Base : 35 particules subtiles (70 % accent du thème, 30 % argentées) qui
dérivent lentement vers le haut avec oscillation sinusoïdale et opacité
oscillante ; 15 % portent un glow.

Saisons (visuellement DISTINCTES, pas un simple recolorage) :
- halloween : braises — orange/violet, glow fréquent et large, scintillement
  rapide, montée plus vive ;
- noel : vrais flocons DESSINÉS (6 branches) qui tombent en tournoyant avec
  une large oscillation, plus nombreux.
"""

import logging
import math
import random

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from src.ui import theme
from src.ui.ticker import TICK_MS, Ticker

log = logging.getLogger(__name__)

PARTICLE_COUNT = 35
SEASON_COUNTS = {"halloween": 45, "noel": 55}
FPS_INTERVAL = TICK_MS  # cadence du ticker partagé (~30 FPS)


class _Particle:
    __slots__ = (
        "x", "y", "size", "speed_y", "speed_x", "phase", "phase_speed",
        "base_opacity", "opacity_variation", "color_rgb", "has_glow",
        "glow_size", "shape", "sway", "flicker", "rotation", "rot_speed",
    )

    def __init__(self, width: int, height: int, season: str = "aucune") -> None:
        self.x = random.uniform(0, max(width, 1))
        self.y = random.uniform(0, max(height, 1))
        self.size = random.uniform(1.5, 4.0)

        # Movement
        self.speed_y = random.uniform(-0.5, -0.2)   # drift up, faster
        self.speed_x = random.uniform(-0.2, 0.2)     # slight horizontal drift
        self.phase = random.uniform(0, math.tau)
        self.phase_speed = 0.008
        self.sway = 0.15          # amplitude de l'oscillation horizontale
        self.shape = "dot"
        self.rotation = 0.0
        self.rot_speed = 0.0
        self.flicker = 1.5        # vitesse de l'oscillation d'opacité

        # Oscillating opacity — more visible
        self.base_opacity = random.uniform(0.10, 0.35)
        self.opacity_variation = random.uniform(0.05, 0.15)

        # Color: 70% accent du thème, 30% silver
        if random.random() < 0.7:
            self.color_rgb = theme.current().accent_rgb
        else:
            self.color_rgb = (200, 200, 230)

        # 15% have glow — bigger
        self.has_glow = random.random() < 0.15
        self.glow_size = random.uniform(8, 14) if self.has_glow else 0

        # ── Variantes saisonnières ──
        if season == "halloween":
            # Braises : orange/violet, glow large et fréquent, scintillement
            # rapide, montée plus vive — ambiance feu de sorcière.
            roll = random.random()
            if roll < 0.60:
                self.color_rgb = (255, 140, 0)
            elif roll < 0.85:
                self.color_rgb = (150, 90, 220)
            else:
                self.color_rgb = (200, 200, 230)
            self.size = random.uniform(1.5, 3.5)
            self.speed_y = random.uniform(-0.75, -0.35)
            self.sway = 0.30
            self.flicker = random.uniform(3.0, 5.0)
            self.base_opacity = random.uniform(0.15, 0.40)
            self.opacity_variation = random.uniform(0.12, 0.28)
            self.has_glow = random.random() < 0.55
            self.glow_size = random.uniform(10, 18) if self.has_glow else 0
        elif season == "noel":
            # Flocons : DESSINÉS (6 branches), blancs/bleutés, qui TOMBENT en
            # tournoyant avec une large oscillation.
            self.color_rgb = (235, 240, 255) if random.random() < 0.8 else (200, 210, 240)
            self.speed_y = random.uniform(0.25, 0.6)
            self.sway = 0.50
            self.phase_speed = 0.012
            if random.random() < 0.75:
                self.shape = "flake"
                self.size = random.uniform(2.5, 5.0)   # longueur d'une branche
                self.rotation = random.uniform(0, 360)
                self.rot_speed = random.uniform(-0.8, 0.8)
                self.base_opacity = random.uniform(0.20, 0.45)
            else:
                self.size = random.uniform(1.2, 2.5)    # poudreuse en fond
            self.has_glow = random.random() < 0.10
            self.glow_size = random.uniform(8, 14) if self.has_glow else 0


class ParticleOverlay(QWidget):
    """Overlay transparent avec particules subtiles style prototype HTML."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._particles: list[_Particle] = []
        self._time = 0.0
        self._ticking = False
        self._season = "aucune"

        self.resume()

        log.debug("[FX] ParticleOverlay — %d particules, ticker partagé, glow+oscillation", PARTICLE_COUNT)

    def apply_season(self, season: str) -> None:
        """Change la saison EN DIRECT : les particules sont re-semées au tick suivant."""
        if season == self._season:
            return
        self._season = season
        self._particles.clear()
        self.update()
        log.info("Particules saisonnières : %s", season)

    def _target_count(self) -> int:
        return SEASON_COUNTS.get(self._season, PARTICLE_COUNT)

    def _ensure_particles(self) -> None:
        w, h = self.width(), self.height()
        while len(self._particles) < self._target_count():
            self._particles.append(_Particle(w, h, self._season))

    def _advance(self) -> None:
        if not self.isVisible():
            return
        self._ensure_particles()
        self._time += FPS_INTERVAL / 1000.0
        h = self.height()
        w = self.width()
        for pt in self._particles:
            # Vertical drift (upward)
            pt.y += pt.speed_y
            # Horizontal: slight drift + sinusoidal oscillation
            pt.x += pt.speed_x + math.sin(pt.phase) * pt.sway
            pt.phase += pt.phase_speed
            pt.rotation += pt.rot_speed

            # Wrap around (les flocons de Noël descendent → wrap dans les deux sens)
            if pt.y < -20:
                pt.y = h + 10
                pt.x = random.uniform(0, max(w, 1))
            elif pt.y > h + 20:
                pt.y = -10
                pt.x = random.uniform(0, max(w, 1))
            if pt.x < -20:
                pt.x = w + 10
            elif pt.x > w + 20:
                pt.x = -10
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        for pt in self._particles:
            # Oscillating opacity (flicker rapide pour les braises d'halloween)
            opacity = pt.base_opacity + math.sin(
                self._time * pt.flicker + pt.phase
            ) * pt.opacity_variation
            opacity = max(0.05, min(opacity, 0.55))
            alpha = int(opacity * 255)

            r, g, b = pt.color_rgb

            # ── Glow (drawn behind, larger and more transparent) ──
            if pt.has_glow:
                glow_alpha = max(int(alpha * 0.30), 3)
                gs = pt.glow_size
                grad = QRadialGradient(pt.x, pt.y, gs)
                grad.setColorAt(0, QColor(r, g, b, glow_alpha))
                grad.setColorAt(1, QColor(r, g, b, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(grad)
                p.drawEllipse(QRectF(pt.x - gs, pt.y - gs, gs * 2, gs * 2))

            if pt.shape == "flake":
                self._paint_flake(p, pt, QColor(r, g, b, alpha))
                continue

            # ── Main particle (dot) ──
            color = QColor(r, g, b, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            s = pt.size
            p.drawEllipse(QRectF(pt.x - s, pt.y - s, s * 2, s * 2))

        p.end()

    @staticmethod
    def _paint_flake(p: QPainter, pt: _Particle, color: QColor) -> None:
        """Flocon 6 branches : 3 segments croisés à 60° + pointe centrale."""
        p.save()
        p.translate(pt.x, pt.y)
        p.rotate(pt.rotation)
        p.setPen(QPen(color, 1.0))
        s = pt.size
        for angle in (0.0, 60.0, 120.0):
            rad = math.radians(angle)
            dx, dy = math.cos(rad) * s, math.sin(rad) * s
            p.drawLine(QPointF(-dx, -dy), QPointF(dx, dy))
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(-0.8, -0.8, 1.6, 1.6))
        p.restore()

    def showEvent(self, event) -> None:
        self.resume()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self.pause()
        super().hideEvent(event)

    def pause(self) -> None:
        if self._ticking:
            Ticker.instance().tick.disconnect(self._advance)
            self._ticking = False

    def resume(self) -> None:
        if not self._ticking:
            Ticker.instance().tick.connect(self._advance)
            self._ticking = True

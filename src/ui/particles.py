"""Particules magiques flottantes — style prototype HTML.

35 particules subtiles : 70% dorées, 30% argentées.
Mouvement : dérive lente vers le haut + oscillation sinusoïdale horizontale.
15% ont un glow (cercle flou derrière).
Opacité individuelle oscillante (phase sinusoïdale propre).
"""

import logging
import math
import random

log = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget

PARTICLE_COUNT = 35
FPS_INTERVAL = 33  # ~30 FPS


class _Particle:
    __slots__ = (
        "x", "y", "size", "speed_y", "speed_x", "phase", "phase_speed",
        "base_opacity", "opacity_variation", "color_rgb", "has_glow",
        "glow_size",
    )

    def __init__(self, width: int, height: int) -> None:
        self.x = random.uniform(0, max(width, 1))
        self.y = random.uniform(0, max(height, 1))
        self.size = random.uniform(1.5, 4.0)

        # Movement
        self.speed_y = random.uniform(-0.5, -0.2)   # drift up, faster
        self.speed_x = random.uniform(-0.2, 0.2)     # slight horizontal drift
        self.phase = random.uniform(0, math.tau)
        self.phase_speed = 0.008

        # Oscillating opacity — more visible
        self.base_opacity = random.uniform(0.10, 0.35)
        self.opacity_variation = random.uniform(0.05, 0.15)

        # Color: 70% gold, 30% silver
        if random.random() < 0.7:
            self.color_rgb = (212, 160, 23)
        else:
            self.color_rgb = (200, 200, 230)

        # 15% have glow — bigger
        self.has_glow = random.random() < 0.15
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

        self._timer = QTimer(self)
        self._timer.setInterval(FPS_INTERVAL)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

        log.debug("[FX] ParticleOverlay — %d particules, 30 FPS, glow+oscillation", PARTICLE_COUNT)

    def _ensure_particles(self) -> None:
        w, h = self.width(), self.height()
        while len(self._particles) < PARTICLE_COUNT:
            self._particles.append(_Particle(w, h))

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
            pt.x += pt.speed_x + math.sin(pt.phase) * 0.15
            pt.phase += pt.phase_speed

            # Wrap around
            if pt.y < -20:
                pt.y = h + 10
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
            # Oscillating opacity
            opacity = pt.base_opacity + math.sin(
                self._time * 1.5 + pt.phase
            ) * pt.opacity_variation
            opacity = max(0.05, min(opacity, 0.50))
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

            # ── Main particle ──
            color = QColor(r, g, b, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            s = pt.size
            p.drawEllipse(QRectF(pt.x - s, pt.y - s, s * 2, s * 2))

        p.end()

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        self._timer.start()

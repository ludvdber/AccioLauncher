"""Boutons entièrement peints — style launcher moderne.

Deux variantes :
- "filled" : fond dégradé subtil (pour le bouton principal JOUER)
- "outline" : fond semi-transparent + bordure colorée (pour TELECHARGER)

Pas de QGraphicsEffect — tout est dans paintEvent.
"""

import logging
import math

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import (
    QColor, QEnterEvent, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PyQt6.QtWidgets import QPushButton, QWidget

log = logging.getLogger(__name__)


class GlowButton(QPushButton):
    """Bouton avec glow pulsant et shimmer — deux styles : filled / outline."""

    def __init__(
        self,
        text: str,
        glow_color: str = "#d4a017",
        style: str = "filled",
        bg_stops: tuple[str, str, str] | None = None,
        text_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._style = style  # "filled" or "outline"
        self._glow_color = QColor(glow_color)

        if bg_stops:
            self._bg_top = QColor(bg_stops[0])
            self._bg_mid = QColor(bg_stops[1])
            self._bg_bot = QColor(bg_stops[2])
        else:
            self._bg_top = QColor("#f0d060")
            self._bg_mid = QColor("#d4a017")
            self._bg_bot = QColor("#9a7209")

        if text_color:
            self._text_color = QColor(text_color)
        elif style == "outline":
            self._text_color = QColor(glow_color)
        else:
            self._text_color = QColor("#ffffff")

        self._glow_phase = 0.0
        self._glow_alpha = 40
        self._shimmer_offset = -1.0
        self._hovered = False
        self._pressed = False

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._animate)
        self._timer.start()

        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        log.debug("[FX] GlowButton '%s' — style=%s, glow=%s", text, style, glow_color)

    def _animate(self) -> None:
        if not self.isVisible():
            return
        self._glow_phase += 0.025
        t = (math.sin(self._glow_phase) + 1) / 2

        if self._hovered:
            self._glow_alpha = int(80 + t * 60)
        else:
            self._glow_alpha = int(30 + t * 30)

        self._shimmer_offset += 0.02
        if self._shimmer_offset > 2.5:
            self._shimmer_offset = -1.0

        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        radius = 8.0

        btn_rect = QRectF(0, 0, w, h)
        clip = QPainterPath()
        clip.addRoundedRect(btn_rect, radius, radius)

        # ── Glow externe subtil ──
        r, g, b = self._glow_color.red(), self._glow_color.green(), self._glow_color.blue()
        for i in range(3):
            spread = (i + 1) * 3
            alpha = max(self._glow_alpha // (i + 2), 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(r, g, b, alpha))
            p.drawRoundedRect(
                QRectF(-spread, -spread + 1, w + spread * 2, h + spread * 2),
                radius + spread, radius + spread,
            )

        p.setClipPath(clip)

        if self._style == "filled":
            self._paint_filled(p, w, h, btn_rect)
        else:
            self._paint_outline(p, w, h, btn_rect)

        # ── Shimmer traversant ──
        if -0.5 < self._shimmer_offset < 1.5:
            offset_px = self._shimmer_offset * w
            shimmer = QLinearGradient(offset_px - 50, 0, offset_px + 50, h)
            alpha = 35 if self._style == "filled" else 18
            shimmer.setColorAt(0, QColor(255, 255, 255, 0))
            shimmer.setColorAt(0.4, QColor(255, 255, 255, alpha))
            shimmer.setColorAt(0.5, QColor(255, 255, 255, int(alpha * 1.4)))
            shimmer.setColorAt(0.6, QColor(255, 255, 255, alpha))
            shimmer.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(btn_rect, shimmer)

        p.setClipping(False)

        # ── Bordure ──
        if self._style == "filled":
            border_alpha = 70 if self._hovered else 35
            p.setPen(QPen(QColor(255, 255, 255, border_alpha), 1.0))
        else:
            r, g, b = self._glow_color.red(), self._glow_color.green(), self._glow_color.blue()
            border_alpha = 180 if self._hovered else 120
            p.setPen(QPen(QColor(r, g, b, border_alpha), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)

        # ── Texte ──
        tc = QColor(self._text_color)
        if self._style == "outline" and self._hovered:
            tc = tc.lighter(130)
        p.setPen(tc)
        p.setFont(self.font())
        p.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, self.text())

        p.end()

    def _paint_filled(self, p: QPainter, w: int, h: int, rect: QRectF) -> None:
        """Fond dégradé plein — pour le bouton principal (JOUER)."""
        bg = QLinearGradient(0, 0, 0, h)
        if self._pressed:
            bg.setColorAt(0, self._bg_bot)
            bg.setColorAt(1, self._bg_bot.darker(130))
        elif self._hovered:
            bg.setColorAt(0, self._bg_top.lighter(112))
            bg.setColorAt(0.5, self._bg_mid.lighter(108))
            bg.setColorAt(1, self._bg_bot)
        else:
            bg.setColorAt(0, self._bg_top)
            bg.setColorAt(0.5, self._bg_mid)
            bg.setColorAt(1, self._bg_bot)
        p.fillRect(rect, bg)

        # Highlight haut
        hl = QLinearGradient(0, 0, 0, h * 0.45)
        hl.setColorAt(0, QColor(255, 255, 255, 50 if self._hovered else 30))
        hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(0, 0, w, h * 0.45), hl)

    def _paint_outline(self, p: QPainter, w: int, h: int, rect: QRectF) -> None:
        """Fond semi-transparent — pour TELECHARGER et actions secondaires."""
        if self._pressed:
            p.fillRect(rect, QColor(255, 255, 255, 12))
        elif self._hovered:
            r, g, b = self._glow_color.red(), self._glow_color.green(), self._glow_color.blue()
            p.fillRect(rect, QColor(r, g, b, 20))
        else:
            p.fillRect(rect, QColor(255, 255, 255, 6))

    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

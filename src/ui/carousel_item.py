"""Miniature d'un jeu dans le carrousel — reflet, profondeur, badges."""

import re

from PyQt6.QtCore import (
    Qt, pyqtSignal, QRect, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTransform,
)
from PyQt6.QtWidgets import QWidget

from src.core.config import ASSETS_DIR
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor
from src.ui import theme

THUMB_W = 90
THUMB_H = 125
REFLECTION_RATIO = 0.20
REFLECTION_OPACITY = 0.06

_ARABIC_TO_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
                     7: "VII", 8: "VIII", 9: "IX", 10: "X"}


def _game_roman(game_id: str) -> str:
    """Extrait le chiffre romain depuis l'id du jeu (ex: 'hp3' → 'III')."""
    m = re.search(r"(\d+)$", game_id)
    if m:
        n = int(m.group(1))
        return _ARABIC_TO_ROMAN.get(n, str(n))
    return game_id.upper()


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
        self._anim_scale = 0.9
        self._anim_opacity = 0.45

        self._reflection_cache: QPixmap | None = None
        self._reflection_cache_size: tuple[int, int] = (0, 0)
        self._cached_installed: bool = False
        self._cached_has_update: bool = False
        self._cached_version: str = ""
        self._cached_is_new: bool = False
        self._cached_coming_soon: bool = False

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

    def refresh_state(self) -> None:
        """Recharge les indicateurs (installé, update, version, nouveau) depuis le manager."""
        self._cached_installed = self.manager.is_installed(self.game.id)
        self._cached_has_update = self.manager.has_update(self.game.id)
        self._cached_version = self.manager.installed_version(self.game.id) or ""
        self._cached_is_new = self.manager.is_new(self.game.id)
        # Jeu annoncé dont aucune archive n'est publiée : signalé dans la
        # vignette pour que l'utilisateur le sache AVANT de cliquer.
        self._cached_coming_soon = not self.game.is_downloadable
        self.update()

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
            p.setPen(QPen(accent_qcolor(60), 1.0))
            p.drawRoundedRect(x_off, y_off, w, h, radius, radius)

            p.setOpacity(1.0)
            p.setPen(accent_qcolor(180))
            p.setFont(QFont("Segoe UI Emoji", 20))
            p.drawText(QRect(x_off, y_off - 10, w, h), Qt.AlignmentFlag.AlignCenter, "⚡")

            roman = _game_roman(self.game.id)
            p.setPen(accent_qcolor(140))
            p.setFont(cinzel(12, bold=True))
            p.drawText(QRect(x_off, y_off + 22, w, h), Qt.AlignmentFlag.AlignCenter, roman)
            p.setOpacity(eff_opacity)

        if self._selected:
            p.setOpacity(1.0)
            for i in range(3):
                glow = accent_qcolor(25 - i * 7)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                off = (i + 1) * 3
                p.drawRoundedRect(x_off - off, y_off - off, w + off * 2, h + off * 2, radius + off, radius + off)

            pen = QPen(accent_qcolor(), 2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(x_off + 1, y_off + 1, w - 2, h - 2, radius, radius)

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
            fade.setColorAt(0, theme.bg_qcolor(80))
            fade.setColorAt(1, theme.bg_qcolor(255))
            p.fillRect(x_off, ref_y, w, ref_h, fade)

        if self._cached_installed:
            p.setOpacity(1.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2ecc71"))
            p.drawEllipse(x_off + w - 14, y_off + h - 14, 10, 10)

            ver_text = f"v{self._cached_version}" if self._cached_version else ""
            if ver_text:
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

        if self._cached_has_update:
            p.setOpacity(1.0)
            badge_size = 18
            bx = x_off + w - badge_size - 2
            by = y_off + 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent_qcolor(220))
            p.drawRoundedRect(QRectF(bx, by, badge_size, badge_size), 4, 4)
            p.setPen(QColor(255, 255, 255, 240))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            p.drawText(QRectF(bx, by, badge_size, badge_size), Qt.AlignmentFlag.AlignCenter, "↑")

        if self._cached_is_new and not self._cached_installed:
            # Ruban « NOUVEAU » en haut à gauche (jeu apparu via update du catalogue)
            p.setOpacity(1.0)
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            fm = p.fontMetrics()
            text = "NOUVEAU"
            tw = fm.horizontalAdvance(text)
            bx, by = x_off + 3, y_off + 3
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent_qcolor(235))
            p.drawRoundedRect(QRectF(bx, by, tw + 10, fm.height() + 3), 3, 3)
            p.setPen(QColor("#060611"))
            p.drawText(QRectF(bx, by, tw + 10, fm.height() + 3),
                       Qt.AlignmentFlag.AlignCenter, text)

        if self._cached_coming_soon:
            # Voile sombre + mention discrète : la vignette reste lisible et
            # attractive (c'est un jeu à venir, pas une erreur), mais on ne
            # laisse pas croire qu'elle est jouable.
            p.setOpacity(1.0)
            p.fillRect(x_off, y_off, w, h, theme.bg_qcolor(120))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            fm = p.fontMetrics()
            text = "BIENTÔT"
            tw = fm.horizontalAdvance(text)
            bw, bh = tw + 10, fm.height() + 3
            bx = x_off + (w - bw) // 2
            by = y_off + (h - bh) // 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.bg_qcolor(200))
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 3, 3)
            p.setPen(QColor(200, 200, 220, 230))
            p.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, text)

        p.end()

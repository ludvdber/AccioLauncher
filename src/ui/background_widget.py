"""BackgroundWidget — image de fond avec zoom cinématique et parallaxe."""

import logging
import math
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, pyqtProperty
from PyQt6.QtGui import (
    QColor, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from src.ui.ticker import TICK_MS, Ticker
from src.ui import theme

log = logging.getLogger(__name__)

# Hauteur du raccord entre le bas de la fiche et le haut du carrousel.
# Assez long pour que la transition soit invisible, assez court pour ne pas
# manger l'illustration — à cette hauteur elle est de toute façon déjà noyée
# par le dégradé bas.
_RACCORD_PX = 90
# Débord opaque sous le bord bas, en pixels logiques. Deux suffisent : le
# raccord est déjà saturé à bg_qcolor(255) bien avant, donc à 100 % ce débord
# repeint du fond sur du fond. Il n'existe que pour les échelles fractionnaires.
_DEBORD_PX = 2

# Zoom cinématique : bornes et pas par tick du Ticker (~30 Hz), pour une jambe
# de 8 s aller et 8 s retour — exactement l'ancien cycle de 16 s.
_ZOOM_MIN = 1.0
_ZOOM_MAX = 1.05
_ZOOM_LEG_MS = 8000
_ZOOM_STEP = TICK_MS / _ZOOM_LEG_MS


class BackgroundWidget(QWidget):
    """Image de fond avec zoom lent continu, parallaxe souris,
    vignette renforcée, overlay et dégradé bas 75%.
    Peut aussi afficher des frames vidéo via QVideoSink."""

    PARALLAX_MAX_X = 20
    PARALLAX_MAX_Y = 12
    MAX_SCALE = 1.18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._prepared: QPixmap | None = None
        self._prepared_for: tuple[int, int] = (0, 0)
        self._opacity = 1.0
        self._video_frame: QImage | None = None
        # Cross-fade entre jeux : snapshot de l'ancien rendu peint sous le
        # nouveau fond pendant son fade-in (pas de coupe noire).
        self._old_frame: QPixmap | None = None
        # Overlays statiques (gradients + vignette + voile) pré-rendus — ils ne
        # dépendent que de la taille ; les rebâtir à chaque frame coûtait cher.
        self._overlay_cache: QPixmap | None = None
        self._overlay_for: tuple[int, int] = (0, 0)

        # Zoom cinématique continu (1.0 → 1.05 → 1.0, cycle 16 s), cadencé par
        # le Ticker partagé. Il tournait avant sur une QPropertyAnimation, donc
        # à la cadence de l'horloge d'animation de Qt (~60 Hz) alors que tout le
        # reste de la décoration est à 30 Hz : c'était le premier poste de
        # peinture au repos (88 ms/s à 1200×800, une fenêtre pleine repeinte à
        # chaque frame). La progression se fait par PAS FIXE et non d'après
        # l'horloge : quand le Ticker s'arrête (fenêtre inactive, tray), le zoom
        # reprend exactement où il en était, sans saut ni comptabilité de temps.
        self._zoom = 1.0
        self._zoom_forward = True
        self._zoom_phase = 0.0
        self._zoom_ticking = False
        self._zoom_running = False

        # Parallaxe souris — lerp doux cadencé par le Ticker partagé (~30 FPS),
        # abonnement à la demande (set_parallax_target) et désabonnement une fois
        # la cible atteinte. Les events souris (jusqu'à 1000 Hz) ne font que
        # déplacer la cible, jamais repeindre.
        self._parallax_tx = 0.0
        self._parallax_ty = 0.0
        self._parallax_cx = 0.0
        self._parallax_cy = 0.0
        self._parallax_ticking = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        log.debug("[FX] BackgroundWidget — zoom 16s, parallaxe ±20/±12, gradient 75%%")

    # ── Propriétés Qt animables ──

    def _get_bg_opacity(self) -> float:
        return self._opacity

    def _set_bg_opacity(self, value: float) -> None:
        self._opacity = value
        if value >= 0.999 and self._old_frame is not None:
            self._old_frame = None  # cross-fade terminé, libérer le snapshot
        self.update()

    bg_opacity = pyqtProperty(float, _get_bg_opacity, _set_bg_opacity)

    def _get_zoom(self) -> float:
        return self._zoom

    def _set_zoom(self, value: float) -> None:
        self._zoom = value
        self.update()

    zoom_factor = pyqtProperty(float, _get_zoom, _set_zoom)

    def start_zoom_loop(self) -> None:
        self._zoom = _ZOOM_MIN
        self._zoom_forward = True
        self._zoom_phase = 0.0
        self._zoom_running = True
        self._set_zoom_ticking(True)

    def _set_zoom_ticking(self, on: bool) -> None:
        if on and not self._zoom_ticking:
            Ticker.instance().tick.connect(self._advance_zoom)
            self._zoom_ticking = True
        elif not on and self._zoom_ticking:
            Ticker.detach(self._advance_zoom)
            self._zoom_ticking = False

    def _advance_zoom(self) -> None:
        """Un pas de zoom, courbe InOutSine identique à l'ancienne animation."""
        self._zoom_phase += _ZOOM_STEP
        if self._zoom_phase >= 1.0:
            self._zoom_phase = 0.0
            self._zoom_forward = not self._zoom_forward
        # InOutSine : 0.5 - 0.5*cos(pi*t), même profil que QEasingCurve.InOutSine.
        eased = 0.5 - 0.5 * math.cos(math.pi * self._zoom_phase)
        depart, arrivee = ((_ZOOM_MIN, _ZOOM_MAX) if self._zoom_forward
                           else (_ZOOM_MAX, _ZOOM_MIN))
        self._zoom = depart + (arrivee - depart) * eased
        self.update()

    def set_parallax_target(self, mouse_x: float, mouse_y: float,
                            win_w: float, win_h: float) -> None:
        if win_w <= 0 or win_h <= 0:
            return
        center_x = win_w / 2
        center_y = win_h / 2
        self._parallax_tx = -(mouse_x - center_x) / win_w * self.PARALLAX_MAX_X
        self._parallax_ty = -(mouse_y - center_y) / win_h * self.PARALLAX_MAX_Y
        self._set_parallax_ticking(True)

    def _set_parallax_ticking(self, on: bool) -> None:
        if on and not self._parallax_ticking:
            Ticker.instance().tick.connect(self._update_parallax)
            self._parallax_ticking = True
        elif not on and self._parallax_ticking:
            Ticker.detach(self._update_parallax)
            self._parallax_ticking = False

    def _update_parallax(self) -> None:
        dx = self._parallax_tx - self._parallax_cx
        dy = self._parallax_ty - self._parallax_cy
        if abs(dx) < 0.05 and abs(dy) < 0.05:
            self._set_parallax_ticking(False)
            return
        # 0.10 par tick à 30 FPS ≈ l'ancien 0.05 par frame à 60 FPS (même inertie)
        self._parallax_cx += dx * 0.10
        self._parallax_cy += dy * 0.10
        self.update()

    def pause(self) -> None:
        self._set_parallax_ticking(False)
        self._set_zoom_ticking(False)

    def resume(self) -> None:
        if self._zoom_running:
            self._set_zoom_ticking(True)
        # Reprendre le lerp parallaxe si la cible n'est pas atteinte
        dx = self._parallax_tx - self._parallax_cx
        dy = self._parallax_ty - self._parallax_cy
        if abs(dx) >= 0.05 or abs(dy) >= 0.05:
            self._set_parallax_ticking(True)

    def invalidate_cache(self) -> None:
        """Force le recalcul du pixmap préparé et des overlays au prochain paintEvent."""
        self._prepared = None
        self._prepared_for = (0, 0)
        self._overlay_cache = None
        self._overlay_for = (0, 0)
        self._old_frame = None  # un resize pendant un cross-fade invaliderait le snapshot

    def begin_crossfade(self) -> None:
        """Capture le rendu actuel (image OU frame vidéo) comme sous-couche.

        À appeler AVANT de changer d'image : le nouveau fond fade par-dessus
        (bg_opacity 0 → 1) au lieu d'apparaître sur fond noir.
        """
        if self.width() > 0 and self.height() > 0 and (
                self._prepared is not None or self._video_frame is not None):
            self._old_frame = self.grab()
        else:
            self._old_frame = None

    def set_video_frame(self, image: QImage | None) -> None:
        """Reçoit une frame vidéo à peindre à la place de l'image statique."""
        self._video_frame = image
        self.update()

    def clear_video(self) -> None:
        """Arrête d'afficher la vidéo, retour à l'image statique."""
        self._video_frame = None
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

        # Fond de base — teinté par le thème. En dur, il restait bleu nuit sous
        # les voiles verts de Serpentard partout où l'illustration ne couvre pas.
        p.fillRect(rect, theme.bg_qcolor(255))
        if self._old_frame is not None:
            # Sous-couche du cross-fade : l'ancien rendu reste visible tant que
            # le nouveau fond n'est pas pleinement opaque.
            p.drawPixmap(0, 0, self._old_frame)
        p.setOpacity(self._opacity)

        if self._video_frame is not None and w > 0 and h > 0:
            # Peindre la frame vidéo en cover (aspect ratio)
            vw, vh = self._video_frame.width(), self._video_frame.height()
            if vw > 0 and vh > 0:
                widget_ar = w / h
                video_ar = vw / vh
                if widget_ar > video_ar:
                    draw_w = w
                    draw_h = w / video_ar
                else:
                    draw_h = h
                    draw_w = h * video_ar
                dx = (w - draw_w) / 2
                dy = (h - draw_h) / 2
                p.drawImage(QRectF(dx, dy, draw_w, draw_h), self._video_frame)
        else:
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

            # Overlay brightness (seulement sur l'image statique)
            p.fillRect(rect, QColor(0, 0, 0, 77))

        # ── Permanent elements (opacity 1.0) — pré-rendus dans un pixmap ──
        p.setOpacity(1.0)
        self._ensure_overlay(w, h)
        if self._overlay_cache is not None:
            p.drawPixmap(0, 0, self._overlay_cache)

        # Bord bas — atteindre le pixel PHYSIQUE, pas le pixel logique.
        # Sur un écran à 125 %, le bas du widget tombe sur un demi-pixel
        # (624 px logiques posés à 47,5). L'illustration, peinte en QRectF avec
        # antialiasing, déborde alors d'une rangée physique ; l'overlay opaque,
        # lui, est posé depuis un pixmap à coordonnées entières et ne déborde
        # pas. Il restait donc UNE rangée d'illustration nue entre la fiche et
        # le carrousel — mesurée rgb(6,22,45) contre rgb(6,6,17), et rouge vif
        # avec une illustration rouge de test. Invisible à 100 %, permanente à
        # 125 %. On peint volontairement AU-DELÀ du bord : Qt découpe au rect
        # réel du widget, donc le débord couvre la rangée quelle que soit la
        # façon dont l'échelle est arrondie.
        p.fillRect(QRectF(0, h - _DEBORD_PX, w, _DEBORD_PX * 2),
                   theme.bg_qcolor(255))

        p.end()

    def _ensure_overlay(self, w: int, h: int) -> None:
        """(Re)construit le pixmap des overlays statiques si la taille a changé."""
        if w <= 0 or h <= 0:
            return
        if self._overlay_cache is not None and self._overlay_for == (w, h):
            return

        pix = QPixmap(w, h)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        rect = pix.rect()

        # Subtle dark blue overlay
        p.fillRect(rect, theme.bg_qcolor(30))

        # Top gradient (title bar area)
        grad_top = QLinearGradient(0, 0, 0, h * 0.08)
        grad_top.setColorAt(0, theme.bg_qcolor(160))
        grad_top.setColorAt(1, theme.bg_qcolor(0))
        p.fillRect(rect, grad_top)

        # Bottom gradient — 75% height, very strong
        grad = QLinearGradient(0, h * 0.25, 0, h)
        grad.setColorAt(0.0, theme.bg_qcolor(0))
        grad.setColorAt(0.35, theme.bg_qcolor(38))
        grad.setColorAt(0.55, theme.bg_qcolor(128))
        grad.setColorAt(0.75, theme.bg_qcolor(217))
        grad.setColorAt(1.0, theme.bg_qcolor(247))
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

        # Voile gauche — simple dégradé horizontal, pas de blur
        veil_grad = QLinearGradient(0, 0, w, 0)
        veil_grad.setColorAt(0.0, theme.bg_qcolor(200))
        veil_grad.setColorAt(0.25, theme.bg_qcolor(150))
        veil_grad.setColorAt(0.40, theme.bg_qcolor(80))
        veil_grad.setColorAt(0.55, theme.bg_qcolor(20))
        veil_grad.setColorAt(0.72, theme.bg_qcolor(0))
        p.fillRect(rect, veil_grad)

        # Raccord avec le carrousel — EN DERNIER, après la vignette.
        # Le carrousel est un widget FRÈRE : il ne montre pas l'illustration,
        # et là où son dégradé est encore transparent on voit le fond plat du
        # conteneur. Or le dégradé bas s'arrêtait à alpha 247 et la vignette
        # radiale rajoutait du noir par-dessus : la dernière ligne de la fiche
        # valait rgb(3,3,8) contre rgb(6,6,17) pour la première du carrousel —
        # un trait CLAIR sur toute la largeur, mesuré identique sur les 8 jeux.
        # Terminer exactement sur `bg_qcolor(255)` supprime la marche. La
        # vignette doit passer avant, sinon elle re-creuse le raccord.
        raccord = QLinearGradient(0, h - _RACCORD_PX, 0, h)
        raccord.setColorAt(0.0, theme.bg_qcolor(0))
        # Saturation AVANT le bord : une rampe qui atteint 255 pile au dernier
        # pixel s'y interpole à ~252, et il restait un niveau d'écart par canal.
        raccord.setColorAt(0.92, theme.bg_qcolor(255))
        raccord.setColorAt(1.0, theme.bg_qcolor(255))
        p.fillRect(QRectF(0, h - _RACCORD_PX, w, _RACCORD_PX), raccord)

        p.end()
        self._overlay_cache = pix
        self._overlay_for = (w, h)

"""Particules magiques flottantes — le rendu de l'Almanach.

Ce module ne décide de RIEN : il reçoit un `season.Profil` (des nombres purs,
testables sans Qt) et sait le peindre. Les ambiances, leurs couleurs et leurs
dates vivent dans `season.py`.

Le partage est né du besoin. Les deux premières ambiances tenaient dans une
cascade de `if season == …` au milieu du constructeur d'une particule ; à cinq,
cette cascade devenait un mur, et rien n'y était vérifiable sans construire un
widget. Ici on ne trouve donc plus que les QUATRE gestes de peinture — point,
flocon, enveloppe, flamme — et la mécanique de déplacement, commune à tous.

Formes :
- `point` — le fond ordinaire, et la poudreuse derrière les autres formes ;
- `flocon` — six branches dessinées, qui tournoient (Noël) ;
- `enveloppe` — la lettre de Poudlard, cachet de cire à l'accent du THÈME,
  donc à la couleur de la maison de l'utilisateur (rentrée) ;
- `flamme` — une goutte inversée à cœur clair, posée dans un large halo : ce
  sont les bougies de la Grande Salle, et c'est le HALO qui fait la scène.
"""

import logging
import math
import random

from PyQt6.QtCore import Qt, QPointF, QRect, QRectF
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QRadialGradient, QRegion,
)
from PyQt6.QtWidgets import QWidget

from src.ui import decor, theme
from src.core.season import Profil, profil as profil_de
from src.ui.ticker import TICK_MS, Ticker

log = logging.getLogger(__name__)

FPS_INTERVAL = TICK_MS  # cadence du ticker partagé (~30 FPS)
# Marge autour d'une particule dans sa zone sale : antialiasing + le
# déplacement d'un tick (< 1 px). Généreuse à dessein — deux pixels de trop
# ne coûtent rien, deux de moins laisseraient une trainée.
_MARGE_ZONE = 3


def _tirer(intervalle: tuple[float, float]) -> float:
    return random.uniform(*intervalle)


def _tirer_couleur(palette) -> tuple[int, int, int]:
    """Tire une couleur de la palette pondérée ; `None` = accent du thème.

    Le repli sur l'accent n'est pas une précaution : c'est ce qui fait que les
    particules ordinaires restent vertes chez Serpentard et or chez Poudlard.
    """
    tirage = random.random()
    cumul = 0.0
    for couleur, part in palette:
        cumul += part
        if tirage <= cumul:
            return couleur if couleur is not None else theme.current().accent_rgb
    couleur = palette[-1][0] if palette else None
    return couleur if couleur is not None else theme.current().accent_rgb


class _Particle:
    __slots__ = (
        "x", "y", "size", "speed_y", "speed_x", "phase", "phase_speed",
        "base_opacity", "opacity_variation", "color_rgb", "has_glow",
        "glow_size", "shape", "sway", "flicker", "rotation", "rot_speed",
    )

    def __init__(self, width: int, height: int, profil: Profil) -> None:
        self.x = random.uniform(0, max(width, 1))
        self.y = random.uniform(0, max(height, 1))

        # La forme n'est portée que par une PART des particules : le reste
        # fait le fond (la poudreuse derrière les flocons, les escarbilles
        # derrière les lettres). Sans ce fond, une ambiance à forme paraît
        # vide entre ses éléments.
        porte_la_forme = random.random() < profil.part_forme
        self.shape = profil.forme if porte_la_forme else "point"
        if porte_la_forme or profil.taille_fond is None:
            self.size = _tirer(profil.taille)
        else:
            self.size = _tirer(profil.taille_fond)

        self.speed_y = _tirer(profil.vitesse_y)
        self.speed_x = _tirer(profil.derive_x)
        self.sway = profil.oscillation
        self.phase = random.uniform(0, math.tau)
        self.phase_speed = profil.vitesse_phase
        self.rotation = random.uniform(0, 360) if porte_la_forme else 0.0
        self.rot_speed = _tirer(profil.vitesse_rotation) if porte_la_forme else 0.0
        self.flicker = _tirer(profil.scintillement)

        self.base_opacity = _tirer(profil.opacite)
        self.opacity_variation = _tirer(profil.variation)
        self.color_rgb = _tirer_couleur(profil.palette)

        self.has_glow = random.random() < profil.proba_halo
        self.glow_size = _tirer(profil.halo) if self.has_glow else 0.0


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
        self._profil = profil_de("aucune")

        self.resume()

    def apply_season(self, season: str) -> None:
        """Change l'ambiance EN DIRECT : les particules sont re-semées au tick suivant."""
        if season == self._season:
            return
        self._season = season
        self._profil = profil_de(season)
        self._particles.clear()
        self.update()
        log.info("Particules saisonnières : %s", season)

    def _target_count(self) -> int:
        return self._profil.nombre

    def _ensure_particles(self) -> None:
        w, h = self.width(), self.height()
        while len(self._particles) < self._target_count():
            self._particles.append(_Particle(w, h, self._profil))

    @staticmethod
    def _zone(pt: "_Particle") -> QRect:
        """Rectangle sale d'une particule : sa taille, son halo, et une marge.

        La marge couvre l'antialiasing et le déplacement d'un tick (moins de
        1 px), pour qu'aucune trainée ne subsiste hors de la zone repeinte.
        Les formes ÉTENDUES (enveloppe, flamme) débordent du rayon `size` :
        `_ETALEMENT` le rattrape, sinon une lettre laisserait sa trace.
        """
        rayon = max(pt.size * _ETALEMENT.get(pt.shape, 1.0),
                    pt.glow_size) + _MARGE_ZONE
        return QRect(int(pt.x - rayon), int(pt.y - rayon),
                     int(rayon * 2) + 1, int(rayon * 2) + 1)

    def _advance(self) -> None:
        if not self.isVisible():
            return
        self._ensure_particles()
        self._time += FPS_INTERVAL / 1000.0
        h = self.height()
        w = self.width()
        # Zone à repeindre, et non la fenêtre entière. C'était le premier poste
        # de peinture au repos : cet overlay est TRANSLUCIDE et couvre toute la
        # fenêtre, donc un `update()` nu obligeait Qt à repeindre tout ce qui se
        # trouve dessous — illustration, panneau d'info, étiquettes, carrousel,
        # boutons — trente fois par seconde, pour 35 points de 1,5 à 4 px.
        # Mesuré à 1270×844 : 265 ms/s et 768 peintures/s avant, 156 ms/s et
        # 563 après, soit −41 % de CPU. Le rendu est identique au pixel près :
        # mêmes particules, mêmes positions, même dessin.
        sale = QRegion()
        for pt in self._particles:
            sale += self._zone(pt)          # là où elle était
            # Vertical drift (upward)
            pt.y += pt.speed_y
            # Horizontal: slight drift + sinusoidal oscillation
            pt.x += pt.speed_x + math.sin(pt.phase) * pt.sway
            pt.phase += pt.phase_speed
            pt.rotation += pt.rot_speed

            # Wrap : une ambiance peut MONTER (braises) ou DESCENDRE (flocons,
            # lettres, cendres), donc les deux bords sont gérés.
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
            sale += self._zone(pt)          # là où elle arrive
        self.update(sale)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Le décor AVANT les particules : les lettres et les flocons passent
        # devant la silhouette, jamais derrière. Il est repeint à chaque image
        # parce que l'overlay est translucide et que Qt efface la zone sale
        # avant de la redessiner — mais son TRACÉ est mis en cache, donc le
        # coût est celui d'un `drawPath` écrêté, pas d'une reconstruction.
        decor.peindre(p, self._season, self.width(), self.height())

        for pt in self._particles:
            # Opacité oscillante (scintillement rapide pour les braises).
            opacity = pt.base_opacity + math.sin(
                self._time * pt.flicker + pt.phase
            ) * pt.opacity_variation
            opacity = max(0.05, min(opacity, 0.55))
            alpha = int(opacity * 255)

            r, g, b = pt.color_rgb

            # ── Halo (peint derrière, plus large et plus transparent) ──
            if pt.has_glow:
                glow_alpha = max(int(alpha * 0.30), 3)
                gs = pt.glow_size
                grad = QRadialGradient(pt.x, pt.y, gs)
                grad.setColorAt(0, QColor(r, g, b, glow_alpha))
                grad.setColorAt(1, QColor(r, g, b, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(grad)
                p.drawEllipse(QRectF(pt.x - gs, pt.y - gs, gs * 2, gs * 2))

            peintre = _FORMES.get(pt.shape)
            if peintre is not None:
                peintre(p, pt, QColor(r, g, b, alpha))
                continue

            # ── Point : le fond ordinaire ──
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(r, g, b, alpha))
            s = pt.size
            p.drawEllipse(QRectF(pt.x - s, pt.y - s, s * 2, s * 2))

        p.end()

    # ── Les quatre gestes de peinture ────────────────────────────────────

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

    @staticmethod
    def _paint_envelope(p: QPainter, pt: _Particle, color: QColor) -> None:
        """Lettre de Poudlard : rectangle, rabat en V, cachet de cire.

        Le cachet prend l'accent du THÈME, jamais la couleur du papier : c'est
        le seul point de couleur de la forme, et il porte la maison. Il est
        peint à l'alpha de la lettre pour ne pas rester visible quand elle
        s'efface — un point de couleur qui survit à son support se lit comme
        un défaut d'affichage.
        """
        demi_l = pt.size * 0.78
        demi_h = pt.size * 0.52
        p.save()
        p.translate(pt.x, pt.y)
        p.rotate(pt.rotation)

        corps = QRectF(-demi_l, -demi_h, demi_l * 2, demi_h * 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color.red(), color.green(), color.blue(),
                          int(color.alpha() * 0.62)))
        p.drawRect(corps)
        p.setPen(QPen(color, 0.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(corps)
        # Rabat : les deux arêtes qui descendent des coins hauts vers le centre.
        p.drawLine(QPointF(-demi_l, -demi_h), QPointF(0.0, demi_h * 0.18))
        p.drawLine(QPointF(demi_l, -demi_h), QPointF(0.0, demi_h * 0.18))

        r, g, b = theme.current().accent_rgb
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(r, g, b, color.alpha()))
        cire = max(pt.size * 0.17, 0.7)
        p.drawEllipse(QRectF(-cire, demi_h * 0.18 - cire, cire * 2, cire * 2))
        p.restore()

    @staticmethod
    def _paint_flame(p: QPainter, pt: _Particle, color: QColor) -> None:
        """Bougie flottante : une goutte inversée, et un cœur plus clair.

        Pas de rotation : une flamme qui tourne n'est plus une flamme. Elle
        est peinte en coordonnées locales de sorte que sa POINTE soit vers le
        haut, quel que soit le sens de déplacement de la particule.
        """
        hauteur = pt.size
        largeur = pt.size * 0.62
        p.save()
        p.translate(pt.x, pt.y)

        goutte = QPainterPath()
        goutte.moveTo(0.0, -hauteur)
        goutte.quadTo(largeur, -hauteur * 0.15, 0.0, hauteur)
        goutte.quadTo(-largeur, -hauteur * 0.15, 0.0, -hauteur)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(goutte)

        # Cœur : la même goutte en réduction, plus claire. C'est ce qui
        # empêche la flamme de se lire comme une simple tache.
        coeur = QPainterPath()
        coeur.moveTo(0.0, -hauteur * 0.45)
        coeur.quadTo(largeur * 0.42, 0.0, 0.0, hauteur * 0.55)
        coeur.quadTo(-largeur * 0.42, 0.0, 0.0, -hauteur * 0.45)
        p.setBrush(QColor(255, 248, 225, min(255, int(color.alpha() * 1.35))))
        p.drawPath(coeur)
        p.restore()

    def showEvent(self, event) -> None:
        self.resume()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self.pause()
        super().hideEvent(event)

    def pause(self) -> None:
        if self._ticking:
            Ticker.detach(self._advance)
            self._ticking = False

    def resume(self) -> None:
        if not self._ticking:
            Ticker.instance().tick.connect(self._advance)
            self._ticking = True


# Aiguillage de peinture. Une forme absente de la table retombe sur le point,
# ce qui est le bon défaut : une `config.json` écrite par une version plus
# récente peut nommer une forme que ce launcher ne sait pas dessiner, et un
# point discret vaut mieux qu'une particule invisible.
_FORMES = {
    "flocon": ParticleOverlay._paint_flake,
    "enveloppe": ParticleOverlay._paint_envelope,
    "flamme": ParticleOverlay._paint_flame,
}

# Débordement d'une forme au-delà de son rayon `size`, pour la zone sale.
# Mesuré sur les tracés ci-dessus : la lettre s'étend à 0,78 × size en demi-
# largeur, mais tourne — sa diagonale atteint donc ~0,94. On arrondit au-
# dessus : deux pixels de trop ne coûtent rien, deux de moins laissent une
# trainée à l'écran.
_ETALEMENT = {"enveloppe": 1.1, "flamme": 1.05, "flocon": 1.0}

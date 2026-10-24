"""Le disque de la Médiathèque : la jaquette du jeu imprimée sur un CD qui tourne.

Demandé par Ludo le 2026-10-24 : « un CD à l'ancienne qui tourne lorsqu'une
musique est utilisée », puis « dessiner sur le CD le jeu, un peu comme les
anciens disques de jeu ». L'étiquette est la jaquette du catalogue (déjà
embarquée), recadrée en carré, percée au centre, avec l'anneau de plastique
clair d'un vrai disque. Le reflet ne tourne pas : c'est la lumière, pas le disque.

Une seule image par jeu et par taille, peinte une fois (`_cache`) ; chaque
battement du `Ticker` (règle 18) ne fait que la tourner.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from src.ui.ticker import Ticker

# Le carré de la jaquette qui couvre le disque : centre (fractions de la largeur
# et de la hauteur) et côté (fraction de la largeur). Réglé à l'image sur les
# trois jaquettes le 2026-10-24 : le titre en haut, le personnage dessous.
CADRAGES: dict[str, tuple[float, float, float]] = {
    "hp1": (0.5, 0.367, 1.0),
    "hp2": (0.5, 0.5, 1.0),
    "hp3": (0.5, 0.444, 1.0),
}
_TROU = 0.075          # rayon du trou, en fraction du diamètre
_MOYEU = 0.17          # rayon de l'anneau transparent
_TOUR_S = 5.5          # durée d'un tour, en secondes (le Ticker bat à ~30 images/s)

_cache: dict[tuple[str, int], QPixmap] = {}


def _source(image: QImage, jeu: str) -> QRectF:
    cx, cy, cote = CADRAGES.get(jeu, (0.5, 0.42, 1.0))
    w, h = image.width(), image.height()
    c = min(cote * w, w, h)
    x = min(max(cx * w - c / 2, 0), w - c)
    y = min(max(cy * h - c / 2, 0), h - c)
    return QRectF(x, y, c, c)


def pixmap_disque(jeu: str, jaquette: Path | None, cote_px: int) -> QPixmap:
    """Le disque en `cote_px` pixels réels, fond transparent, troué au centre."""
    cle = (f"{jeu}|{jaquette}", cote_px)
    deja = _cache.get(cle)
    if deja is not None:
        return deja
    pm = QPixmap(cote_px, cote_px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    rect = QRectF(0, 0, cote_px, cote_px)
    centre = rect.center()
    disque = QPainterPath()
    disque.addEllipse(rect.adjusted(1, 1, -1, -1))
    p.setClipPath(disque)
    image = QImage(str(jaquette)) if jaquette is not None else QImage()
    if image.isNull():
        # Sans jaquette : un disque argenté nu.
        argent = QConicalGradient(centre, 20)
        for pos, teinte in ((0, "#c9ced8"), (0.25, "#f2ecdc"), (0.5, "#aebbd0"),
                            (0.75, "#ead9b4"), (1, "#c9ced8")):
            argent.setColorAt(pos, QColor(teinte))
        p.fillRect(rect, QBrush(argent))
    else:
        p.drawImage(rect, image, _source(image, jeu))
    p.setClipping(False)
    r_moyeu = cote_px * _MOYEU
    p.setPen(QPen(QColor(255, 255, 255, 120), max(1.0, cote_px / 320)))
    p.setBrush(QColor(205, 212, 224, 150))
    p.drawEllipse(centre, r_moyeu, r_moyeu)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(220, 225, 235, 200), max(1.0, cote_px / 200)))
    p.drawEllipse(rect.adjusted(1, 1, -1, -1))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0))
    r_trou = cote_px * _TROU
    p.drawEllipse(centre, r_trou, r_trou)
    p.end()
    _cache[cle] = pm
    return pm


class Disque(QWidget):
    """Le disque d'un jeu, qui tourne pendant la lecture.

    `reflet` : la lumière fixe par-dessus (la platine) ; le petit disque de la
    barre du bas s'en passe, il ferait une tache à 20 px.
    """

    def __init__(self, cote: int, reflet: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cote = cote
        self._reflet = reflet
        self._jeu = ""
        self._jaquette: Path | None = None
        self._angle = 0.0
        self._horloge = QElapsedTimer()
        self._tourne = False
        self._abonne = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(cote, cote)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(self._cote, self._cote)

    @property
    def tourne(self) -> bool:
        return self._tourne

    def poser(self, jeu: str, jaquette: Path | None) -> None:
        if (jeu, jaquette) != (self._jeu, self._jaquette):
            self._jeu, self._jaquette = jeu, jaquette
            self.update()

    def set_tourne(self, oui: bool) -> None:
        self._tourne = oui
        self._abonner(oui and self.isVisible())

    def _abonner(self, oui: bool) -> None:
        if oui and not self._abonne:
            Ticker.instance().tick.connect(self._battement)
            self._abonne = True
            self._horloge.start()
        elif not oui and self._abonne:
            Ticker.detach(self._battement)
            self._abonne = False

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self._abonner(self._tourne)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._abonner(False)
        super().hideEvent(event)

    def _battement(self) -> None:
        if not self.isVisible():
            return
        ecoule = self._horloge.restart() / 1000.0
        self._angle = (self._angle + 360.0 * min(ecoule, 0.25) / _TOUR_S) % 360.0
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        ratio = self.devicePixelRatioF()
        cote = min(self.width(), self.height())
        pm = pixmap_disque(self._jeu, self._jaquette, max(1, round(cote * ratio)))
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        centre = QPointF(self.width() / 2, self.height() / 2)
        if self._reflet:
            # L'ombre portée, sous le disque.
            ombre = QRadialGradient(centre + QPointF(0, cote * 0.03), cote * 0.52)
            ombre.setColorAt(0.85, QColor(0, 0, 0, 120))
            ombre.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(ombre))
            p.drawEllipse(centre + QPointF(0, cote * 0.03), cote * 0.52, cote * 0.52)
        p.save()
        p.translate(centre)
        p.rotate(self._angle)
        p.drawPixmap(QRectF(-cote / 2, -cote / 2, cote, cote), pm, QRectF(pm.rect()))
        p.restore()
        if self._reflet:
            lumiere = QConicalGradient(centre, 120)
            for pos, alpha in ((0.0, 0), (0.06, 46), (0.12, 0), (0.5, 0), (0.56, 30), (0.62, 0), (1.0, 0)):
                lumiere.setColorAt(pos, QColor(255, 255, 255, alpha))
            anneau = QPainterPath()
            anneau.addEllipse(centre, cote / 2 - 1, cote / 2 - 1)
            trou = QPainterPath()
            trou.addEllipse(centre, cote * _MOYEU, cote * _MOYEU)
            p.fillPath(anneau.subtracted(trou), QBrush(lumiere))
        p.end()

"""Une carte de collection qui s'incline vers la souris, comme dans la boutique de HP4.

Dans le jeu, la carte est un objet en relief : elle pivote un peu quand on la
déplace et la lumière glisse sur son vernis (Ludo, 2026-10-26 : « HP4 ce sont
des images en 3D qui bougent légèrement quand on bouge la carte, ça serait bien
de les voir comme ça aussi dans le folio »). Ici, une perspective de Qt
(`QTransform.rotate` autour des axes Y puis X) suit le pointeur, un reflet suit
l'angle et une ombre se décale à l'opposé ; la carte revient à plat quand la
souris s'en va. Au repos, rien ne tourne : le minuteur ne vit que le temps du
mouvement.
"""

import math

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QTransform,
)
from PyQt6.QtWidgets import QWidget

INCLINAISON = 12.0      # degrés, pointeur au bord de la carte
_DISTANCE = 900.0       # distance au plan de la perspective (px) : plus court = plus marqué
_LISSAGE = 0.2          # part du chemin restant parcourue à chaque image
_MARGE = 0.07           # place laissée autour de la carte pour l'inclinaison et l'ombre


class Carte3D(QWidget):
    """L'illustration d'une carte, à plat au repos, inclinée sous la souris."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._image: QImage | None = None
        self._pix: QPixmap | None = None
        self.angle = (0.0, 0.0)          # autour de Y (gauche, droite), autour de X
        self._cible = (0.0, 0.0)
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(16)
        # PRÉCIS : le minuteur grossier de Windows tombe sur sa grille de
        # 15,6 ms, et une image sur deux arrivait 31 ms après la précédente.
        # La carte avançait par saccades (Ludo, 2026-10-27 : « encore pas
        # fluide »), comme le minuteur commun des particules (`ticker.py`).
        self._minuteur.setTimerType(Qt.TimerType.PreciseTimer)
        self._horloge = QElapsedTimer()
        self._minuteur.timeout.connect(self._avancer)

    def poser(self, image: QImage | None) -> None:
        self._image = image
        self._pix = None
        self.update()

    @property
    def image(self) -> QImage | None:
        return self._image

    def rect_carte(self) -> QRectF:
        """La carte à plat, à sa proportion, centrée dans la place laissée."""
        zone = QRectF(self.rect()).adjusted(self.width() * _MARGE, self.height() * _MARGE,
                                            -self.width() * _MARGE, -self.height() * _MARGE)
        if self._image is None or self._image.isNull() or zone.isEmpty():
            return zone
        ratio = self._image.width() / max(1, self._image.height())
        largeur = min(zone.width(), zone.height() * ratio)
        hauteur = largeur / ratio
        return QRectF(zone.center().x() - largeur / 2, zone.center().y() - hauteur / 2,
                      largeur, hauteur)

    # ── Mouvement ──

    def viser(self, point: QPointF) -> None:
        """Incline la carte vers ce point (coordonnées du widget)."""
        r = self.rect_carte()
        if r.isEmpty():
            return
        nx = max(-1.0, min(1.0, (point.x() - r.center().x()) / (r.width() / 2)))
        ny = max(-1.0, min(1.0, (point.y() - r.center().y()) / (r.height() / 2)))
        # Le bord sous le pointeur s'enfonce, comme une carte qu'on presse du doigt.
        self._cible = (nx * INCLINAISON, -ny * INCLINAISON)
        self._demarrer()

    def _demarrer(self) -> None:
        if not self._minuteur.isActive():
            self._horloge.start()
            self._minuteur.start()

    def mouseMoveEvent(self, event) -> None:
        self.viser(event.position())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._cible = (0.0, 0.0)
        self._demarrer()
        super().leaveEvent(event)

    def _avancer(self) -> None:
        (ay, ax), (cy, cx) = self.angle, self._cible
        # Le lissage suit le TEMPS écoulé, pas le nombre de tours : une image
        # en retard rattrape son retard au lieu de figer la carte.
        ecoule = self._horloge.restart() if self._horloge.isValid() else 16
        part = 1.0 - (1.0 - _LISSAGE) ** (max(16, min(ecoule, 100)) / 16.0)
        ay += (cy - ay) * part
        ax += (cx - ax) * part
        if abs(cy - ay) < 0.05 and abs(cx - ax) < 0.05:
            ay, ax = cy, cx
            self._minuteur.stop()
        self.angle = (ay, ax)
        self.update()

    # ── Dessin ──

    def resizeEvent(self, event) -> None:
        self._pix = None
        super().resizeEvent(event)

    def _pixmap(self, r: QRectF) -> QPixmap | None:
        if self._image is None or self._image.isNull():
            return None
        dpr = self.devicePixelRatioF()
        taille = (max(1, round(r.width() * dpr)), max(1, round(r.height() * dpr)))
        if self._pix is None or (self._pix.width(), self._pix.height()) != taille:
            self._pix = QPixmap.fromImage(self._image.scaled(
                *taille, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            self._pix.setDevicePixelRatio(dpr)
        return self._pix

    def paintEvent(self, _event) -> None:
        r = self.rect_carte()
        pix = self._pixmap(r)
        if pix is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ay, ax = self.angle
        rayon = r.height() * 0.045
        force = min(1.0, math.hypot(ay, ax) / INCLINAISON)

        # L'ombre, décalée à l'opposé de l'inclinaison, en couches pour l'adoucir.
        decalage = QPointF(-ay * 0.6, ax * 0.6 + 4 + 4 * force)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(4):
            p.setBrush(QColor(0, 0, 0, 34 - 7 * k))
            p.drawRoundedRect(r.translated(decalage).adjusted(-2 * k, -2 * k, 2 * k, 2 * k),
                              rayon + 2 * k, rayon + 2 * k)

        centre = r.center()
        t = QTransform()
        t.translate(centre.x(), centre.y())
        t.rotate(ay, Qt.Axis.YAxis, _DISTANCE)
        t.rotate(ax, Qt.Axis.XAxis, _DISTANCE)
        t.translate(-centre.x(), -centre.y())
        p.setTransform(t)
        contour = QPainterPath()
        contour.addRoundedRect(r, rayon, rayon)
        p.setClipPath(contour)
        p.drawPixmap(r, pix, QRectF(pix.rect()))

        # Le reflet du vernis : une bande claire qui traverse la carte avec l'angle.
        position = 0.5 - ay / INCLINAISON * 0.45 + ax / INCLINAISON * 0.2
        reflet = QLinearGradient(r.topLeft(), r.bottomRight())
        lumiere = round(26 + 46 * force)
        for arret, alpha in ((position - 0.22, 0), (position, lumiere), (position + 0.22, 0)):
            if 0.0 <= arret <= 1.0:
                reflet.setColorAt(arret, QColor(255, 250, 235, alpha))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.fillRect(r, reflet)
        p.end()

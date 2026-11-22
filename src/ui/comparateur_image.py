"""Le comparateur avant/après de la fiche de la page Image (`apercus_image`).

Les deux images d'un réglage l'une sur l'autre : l'autre valeur à gauche du trait, la valeur Accio à
droite. Le trait suit la souris pendant le survol et revient au milieu à la sortie ; chaque côté porte
son nom dans un coin bas. Les images sont lues à la première demande et gardées tant que la fiche vit
(une poignée de JPEG de 640 × 360). Sans aperçu, le widget se cache.
"""

from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QEnterEvent, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from src.core.apercus_image import Apercu
from src.core.i18n import tr
from src.ui.composants import police
from src.ui.theme import accent_qcolor, bg_qcolor

_RAYON = 8


class Comparateur(QWidget):
    """`montrer(apercu)` : les deux images de ce réglage ; None cache le widget."""

    def __init__(self, largeur: int) -> None:
        super().__init__()
        self.setFixedSize(largeur, round(largeur * 9 / 16))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setFont(police(11, gras=True))
        self._images: dict[Path, QPixmap] = {}
        self._apercu: Apercu | None = None
        self._part = 0.5          # la place du trait, de 0 (tout Accio) à 1 (tout l'autre valeur)
        self.hide()

    def montrer(self, apercu: Apercu | None) -> None:
        if apercu == self._apercu:
            return     # la fiche se refait à chaque cran d'un curseur : le trait ne saute pas au milieu
        self._apercu = apercu
        self._part = 0.5
        self.setVisible(apercu is not None)
        self.update()

    def _image(self, chemin: Path) -> QPixmap:
        if chemin not in self._images:
            self._images[chemin] = QPixmap(str(chemin))
        return self._images[chemin]

    def enterEvent(self, event: QEnterEvent | None) -> None:  # noqa: N802 (Qt)
        if event is not None:
            self._suivre(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802 (Qt)
        if event is not None:
            self._suivre(event.position().x())

    def leaveEvent(self, event: object) -> None:  # noqa: N802 (Qt)
        self._part = 0.5
        self.update()

    def _suivre(self, x: float) -> None:
        self._part = min(1.0, max(0.0, x / max(1, self.width())))
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 (Qt)
        if self._apercu is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cadre = QRectF(self.rect())
        bord = QPainterPath()
        bord.addRoundedRect(cadre, _RAYON, _RAYON)
        p.setClipPath(bord)
        x = cadre.width() * self._part
        p.drawPixmap(cadre, self._image(self._apercu.accio), QRectF(self._image(self._apercu.accio).rect()))
        autre = self._image(self._apercu.autre)
        p.save()
        p.setClipRect(QRectF(0, 0, x, cadre.height()), Qt.ClipOperation.IntersectClip)
        p.drawPixmap(cadre, autre, QRectF(autre.rect()))
        p.restore()
        # Le trait et sa poignée.
        p.setPen(QPen(accent_qcolor(), 2))
        p.drawLine(QPointF(x, 0), QPointF(x, cadre.height()))
        p.setBrush(accent_qcolor())
        p.setPen(QPen(QColor(0, 0, 0, 140), 1))
        p.drawEllipse(QPointF(x, cadre.height() / 2), 6, 6)
        # Les noms, chacun dans son coin, seulement si son côté se voit assez.
        fm = QFontMetrics(self.font())
        for texte, gauche in ((tr(self._apercu.libelle), True), (tr("Accio"), False)):
            largeur = fm.horizontalAdvance(texte) + 12
            place = x if gauche else cadre.width() - x
            if place < largeur + 8:
                continue
            boite = QRectF(6 if gauche else cadre.width() - largeur - 6, cadre.height() - fm.height() - 12,
                           largeur, fm.height() + 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg_qcolor(190))
            p.drawRoundedRect(boite, 4, 4)
            p.setPen(QColor("#f4f2f8") if gauche else accent_qcolor())
            p.drawText(boite, Qt.AlignmentFlag.AlignCenter, texte)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(cadre.adjusted(0.5, 0.5, -0.5, -0.5), _RAYON, _RAYON)
        p.end()

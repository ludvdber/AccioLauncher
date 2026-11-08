"""Le disque de la Médiathèque : la jaquette du jeu imprimée sur un CD qui tourne.

Demandé par Ludo le 2026-10-24 : « un CD à l'ancienne qui tourne lorsqu'une
musique est utilisée », puis « dessiner sur le CD le jeu, un peu comme les
anciens disques de jeu ». L'étiquette est la jaquette du catalogue (déjà
embarquée), recadrée en carré, percée au centre, avec l'anneau de plastique
clair d'un vrai disque. Le reflet ne tourne pas : c'est la lumière, pas le disque.

Une seule image par jeu et par taille, peinte une fois (`_cache`) ; chaque
battement du `Ticker` (règle 18) ne fait que la tourner.
"""

from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, QEvent, QPointF, QRectF, QSize, Qt, QUrl
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

from src.core.config import ASSETS_DIR
from src.ui import carrousel_gpu, fond_gpu
from src.ui.theme import themed
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

_QML = ASSETS_DIR / "qml" / "DisqueScene.qml"


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


def _peindre_ombre(p: QPainter, centre: QPointF, cote: float) -> None:
    """L'ombre portée, sous le disque."""
    ombre = QRadialGradient(centre + QPointF(0, cote * 0.03), cote * 0.52)
    ombre.setColorAt(0.85, QColor(0, 0, 0, 120))
    ombre.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(ombre))
    p.drawEllipse(centre + QPointF(0, cote * 0.03), cote * 0.52, cote * 0.52)


def _peindre_lumiere(p: QPainter, centre: QPointF, cote: float) -> None:
    """Le reflet fixe : la lumière, pas le disque."""
    lumiere = QConicalGradient(centre, 120)
    for pos, alpha in ((0.0, 0), (0.06, 46), (0.12, 0), (0.5, 0), (0.56, 30), (0.62, 0), (1.0, 0)):
        lumiere.setColorAt(pos, QColor(255, 255, 255, alpha))
    anneau = QPainterPath()
    anneau.addEllipse(centre, cote / 2 - 1, cote / 2 - 1)
    trou = QPainterPath()
    trou.addEllipse(centre, cote * _MOYEU, cote * _MOYEU)
    p.fillPath(anneau.subtracted(trou), QBrush(lumiere))


class _DisqueGPU(fond_gpu.QQuickWidget if fond_gpu.QUICK_DISPONIBLE else QWidget):  # type: ignore[misc]
    """La scène d'un disque, de la taille du widget `Disque`, posée sur lui.

    Dans la fenêtre du launcher, une repeinte de widget compose TOUTE la fenêtre,
    à part des images du fond et des particules. La scène part dans leur composition :
    même Ticker, même image. Et ne se crée qu'au premier affichage (une
    `QQuickWidget` compte), le temps d'une fenêtre où le disque se voit.
    """

    def __init__(self, cote: int, reflet: bool, fond: QColor, parent: QWidget) -> None:
        super().__init__(parent)
        self._cote = cote
        self._reflet = reflet
        self._images: dict[str, QImage] = {}
        # Gardé par Python, comme ceux du fond.
        self._fournisseur = carrousel_gpu.ImagesPeintes(self._images)
        self.engine().addImageProvider("accio", self._fournisseur)
        self.setResizeMode(fond_gpu.QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setClearColor(fond)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)    # un QQuickWidget prend Tab, d'office
        self.setSource(QUrl.fromLocalFile(str(_QML)))
        self._racine = self.rootObject()
        if self._racine is None:
            return
        self._racine.setProperty("fond", fond)
        self.poser_calques()

    def poser_calques(self) -> None:
        """L'ombre et la lumière, à l'échelle de l'écran du moment."""
        if self._racine is not None and self._reflet:
            self._racine.setProperty("ombre", self._calque("ombre", _peindre_ombre))
            self._racine.setProperty("lumiere", self._calque("lumiere", _peindre_lumiere))

    def _calque(self, nom: str, geste) -> str:
        dpr = self.devicePixelRatioF()
        cle = f"{nom}/{dpr:g}"          # QML garde un cache par URL
        if cle in self._images:
            return f"image://accio/{cle}"
        cote = self._cote
        cote_px = max(1, round(cote * dpr))
        image = QImage(cote_px, cote_px, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        geste(p, QPointF(cote / 2, cote / 2), cote)
        p.end()
        self._images[cle] = image
        return f"image://accio/{cle}"

    def valide(self) -> bool:
        return self._racine is not None

    def poser_disque(self, pm: QPixmap) -> None:
        if self._racine is not None:
            cle = f"disque/{pm.cacheKey()}"
            self._images.setdefault(cle, pm.toImage())
            self._racine.setProperty("disque", f"image://accio/{cle}")

    def poser_angle(self, angle: float) -> None:
        if self._racine is not None:
            self._racine.setProperty("angle", angle)


class Disque(QWidget):
    """Le disque d'un jeu, qui tourne pendant la lecture.

    `reflet` : la lumière fixe par-dessus (la platine) ; le petit disque de la
    barre du bas s'en passe, il ferait une tache à 20 px.

    `fond_scene` : la couleur (forme Poudlard) sur laquelle se pose le disque,
    pour le dessiner dans une scène (`carrousel_gpu.actif()`) ; None, ou la scène
    absente : `paintEvent`.
    """

    def __init__(self, cote: int, reflet: bool = True, parent: QWidget | None = None,
                 fond_scene: str | None = None) -> None:
        super().__init__(parent)
        self._cote = cote
        self._reflet = reflet
        self._fond_scene = fond_scene
        self._gpu: _DisqueGPU | None = None
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

    def event(self, e: QEvent | None) -> bool:
        # Fenêtre passée sur un écran d'une autre échelle : la scène reprend ses images.
        if e is not None and e.type() == QEvent.Type.DevicePixelRatioChange and self._gpu is not None:
            self._gpu.poser_calques()
            self._poser_image_scene()
        return super().event(e)

    @property
    def tourne(self) -> bool:
        return self._tourne

    def poser(self, jeu: str, jaquette: Path | None) -> None:
        if (jeu, jaquette) != (self._jeu, self._jaquette):
            self._jeu, self._jaquette = jeu, jaquette
            self.update()
            self._poser_image_scene()

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
        self._poser_scene()
        self._abonner(self._tourne)

    def _poser_scene(self) -> None:
        """Au premier affichage : la scène, si elle se charge (repli silencieux)."""
        if self._fond_scene is None or self._gpu is not None or not carrousel_gpu.actif():
            return
        gpu = _DisqueGPU(self._cote, self._reflet, QColor(themed(self._fond_scene)), self)
        if not gpu.valide():
            gpu.deleteLater()
            self._fond_scene = None
            return
        gpu.setGeometry(self.rect())
        gpu.show()
        self._gpu = gpu
        self._poser_image_scene()
        gpu.poser_angle(self._angle)

    def _poser_image_scene(self) -> None:
        if self._gpu is not None:
            cote_px = max(1, round(self._cote * self.devicePixelRatioF()))
            self._gpu.poser_disque(pixmap_disque(self._jeu, self._jaquette, cote_px))

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._abonner(False)
        super().hideEvent(event)

    def _battement(self) -> None:
        if not self.isVisible():
            return
        ecoule = self._horloge.restart() / 1000.0
        self._angle = (self._angle + 360.0 * min(ecoule, 0.25) / _TOUR_S) % 360.0
        if self._gpu is not None:
            self._gpu.poser_angle(self._angle)
        else:
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        if self._gpu is not None:
            return                  # la scène le dessine
        ratio = self.devicePixelRatioF()
        cote = min(self.width(), self.height())
        pm = pixmap_disque(self._jeu, self._jaquette, max(1, round(cote * ratio)))
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        centre = QPointF(self.width() / 2, self.height() / 2)
        if self._reflet:
            _peindre_ombre(p, centre, cote)
        p.save()
        p.translate(centre)
        p.rotate(self._angle)
        p.drawPixmap(QRectF(-cote / 2, -cote / 2, cote, cote), pm, QRectF(pm.rect()))
        p.restore()
        if self._reflet:
            _peindre_lumiere(p, centre, cote)
        p.end()

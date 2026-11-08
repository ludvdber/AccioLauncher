"""La fiche du jeu sur la carte graphique : un jumeau visuel, sans doubler la logique.

`InfoPanel` (avec `ActionPanel`, `AlertBanner`, `CarteProgression`, `BlocFolio`) et
`AudioBar` restent les seuls vrais widgets : mêmes classes, signaux, mise en page,
troncature, focus, clavier, manette, visite guidée. Ils restent visibles et
reçoivent les événements, mais ne se peignent plus : `setUpdatesEnabled(False)`,
posé avant le premier affichage, retire le sous-arbre de toute repeinte (celle de
ses parents comprise, vérifié sur Qt 6.11) sans toucher aux géométries, aux layouts
ni aux enfants créés plus tard, qui en héritent. Leur zone reste un trou dans la
composition, au-dessus du `QQuickWidget` du fond.

Un jumeau dans la scène du fond (`assets/qml/FicheJumeau.qml`) dessine chaque widget
à sa place, à partir de l'image que le widget a lui-même peinte : `QWidget.render`
sans les enfants, une fois, à chaque changement. Chaque type de rendu ne vit donc
qu'à un endroit, le widget, et tout type inconnu continue d'apparaître. La scène
n'a qu'une chose à faire : composer des textures. Python ne pousse que les
changements (texte, état de bouton, valeur, géométrie, visibilité) détectés par un
filtre d'événements, jamais à chaque image ; le fondu de la fiche au changement de
jeu est une animation de scène, à la place du `QGraphicsOpacityEffect` qui repeignait
toute la fiche à chaque image.

Dans la scène du fond et pas dans un `QQuickWidget` dédié : un second serait composé
au-dessus du premier avec un canal alpha, et prendrait les événements souris.
"""

import logging
import math
import os
from dataclasses import dataclass, field
from typing import cast

from PyQt6 import sip
from PyQt6.QtCore import Q_ARG, QEvent, QMetaObject, QObject, QPoint, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QImage, QPainter, QRegion
from PyQt6.QtWidgets import QAbstractButton, QAbstractSlider, QLabel, QScrollArea, QWidget

from src.core.config import ASSETS_DIR
from src.ui import fond_gpu

if fond_gpu.QUICK_DISPONIBLE:
    from PyQt6.QtQuick import QQuickImageProvider
else:                                                  # pragma: no cover
    QQuickImageProvider = None                         # type: ignore[assignment,misc]

log = logging.getLogger(__name__)

_QML = ASSETS_DIR / "qml" / "FicheJumeau.qml"

# Tolérance d'arrondi (une coordonnée logique × 1,25 tombe pile sur un quart de pixel).
_EPSILON = 1e-6

_E = QEvent.Type
# Ce qui change l'aspect d'un widget sans passer par `update()` côté Python.
_REPEINDRE = frozenset({
    _E.Enter, _E.Leave, _E.HoverEnter, _E.HoverLeave, _E.MouseButtonPress,
    _E.MouseButtonRelease, _E.MouseButtonDblClick, _E.FocusIn, _E.FocusOut,
    _E.KeyPress, _E.KeyRelease, _E.EnabledChange, _E.StyleChange, _E.PaletteChange,
    _E.FontChange, _E.DynamicPropertyChange, _E.LanguageChange,
})
# Ce qui peut déplacer, montrer ou cacher (`LayoutRequest` couvre aussi `QLabel.setText`,
# qui ne se signale pas autrement une fois les mises à jour coupées).
_REVOIR = frozenset({
    _E.Move, _E.Resize, _E.Show, _E.Hide, _E.ShowToParent, _E.HideToParent,
    _E.LayoutRequest, _E.DevicePixelRatioChange,
})
_STRUCTURE = frozenset({_E.ChildAdded, _E.ChildRemoved})


def actif() -> bool:
    """Le jumeau est-il allumé ? Oui dès que le fond est sur la carte graphique.

    Mesuré en vraie fenêtre : changement de jeu 56 → 22 % d'un cœur (ARCHITECTURE_UI.md).
    `ACCIO_FICHE_GPU=0` l'éteint : le chemin des widgets ne change alors pas d'un pixel.
    """
    return fond_gpu.actif() and _QML.exists() and os.environ.get("ACCIO_FICHE_GPU") != "0"


if fond_gpu.QUICK_DISPONIBLE:
    class _Images(QQuickImageProvider):
        """Les images peintes par les widgets, servies à la scène par `cle/version`."""

        def __init__(self) -> None:
            super().__init__(QQuickImageProvider.ImageType.Image)
            self.images: dict[int, QImage] = {}

        def requestImage(self, ident: str, voulue: QSize):
            cle = int(ident.partition("/")[0])
            image = self.images.get(cle)
            if image is None:           # le widget est parti entre-temps
                image = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(0)
            return image, image.size()


@dataclass(eq=False)
class _Noeud:
    """Un widget du sous-arbre et ce qui a déjà été envoyé à son double."""

    widget: QWidget
    cle: int
    a_peindre: bool = True       # l'image est à refaire au prochain passage
    version: int = 0
    texte: str | None = None     # dernier `text()` vu (QLabel)
    image: QImage | None = None
    groupe: str = "fiche"
    z: int = 0
    decalage: tuple[float, float] = (0.0, 0.0)
    posee: bool = False
    pose: dict[str, object] = field(default_factory=dict)


def _ne_dessine_rien(w: QWidget) -> bool:
    """Un conteneur nu (QWidget, zone défilante) : pas de double dans la scène."""
    if isinstance(w, QScrollArea) or w.objectName() == "qt_scrollarea_viewport":
        return True
    if type(w) is not QWidget:
        return False
    feuille = w.styleSheet()
    return not feuille or ("background" in feuille and "transparent" in feuille)


class FicheGPU(QObject):
    """Tient le jumeau à jour : parcours du sous-arbre, filtre d'événements, envois."""

    def __init__(self, fond: fond_gpu.FondGPU, info: QWidget, audio: QWidget,
                 repere: QWidget) -> None:
        super().__init__(repere)
        self._fond = fond
        self._info = info
        self._audio = audio
        self._repere = repere
        self._racine: QObject | None = None
        self._images = _Images()
        fond.engine().addImageProvider("jumeau", self._images)
        fond._poser("ficheSource", QUrl.fromLocalFile(str(_QML)))
        racine_fond = fond._racine
        if racine_fond is None:
            return
        self._racine = racine_fond.findChild(QObject, "ficheJumeau")
        if self._racine is None:
            log.warning("Fiche sur la carte graphique : scène non chargée")
            return
        self._suivis: dict[int, QWidget] = {}
        self._noeuds: dict[int, _Noeud] = {}
        self._cles: dict[int, int] = {}
        self._cle_suivante = 1
        self._a_repeindre: set[int] = set()
        self._revoir_tout = True
        self._structure_sale = True
        self._ratio = 0.0
        self._origine_zone = (0, 0)
        self._rect_zone = QRectF()
        # L'aire de défilement, s'il y en a une, avec son contenu.
        zone = info.findChild(QScrollArea)
        self._zone: QScrollArea | None = zone
        self._contenu: QWidget | None = zone.widget() if zone is not None else None
        # Un seul filtre, un passage par tour de boucle, quel que soit le nombre d'événements.
        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.setInterval(0)
        self._minuteur.timeout.connect(self._synchroniser)
        for racine in (info, audio):
            racine.setUpdatesEnabled(False)
        self._planifier()

    def valide(self) -> bool:
        return self._racine is not None

    def fondu_zero(self) -> None:
        """La fiche s'efface d'un coup, avant de poser les données du jeu suivant."""
        self._appeler("fonduZero")

    def fondu_entree(self, duree_ms: int = 500) -> None:
        """Le fondu d'arrivée de la fiche, dessiné par la scène."""
        self._appeler("fonduEntree", duree_ms)

    # ── Scène ──

    def _appeler(self, nom: str, *arguments: object) -> None:
        if self._racine is not None:
            QMetaObject.invokeMethod(
                self._racine, nom, Qt.ConnectionType.DirectConnection,
                *(Q_ARG("QVariant", a) for a in arguments))

    # ── Événements ──

    def eventFilter(self, w: QObject | None, e: QEvent | None) -> bool:  # noqa: N802 (Qt)
        if e is None:
            return False
        t = e.type()
        if t in _REPEINDRE:
            self.marquer(cast(QWidget, w))
        elif t in _REVOIR:
            self._revoir_tout = True
            self._planifier()
        elif t in _STRUCTURE:
            self._structure_sale = True
            self._revoir_tout = True
            self._planifier()
        elif t == _E.HoverMove and isinstance(w, QAbstractSlider):
            self.marquer(w)     # la poignée survolée
        return False

    def marquer(self, w: QWidget) -> None:
        """L'aspect du widget a pu changer : son image sera refaite au prochain tour."""
        cle = self._cles.get(id(w))
        if cle is None or cle not in self._noeuds:
            return
        self._noeuds[cle].a_peindre = True
        self._a_repeindre.add(cle)
        self._planifier()

    def _planifier(self) -> None:
        if not self._minuteur.isActive():
            self._minuteur.start()

    # ── Le parcours ──

    def _brancher(self, w: QWidget) -> None:
        """Premier passage d'un widget : le filtre, et les changements sans événement."""
        w.installEventFilter(self)
        if isinstance(w, QAbstractButton):
            for signal in (w.pressed, w.released, w.toggled):
                signal.connect(lambda *_a, cible=w: self.marquer(cible))
        if isinstance(w, QAbstractSlider):
            for signal in (w.valueChanged, w.rangeChanged, w.sliderPressed, w.sliderReleased):
                signal.connect(lambda *_a, cible=w: self.marquer(cible))
        # Les widgets peints en Python (`_Barre`, IconButton…) changent par leur propre
        # `update()` : avec les mises à jour coupées il ne fait rien, on l'écoute donc.
        if type(w).__module__.startswith("src."):
            origine = w.update
            def sonde(*args: object) -> None:
                origine(*args)
                self.marquer(w)
            w.update = sonde  # type: ignore[assignment]

    def _parcourir(self) -> None:
        """Retrouve l'arbre : nouveaux widgets branchés, disparus oubliés."""
        vus: set[int] = set()
        ordre = 0

        def visiter(w: QWidget) -> None:
            nonlocal ordre
            ident = id(w)
            vus.add(ident)
            if ident not in self._suivis:
                self._suivis[ident] = w
                self._brancher(w)
                if not _ne_dessine_rien(w):
                    cle = self._cle_suivante
                    self._cle_suivante += 1
                    self._cles[ident] = cle
                    self._noeuds[cle] = _Noeud(w, cle, groupe=self._groupe_de(w))
            cle = self._cles.get(ident)
            if cle is not None:
                ordre += 1
                self._noeuds[cle].z = ordre
            for enfant in w.children():
                if isinstance(enfant, QWidget) and not enfant.isWindow():
                    visiter(enfant)

        visiter(self._info)
        visiter(self._audio)
        disparus = [i for i in self._suivis if i not in vus]
        cles = []
        for ident in disparus:
            del self._suivis[ident]
            cle = self._cles.pop(ident, None)
            if cle is not None:
                self._noeuds.pop(cle, None)
                self._images.images.pop(cle, None)
                self._a_repeindre.discard(cle)
                cles.append(cle)
        if cles:
            self._appeler("oublier", cles)

    def _groupe_de(self, w: QWidget) -> str:
        if self._contenu is not None and (w is self._contenu or self._contenu.isAncestorOf(w)):
            return "contenu"
        return "audio" if w is self._audio or self._audio.isAncestorOf(w) else "fiche"

    # ── La synchronisation ──

    def _peindre(self, n: _Noeud, ratio: float, dx: float, dy: float) -> bool:
        """L'image du widget : son propre rendu, sans ses enfants, décalé comme à
        l'écran (à 125 %, un widget tombe souvent entre deux pixels physiques, et ses
        lettres sont alors posées à cette fraction). Vrai si elle a changé."""
        w = n.widget
        image = QImage(max(1, math.ceil(w.width() * ratio + dx)),
                       max(1, math.ceil(w.height() * ratio + dy)),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(0)
        peintre = QPainter(image)
        peintre.translate(dx / ratio, dy / ratio)
        w.render(peintre, QPoint(0, 0), QRegion(), QWidget.RenderFlag(0))
        peintre.end()
        n.a_peindre = False
        n.decalage = (dx, dy)
        if n.image is not None and n.image == image:
            return False
        n.image = image
        n.version += 1
        self._images.images[n.cle] = image
        return True

    def _etat(self, n: _Noeud, ratio: float) -> dict[str, object]:
        """Ce qui diffère de la dernière image envoyée au double de ce widget."""
        w = n.widget
        if isinstance(w, QLabel):
            texte = w.text()
            if texte != n.texte:
                n.texte = texte
                n.a_peindre = True
        etat: dict[str, object] = {"visible": w.isVisible()}
        if etat["visible"] and w.width() > 0 and w.height() > 0:
            # Le pixel physique où le widget commence, et la fraction qui reste.
            origine = w.mapTo(self._repere, QPoint(0, 0))
            px, py = origine.x() * ratio, origine.y() * ratio
            bx, by = math.floor(px + _EPSILON), math.floor(py + _EPSILON)
            dx, dy = px - bx, py - by
            voulue = QSize(max(1, math.ceil(w.width() * ratio + dx)),
                           max(1, math.ceil(w.height() * ratio + dy)))
            if n.image is None or n.image.size() != voulue or n.decalage != (dx, dy):
                n.a_peindre = True
            if n.a_peindre and self._peindre(n, ratio, dx, dy):
                etat["source"] = f"image://jumeau/{n.cle}/{n.version}"
            ox, oy = self._origine_zone if n.groupe == "contenu" else (0, 0)
            etat["x"] = (bx - ox) / ratio
            etat["y"] = (by - oy) / ratio
            image = n.image
            if image is not None:
                etat["width"] = image.width() / ratio
                etat["height"] = image.height() / ratio
            etat["z"] = n.z
        diff = {k: v for k, v in etat.items() if n.pose.get(k) != v}
        n.pose.update(diff)
        if diff:
            diff["cle"] = n.cle
            if not n.posee:             # sa première apparition dans la scène
                n.posee = True
                diff["groupe"] = n.groupe
        return diff

    def _synchroniser(self) -> None:
        if self._racine is None or sip.isdeleted(self._fond) or sip.isdeleted(self._repere):
            return
        if self._structure_sale:
            self._structure_sale = False
            self._parcourir()
        ratio = self._fond.devicePixelRatioF()
        if ratio != self._ratio:
            self._ratio = ratio
            self._revoir_tout = True
            for n in self._noeuds.values():
                n.a_peindre = True
        tout = self._revoir_tout
        self._revoir_tout = False
        if tout:
            self._poser_zone(ratio)
        cles = list(self._noeuds) if tout else list(self._a_repeindre)
        self._a_repeindre.clear()
        lot = []
        for cle in cles:
            n = self._noeuds.get(cle)
            if n is None or sip.isdeleted(n.widget):
                continue
            diff = self._etat(n, ratio)
            if diff:
                lot.append(diff)
        if lot:
            self._appeler("poser", lot)

    def _poser_zone(self, ratio: float) -> None:
        """La zone défilante : le rognage de la vue, calé sur les pixels physiques."""
        zone = self._zone
        if zone is None or self._racine is None:
            return
        vue = zone.viewport()
        if vue is None:
            return
        o = vue.mapTo(self._repere, QPoint(0, 0))
        ox, oy = math.floor(o.x() * ratio + _EPSILON), math.floor(o.y() * ratio + _EPSILON)
        self._origine_zone = (ox, oy)
        rect = QRectF(ox / ratio, oy / ratio, vue.width(), vue.height())
        if rect != self._rect_zone:
            self._rect_zone = rect
            self._racine.setProperty("zoneDefilante", rect)

    # ── Tests et diagnostic ──

    def noeud_de(self, w: QWidget) -> _Noeud | None:
        cle = self._cles.get(id(w))
        return self._noeuds.get(cle) if cle is not None else None


def creer(fond: QWidget, info: QWidget, audio: QWidget, repere: QWidget) -> FicheGPU | None:
    """Le jumeau, ou None (éteint, ou scène non chargée) : le chemin des widgets reste."""
    if not actif() or not isinstance(fond, fond_gpu.FondGPU):
        return None
    jumeau = FicheGPU(fond, info, audio, repere)
    if jumeau.valide():
        log.info("Fiche sur la carte graphique")
        return jumeau
    jumeau.deleteLater()
    return None

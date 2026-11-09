"""Le carrousel de l'accueil dessiné par la carte graphique (Qt Quick).

Le principe du « jumeau visuel » : les `CarouselItem` restent la seule source de
vérité (signaux, clics, survol, géométrie, tests) et ne se peignent plus ; la
scène `assets/qml/CarrouselAccueil.qml`, posée SOUS eux avec les étoiles, dessine
leur double à la même géométrie. Mesuré avant (2026-11-01) : au changement de
jeu, l'animation des vignettes prenait 12 points d'un cœur sur 46.

À chaque sélection, les widgets prennent leur taille finale d'un coup (une seule
mise en page) et la scène anime la transformation de leur texture en 400 ms.

Le clic vise ce qui est VU : pendant ces 400 ms, `Glissement` rejoue la course de
la scène et `Carousel` résout le clic sur cette position, sans aucune mise en page.

Allumé avec le fond sur la carte graphique (`fond_gpu.actif()`) ; `ACCIO_CARROUSEL_GPU=0`
l'éteint. Éteint, ou si la scène ne se charge pas : `Carousel` garde son chemin
QPainter, tel quel.
"""

import logging
import os
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QWidget

from src.core.config import ASSETS_DIR
from src.core.i18n import tr
from src.ui import fond_gpu, theme
from src.ui.carousel_item import CarouselItem

if fond_gpu.QUICK_DISPONIBLE:
    from PyQt6.QtQuick import QQuickImageProvider
else:                                                  # pragma: no cover
    QQuickImageProvider = None                         # type: ignore[assignment,misc]

log = logging.getLogger(__name__)

_QML = ASSETS_DIR / "qml" / "CarrouselAccueil.qml"


def actif() -> bool:
    """Le carrousel passe-t-il par la carte graphique ?

    Oui dès que le fond y est ; `ACCIO_CARROUSEL_GPU=0` l'éteint. Mesuré en vraie
    fenêtre : changement de jeu 56 → 22 % d'un cœur (ARCHITECTURE_UI.md).
    """
    return fond_gpu.actif() and _QML.exists() and os.environ.get("ACCIO_CARROUSEL_GPU") != "0"


class Glissement:
    """Où les vignettes se VOIENT pendant que la scène les anime.

    Les widgets sont déjà à leur place finale : sans ce relevé, un clic tombait
    dans le vide ou sur la voisine. Chaque valeur suit le `Behavior` de la scène : si
    elle change, elle repart de là où elle se voit, pour toute la durée ; si elle ne
    change pas, sa course continue ; sans animation, elle saute. Aucune horloge
    ne bat : le calcul n'a lieu qu'au clic.
    """

    DUREE_MS = 400        # `duree` de CarrouselAccueil.qml, InOutQuad comme ses Behavior

    def __init__(self) -> None:
        self._courbe = QEasingCurve(QEasingCurve.Type.InOutQuad)
        self._horloge = QElapsedTimer()
        self._horloge.start()
        # Par vignette, par valeur (x, y, largeur, hauteur) : départ, arrivée, début.
        self._courses: list[list[tuple[float, float, int]]] = []

    def _vue(self, course: tuple[float, float, int], maintenant: int) -> float:
        depart, arrivee, debut = course
        t = (maintenant - debut) / self.DUREE_MS
        return arrivee if t >= 1 else depart + (arrivee - depart) * self._courbe.valueForProgress(t)

    def poser(self, rects: Sequence[Sequence[float]], animer: bool) -> None:
        """La nouvelle géométrie envoyée à la scène."""
        maintenant = self._horloge.elapsed()
        if len(rects) != len(self._courses):    # le Repeater recrée ses vignettes : pas d'animation
            self._courses = [[(v, v, maintenant) for v in rect] for rect in rects]
            return
        for courses, rect in zip(self._courses, rects, strict=True):
            for i, cible in enumerate(rect):
                if cible != courses[i][1]:
                    depart = self._vue(courses[i], maintenant) if animer else cible
                    courses[i] = (depart, cible, maintenant)

    def en_cours(self) -> bool:
        maintenant = self._horloge.elapsed()
        return any(depart != arrivee and maintenant - debut < self.DUREE_MS
                   for courses in self._courses for depart, arrivee, debut in courses)

    def rects_vus(self) -> list[QRectF]:
        maintenant = self._horloge.elapsed()
        return [QRectF(*(self._vue(course, maintenant) for course in courses))
                for courses in self._courses]


if fond_gpu.QUICK_DISPONIBLE:
    class ImagesPeintes(QQuickImageProvider):
        """Sert à une scène des images peintes par Python, rangées par clé.

        Le dictionnaire reste à l'appelant ; toute image change de clé quand elle
        change de contenu : QML garde un cache par URL.
        """

        def __init__(self, images: dict[str, QImage]) -> None:
            super().__init__(QQuickImageProvider.ImageType.Image)
            self._images = images

        def requestImage(self, ident: str, voulue):  # noqa: N802 (Qt)
            image = self._images.get(ident, QImage())
            return image, image.size()


class CarrouselGPU(fond_gpu.EtoilesGPU):
    """La scène des étoiles, plus le double des vignettes."""

    def __init__(self, etoiles: list[tuple[float, float, float, int, bool, float]],
                 parent: QWidget | None = None) -> None:
        self._images: dict[str, QImage] = {}
        super().__init__(etoiles, parent, qml=_QML, fournisseur=ImagesPeintes(self._images))
        # La scène ne fait que montrer : un clic dans la bande revient au `Carousel`.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._glissement = Glissement()
        self._generation = 0
        self._geometries: list[tuple[object, ...]] = []
        self._dernier: list[dict[str, object]] = []

    def oublier(self) -> None:
        """Les vignettes sont reconstruites (catalogue) : autre génération d'images."""
        self._images.clear()
        self._generation += 1
        self._dernier = []

    def _url(self, cle: str, faire: Callable[[], QImage]) -> str:
        if cle not in self._images:
            self._images[cle] = faire()
        return f"image://accio/{cle}"

    def _etat(self, item: CarouselItem, dpr: float, teinte: str) -> dict[str, object]:
        e = item.etat_jumeau()
        id_jeu = item.game.id
        w, h = e["cw"], e["ch"]
        base = f"{self._generation}/{id_jeu}"
        if e["jaquette"]:
            e["image"] = self._url(f"{base}/j/{item.largeur_base()}", item.image_jaquette)
            e["chiffre"] = ""
            e["gris"] = (self._url(f"{base}/g/{item.largeur_base()}", item.image_gris)
                         if e["absent"] else "")
        else:
            taille = f"{w}x{h}/{dpr:g}/{teinte}"
            e["image"] = self._url(f"{base}/r/{taille}", lambda: item.image_fond_repli(dpr))
            e["chiffre"] = self._url(f"{base}/c/{taille}", lambda: item.image_chiffre_repli(dpr))
            e["gris"] = ""
        marques = item.cle_marques()
        if marques:
            # Le texte des pastilles dépend de la langue, leur fond du thème.
            libelles = abs(hash((tr("MAJ"), tr("NOUVEAU"), tr("BIENTÔT"))))
            cle = f"{base}/m/{w}x{h}/{dpr:g}/{teinte}/{libelles}/{marques}"
            e["marques"] = self._url(cle, lambda: item.image_marques(dpr))
        else:
            e["marques"] = ""
        return e

    def synchroniser(self, items: Sequence[CarouselItem], animer: bool) -> None:
        """Le double reprend l'état des vrais widgets.

        `animer` ne vaut que pour une sélection. Une géométrie qui change autrement
        (taille de la fenêtre, bande compacte) suit sans animation, comme les widgets ;
        un état sans nouvelle géométrie (survol) laisse tourner l'animation en cours.
        """
        if self._racine is None:
            return
        dpr = self.devicePixelRatioF()
        teinte = theme.current().id
        self._racine.setProperty("dpr", dpr)
        self._racine.setProperty("fond", theme.bg_qcolor(255))
        self._racine.setProperty("accent", theme.accent_qcolor(255))
        etats = [self._etat(item, dpr, teinte) for item in items]
        geometries = [tuple(e[k] for k in ("x", "y", "cw", "ch", "opacite")) for e in etats]
        if geometries != self._geometries:
            self._geometries = geometries
            self._racine.setProperty("animer", animer)
            self._glissement.poser([(e["x"], e["y"], e["cw"] + 10, e["ch"] + 16)
                                    for e in etats], animer)
        if etats != self._dernier:
            self._dernier = etats
            self._racine.setProperty("etats", etats)

    def glisse(self) -> bool:
        """Les vignettes sont-elles encore en route vers leur place ?"""
        return self._glissement.en_cours()

    def vignette_vue_en(self, pos: QPointF) -> int | None:
        """L'index de la vignette dessinée sous `pos` (coordonnées de la bande).

        À recouvrement, la dernière l'emporte : c'est elle que la scène pose dessus.
        """
        rects = self._glissement.rects_vus()
        return next((i for i in reversed(range(len(rects))) if rects[i].contains(pos)), None)

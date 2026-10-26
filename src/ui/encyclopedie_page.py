"""Les rubriques Personnages et Bestiaire des Collections.

Option 1 retenue par Ludo le 2026-10-26 : des fiches de texte d'abord (nom,
rôle ou lieu, description), une image seulement quand le jeu en a une propre,
un emblème sinon (`core/encyclopedie.py` dit lesquelles). Le choix du jeu est
celui de la page, en haut, commun à toutes les rubriques.

Les images se lisent dans la copie du joueur : une texture de 256 couleurs ou
une carte de HP4 se décode en quelques dizaines de millisecondes, d'où un fil
à part et un minuteur qui les pose au fil de l'eau, comme la Galerie. Le fil
ne rend que des octets B V R A : la QImage se fait ici, dans le fil de
l'interface.

Les fiches de HP1 et HP2 ont aussi leur modèle 3D (`maillages_ue1`) : la fiche
choisie s'affiche en grand en haut de la page, dans une visionneuse qu'on fait
tourner (`modele_3d`), et une fiche sans image reçoit le rendu de son modèle
en vignette, une par tour de minuteur pour ne pas figer la page.
"""

from concurrent.futures import Future, ThreadPoolExecutor

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import encyclopedie, maillages_ue1
from src.core.i18n import dans_la_langue, tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, texte
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.modele_3d import Modele3D
from src.ui.theme import accent_qcolor, current as current_theme
from src.ui.utils import clear_layout, zone_defilable

_LARGEUR_FICHE = 400
_IMAGE = QSize(96, 120)          # une carte de HP4 est deux fois plus haute que large
_ICONE = {encyclopedie.PERSONNAGES: "personnages", encyclopedie.BESTIAIRE: "patte"}
_SCENE = QSize(340, 420)

ModeleLu = tuple[maillages_ue1.Maillage, dict[str, QImage]]


def _images(textures: dict[str, encyclopedie.ImageBgra]) -> dict[str, QImage]:
    return {nom: QImage(px, w, h, 4 * w, QImage.Format.Format_ARGB32).copy()
            for nom, (w, h, px) in textures.items()}


def embleme(rubrique: str, taille: QSize, dpr: float) -> QPixmap:
    """Le cercle doré et le pictogramme de la rubrique, pour une fiche sans image."""
    pix = QPixmap(round(taille.width() * dpr), round(taille.height() * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.GlobalColor.transparent)
    cote = min(taille.width(), taille.height()) - 16
    cercle = QRectF((taille.width() - cote) / 2, (taille.height() - cote) / 2, cote, cote)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(accent_qcolor(110), 1.5))
    p.setBrush(accent_qcolor(18))
    p.drawEllipse(cercle)
    icone = round(cote * 0.45)
    p.drawPixmap(round(cercle.center().x() - icone / 2), round(cercle.center().y() - icone / 2),
                 pixmap_icone(_ICONE[rubrique], icone, accent_qcolor(200)))
    p.end()
    return pix


class _Fiche(QFrame):
    """Une fiche : l'image (ou l'emblème) à gauche, le texte à droite. Avec un
    modèle 3D, un clic la montre en grand."""

    choisie = pyqtSignal(object)

    def __init__(self, rubrique: str, fiche: encyclopedie.Fiche) -> None:
        super().__init__()
        self.setObjectName("carteJeu")      # le cadre des cartes de la page (`mediatheque_page._STYLE`)
        self.fiche = fiche
        self.setProperty("modele", fiche.modele is not None)
        self.setFixedWidth(_LARGEUR_FICHE)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 14, 16, 14)
        h.setSpacing(14)
        self._image = QLabel()
        self._image.setFixedSize(_IMAGE)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setStyleSheet("background: transparent;")
        self._image.setPixmap(embleme(rubrique, _IMAGE, self.devicePixelRatioF()))
        h.addWidget(self._image, alignment=Qt.AlignmentFlag.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(3)
        nom = texte(dans_la_langue(fiche.nom), 15, ENCRE, retour=True)
        nom.setFont(cinzel(12, bold=True))
        v.addWidget(nom)
        v.addWidget(texte(dans_la_langue(fiche.sous_titre), 12, current_theme().accent_light,
                          retour=True))
        v.addSpacing(4)
        v.addWidget(texte(dans_la_langue(fiche.texte), 13, "#c9c7da", retour=True))
        v.addStretch()
        h.addLayout(v, stretch=1)
        self.setAccessibleName(dans_la_langue(fiche.nom))

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if self.property("modele") and event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.choisie.emit(self)

    def marquer(self, choisie: bool) -> None:
        self.setProperty("choisie", choisie)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def sizeHint(self) -> QSize:
        # La hauteur du texte REPLIÉ à la largeur de la fiche : le `FlowLayout`
        # prend la taille souhaitée telle quelle, et celle d'un QLabel qui se
        # replie compte une seule ligne (descriptions coupées, rendu du 2026-10-26).
        lay = self.layout()
        hauteur = lay.heightForWidth(_LARGEUR_FICHE) if lay is not None else -1
        return QSize(_LARGEUR_FICHE, max(hauteur, super().sizeHint().height()))

    def poser(self, image: encyclopedie.ImageBgra) -> None:
        largeur, hauteur, pixels = image
        self.poser_image(QImage(pixels, largeur, hauteur, largeur * 4, QImage.Format.Format_ARGB32))
        self.a_une_image = True

    def poser_image(self, brute: QImage) -> None:
        dpr = self.devicePixelRatioF()
        pix = QPixmap.fromImage(brute.scaled(
            round(_IMAGE.width() * dpr), round(_IMAGE.height() * dpr),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        pix.setDevicePixelRatio(dpr)
        self._image.setPixmap(pix)

    a_une_image = False
    a_une_vignette = False      # le rendu de son modèle, faute d'image


class _Scene(QFrame):
    """La fiche choisie en grand : son modèle qu'on fait tourner, son texte."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("carteJeu")
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 14, 24, 14)
        h.setSpacing(24)
        self.modele = Modele3D()
        self.modele.setFixedSize(_SCENE)
        h.addWidget(self.modele)
        v = QVBoxLayout()
        v.setSpacing(6)
        v.addStretch()
        self._nom = texte("", 18, ENCRE, retour=True)
        self._nom.setFont(cinzel(17, bold=True))
        self._sous_titre = texte("", 13, current_theme().accent_light, retour=True)
        self._texte = texte("", 14, "#c9c7da", retour=True)
        self._texte.setMaximumWidth(520)
        v.addWidget(self._nom)
        v.addWidget(self._sous_titre)
        v.addSpacing(6)
        v.addWidget(self._texte)
        v.addSpacing(14)
        v.addWidget(texte(tr("Glisser pour tourner · molette pour zoomer · double-clic pour revenir"),
                          12, ENCRE_DOUCE, retour=True))
        v.addStretch()
        h.addLayout(v, stretch=1)

    def montrer(self, fiche: encyclopedie.Fiche, modele: ModeleLu | None) -> None:
        self._nom.setText(dans_la_langue(fiche.nom))
        self._sous_titre.setText(dans_la_langue(fiche.sous_titre))
        self._texte.setText(dans_la_langue(fiche.texte))
        if modele is None:
            self.modele.poser(None)
        else:
            self.modele.poser(*modele)


class VueEncyclopedie(QWidget):
    """Les fiches d'une rubrique pour le jeu choisi en haut de la page."""

    def __init__(self, media, rubrique: str) -> None:
        super().__init__()
        self.setObjectName("transparent")
        self._media = media
        self.rubrique = rubrique
        self._jeu = ""
        self.fiches: list[_Fiche] = []
        page = QWidget()
        page.setObjectName("transparent")
        self._lay = QVBoxLayout(page)
        self._lay.setContentsMargins(40, 22, 40, 28)
        self._lay.setSpacing(14)
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.addWidget(zone_defilable(page))
        self._fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix="encyclopedie")
        self._attendues: list[tuple[_Fiche, Future]] = []
        self._modeles_attendus: list[tuple[_Fiche, Future]] = []
        self._modeles: dict[str, ModeleLu] = {}
        self._vignettes: list[_Fiche] = []
        self._choisie: _Fiche | None = None
        self.scene: _Scene | None = None
        # Rend les vignettes des fiches sans image ; jamais montré.
        self._peintre = Modele3D()
        self._chargeur = QTimer(self)
        self._chargeur.setInterval(30)
        self._chargeur.timeout.connect(self._poser_pretes)

    def montrer(self, jeu: str) -> None:
        if jeu == self._jeu and self.fiches:
            return
        self._jeu = jeu
        for _fiche, futur in self._attendues + self._modeles_attendus:
            futur.cancel()
        self._attendues, self._modeles_attendus, self._vignettes = [], [], []
        self._modeles = {}
        self._choisie = None
        if self.scene is not None:
            self.scene.modele.poser(None)
        self.scene = None
        self.fiches = []
        clear_layout(self._lay)
        fiches = encyclopedie.fiches(self.rubrique, jeu)
        if not fiches:
            self._lay.addWidget(texte(tr("Aucune fiche pour ce jeu."), 14, ENCRE_DOUCE))
            self._lay.addStretch()
            return
        compte = (tr("{} personnage") if len(fiches) == 1 else tr("{} personnages")) \
            if self.rubrique == encyclopedie.PERSONNAGES else \
            (tr("{} créature") if len(fiches) == 1 else tr("{} créatures"))
        dossier = self._media.dossier_exe(jeu)
        if dossier is not None and any(f.modele is not None for f in fiches):
            self.scene = _Scene()
            self.scene.hide()               # jusqu'au premier modèle lu
            self._lay.addWidget(self.scene)
        self._lay.addWidget(texte(compte.format(len(fiches)), 13, ENCRE_DOUCE))
        flux = FlowLayout(spacing=14)
        for fiche in fiches:
            vue = _Fiche(self.rubrique, fiche)
            vue.choisie.connect(self.choisir)
            flux.addWidget(vue)
            self.fiches.append(vue)
            if dossier is None:
                continue
            if fiche.image is not None:
                self._attendues.append((vue, self._fil.submit(encyclopedie.image, dossier, fiche)))
            if fiche.modele is not None:
                self._modeles_attendus.append(
                    (vue, self._fil.submit(maillages_ue1.de_la_fiche, dossier, fiche)))
        self._lay.addLayout(flux)
        self._lay.addStretch()
        if self._attendues or self._modeles_attendus:
            self._chargeur.start()

    def choisir(self, vue: _Fiche) -> None:
        """Montre la fiche en grand, avec son modèle s'il est déjà lu."""
        if self.scene is None:
            return
        if self._choisie is not None:
            self._choisie.marquer(False)
        self._choisie = vue
        vue.marquer(True)
        self.scene.montrer(vue.fiche, self._modeles.get(vue.fiche.cle))
        self.scene.show()

    def _poser_pretes(self) -> None:
        restantes = []
        for vue, futur in self._attendues:
            if not futur.done():
                restantes.append((vue, futur))
            elif not futur.cancelled() and futur.exception() is None and futur.result() is not None:
                vue.poser(futur.result())
        self._attendues = restantes
        modeles = []
        for vue, futur in self._modeles_attendus:
            if not futur.done():
                modeles.append((vue, futur))
            elif not futur.cancelled() and futur.exception() is None and futur.result() is not None:
                maillage, textures = futur.result()
                self._modeles[vue.fiche.cle] = (maillage, _images(textures))
                self._vignettes.append(vue)
                if self._choisie is None or self._choisie is vue:
                    self.choisir(vue)
        self._modeles_attendus = modeles
        # Une vignette par tour : une trentaine de millisecondes chacune.
        while self._vignettes:
            vue = self._vignettes.pop(0)
            if not vue.a_une_image and not vue.a_une_vignette:
                self._peintre.poser(*self._modeles[vue.fiche.cle])
                vue.poser_image(self._peintre.rendu(_IMAGE, vue.devicePixelRatioF()))
                vue.a_une_vignette = True
                break
        if not restantes and not modeles and not self._vignettes:
            self._chargeur.stop()

    def fermer(self) -> None:
        """La page se ferme : plus rien à décoder."""
        self._chargeur.stop()
        self._fil.shutdown(wait=False, cancel_futures=True)
        if self.scene is not None:
            self.scene.modele.poser(None)

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
"""

from concurrent.futures import Future, ThreadPoolExecutor

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import encyclopedie
from src.core.i18n import dans_la_langue, tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, texte
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, current as current_theme
from src.ui.utils import clear_layout, zone_defilable

_LARGEUR_FICHE = 400
_IMAGE = QSize(96, 120)          # une carte de HP4 est deux fois plus haute que large
_ICONE = {encyclopedie.PERSONNAGES: "personnages", encyclopedie.BESTIAIRE: "patte"}


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
    """Une fiche : l'image (ou l'emblème) à gauche, le texte à droite."""

    def __init__(self, rubrique: str, fiche: encyclopedie.Fiche) -> None:
        super().__init__()
        self.setObjectName("carteJeu")      # le cadre des cartes de la page (`mediatheque_page._STYLE`)
        self.fiche = fiche
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

    def sizeHint(self) -> QSize:
        # La hauteur du texte REPLIÉ à la largeur de la fiche : le `FlowLayout`
        # prend la taille souhaitée telle quelle, et celle d'un QLabel qui se
        # replie compte une seule ligne (descriptions coupées, rendu du 2026-10-26).
        lay = self.layout()
        hauteur = lay.heightForWidth(_LARGEUR_FICHE) if lay is not None else -1
        return QSize(_LARGEUR_FICHE, max(hauteur, super().sizeHint().height()))

    def poser(self, image: encyclopedie.ImageBgra) -> None:
        largeur, hauteur, pixels = image
        dpr = self.devicePixelRatioF()
        brute = QImage(pixels, largeur, hauteur, largeur * 4, QImage.Format.Format_ARGB32)
        pix = QPixmap.fromImage(brute.scaled(
            round(_IMAGE.width() * dpr), round(_IMAGE.height() * dpr),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        pix.setDevicePixelRatio(dpr)
        self._image.setPixmap(pix)
        self.a_une_image = True

    a_une_image = False


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
        self._chargeur = QTimer(self)
        self._chargeur.setInterval(30)
        self._chargeur.timeout.connect(self._poser_pretes)

    def montrer(self, jeu: str) -> None:
        if jeu == self._jeu and self.fiches:
            return
        self._jeu = jeu
        for _fiche, futur in self._attendues:
            futur.cancel()
        self._attendues = []
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
        self._lay.addWidget(texte(compte.format(len(fiches)), 13, ENCRE_DOUCE))
        flux = FlowLayout(spacing=14)
        dossier = self._media.dossier_exe(jeu)
        for fiche in fiches:
            vue = _Fiche(self.rubrique, fiche)
            flux.addWidget(vue)
            self.fiches.append(vue)
            if fiche.image is not None and dossier is not None:
                self._attendues.append((vue, self._fil.submit(encyclopedie.image, dossier, fiche)))
        self._lay.addLayout(flux)
        self._lay.addStretch()
        if self._attendues:
            self._chargeur.start()

    def _poser_pretes(self) -> None:
        restantes = []
        for vue, futur in self._attendues:
            if not futur.done():
                restantes.append((vue, futur))
            elif not futur.cancelled() and futur.exception() is None and futur.result() is not None:
                vue.poser(futur.result())
        self._attendues = restantes
        if not restantes:
            self._chargeur.stop()

    def fermer(self) -> None:
        """La page se ferme : plus rien à décoder."""
        self._chargeur.stop()
        self._fil.shutdown(wait=False, cancel_futures=True)

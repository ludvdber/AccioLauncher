"""Le bandeau en tête des réglages d'un jeu (maquette B « L'En-tête », choisie par Ludo le 2026-11-13).

Le fond du jeu (`assets/backgrounds/<id>_bg.jpg`, 3840 × 1240, sombre à gauche et le personnage à droite) en
fond, fondu vers la page à gauche et en bas ; dessus, le retour vers la bibliothèque, le nom du jeu en grand et
ses rubriques en pastilles, les mêmes que celles du Carnet et des Collections (`composants.filtre`). Il remplace
le rail de gauche : la page gagne ses 270 px (« on reconnaît le jeu plus vite à la vue », Ludo).

Les Paramètres ont le même bandeau (maquette A « Voûte », Ludo, 2026-11-15), sur un ciel : la Voie lactée de
l'ESO (`ciel_parametres.jpg`, CC BY 4.0, repeinte dans les bleus du thème), cadrée pour COUVRIR toute la largeur,
fondue en bleu nuit sur ses bords (`Bandeau(couvrir=True, bords=…)`).
"""

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import (QColor, QFontMetrics, QIcon, QImage, QLinearGradient, QPainter, QPixmap,
                         QRadialGradient)
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from src.core.config import ASSETS_DIR
from src.ui.composants import ECART_PICTO, MARGES_PAGE, filtre, picto_espace, retrait_de_colonne, transparent
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.theme import current

# Hauteur du bandeau : retour, nom, pastilles, et l'air autour. Le fond se cadre sur le haut du personnage.
HAUTEUR_BANDEAU = 180
# L'image fait ce multiple de la hauteur du bandeau : assez grande pour le visage, assez petite pour laisser
# le nom du jeu sur le noir de sa gauche (à la largeur du bandeau, le visage passait sous le titre).
_ECHELLE = 1.7
# Où, dans la hauteur de l'image, tombe le haut du cadrage (le visage des huit fonds est dans le premier tiers).
_HAUT_DU_CADRAGE = 0.04
# La part de la largeur que l'image couvre au moins : à 1,7 fois la hauteur, elle ne prenait que le coin droit
# d'un écran de 2 048 px, le reste du bandeau restait noir (audit plein écran, 2026-11-16).
_LARGEUR_MINI_IMAGE = 0.55
_FOND_PAGE = QColor("#060611")
_TAILLE_PICTO = 16


CIEL_PARAMETRES = ASSETS_DIR / "backgrounds" / "ciel_parametres.jpg"
# Le bleu nuit des bords du ciel : la couleur des bordures fortes du thème Poudlard (#2c3e6b), assombrie.
BLEU_NUIT = QColor(16, 30, 86)


def fond_du_jeu(ident: str) -> Path:
    return ASSETS_DIR / "backgrounds" / f"{ident}_bg.jpg"


# Le JPEG du fond (3 840 × 1 240) prenait 100 à 170 ms sur le fil de l'interface, à chaque ouverture des
# réglages d'un jeu (banc du 2026-11-19) : il se décode ici pendant que la page se bâtit, et la
# première peinture le prend. Une QImage sur ce fil, jamais une QPixmap (fil de l'interface seul).
_FIL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bandeau")
# Le dernier fond demandé (chemin → décodage, prêt ou en cours) : la fiche du jeu le demande dès
# qu'elle montre le jeu (`precharger`), et ses réglages le trouvent prêt. Avec les rubriques bâties à la
# demande, la page se bâtissait plus vite que le JPEG ne se décodait : la première peinture l'attendait
# 60 à 75 ms (banc du 2026-11-19). Un seul gardé : 19 Mo pour un fond de 3 840 × 1 240.
_DERNIER: dict[str, Future[QImage]] = {}


def _decodage(chemin: Path) -> Future[QImage] | None:
    """Le décodage de `chemin` : celui déjà lancé, sinon un nouveau (le précédent, pas commencé, s'annule)."""
    cle = str(chemin)
    if (deja := _DERNIER.get(cle)) is not None and not deja.cancelled():
        return deja
    if not chemin.is_file():
        return None
    for ancien in _DERNIER.values():
        ancien.cancel()
    _DERNIER.clear()
    _DERNIER[cle] = _FIL.submit(QImage, cle)
    return _DERNIER[cle]


def precharger(ident_jeu: str) -> None:
    """Décode d'avance le fond du bandeau de ce jeu, sur le fil : ses réglages s'ouvriront sans l'attendre."""
    _decodage(fond_du_jeu(ident_jeu))


class Bandeau(QWidget):
    """Le bandeau peint : l'image, puis les fondus. Les widgets se posent dessus.

    `couvrir` : l'image couvre toute la largeur (le ciel des Paramètres) au lieu d'être mise à `_ECHELLE` fois
    la hauteur, ancrée à droite (le personnage d'un jeu). `bords` : une couleur qui voile les bords avant le
    fondu vers la page (le bleu nuit du ciel)."""

    def __init__(self, image: Path, parent: QWidget | None = None, *, hauteur: int = HAUTEUR_BANDEAU,
                 couvrir: bool = False, bords: QColor | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("bandeauJeu")
        self.setFixedHeight(hauteur)
        self._couvrir = couvrir
        self._bords = bords
        self._chemin = image
        self._attente = _decodage(image)
        self._pixmap: QPixmap | None = None
        self._cache: QPixmap | None = None
        self._cache_pour: QSize | None = None
        self._marges_de_base: tuple[int, int, int, int] | None = None

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        """Le contenu (retour, nom, pastilles) s'aligne sur la colonne centrée des pages ; l'image, elle, reste
        sur toute la largeur."""
        super().resizeEvent(event)
        lay = self.layout()
        if lay is None:
            return
        if self._marges_de_base is None:
            m = lay.contentsMargins()
            self._marges_de_base = (m.left(), m.top(), m.right(), m.bottom())
        gauche, haut, droite, bas = self._marges_de_base
        retrait = retrait_de_colonne(self.width())
        lay.setContentsMargins(gauche + retrait, haut, droite + retrait, bas)

    def _image(self) -> QPixmap:
        """L'image source, attendue au besoin (le plus souvent déjà décodée à la première peinture)."""
        if self._pixmap is None:
            attente, self._attente = self._attente, None
            if attente is None:
                self._pixmap = QPixmap()
            elif attente.cancelled():
                # Un autre fond demandé avant que celui-ci commence (les Paramètres, un autre jeu) : sur place.
                self._pixmap = QPixmap(str(self._chemin))
            else:
                self._pixmap = QPixmap.fromImage(attente.result())
        return self._pixmap

    def _fond(self) -> QPixmap | None:
        """L'image mise à la largeur du bandeau (à sa densité de pixels), recalculée seulement au redimensionnement."""
        image = self._image()
        if image.isNull():
            return None
        dpr = self.devicePixelRatioF()
        taille = QSize(round(self.width() * dpr), round(self.height() * dpr))
        if self._cache is None or self._cache_pour != taille:
            if self._couvrir:
                echelle = max(taille.width() / image.width(), taille.height() / image.height())
                mise = image.scaled(round(image.width() * echelle), round(image.height() * echelle),
                                    transformMode=Qt.TransformationMode.SmoothTransformation)
                haut = (mise.height() - taille.height()) // 2
            else:
                hauteur = round(taille.height() * _ECHELLE)
                largeur_mini = taille.width() * _LARGEUR_MINI_IMAGE
                if image.width() * hauteur / image.height() < largeur_mini:
                    hauteur = round(largeur_mini * image.height() / image.width())
                mise = image.scaledToHeight(hauteur, Qt.TransformationMode.SmoothTransformation)
                haut = min(round(mise.height() * _HAUT_DU_CADRAGE), max(0, mise.height() - taille.height()))
            # Ancré à droite : le personnage est à droite des huit fonds ; à gauche, la page.
            self._cache = QPixmap(taille)
            self._cache.fill(_FOND_PAGE)
            peintre = QPainter(self._cache)
            peintre.drawPixmap(taille.width() - mise.width(), -haut, mise)
            peintre.end()
            self._cache.setDevicePixelRatio(dpr)
            self._cache_pour = taille
        return self._cache

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        r = QRectF(self.rect())
        p.fillRect(r, _FOND_PAGE)
        fond = self._fond()
        if fond is not None:
            p.drawPixmap(0, 0, fond)
        if self._bords is not None:
            # Le voile des bords : un ovale clair au centre droit, le bleu nuit vers les quatre côtés.
            voile = QRadialGradient(r.width() * 0.7, r.height() * 0.4, max(r.width(), r.height()) * 0.75)
            couleur = QColor(self._bords)
            couleur.setAlpha(0)
            voile.setColorAt(0.0, couleur)
            voile.setColorAt(0.45, couleur)
            couleur.setAlpha(225)
            voile.setColorAt(1.0, couleur)
            p.fillRect(r, voile)
        # Fondu vers la gauche : le nom et les pastilles se lisent sur du noir, l'image vit à droite.
        gauche = QLinearGradient(0, 0, r.width(), 0)
        if self._bords is None:
            gauche.setColorAt(0.0, _FOND_PAGE)
            gauche.setColorAt(0.45, _FOND_PAGE)
            gauche.setColorAt(0.7, QColor(6, 6, 17, 90))
        else:
            # Le ciel reste visible sous les pastilles : un fondu bleu nuit, pas un noir plein.
            gauche.setColorAt(0.0, QColor(8, 10, 30, 225))
            gauche.setColorAt(0.36, QColor(16, 30, 86, 120))
        gauche.setColorAt(1.0, QColor(6, 6, 17, 0))
        p.fillRect(r, gauche)
        # Fondu vers le bas : le bandeau se fond dans la page, sans trait.
        bas = QLinearGradient(0, r.height() * 0.55, 0, r.height())
        bas.setColorAt(0.0, QColor(6, 6, 17, 0))
        bas.setColorAt(1.0, _FOND_PAGE)
        p.fillRect(r, bas)
        p.end()


class NomDuJeu(QLabel):
    """Le nom du jeu, sur une ligne : sa police descend de 24 à 15 points pour tenir dans la largeur (« Harry
    Potter et les Reliques de la Mort - 1re partie » ne tient pas en 24 dans la plus petite fenêtre), et ne
    passe à la ligne qu'en dernier recours ; le bandeau garde sa hauteur."""

    _TAILLES = (24, 22, 20, 18, 16, 15)

    def __init__(self, nom: str) -> None:
        super().__init__(nom)
        self.setTextFormat(Qt.TextFormat.PlainText)   # le nom vient du CATALOGUE
        self.setObjectName("nomDuJeu")
        self.setStyleSheet("color: #f4f2f8; background: transparent;")
        self.setMinimumWidth(1)
        self.setFont(cinzel(self._TAILLES[0], bold=True))

    def setText(self, texte: str) -> None:  # noqa: N802 (Qt)
        """Un nom posé après la mise en page se réajuste aussi : seul `resizeEvent` le faisait."""
        super().setText(texte)
        self._ajuster()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._ajuster()

    def _ajuster(self) -> None:
        for taille in self._TAILLES:
            police = cinzel(taille, bold=True)
            if QFontMetrics(police).horizontalAdvance(self.text()) <= self.width():
                break
        if police.pointSize() != self.font().pointSize():
            self.setFont(police)
        self.setWordWrap(QFontMetrics(police).horizontalAdvance(self.text()) > self.width())


def pastille_rubrique(libelle: str, icone: str) -> QPushButton:
    """Une rubrique du jeu en pastille, comme celles du Carnet et des Collections, avec son pictogramme."""
    b = filtre(libelle, grand=True)
    picto = QIcon()
    picto.addPixmap(picto_espace(pixmap_icone(icone, _TAILLE_PICTO, QColor("#c9c7da"))),
                    QIcon.Mode.Normal, QIcon.State.Off)
    picto.addPixmap(picto_espace(pixmap_icone(icone, _TAILLE_PICTO, QColor(current().accent_light))),
                    QIcon.Mode.Normal, QIcon.State.On)
    b.setIcon(picto)
    b.setIconSize(QSize(_TAILLE_PICTO + ECART_PICTO, _TAILLE_PICTO))
    return b


def badge_dans_la_pastille(pastille: QPushButton, badge: QWidget) -> None:
    """« BÊTA » DANS la pastille de sa rubrique, à droite du nom. Posé à côté, entre deux pastilles, on ne savait
    pas s'il parlait de Difficulté ou de Fichiers (Ludo, 2026-11-15). Le badge laisse passer la souris : le clic
    et l'infobulle sont ceux de la pastille, qui reprend son explication."""
    lay = QHBoxLayout(pastille)
    lay.setContentsMargins(0, 0, 10, 0)
    lay.addStretch()
    lay.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)
    badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    if badge.toolTip():
        pastille.setToolTip(badge.toolTip())
    # La place du badge s'ajoute à droite du nom : la largeur conseillée de la pastille la compte.
    # Une règle sur CETTE pastille seule (propriété `badge`) : la feuille des filtres vit dans `composants`.
    pastille.setProperty("badge", True)
    pastille.setStyleSheet(f'QPushButton[badge="true"] {{ padding-right: {badge.sizeHint().width() + 22}px; }}')
    # Sa largeur conseillée, pas plus : le ressort de la mise en page intérieure la rendait extensible, et la
    # pastille mangeait toute la rangée.
    pastille.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def bandeau_du_jeu(game, retour: QPushButton) -> tuple[Bandeau, QLabel, QHBoxLayout]:
    """Le bandeau d'un jeu : (bandeau, nom du jeu, rangée où poser les pastilles des rubriques)."""
    bandeau = Bandeau(fond_du_jeu(game.id))
    lay = QVBoxLayout(bandeau)
    lay.setContentsMargins(MARGES_PAGE[0], 18, MARGES_PAGE[2], 14)
    lay.setSpacing(0)
    lay.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
    lay.addSpacing(10)
    nom = NomDuJeu(game.name)
    lay.addWidget(nom)
    lay.addSpacing(16)
    rangee_w = QWidget()
    transparent(rangee_w, "rubriquesDuJeu")
    rangee = QHBoxLayout(rangee_w)
    rangee.setContentsMargins(0, 0, 0, 0)
    rangee.setSpacing(10)
    lay.addWidget(rangee_w)
    lay.addStretch()
    return bandeau, nom, rangee

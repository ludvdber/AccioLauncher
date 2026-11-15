"""Le bandeau en tête des réglages d'un jeu (maquette B « L'En-tête », choisie par Ludo le 2026-11-13).

Le fond du jeu (`assets/backgrounds/<id>_bg.jpg`, 3840 × 1240, sombre à gauche et le personnage à droite) en
fond, fondu vers la page à gauche et en bas ; dessus, le retour vers la bibliothèque, le nom du jeu en grand et
ses rubriques en pastilles, les mêmes que celles du Carnet et des Collections (`composants.filtre`). Il remplace
le rail de gauche : la page gagne ses 270 px (« on reconnaît le jeu plus vite à la vue », Ludo).
"""

from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QIcon, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.core.config import ASSETS_DIR
from src.ui.composants import MARGES_PAGE, filtre, transparent
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
_FOND_PAGE = QColor("#060611")
_TAILLE_PICTO = 16


def fond_du_jeu(ident: str) -> Path:
    return ASSETS_DIR / "backgrounds" / f"{ident}_bg.jpg"


class Bandeau(QWidget):
    """Le bandeau peint : l'image du jeu, puis les deux fondus. Les widgets se posent dessus (`contenu`)."""

    def __init__(self, ident_jeu: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("bandeauJeu")
        self.setFixedHeight(HAUTEUR_BANDEAU)
        chemin = fond_du_jeu(ident_jeu)
        self._image = QPixmap(str(chemin)) if chemin.is_file() else QPixmap()
        self._cache: QPixmap | None = None
        self._cache_pour: QSize | None = None

    def _fond(self) -> QPixmap | None:
        """L'image mise à la largeur du bandeau (à sa densité de pixels), recalculée seulement au redimensionnement."""
        if self._image.isNull():
            return None
        dpr = self.devicePixelRatioF()
        taille = QSize(round(self.width() * dpr), round(self.height() * dpr))
        if self._cache is None or self._cache_pour != taille:
            mise = self._image.scaledToHeight(round(taille.height() * _ECHELLE),
                                              Qt.TransformationMode.SmoothTransformation)
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
        # Fondu vers la gauche : le nom et les pastilles se lisent sur du noir, l'image vit à droite.
        gauche = QLinearGradient(0, 0, r.width(), 0)
        gauche.setColorAt(0.0, _FOND_PAGE)
        gauche.setColorAt(0.45, _FOND_PAGE)
        gauche.setColorAt(0.7, QColor(6, 6, 17, 90))
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

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
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
    picto.addPixmap(pixmap_icone(icone, _TAILLE_PICTO, QColor("#c9c7da")), QIcon.Mode.Normal, QIcon.State.Off)
    picto.addPixmap(pixmap_icone(icone, _TAILLE_PICTO, QColor(current().accent_light)),
                    QIcon.Mode.Normal, QIcon.State.On)
    b.setIcon(picto)
    b.setIconSize(QSize(_TAILLE_PICTO, _TAILLE_PICTO))
    return b


def bandeau_du_jeu(game, retour: QPushButton) -> tuple[Bandeau, QLabel, QHBoxLayout]:
    """Le bandeau d'un jeu : (bandeau, nom du jeu, rangée où poser les pastilles des rubriques)."""
    bandeau = Bandeau(game.id)
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

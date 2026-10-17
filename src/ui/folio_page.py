"""Le folio d'un jeu, en PAGE : les emplacements à gauche, ce que dit la sauvegarde à droite.

Maquette « Folio HP1, quatre maisons » validée par Ludo le 2026-10-14 : les
cartes trouvées, les dragées, et la Coupe des quatre maisons en sabliers (les
points de chaque maison sont dans la sauvegarde, pas seulement ceux de
Gryffondor : la course se voit).

Ouverte depuis la fiche du jeu dans Mes années, ou depuis le bouton Folio de
la bibliothèque ; son retour ramène d'où l'on vient. Lecture seule :
`src/core/folio.py` ne fait que lire la sauvegarde, les textes du jeu et les
images des cartes (`textures_ue1.py`), toutes dans la copie installée.

La carte choisie s'affiche dans une colonne FIXE à droite (Ludo, 2026-10-14) :
sous la grille, sa fiche tombait hors de l'écran et l'on cliquait sans rien voir.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, qRgba,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core import folio, sauvegardes
from src.core.i18n import get_language, tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, feuille_de_style, police, surtitre, texte
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.galerie_page import nom_court
from src.ui.icon_button import pixmap_icone
from src.ui.reglages_widgets import _STYLE as _STYLE_RAIL
from src.ui.theme import accent_qcolor, current as current_theme, themed
from src.ui.utils import zone_defilable

_LARGEUR_RAIL = 280
_VIGNETTE = 56        # hauteur de l'image d'une sauvegarde dans le rail
_MARGE_RAIL = 18      # marges latérales du rail
_MARGE_LIGNE = 12     # marges latérales d'une ligne de partie
_LARGEUR_FICHE = (236, 420)   # suit la fenêtre : 30 % de ce qui reste après le rail
_MARGE_FICHE = 24
_IMAGE_FICHE = 220        # la carte du jeu fait 256 : jamais agrandie
_COLONNES = 5             # 25 cartes : cinq rangées de cinq, au moins
_ECART_CASES = 8
# Plafonds relevés le 2026-10-14 (108 et 290 px) : en plein écran, la grille
# restait minuscule à gauche d'un grand vide (capture de Ludo, 2552 px).
_CASE_MIN, _CASE_MAX = 56, 160
# HP1 seul : au-delà de cinq colonnes, la grille en prend autant que la place
# le permet (capture de Ludo, 2026-10-16 : un tiers vide à droite), et des
# cases jusqu'à 200 px (la grande texture fait 256).
_CASE_MAX_HP1 = 200

# Les couleurs des maisons (maquette) : le haut du sablier, puis le bas.
_COULEURS = {
    folio.GRYFFONDOR: ("#e0473f", "#ae0001"),
    folio.SERPENTARD: ("#3f9a5c", "#1a472a"),
    folio.SERDAIGLE: ("#5b7bd6", "#222f5b"),
    folio.POUFSOUFFLE: ("#ecb939", "#b8860b"),
}

_STYLE = """
QPushButton#emplacement {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;
}
QPushButton#emplacement:hover { background: rgba(255, 255, 255, 0.04); }
QPushButton#emplacement:checked {
    background: rgba(214, 167, 44, 0.09); border-color: rgba(214, 167, 44, 0.45);
}
QPushButton#emplacement[focusClavier="true"]:focus { border: 2px solid #d6a72c; }
QFrame#tuile, QFrame#coupe, QFrame#objet {
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.16); border-radius: 12px;
}
#sortAppris {
    color: #f2e6c4; background: rgba(214, 167, 44, 0.12);
    border: 1px solid rgba(214, 167, 44, 0.55); border-radius: 15px; padding: 5px 14px;
}
#sortAVenir {
    color: #7d7b96; background: transparent;
    border: 1px dashed rgba(255, 255, 255, 0.16); border-radius: 15px; padding: 5px 14px;
}
QFrame#fiche {
    background: #0a0a16; border: none; border-left: 1px solid rgba(214, 167, 44, 0.16);
}
"""


def nom_maison(maison: str) -> str:
    return {folio.GRYFFONDOR: tr("Gryffondor"), folio.SERPENTARD: tr("Serpentard"),
            folio.SERDAIGLE: tr("Serdaigle"), folio.POUFSOUFFLE: tr("Poufsouffle")}[maison]


def phrase_coupe(releve: folio.Releve) -> str:
    """« Serpentard mène de 18 points », « Gryffondor mène », « À égalité »."""
    tete = releve.en_tete()
    if tete is None:
        return tr("À égalité") if releve.lu and any(releve.points.values()) else ""
    maison, ecart = tete
    if maison == folio.GRYFFONDOR:
        return tr("Gryffondor mène")
    return tr("{} mène de {} points").format(nom_maison(maison), ecart)


class _Sablier(QWidget):
    """Une colonne de sable aux couleurs de la maison, haute de ses points."""

    def __init__(self, maison: str, part: float) -> None:
        super().__init__()
        self._maison = maison
        self._part = max(0.0, min(1.0, part))
        self.setFixedSize(46, 120)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        verre = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(255, 255, 255, 8))
        p.drawRoundedRect(verre, 8, 8)
        if self._part > 0:
            haut = max(4.0, (verre.height() - 6) * self._part)
            sable = QRectF(verre.x() + 3, verre.bottom() - 3 - haut, verre.width() - 6, haut)
            clair, fonce = _COULEURS[self._maison]
            degrade = QLinearGradient(sable.topLeft(), sable.bottomLeft())
            degrade.setColorAt(0.0, QColor(clair))
            degrade.setColorAt(1.0, QColor(fonce))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(degrade)
            p.drawRoundedRect(sable, 5, 5)
        p.end()


def cadre_visible(tex) -> tuple[int, int, int, int] | None:
    """(x, y, largeur, hauteur) de ce qui n'est pas transparent dans une
    texture masquée ; None si rien à rogner. Les icônes du menu de HP2 n'occupent
    que le centre de leur texture de 128 px : sans ce cadre, un blason
    s'affichait à 40 % de sa taille."""
    if not tex.masquee:
        return None
    lignes = [y for y in range(tex.hauteur)
              if tex.indices[y * tex.largeur:(y + 1) * tex.largeur].strip(b"\x00")]
    if not lignes:
        return None
    gauche, droite = tex.largeur, 0
    for y in lignes:
        ligne = tex.indices[y * tex.largeur:(y + 1) * tex.largeur]
        gauche = min(gauche, len(ligne) - len(ligne.lstrip(b"\x00")))
        droite = max(droite, len(ligne.rstrip(b"\x00")))
    return gauche, lignes[0], droite - gauche, lignes[-1] - lignes[0] + 1


def pixmap_texture(tex, cote: int, dpr: float, rogner: bool = False) -> QPixmap:
    """Une texture du jeu (256 couleurs) en pixmap de `cote` px logiques ;
    `rogner` : seulement sa partie visible (icônes du menu)."""
    image = QImage(tex.indices, tex.largeur, tex.hauteur, tex.largeur,
                   QImage.Format.Format_Indexed8)
    image.setColorTable([qRgba(r, v, b, 0 if tex.masquee and i == 0 else 255)
                         for i, (r, v, b, _a) in enumerate(tex.palette)])
    cadre = cadre_visible(tex) if rogner else None
    if cadre is not None:
        image = image.copy(*cadre)
    physique = max(1, round(cote * dpr))
    pix = QPixmap.fromImage(
        image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied).scaled(
            physique, physique, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
    pix.setDevicePixelRatio(dpr)
    return pix


def image_bgra(image: tuple[int, int, bytes] | None, cote: int, dpr: float,
               rogner: bool = False, colonnes: tuple[float, float] = (0.0, 1.0)) -> QPixmap | None:
    """Une image du jeu en B V R A (HP3 à HP6) à `cote` px logiques, ou None.
    `colonnes` : la bande verticale gardée (les objets de la pensine de HP4 ont
    une volute de chaque côté) ; `rogner` : puis seulement sa partie visible."""
    if image is None:
        return None
    largeur, hauteur, pixels = image
    brute = QImage(pixels, largeur, hauteur, largeur * 4, QImage.Format.Format_ARGB32)
    gauche, droite = round(largeur * colonnes[0]), round(largeur * colonnes[1])
    x, y, w, h = gauche, 0, max(1, droite - gauche), hauteur
    if rogner:
        opaques = [(i % largeur, i // largeur) for i in range(largeur * hauteur)
                   if pixels[4 * i + 3] > 16 and gauche <= i % largeur < droite]
        if opaques:
            xs, ys = [p[0] for p in opaques], [p[1] for p in opaques]
            x, y, w, h = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    physique = max(1, round(cote * dpr))
    pix = QPixmap.fromImage(brute.copy(x, y, w, h).scaled(
        physique, physique, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation))
    pix.setDevicePixelRatio(dpr)
    return pix


class _Jauge(QWidget):
    """Une part sur un total, en or sur un rail discret."""

    def __init__(self, part: float) -> None:
        super().__init__()
        self.setFixedHeight(5)
        self._part = max(0.0, min(1.0, part))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(self.rect().toRectF(), 2.5, 2.5)
        if self._part > 0:
            plein = self.rect().toRectF()
            plein.setWidth(max(5.0, plein.width() * self._part))
            p.setBrush(accent_qcolor())
            p.drawRoundedRect(plein, 2.5, 2.5)
        p.end()


_ICONE_TUILE = 44


def _tuile(chiffre: str, libelle: str, part: float | None = None,
           icone: QPixmap | None = None) -> QFrame:
    """Le chiffre en or, son libellé, et sa jauge s'il a un total ; à droite,
    l'icône du jeu (dragées, cartes, écussons…), dans une place de même largeur
    pour toutes : les chiffres d'une rangée restent alignés."""
    tuile = QFrame()
    tuile.setObjectName("tuile")
    # Pas de largeur minimale imposée : elle passait sous celle du chiffre, et
    # « 6 / 80 » de HP3 se coupait à droite (capture de Ludo, 2026-10-17).
    h = QHBoxLayout(tuile)
    h.setContentsMargins(18, 14, 14, 14)
    h.setSpacing(10)
    v = QVBoxLayout()
    v.setSpacing(4)
    h.addLayout(v, stretch=1)
    if icone is not None:
        image = QLabel()
        image.setStyleSheet("background: transparent;")
        image.setPixmap(icone)
        image.setFixedWidth(_ICONE_TUILE)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(image, alignment=Qt.AlignmentFlag.AlignVCenter)
    nombre = texte(chiffre, 26, current_theme().accent_light)
    nombre.setFont(police(26, gras=True))
    v.addWidget(nombre)
    v.addWidget(texte(libelle, 13, ENCRE_DOUCE, retour=True))
    if part is not None:
        v.addSpacing(4)
        v.addWidget(_Jauge(part))
    return tuile


class Rangee(QWidget):
    """Les tuiles d'une page, de même largeur : sur une ligne quand elles y
    tiennent, sinon sur autant de lignes qu'il faut (4 tuiles → 2 × 2)."""

    def __init__(self, *tuiles: QFrame) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self._tuiles = tuiles
        self._grille = QGridLayout(self)
        self._grille.setContentsMargins(0, 0, 0, 0)
        self._grille.setSpacing(12)
        self._colonnes = 0
        self._placer(len(tuiles))

    def _placer(self, colonnes: int) -> None:
        colonnes = max(1, min(len(self._tuiles), colonnes))
        if colonnes == self._colonnes:
            return
        self._colonnes = colonnes
        for t in self._tuiles:
            self._grille.removeWidget(t)
        for c in range(self._grille.columnCount()):
            self._grille.setColumnStretch(c, 0)
        for i, t in enumerate(self._tuiles):
            self._grille.addWidget(t, i // colonnes, i % colonnes)
        for c in range(colonnes):
            self._grille.setColumnStretch(c, 1)

    def _colonnes_pour(self, largeur: int) -> int:
        tuile = max((t.minimumSizeHint().width() for t in self._tuiles), default=0)
        tiennent = max(1, (largeur + 12) // (tuile + 12))
        if tiennent >= len(self._tuiles):
            return len(self._tuiles)
        lignes = -(-len(self._tuiles) // tiennent)
        return -(-len(self._tuiles) // lignes)       # des lignes équilibrées

    def minimumSizeHint(self) -> QSize:
        # UNE tuile : la page peut se rétrécir, les tuiles passeront à la ligne.
        tuile = max((t.minimumSizeHint().width() for t in self._tuiles), default=0)
        return QSize(tuile, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        self._placer(self._colonnes_pour(event.size().width()))
        super().resizeEvent(event)


def en_tete(titre: str, icone: QPixmap | None = None, compte: str = "") -> QHBoxLayout:
    """Le titre d'une section : son icône du jeu s'il y en a une, le surtitre,
    et à droite un compte (« 4 / 15 »)."""
    ligne = QHBoxLayout()
    ligne.setSpacing(8)
    if icone is not None:
        image = QLabel()
        image.setStyleSheet("background: transparent;")
        image.setPixmap(icone)
        ligne.addWidget(image, alignment=Qt.AlignmentFlag.AlignTop)
    # Le titre passe à la ligne : sur une seule, deux séries côte à côte de
    # HP3 imposaient 729 px à une zone qui en avait 680 (2026-10-17).
    nom = surtitre(titre)
    nom.setWordWrap(True)
    ligne.addWidget(nom, stretch=1)
    if compte:
        ligne.addWidget(texte(compte, 12, ENCRE_DOUCE), alignment=Qt.AlignmentFlag.AlignTop)
    return ligne


class _CarteSorcier(QPushButton):
    """Une case du folio : la carte trouvée telle que le jeu la dessine, son
    numéro si le jeu n'est plus installé, des pointillés si elle reste à trouver."""

    def __init__(self, numero: int, carte: folio.Carte | None, trouvee: bool,
                 vignette=None) -> None:
        super().__init__()
        self.numero = numero
        self.trouvee = trouvee
        self.vignette = vignette if trouvee else None   # textures_ue1.TexturePaletee
        self._pix: QPixmap | None = None
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(_CASE_MIN, _CASE_MIN)
        nom = carte.nom if carte else tr("Carte {}").format(numero)
        self.setAccessibleName(nom if trouvee else tr("Carte pas encore trouvée"))

    def resizeEvent(self, event) -> None:
        self._pix = None
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cadre = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        choisie = self.isChecked()
        if self.trouvee:
            p.setBrush(QColor("#2a1f10") if choisie else QColor("#1a1508"))
            p.setPen(QPen(QColor("#e8c547") if choisie else QColor(214, 167, 44, 90),
                          2 if choisie else 1))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            stylo = QPen(QColor("#e8c547") if choisie else QColor(255, 255, 255, 46),
                         2 if choisie else 1)
            stylo.setStyle(Qt.PenStyle.DashLine)
            p.setPen(stylo)
        p.drawRoundedRect(cadre, 6, 6)
        if self.vignette is not None:
            if self._pix is None:
                self._pix = pixmap_texture(self.vignette, self.width() - 6,
                                           self.devicePixelRatioF())
            p.drawPixmap(3, 3, self._pix)
        elif self.trouvee:
            p.setPen(QColor("#f2e6c4") if choisie else QColor("#d9cfae"))
            p.setFont(cinzel(10, bold=True))
            p.drawText(cadre, Qt.AlignmentFlag.AlignCenter, str(self.numero))
        p.end()


def nom_emplacement(releve) -> str:
    """« Sauvegarde rapide » ou « Emplacement 2 » (HP1, HP3)."""
    return (tr("Sauvegarde rapide") if releve.rapide
            else tr("Emplacement {}").format(releve.emplacement))


def vignette_sauvegarde(image: Path | QImage | None, dpr: float) -> QPixmap | None:
    """L'image d'une sauvegarde (BMP du jeu, ou image déjà décodée) à
    `_VIGNETTE` px de haut, coins arrondis ; None sans image lisible."""
    if image is None:
        return None
    source = image if isinstance(image, QImage) else QImage(str(image))
    if source.isNull():
        return None
    haut = round(_VIGNETTE * dpr)
    large = max(1, round(haut * source.width() / max(1, source.height())))
    pix = QPixmap(large, haut)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    chemin = QPainterPath()
    chemin.addRoundedRect(QRectF(0, 0, large, haut), 5 * dpr, 5 * dpr)
    p.setClipPath(chemin)
    p.drawImage(QRectF(0, 0, large, haut), source)
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


class _LigneEmplacement(QPushButton):
    def __init__(self, nom: str, quand: datetime | None, lieu: str, plus_avance: bool,
                 vignette: QPixmap | None = None) -> None:
        super().__init__()
        self.setObjectName("emplacement")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # L'image de la sauvegarde à gauche (HP1 : celle du menu de chargement
        # du jeu ; HP2 : la capture prise en sauvegardant). Le rail devient
        # coloré, et l'endroit se reconnaît avant de lire son nom.
        dehors = QHBoxLayout(self)
        dehors.setContentsMargins(_MARGE_LIGNE, 9, _MARGE_LIGNE, 9)
        dehors.setSpacing(10)
        place_image = 0
        if vignette is not None:
            image = QLabel()
            image.setPixmap(vignette)
            image.setFixedSize(vignette.deviceIndependentSize().toSize())
            image.setStyleSheet("background: transparent;")
            dehors.addWidget(image, alignment=Qt.AlignmentFlag.AlignTop)
            place_image = image.width() + dehors.spacing()
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        dehors.addLayout(v, stretch=1)
        haut = QHBoxLayout()
        haut.setSpacing(8)
        titre = texte(nom, 15, ENCRE)
        titre.setFont(police(15, gras=True))
        titre.setMinimumWidth(titre.sizeHint().width())
        haut.addWidget(titre)
        haut.addStretch()
        v.addLayout(haut)
        if quand is not None:
            from src.ui.versions_dialog import date_longue
            date = texte(date_longue(quand.strftime("%Y-%m-%d")), 12, ENCRE_DOUCE)
            # « Emplacement 1 » et « 28 septembre 2026 » ne tiennent pas côte à
            # côte dans le rail : la date passe dessous plutôt que de rogner le
            # nom (mesuré avec la police réelle, pas un nombre écrit à la main).
            place = _LARGEUR_RAIL - 2 * (_MARGE_RAIL + _MARGE_LIGNE) - 2 - place_image
            if titre.sizeHint().width() + haut.spacing() + date.sizeHint().width() <= place:
                haut.addWidget(date)
            else:
                v.addWidget(date)
        if lieu:
            v.addWidget(texte(lieu, 13, "#c9c7da", retour=place_image > 0))
        if plus_avance:
            v.addWidget(texte(tr("La plus avancée"), 12, current_theme().accent_light))
        etats = [nom, lieu,
                 tr("La plus avancée") if plus_avance else ""]
        self.setAccessibleName(", ".join(e for e in etats if e))
        for enfant in self.findChildren(QLabel):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # La hauteur de son CONTENU : un QPushButton ne la tire pas de son layout.
        self.setMinimumHeight(dehors.sizeHint().height())


def colonnes_hp1(dispo: int) -> int:
    """Le nombre de colonnes des 25 cartes de HP1 pour `dispo` px : le moins
    possible sans dépasser 200 px par case, cinq au minimum, et des rangées
    équilibrées (7 colonnes : 7-7-7-4, plutôt que 8 : 8-8-8-1)."""
    n = folio.CARTES_HP1
    voulu = max(_COLONNES, -(-(dispo + _ECART_CASES) // (_CASE_MAX_HP1 + _ECART_CASES)))
    rangees = -(-n // min(voulu, n))
    return max(_COLONNES, -(-n // rangees))


class FolioPage(QDialog):
    """Ce que les sauvegardes de HP1 disent de la partie.

    Les autres jeux (`ui/folio_jeux.py`) en héritent le rail des parties et
    la mise en page, et remplacent `_charger`, `_entree` et `_construire`."""

    _colonnes = _COLONNES
    _case_min = _CASE_MIN
    _case_max = _CASE_MAX

    def __init__(self, game, install_path: Path, parent: QWidget | None = None,
                 revenir=None) -> None:
        super().__init__(parent)
        self.setObjectName("folio")
        self.game = game
        self._revenir = revenir
        self.setWindowTitle(tr("Folio"))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE_RAIL + _STYLE) + feuille_de_style())
        self._system = install_path / Path(game.executable).parent
        self._cases: list[_CarteSorcier] = []
        self._grille_hp1: QGridLayout | None = None
        self._colonnes_hp1 = 0
        self._plus = None
        self.releves: list = []
        self._blasons: dict = {}      # maison → texture du jeu (`_charger`)
        self._charger()
        self.releve = None
        self._lignes: dict[int, _LigneEmplacement] = {}

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._rail())
        self._hote = QVBoxLayout()
        self._hote.setContentsMargins(0, 0, 0, 0)
        corps = QWidget()
        corps.setLayout(self._hote)
        racine.addWidget(corps, stretch=1)
        self._corps: QWidget | None = None
        depart = self._depart()
        if depart is not None:
            self.choisir(depart.emplacement)
        else:
            self._afficher(None)

    def _charger(self) -> None:
        self.releves = folio.emplacements_hp1(sauvegardes.fichiers(self.game.sauvegardes))
        self.cartes, self._titres = folio.textes_hp1(
            folio.fichier_textes(self._system, get_language()))
        self._paquet = folio.paquet_menu(self._system) if self._system.is_dir() else None
        self._plus = folio.le_plus_avance(self.releves)
        self._blasons = {m: folio.image_menu_hp1(self._paquet, nom)
                         for m, nom in folio.BLASONS_HP1.items()}

    def _depart(self):
        """La partie montrée à l'ouverture."""
        return folio.la_derniere_jouee(self.releves)

    def _entree(self, releve) -> tuple[str, datetime | None, str]:
        """Ce que le rail montre d'une partie : nom, date, lieu."""
        return nom_emplacement(releve), releve.modifie, folio.lieu(self._titres, releve.niveau)

    def _image(self, releve) -> Path | QImage | None:
        """L'image de la partie dans le rail ; None : la ligne n'en a pas. Les
        pages des autres jeux héritent de celle-ci : seul HP1 a ces images."""
        if self.game.id != "hp1":
            return None
        return folio.image_sauvegarde_hp1(self._system, releve.chemin)

    # ── Rail ──

    def _rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(_LARGEUR_RAIL)
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(_MARGE_RAIL, 22, _MARGE_RAIL, 20)
        lay.setSpacing(6)
        retour = QPushButton(tr("Mes années") if self._revenir else tr("Bibliothèque"))
        retour.setObjectName("retour")
        retour.setFont(police(13))
        retour.setIcon(QIcon(pixmap_icone("retour", 16, QColor("#a9a7c4"))))
        retour.setIconSize(QSize(16, 16))
        retour.setCursor(Qt.CursorShape.PointingHandCursor)
        retour.setAutoDefault(False)
        retour.clicked.connect(self._retour)
        lay.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(16)
        lay.addWidget(surtitre(tr("Folio")))
        nom = QLabel(nom_court(self.game.name))
        nom.setTextFormat(Qt.TextFormat.PlainText)   # le nom vient du CATALOGUE
        nom.setWordWrap(True)
        nom.setFont(cinzel(13, bold=True))
        nom.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        lay.addWidget(nom)
        lay.addSpacing(16)
        if self.releves:
            lay.addWidget(surtitre(tr("Sauvegarde lue")))
            lay.addSpacing(4)
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        for r in self.releves:
            ligne = _LigneEmplacement(*self._entree(r), r is self._plus,
                                      vignette_sauvegarde(self._image(r), self.devicePixelRatioF()))
            ligne.toggled.connect(lambda oui, rel=r: oui and self._afficher(rel))
            self._groupe.addButton(ligne)
            self._lignes[r.emplacement] = ligne
            lay.addWidget(ligne)
        lay.addStretch()
        lay.addWidget(texte(tr("Lue sans être modifiée."),
                            12, ENCRE_DOUCE, retour=True))
        return rail

    def _retour(self) -> None:
        self.accept()
        if self._revenir is not None:
            self._revenir()

    def choisir(self, emplacement: int) -> None:
        ligne = self._lignes.get(emplacement)
        if ligne is not None:
            ligne.setChecked(True)

    # ── Corps ──

    def _afficher(self, releve: folio.Releve | None) -> None:
        self.releve = releve
        if self._corps is not None:
            self._corps.hide()
            self._corps.deleteLater()
        self._corps = self._construire(releve)
        self._hote.addWidget(self._corps)

    def _construire(self, releve: folio.Releve | None) -> QWidget:
        corps = QWidget()
        h = QHBoxLayout(corps)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(36, 30, 36, 28)
        lay.setSpacing(0)
        self._zone = zone_defilable(page)
        # La largeur utile est celle du VIEWPORT, connue après la mise en page
        # de la zone, pas au redimensionnement de la page (cases trop petites).
        self._zone.viewport().installEventFilter(self)
        h.addWidget(self._zone, stretch=1)
        self._cases = []
        self._grille_hp1 = None

        if releve is None or not releve.lu:
            message = (tr("Aucune sauvegarde trouvée pour ce jeu.") if releve is None else
                       tr("Partie tout juste commencée : pas encore de carte ni de points."))
            titre = QLabel(tr("Folio"))
            titre.setFont(cinzel_decorative(22))
            titre.setStyleSheet("color: #f4f2f8; background: transparent;")
            lay.addWidget(titre)
            lay.addSpacing(12)
            lay.addWidget(texte(message, 16, "#c9c7da", retour=True))
            lay.addStretch()
            return corps

        # Tout dans UNE colonne : à 980 px, rail, coupe et fiche côte à côte ne
        # laissaient que 380 px aux sabliers et aux cartes.
        lay.addWidget(Rangee(
            _tuile(f"{len(releve.cartes)} / {folio.CARTES_HP1}", tr("Cartes trouvées"),
                   len(releve.cartes) / folio.CARTES_HP1, self._icone("cartes")),
            _tuile(str(releve.dragees), tr("Dragées surprises"), None, self._icone("dragees"))))
        lay.addSpacing(12)
        lay.addWidget(self._coupe(releve))
        lay.addSpacing(26)
        sorts = folio.sorts_hp1(releve.niveau)
        if sorts is not None:
            lay.addWidget(surtitre(tr("Sorts appris")))
            lay.addSpacing(10)
            ligne = FlowLayout(spacing=8)
            for nom, appris in sorts:
                pastille = QLabel(nom)    # nom latin du sort : le même dans toutes les langues
                pastille.setObjectName("sortAppris" if appris else "sortAVenir")
                pastille.setFont(police(14, gras=appris))
                pastille.setAccessibleName(nom + (", " + tr("appris") if appris
                                                  else ", " + tr("pas encore appris")))
                ligne.addWidget(pastille)
            lay.addLayout(ligne)
            lay.addSpacing(26)

        # L'un SOUS l'autre : côte à côte, ils imposaient 470 px à la colonne
        # et la faisaient déborder sous la fiche de la carte à 980 px.
        lay.addWidget(surtitre(tr("Cartes des sorcières et sorciers célèbres")))
        lay.addSpacing(4)
        lay.addWidget(texte(tr("Pointillés : pas encore trouvée"), 12, ENCRE_DOUCE))
        lay.addSpacing(12)
        grille = QGridLayout()
        grille.setHorizontalSpacing(_ECART_CASES)
        grille.setVerticalSpacing(_ECART_CASES)
        self._grille_hp1 = grille
        self._groupe_cartes = QButtonGroup(corps)
        self._groupe_cartes.setExclusive(True)
        for numero in range(1, folio.CARTES_HP1 + 1):
            trouvee = numero in releve.cartes
            vignette = folio.image_carte_hp1(self._paquet, numero) if trouvee else None
            case = _CarteSorcier(numero, self.cartes.get(numero), trouvee, vignette)
            case.toggled.connect(lambda oui, n=numero: oui and self._montrer_carte(n))
            self._groupe_cartes.addButton(case)
            self._cases.append(case)
        self._colonnes_hp1 = 0
        lay.addLayout(grille)
        lay.addStretch()
        h.addWidget(self._colonne_fiche())
        premiere = min(releve.cartes) if releve.cartes else 1
        self._cases[premiere - 1].setChecked(True)
        self._ajuster_cases()
        return corps

    def _colonne_fiche(self) -> QFrame:
        """La carte choisie, toujours visible à droite de la grille."""
        self._fiche = QFrame()
        self._fiche.setObjectName("fiche")
        self._fiche.setFixedWidth(self._largeur_fiche())
        contenu = QWidget()
        contenu.setStyleSheet("background: transparent;")
        f = QVBoxLayout(contenu)
        f.setContentsMargins(_MARGE_FICHE, 30, _MARGE_FICHE, 24)
        f.setSpacing(6)
        self._fiche_image = QLabel()
        self._fiche_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fiche_image.setStyleSheet("background: transparent;")
        f.addWidget(self._fiche_image)
        f.addSpacing(10)
        self._fiche_nom = texte("", 18, ENCRE, retour=True)
        self._fiche_nom.setFont(cinzel(13, bold=True))
        self._fiche_dates = texte("", 13, current_theme().accent_light, retour=True)
        self._fiche_texte = texte("", 14, "#c9c7da", retour=True)
        f.addWidget(self._fiche_nom)
        f.addWidget(self._fiche_dates)
        f.addSpacing(8)
        f.addWidget(self._fiche_texte)
        f.addStretch()
        v = QVBoxLayout(self._fiche)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(zone_defilable(contenu))
        return self._fiche

    def _largeur_fiche(self) -> int:
        mini, maxi = _LARGEUR_FICHE
        return max(mini, min(maxi, int((self.width() - _LARGEUR_RAIL) * 0.3)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._cases and self._fiche.width() != self._largeur_fiche():
            self._fiche.setFixedWidth(self._largeur_fiche())
            self._montrer_carte(self.carte_montree)

    def eventFilter(self, objet, event) -> bool:
        if event.type() == QEvent.Type.Resize and self._cases and objet is self._zone.viewport():
            self._ajuster_cases()
        return super().eventFilter(objet, event)

    def _ajuster_cases(self) -> None:
        """Les cases suivent la place : cinq par rangée, entre 56 et 160 px
        (la grande texture, 256 px : la petite serait floue à cette taille)."""
        if not self._cases:
            return
        marges = self._zone.widget().layout().contentsMargins()
        dispo = self._zone.viewport().width() - marges.left() - marges.right()
        colonnes, plafond = self._colonnes, self._case_max
        if self._grille_hp1 is not None:
            colonnes, plafond = colonnes_hp1(dispo), _CASE_MAX_HP1
            self._placer_hp1(colonnes)
        cote = (dispo - (colonnes - 1) * _ECART_CASES) // colonnes
        cote = max(self._case_min, min(plafond, cote))
        for case in self._cases:
            if case.width() != cote:
                case.setFixedSize(cote, cote)

    def _placer_hp1(self, colonnes: int) -> None:
        if colonnes == self._colonnes_hp1 or self._grille_hp1 is None:
            return
        self._colonnes_hp1 = colonnes
        grille = self._grille_hp1
        for case in self._cases:
            grille.removeWidget(case)
        for k, case in enumerate(self._cases):
            grille.addWidget(case, k // colonnes, k % colonnes)
        for c in range(grille.columnCount()):
            grille.setColumnStretch(c, 1 if c == colonnes else 0)

    def _icone(self, cle: str) -> QPixmap | None:
        """Une icône des tuiles (`folio.ICONES_HP1`), rognée à sa partie visible."""
        tex = folio.image_menu_hp1(self._paquet, folio.ICONES_HP1[cle])
        return (pixmap_texture(tex, 40, self.devicePixelRatioF(), rogner=True)
                if tex is not None else None)

    def _coupe(self, releve: folio.Releve) -> QFrame:
        coupe = QFrame()
        coupe.setObjectName("coupe")
        v = QVBoxLayout(coupe)
        v.setContentsMargins(20, 14, 20, 16)
        v.setSpacing(12)
        # La phrase SOUS le titre : côte à côte, ils faisaient déborder la colonne à 980 px.
        entete = QVBoxLayout()
        entete.setSpacing(4)
        entete.addWidget(surtitre(tr("La Coupe des quatre maisons")))
        self.phrase_coupe = texte(phrase_coupe(releve), 13, current_theme().accent_light)
        entete.addWidget(self.phrase_coupe)
        v.addLayout(entete)
        rangee = QHBoxLayout()
        rangee.setSpacing(10)
        plus_haut = max(1, *releve.points.values())
        tete = releve.en_tete()
        for maison in folio.MAISONS:
            points = releve.points.get(maison, 0)
            col = QVBoxLayout()
            col.setSpacing(6)
            blason = self._blasons.get(maison)
            if blason is not None:
                # Le blason du jeu au-dessus du sable (HPMenu.u, HP2_Menu.utx).
                image = QLabel()
                image.setStyleSheet("background: transparent;")
                image.setPixmap(pixmap_texture(blason, 44, self.devicePixelRatioF(), rogner=True))
                col.addWidget(image, alignment=Qt.AlignmentFlag.AlignHCenter)
            chiffre = texte(str(points), 15, ENCRE)
            chiffre.setFont(police(15, gras=True))
            col.addWidget(chiffre, alignment=Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(_Sablier(maison, points / plus_haut), alignment=Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(texte(nom_maison(maison), 13, "#dcdaea"), alignment=Qt.AlignmentFlag.AlignHCenter)
            note = (tr("En tête") if tete and tete[0] == maison
                    else tr("Votre maison") if maison == folio.GRYFFONDOR else "")
            etiquette = texte(note, 11, current_theme().accent_light if note == tr("En tête")
                              else ENCRE_DOUCE)
            etiquette.setMinimumHeight(16)
            col.addWidget(etiquette, alignment=Qt.AlignmentFlag.AlignHCenter)
            rangee.addLayout(col, stretch=1)
        v.addLayout(rangee)
        coupe.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        return coupe

    def _montrer_carte(self, numero: int) -> None:
        carte = self.cartes.get(numero)
        trouvee = self.releve is not None and numero in self.releve.cartes
        # Une carte pas trouvée ne montre pas son image : ce serait la dévoiler.
        image = folio.image_carte_hp1(self._paquet, numero) if trouvee else None
        self._fiche_image.setVisible(image is not None)
        if image is not None:
            cote = min(_IMAGE_FICHE, self._fiche.width() - 2 * _MARGE_FICHE - 1)   # 1 : le liseré
            self._fiche_image.setFixedHeight(cote)
            self._fiche_image.setPixmap(pixmap_texture(image, cote, self.devicePixelRatioF()))
        if trouvee:
            self._fiche_nom.setText(carte.nom if carte else tr("Carte {}").format(numero))
            self._fiche_dates.setText(carte.dates if carte else "")
            self._fiche_texte.setText(carte.texte if carte else
                                      tr("Installez le jeu pour lire le texte de la carte."))
        else:
            self._fiche_nom.setText(tr("Pas encore trouvée"))
            self._fiche_dates.setText("")
            self._fiche_texte.setText(tr("Elle se cache quelque part dans le château."))
        self.carte_montree = numero

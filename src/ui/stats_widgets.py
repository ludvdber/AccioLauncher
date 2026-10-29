"""Les pièces de « Mes années à Poudlard » : les mois, les cartes de sauvegarde et leurs petites fonctions de mise en forme. Sorti de `stats_dialog` le 2026-10-03 (1 062 lignes) ; la fenêtre les assemble.
"""
from datetime import date
from PyQt6.QtCore import QLocale, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from src.core import sauvegardes
from src.core.formatting import format_duree_compacte, minutes_arrondies
from src.core.i18n import get_language, tr
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor, current as current_theme

_SECONDAIRE = "#b0b0c8"
_DISCRET = "#8a8aa6"

_HISTO_H = 130
_COLONNE_SAGA = 250

# Plafond d'ouverture : au-delà, le corps défile. La fenêtre ne s'ouvre
# JAMAIS plus haute que son contenu — c'est ce plafond qui borne, pas un vide.
# Il suit l'ÉCRAN : 720 px fixes coupaient les douze mois sur un 1440p, où il
# restait 400 px libres, et 900 fixes déborderaient d'un portable 1366×768.
_HAUTEUR_MAX = 900
_MARGE_ECRAN = 80


def _hauteur_max(widget: QWidget) -> int:
    ecran = widget.screen()
    if ecran is None:
        return _HAUTEUR_MAX
    return max(400, min(_HAUTEUR_MAX, ecran.availableGeometry().height() - _MARGE_ECRAN))


def _duree_courte(secondes: int) -> str:
    """Durée pour une LÉGENDE, où la place se compte en dizaines de pixels.

    `format_duree_compacte` rend « moins d'une minute » (105 px dans une case
    de 98 : on lisait « oins d'une minu ») et « 12 h 05 min », trop long au
    pied d'une barre.
    """
    if secondes < 60:
        return tr("< 1 min")
    if secondes < 3600:
        # Même arrondi que la colonne de la saga : la barre de septembre et
        # la ligne « En septembre » portaient 38 et 39 min pour 38,5.
        return _duree(secondes)
    return tr("{} h").format(int(secondes / 3600 + 0.5))


def _minutes(secondes: int) -> int:
    """La règle commune (`formatting.minutes_arrondies`) : demi-minute vers le haut."""
    return minutes_arrondies(secondes)


def _duree(secondes: int) -> str:
    """Toute durée de la page passe par ici. Même arrondi que la fiche du jeu :
    `format_duree_compacte` suit `minutes_arrondies` depuis le 2026-10-29."""
    return format_duree_compacte(secondes)


def _date(jour: date | None) -> str:
    return jour.strftime("%d/%m/%Y") if jour else ""


def _locale() -> QLocale:
    """Les noms de mois dans la langue de l'INTERFACE, par Qt : vingt-quatre
    chaînes de moins à faire traduire à des bénévoles."""
    return QLocale(get_language())


def _texte(contenu: str, taille: int = 13, couleur: str = "#ffffff",
           gras: bool = False) -> QLabel:
    """QLabel en PlainText — ces chaînes portent des noms venus du CATALOGUE,
    et `AutoText` bascule en rich text dès que Qt renifle du HTML."""
    lbl = QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    poids = "bold" if gras else "normal"
    lbl.setStyleSheet(
        f"color: {couleur}; font-size: {taille}px; font-weight: {poids};"
        " background: transparent;")
    return lbl


def _chiffre(valeur: str, taille: int = 20, couleur: str = "#ffffff") -> QLabel:
    lbl = QLabel(valeur)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(cinzel(taille, bold=True))
    lbl.setStyleSheet(f"color: {couleur}; background: transparent;")
    return lbl


def _titre_section(texte: str) -> QLabel:
    lbl = QLabel(texte.upper())
    lbl.setObjectName("titreSection")
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    return lbl


class _Paragraphe(QLabel):
    """Texte long en `wordWrap`, dont la hauteur suit la largeur RÉELLE.

    Un `QLabel` en `wordWrap` posé dans un layout sans hauteur imposée annonce
    un `sizeHint` calculé à une largeur qui n'est pas la sienne : le layout ne
    lui accorde qu'une ligne et le texte se coupe. Le piège a été payé cinq
    fois dans ce projet ; le remède vit ici une fois pour toutes.
    """

    def __init__(self, contenu: str, parent=None, taille: int = 12) -> None:
        super().__init__(contenu, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setStyleSheet(
            f"color: {_SECONDAIRE}; font-size: {taille}px; background: transparent;")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMinimumHeight(0)
        self.setMinimumHeight(self.heightForWidth(self.width()))


class _Mois(QWidget):
    """Les douze derniers mois en barres, le mois en cours en or vif.

    Toujours douze colonnes : c'est l'AXE. Un mois sans partie garde un trait
    au ras du sol et ne porte pas de chiffre — aucun « 0 » n'est écrit.
    """

    def __init__(self, cases: list[tuple[int, int, int]], parent=None) -> None:
        super().__init__(parent)
        self._cases = cases
        self.setFixedHeight(_HISTO_H)
        self.setMouseTracking(True)

    def _colonne(self, i: int) -> QRectF:
        n = len(self._cases)
        ecart = 6.0
        largeur = (self.width() - ecart * (n - 1)) / n
        return QRectF(i * (largeur + ecart), 0.0, largeur, float(self.height()))

    def mouseMoveEvent(self, event) -> None:
        x = event.position().x()
        for i, (annee, mois, secondes) in enumerate(self._cases):
            col = self._colonne(i)
            if col.left() <= x <= col.right():
                nom = _locale().standaloneMonthName(mois, QLocale.FormatType.LongFormat)
                valeur = _duree(secondes) if secondes else tr("aucune partie")
                self.setToolTip(f"{nom} {annee} : {valeur}")
                return
        self.setToolTip("")

    def _police(self) -> QFont:
        police = QFont(self.font())
        police.setPointSize(8)
        return police

    def _haut_barre(self, i: int) -> float | None:
        """Le haut de la barre `i` (son chiffre s'y pose), None sans partie."""
        secondes = self._cases[i][2]
        if not secondes:
            return None
        haut_texte = QFontMetrics(self._police()).height() + 4
        zone_h = self.height() - 2 * haut_texte
        maxi = max((s for _, _, s in self._cases), default=0) or 1
        return haut_texte + zone_h - max(4.0, zone_h * secondes / maxi)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        police = self._police()
        p.setFont(police)
        fm = QFontMetrics(police)
        haut_texte = fm.height() + 4
        zone_h = self.height() - 2 * haut_texte
        noms = self._noms(fm)
        for i in range(len(self._cases)):
            col = self._colonne(i)
            actuel = i == len(self._cases) - 1
            sol = haut_texte + zone_h
            haut = self._haut_barre(i)
            if haut is not None:
                barre = QRectF(col.left(), haut, col.width(), sol - haut)
                p.fillRect(barre, accent_qcolor(255 if actuel else 175))
                p.setPen(QColor("#ffffff") if actuel else QColor(_SECONDAIRE))
                x, largeur, valeur = self._valeur(i, fm)
                p.drawText(QRectF(x, barre.top() - haut_texte, largeur, haut_texte),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                           valeur)
            else:
                p.fillRect(QRectF(col.left(), sol - 2, col.width(), 2),
                           QColor(44, 62, 107, 140))
            p.setPen(accent_qcolor() if actuel else QColor(_DISCRET))
            p.drawText(QRectF(col.left(), sol + 3, col.width(), haut_texte),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                       noms[i])
        p.end()

    def _valeur(self, i: int, fm: QFontMetrics) -> tuple[float, float, str]:
        """(x, largeur, texte) du chiffre au-dessus de la barre `i`.

        Rogné d'après la place DISPONIBLE, jamais d'après sa propre largeur :
        arrondie à l'entier, elle coupait « 3 h » en « 3… » à 125 % (15 px
        mesurés, un peu plus dessinés ; Relevé de Ludo, 2026-10-24).
        """
        gauche, droite = self._place_valeur(i)
        texte = _duree_courte(self._cases[i][2])
        largeur = min(fm.horizontalAdvance(texte) + 4.0, droite - gauche)
        x = min(max(self._colonne(i).center().x() - largeur / 2, gauche), droite - largeur)
        return x, largeur, fm.elidedText(texte, Qt.TextElideMode.ElideRight, int(largeur))

    def _place_valeur(self, i: int) -> tuple[float, float]:
        """Bornes gauche et droite du chiffre posé au-dessus de la barre `i`.

        La barre seule (≈ 20 px) coupait « 14 h » en « 14… » à toutes les
        tailles (Bazzite, 2026-10-20). Le chiffre prend aussi l'écart, et la
        moitié d'une voisine sans partie, qui n'a pas de chiffre à elle.
        """
        col = self._colonne(i)
        gauche, droite = col.left() - 3.0, col.right() + 3.0
        if i > 0 and self._voisine_libre(i, i - 1):
            gauche -= col.width() / 2
        if i < len(self._cases) - 1 and self._voisine_libre(i, i + 1):
            droite += col.width() / 2
        return max(0.0, gauche), min(float(self.width()), droite)

    def _voisine_libre(self, i: int, j: int) -> bool:
        """La voisine `j` prête la moitié de sa colonne : sans partie, ou son
        chiffre à une autre HAUTEUR que celui de `i`. Octobre, dernier et collé
        au bord, lisait « 3… » à côté d'un septembre plus bas (2026-10-24)."""
        haut_j = self._haut_barre(j)
        haut_i = self._haut_barre(i)
        if haut_j is None or haut_i is None:
            return True
        return abs(haut_i - haut_j) >= QFontMetrics(self._police()).height() + 4

    def _noms(self, fm: QFontMetrics) -> list[str]:
        """« nov. déc. janv. 26 … », ou les initiales si UNE seule ne tient pas.

        Les abréviations du système rognées donnaient « n… ja… fé… se… », vu
        avec les vraies polices le 2026-10-14. Toutes en initiales plutôt qu'un
        mélange : l'infobulle redit le mois et l'année en entier.
        """
        loc = _locale()
        largeur = self._colonne(0).width()
        courts = []
        for annee, mois, _s in self._cases:
            nom = loc.standaloneMonthName(mois, QLocale.FormatType.ShortFormat)
            courts.append(f"{nom} {annee % 100:02d}" if mois == 1 else nom)
        if all(fm.horizontalAdvance(nom) <= largeur for nom in courts):
            return courts
        return [loc.standaloneMonthName(mois, QLocale.FormatType.NarrowFormat)
                for _a, mois, _s in self._cases]


class _Jauge(QWidget):
    """La part d'une sauvegarde dans le temps de son jeu : un filet, pas un
    pourcentage écrit."""

    def __init__(self, part: float, parent=None) -> None:
        super().__init__(parent)
        self._part = max(0.0, min(1.0, part))
        self.setFixedHeight(3)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(44, 62, 107, 140))
        if self._part:
            p.fillRect(QRectF(0, 0, self.width() * self._part, self.height()),
                       accent_qcolor())
        p.end()


class _GrilleSauvegardes(QWidget):
    """Les cartes des sauvegardes, autant par rangée que la largeur le permet
    (entre 300 et 460 px chacune, quatre au plus) : deux colonnes fixes en
    faisaient des bandeaux de 980 px en plein écran (capture de Ludo,
    2026-10-16)."""

    LARGEUR_MIN, LARGEUR_MAX, ECART = 300, 460, 12

    def __init__(self, cartes: list[QWidget], parent=None) -> None:
        super().__init__(parent)
        self._cartes = cartes
        self._colonnes = 0
        self._grille = QGridLayout(self)
        self._grille.setContentsMargins(0, 0, 0, 0)
        self._grille.setSpacing(self.ECART)
        for carte in cartes:
            carte.setMaximumWidth(self.LARGEUR_MAX)
        self._placer(2)

    @classmethod
    def colonnes(cls, largeur: int, nombre: int) -> int:
        voulu = (largeur + cls.ECART) // (cls.LARGEUR_MIN + cls.ECART)
        return max(1, min(4, nombre, voulu))

    def _placer(self, colonnes: int) -> None:
        if colonnes == self._colonnes:
            return
        self._colonnes = colonnes
        for carte in self._cartes:
            self._grille.removeWidget(carte)
        for i, carte in enumerate(self._cartes):
            self._grille.addWidget(carte, i // colonnes, i % colonnes)
        for c in range(self._grille.columnCount()):
            self._grille.setColumnStretch(c, 1 if c < colonnes else 0)
        # Ce qui reste à droite des cartes plafonnées reste vide, à droite.
        self._grille.setColumnStretch(colonnes, 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._placer(self.colonnes(self.width(), len(self._cartes)))


class _CarteSauvegarde(QFrame):
    """Une sauvegarde : son nom, son temps, et ce que le disque sait d'elle."""

    def __init__(self, vue: sauvegardes.Vue, temps_max: int,
                 recente: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("carteSave")
        couche = QVBoxLayout(self)
        couche.setContentsMargins(14, 12, 14, 12)
        couche.setSpacing(8)

        haut = QHBoxLayout()
        nom = (tr("Sauvegarde rapide") if vue.rapide
               else tr("Emplacement {}").format(vue.numero) if vue.numero is not None
               else tr("Sauvegarde"))
        lbl_nom = QLabel(nom)
        lbl_nom.setFont(cinzel(12, bold=True))
        lbl_nom.setStyleSheet("background: transparent;")
        haut.addWidget(lbl_nom)
        if recente:
            # Celle qu'on reprendra : c'est la question qu'on se pose en
            # ouvrant un jeu à quatre emplacements, et les dates seules
            # obligent à les comparer de tête.
            haut.addWidget(_texte(tr("dernière jouée"), 12, current_theme().accent))
        haut.addStretch(1)
        if vue.temps:
            haut.addWidget(_chiffre(_duree(vue.temps), 14, current_theme().accent))
        couche.addLayout(haut)
        if vue.temps:
            # Une jauge vide sur quatre cartes n'est pas une information, c'est
            # quatre fois la même absence : elle n'apparaît qu'avec un temps.
            couche.addWidget(_Jauge(vue.temps / temps_max if temps_max else 0.0))

        grille = QGridLayout()
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(2)
        grille.setColumnStretch(1, 1)
        # Un emplacement RECOMMENCÉ (`progression`) : la carte suit l'aventure
        # en cours, celles d'avant tiennent en une ligne, jamais effacées.
        debut = tr("Nouvelle aventure") if vue.nouvelle else tr("Commencée")
        if vue.commencee == vue.derniere:
            # « Commencée le 4, dernière fois le 4 » : une date, dite une fois.
            lignes = [(debut if vue.nouvelle else tr("Jouée le"), _date(vue.derniere))]
        else:
            lignes = [(debut, _date(vue.commencee)),
                      (tr("Dernière fois"), _date(vue.derniere))]
        if vue.avancement is not None:
            # Le pourcentage du jeu lui-même (HP5 : « 14 % TERMINÉ »).
            lignes.insert(0, (tr("Avancement"), tr("{} %").format(vue.avancement)))
        lignes.append((tr("Parties"), str(vue.parties) if vue.parties else ""))
        if vue.precedentes and vue.temps_precedent:
            avant = _duree(vue.temps_precedent)
            lignes.append((tr("Aventure précédente"), avant) if vue.precedentes == 1
                          else (tr("Aventures précédentes"), f"{vue.precedentes} · {avant}"))
        rang = 0
        for libelle, valeur in lignes:
            if not valeur:
                continue            # aucun zéro, aucune case vide
            grille.addWidget(_texte(libelle, 13, _DISCRET), rang, 0)
            v = _texte(valeur, 13, _SECONDAIRE)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grille.addWidget(v, rang, 1)
            rang += 1
        couche.addLayout(grille)
        # Les cartes d'une rangée ont la hauteur de la plus haute : sans ressort,
        # la place en trop s'étalait entre les lignes et les titres voisins ne
        # tombaient plus à la même hauteur (3 px d'écart, capture du 2026-10-17).
        couche.addStretch(1)

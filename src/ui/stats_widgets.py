"""Les pièces de « Mes années à Poudlard » : les mois, les cartes de sauvegarde et leurs petites fonctions de mise en forme. Sorti de `stats_dialog` le 2026-10-03 (1 062 lignes) ; la fenêtre les assemble.
"""
from datetime import date
from PyQt6.QtCore import QLocale, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from src.core import sauvegardes
from src.core.formatting import format_duree_compacte
from src.core.i18n import get_language, tr
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor

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
    """Arrondi à la minute la plus proche, demi-minute vers le haut.

    `round()` arrondit au PAIR (46,5 → 46) : juste pour une moyenne, faux pour
    un compteur qu'on additionne à la main.
    """
    return int(secondes / 60 + 0.5) if secondes > 0 else 0


def _duree(secondes: int) -> str:
    """Toute durée de la page passe par ici : même arrondi partout.

    `format_duree_compacte` arrondit au PAIR (`round`), `_minutes` à la
    demi-minute supérieure : mélangés, 38,5 min s'écrivaient 38 sur la barre
    et 39 dans la colonne.
    """
    return format_duree_compacte(60 * _minutes(secondes) if secondes >= 60 else secondes)


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

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        police = p.font()
        police.setPointSize(8)
        p.setFont(police)
        fm = QFontMetrics(police)
        haut_texte = fm.height() + 4
        maxi = max((s for _, _, s in self._cases), default=0) or 1
        zone_h = self.height() - 2 * haut_texte
        loc = _locale()
        for i, (annee, mois, secondes) in enumerate(self._cases):
            col = self._colonne(i)
            actuel = i == len(self._cases) - 1
            sol = haut_texte + zone_h
            if secondes:
                h = max(4.0, zone_h * secondes / maxi)
                barre = QRectF(col.left(), sol - h, col.width(), h)
                p.fillRect(barre, accent_qcolor(255 if actuel else 175))
                p.setPen(QColor("#ffffff") if actuel else QColor(_SECONDAIRE))
                valeur = fm.elidedText(_duree_courte(secondes),
                                       Qt.TextElideMode.ElideRight, int(col.width()))
                p.drawText(QRectF(col.left(), barre.top() - haut_texte,
                                  col.width(), haut_texte),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                           valeur)
            else:
                p.fillRect(QRectF(col.left(), sol - 2, col.width(), 2),
                           QColor(44, 62, 107, 140))
            nom = loc.standaloneMonthName(mois, QLocale.FormatType.ShortFormat)
            if mois == 1:
                nom = f"{nom} {annee % 100:02d}"
            p.setPen(accent_qcolor() if actuel else QColor(_DISCRET))
            p.drawText(QRectF(col.left(), sol + 3, col.width(), haut_texte),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                       fm.elidedText(nom, Qt.TextElideMode.ElideRight, int(col.width())))
        p.end()


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
        nom = (tr("Emplacement {}").format(vue.numero) if vue.numero is not None
               else tr("Sauvegarde"))
        lbl_nom = QLabel(nom)
        lbl_nom.setFont(cinzel(11, bold=True))
        lbl_nom.setStyleSheet("background: transparent;")
        haut.addWidget(lbl_nom)
        if recente:
            # Celle qu'on reprendra : c'est la question qu'on se pose en
            # ouvrant un jeu à quatre emplacements, et les dates seules
            # obligent à les comparer de tête.
            haut.addWidget(_texte(tr("dernière jouée"), 11, "#d6a72c"))
        haut.addStretch(1)
        if vue.temps:
            haut.addWidget(_chiffre(_duree(vue.temps), 14, "#d6a72c"))
        couche.addLayout(haut)
        if vue.temps:
            # Une jauge vide sur quatre cartes n'est pas une information, c'est
            # quatre fois la même absence : elle n'apparaît qu'avec un temps.
            couche.addWidget(_Jauge(vue.temps / temps_max if temps_max else 0.0))

        grille = QGridLayout()
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(2)
        grille.setColumnStretch(1, 1)
        if vue.commencee == vue.derniere:
            # « Commencée le 4, dernière fois le 4 » : une date, dite une fois.
            lignes = [(tr("Jouée le"), _date(vue.derniere))]
        else:
            lignes = [(tr("Commencée"), _date(vue.commencee)),
                      (tr("Dernière fois"), _date(vue.derniere))]
        lignes.append((tr("Parties"), str(vue.parties) if vue.parties else ""))
        rang = 0
        for libelle, valeur in lignes:
            if not valeur:
                continue            # aucun zéro, aucune case vide
            grille.addWidget(_texte(libelle, 12, _DISCRET), rang, 0)
            v = _texte(valeur, 12, _SECONDAIRE)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grille.addWidget(v, rang, 1)
            rang += 1
        couche.addLayout(grille)

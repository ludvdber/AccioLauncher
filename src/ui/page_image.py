"""L'onglet Image des réglages d'un jeu (HP4 à HP7b), refait d'après la maquette « Curseurs gradués »
(2026-11-12, choisie par Ludo) : six catégories en onglets, une recherche, une ligne par réglage
(nom, coût, contrôle) et, à droite, la fiche du réglage survolé.

Ce que la maquette corrige de la page d'avant :

- une longue page de 35 lignes : six catégories, comme dans un jeu ;
- un « ? » et un œil sur chaque ligne : la fiche de droite les remplace et dit en plus ce que
  fait le jeu d'origine, ce que livre Accio, et la valeur choisie ;
- des listes déroulantes pour des nombres : un curseur gradué (`CurseurGradue`) avec ses
  paliers nommés, le repère Accio (or) et celui du jeu (argent), et une valeur exacte ;
- deux à cinq choix courts : des boutons côte à côte, lisibles sans ouvrir de liste.

Tout s'écrit AUSSITÔT dans l'ini du correctif (`reglages_correctif.ecrire`), comme le reste de la
fenêtre ; un échec remet le contrôle sur ce que porte le fichier et la fenêtre le dit.
"""

import html
import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core import reglages_correctif as rc
from src.core import reglages_image, resolution_jeu
from src.core.config import Config
from src.core.game_data import GameData
from src.core.i18n import tr, trn, typo
from src.core.reglages_table import Reglage
from src.ui.flow_layout import FlowLayout
from src.ui.composants import bouton, ENCRE_DOUCE, LISTE, petit_titre, police, transparent
from src.ui.fonts import cinzel
from src.ui.reglages_rubriques import _COULEUR_NOTE, _COULEUR_SE_VOIT, _COULEURS_COUT, _NIVEAUX, _RESSOURCES
from src.ui.reglages_widgets import _CartePrereglage, _etiquette_beta, _Points, _texte_beta
from src.ui.theme import RAYON_CARTE, accent_qcolor, themed
from src.ui.theme import current as theme_courant
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import liste_deroulante, zone_defilable

log = logging.getLogger(__name__)

# Les deux repères : Accio en or (la marque, et la valeur conseillée), le jeu en argent, pour ne pas
# lui faire concurrence (maquette, « Designer »).
OR = "#d6a72c"
ARGENT = "#b9bccb"
# La fiche de droite, et la largeur sous laquelle elle laisse sa place à la liste (la description
# passe alors dans l'infobulle de la ligne).
_LARGEUR_FICHE = 300
_SEUIL_FICHE = 860
# La colonne des contrôles : un curseur y tient avec ses étiquettes, sa valeur et son ↺.
_LARGEUR_CONTROLE = 330
# L'identifiant de la ligne « Résolution », qui n'est pas un réglage du correctif mais du launcher.
RESOLUTION = "resolution_ecran"

_STYLE = f"""
QFrame#carteImage {{
    background: #0d0d1a; border: 1px solid rgba(214, 167, 44, 0.14); border-radius: {RAYON_CARTE}px;
}}
QFrame#ficheImage {{
    background: #0b0b18; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: {RAYON_CARTE}px;
}}
QPushButton#categorie {{
    color: #c8c6dc; background: transparent; border: none; border-bottom: 2px solid transparent;
    padding: 8px 4px; text-align: center;
}}
QPushButton#categorie:hover {{ color: #f4f2f8; }}
QPushButton#categorie:checked {{ color: #e8c547; border-bottom-color: #d6a72c; }}
QPushButton#categorie[focusClavier="true"]:focus {{ color: #e8c547; }}
QPushButton#segment {{
    color: #d8d6e6; background: #12121f; border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 6px; padding: 5px 10px;
}}
QPushButton#segment:hover {{ border-color: rgba(214, 167, 44, 0.55); }}
QPushButton#segment:checked {{
    color: #f4e2a8; border-color: #d6a72c; background: rgba(214, 167, 44, 0.16);
}}
QPushButton#segment:disabled {{ color: #5d5b72; border-color: rgba(255, 255, 255, 0.05); }}
QPushButton#segment[focusClavier="true"]:focus {{ border: 2px solid #d6a72c; }}
QPushButton#retourAccio {{
    color: #d6a72c; background: transparent; border: none; padding: 0px 2px;
}}
QPushButton#retourAccio:hover {{ color: #f4e2a8; }}
QLineEdit#recherche {{
    color: #ecebf3; background: #10101d; border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 6px; padding: 6px 10px;
}}
QLineEdit#recherche[focusClavier="true"]:focus {{ border-color: #d6a72c; }}
"""


# La ligne dont parle la fiche de droite (survolée ou au focus) se voit (Ludo, 2026-11-13).
_STYLE_LIGNE = """
QFrame#ligneImage { background: transparent; border-radius: 6px; }
QFrame#ligneImage[active="true"] { background: rgba(214, 167, 44, 0.12); }
"""


def _texte(reglage: Reglage, valeur: object) -> str:
    """Une valeur pour la personne : le nom du cran, sinon le nombre à la virgule de sa langue."""
    if valeur is None:
        return tr("inconnue")
    if not reglage.choix:
        return tr("Allumé") if valeur else tr("Éteint")
    if reglage.ident == "ciel_heure" and isinstance(valeur, (int, float)):
        heures, minutes = int(valeur), round((float(valeur) - int(valeur)) * 60)
        return tr("{} h {:02d}").format(heures % 24, minutes)
    for c in reglage.choix:
        if rc.meme_valeur(c, valeur):
            return rc.libelle_choix(reglage, c)
    return rc.texte_valeur(valeur)


def _nom_palier(reglage: Reglage, valeur: object) -> str:
    """Le nom court d'un palier sous le curseur (« Moyenne », sans son chiffre : la valeur exacte est à côté)."""
    if rc.meme_valeur(valeur, reglage.choix[0]) and reglage.zero:
        return tr(reglage.zero)
    noms = dict(reglage.etiquettes)
    for v, nom in noms.items():
        if rc.meme_valeur(v, valeur):
            return tr(nom)
    return _texte(reglage, valeur)


def _chiffre(reglage: Reglage, valeur: object) -> str:
    """La valeur exacte d'un curseur, à droite de sa piste : « 0,35 », « 60 % », « 19 h 30 »."""
    if reglage.ident == "ciel_heure":
        return _texte(reglage, valeur)
    if reglage.ident == "force_halo" and isinstance(valeur, (int, float)):
        return f"{rc.texte_valeur(valeur)} %"
    return rc.texte_valeur(valeur)


class _Repere:
    """Les deux formes des repères, peintes partout pareil : un losange or, un rond argent."""

    @staticmethod
    def accio(p: QPainter, centre: QPointF, r: float = 4.0) -> None:
        chemin = QPainterPath()
        chemin.moveTo(centre.x(), centre.y() - r)
        chemin.lineTo(centre.x() + r, centre.y())
        chemin.lineTo(centre.x(), centre.y() + r)
        chemin.lineTo(centre.x() - r, centre.y())
        chemin.closeSubpath()
        p.fillPath(chemin, QColor(OR))

    @staticmethod
    def jeu(p: QPainter, centre: QPointF, r: float = 3.2) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ARGENT))
        p.drawEllipse(centre, r, r)


class _Segment(QPushButton):
    """Un choix parmi deux à cinq : le texte, et les repères Accio et jeu dans ses coins."""

    def __init__(self, texte: str, accio: bool, jeu: bool, teinte: str = "") -> None:
        super().__init__("" if teinte else texte)
        self.setObjectName("segment")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(police(12))
        self.setAccessibleName(texte)
        self.accio, self.jeu = accio, jeu
        if teinte:
            # La couleur EST le choix : une pastille, son nom au survol.
            self.setToolTip(texte)
            self.setFixedSize(30, 26)
            self.setStyleSheet(themed(
                f"QPushButton#segment {{ background: #{teinte}; border: 2px solid rgba(255,255,255,0.12);"
                " border-radius: 13px; padding: 0px; }"
                f"QPushButton#segment:checked {{ border: 2px solid {OR}; }}"))

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().paintEvent(event)
        if not (self.accio or self.jeu):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.accio:
            _Repere.accio(p, QPointF(self.width() - 7, 7), 3.2)
        if self.jeu:
            _Repere.jeu(p, QPointF(7, 7), 2.6)
        p.end()


class Boutons(QWidget):
    """Deux à cinq choix côte à côte (ou des pastilles de couleur) ; `choisi` à chaque clic."""

    choisi = pyqtSignal(object)

    def __init__(self, reglage: Reglage, accio: object, jeu: object) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self._valeurs = list(reglage.choix)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6 if reglage.ident == "ciel_couleur" else 4)
        lay.addStretch()
        for rang, v in enumerate(self._valeurs):
            teinte = str(v) if reglage.ident == "ciel_couleur" else ""
            b = _Segment(_texte(reglage, v), rc.meme_valeur(v, accio), rc.meme_valeur(v, jeu), teinte)
            self._groupe.addButton(b, rang)
            lay.addWidget(b)
        self._groupe.idClicked.connect(lambda rang: self.choisi.emit(self._valeurs[rang]))

    def boutons(self) -> list[QPushButton]:
        return [b for b in self._groupe.buttons() if isinstance(b, QPushButton)]

    def valeur(self) -> object:
        rang = self._groupe.checkedId()
        return self._valeurs[rang] if rang >= 0 else None

    def poser(self, valeur: object) -> None:
        """Coche le choix qui porte `valeur` ; une valeur posée à la main n'en coche aucun."""
        rang = next((i for i, v in enumerate(self._valeurs) if rc.meme_valeur(v, valeur)), -1)
        self._groupe.setExclusive(False)
        for b in self._groupe.buttons():
            b.setChecked(self._groupe.id(b) == rang)
        self._groupe.setExclusive(True)


class CurseurGradue(QWidget):
    """Un curseur peint pour des nombres : paliers nommés, repères Accio et jeu, aimant à 2 %.

    QSlider ne connaît que des entiers et ne dessine pas d'étiquettes (maquette, « Développeur »).
    `glisse` pendant le geste (la ligne seule se met à jour), `choisi` au relâchement et au clavier :
    l'ini n'est écrit qu'une fois par geste. La molette ne le règle que s'il a le focus : dans une
    page qui défile, il ne la vole pas.
    """

    glisse = pyqtSignal(float)
    choisi = pyqtSignal(float)

    _HAUT_PISTE = 13
    _RAYON = 7

    def __init__(self, reglage: Reglage, accio: object, jeu: object) -> None:
        super().__init__()
        bornes = rc.curseur(reglage)
        if bornes is None:
            raise ValueError(f"{reglage.ident} n'a pas de curseur")
        self.reglage = reglage
        self.bas, self.haut, self.pas = bornes
        self.accio = float(accio) if isinstance(accio, (int, float)) and not isinstance(accio, bool) else None
        self.jeu = float(jeu) if isinstance(jeu, (int, float)) and not isinstance(jeu, bool) else None
        self.paliers = sorted((float(v), _nom_palier(reglage, v)) for v in reglage.choix
                              if isinstance(v, (int, float)) and not isinstance(v, bool))
        # D'où part le remplissage : la valeur du jeu, sinon le premier cran (« l'éteint »).
        premier = reglage.choix[0]
        depart = self.jeu if self.jeu is not None else (
            float(premier) if isinstance(premier, (int, float)) else self.bas)
        self.origine = min(self.haut, max(self.bas, depart))
        self._valeur = self.origine
        self._geste = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(180)
        self.setFixedHeight(46)
        self.setFont(police(11))
        self.setAccessibleName(tr(reglage.libelle))

    # ── valeur ──

    def valeur(self) -> float:
        return self._valeur

    def poser(self, valeur: object) -> None:
        if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
            self._valeur = float(valeur)
            self.update()

    def _borner(self, x: float) -> float:
        return float(rc.arrondir(self.reglage, x))

    def _x(self, v: float) -> float:
        marge = self._RAYON + 1
        return marge + (v - self.bas) / (self.haut - self.bas) * (self.width() - 2 * marge)

    def _depuis_x(self, x: float) -> float:
        marge = self._RAYON + 1
        part = (x - marge) / max(1.0, self.width() - 2 * marge)
        v = self.bas + part * (self.haut - self.bas)
        aimants = [p for p, _n in self.paliers] + [a for a in (self.accio, self.jeu) if a is not None]
        proche = min(aimants, key=lambda a: abs(a - v), default=None)
        if proche is not None and abs(proche - v) < (self.haut - self.bas) * 0.02:
            return proche
        return self._borner(v)

    # ── souris, clavier, molette ──

    def mousePressEvent(self, e: QMouseEvent | None) -> None:  # noqa: N802 (Qt)
        if e is None or e.button() != Qt.MouseButton.LeftButton or not self.isEnabled():
            return
        self._geste = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._suivre(e.position().x())

    def mouseMoveEvent(self, e: QMouseEvent | None) -> None:  # noqa: N802 (Qt)
        if e is not None and self._geste:
            self._suivre(e.position().x())

    def mouseReleaseEvent(self, e: QMouseEvent | None) -> None:  # noqa: N802 (Qt)
        if self._geste:
            self._geste = False
            self.choisi.emit(self._valeur)

    def _suivre(self, x: float) -> None:
        v = self._depuis_x(x)
        if v != self._valeur:
            self._valeur = v
            self.update()
            self.glisse.emit(v)

    def keyPressEvent(self, e: QKeyEvent | None) -> None:  # noqa: N802 (Qt)
        if e is None:
            return
        v = self._valeur
        crans = sorted({p for p, _n in self.paliers} | ({self.accio} if self.accio is not None else set()))
        suite = {
            Qt.Key.Key_Right: v + self.pas, Qt.Key.Key_Up: v + self.pas,
            Qt.Key.Key_Left: v - self.pas, Qt.Key.Key_Down: v - self.pas,
            Qt.Key.Key_Home: self.bas, Qt.Key.Key_End: self.haut,
            Qt.Key.Key_PageUp: next((c for c in crans if c > v + 1e-9), self.haut),
            Qt.Key.Key_PageDown: next((c for c in reversed(crans) if c < v - 1e-9), self.bas),
        }.get(Qt.Key(e.key()))
        if suite is None:
            super().keyPressEvent(e)
            return
        nouvelle = self._borner(suite)
        if nouvelle != self._valeur:
            self._valeur = nouvelle
            self.update()
            self.choisi.emit(nouvelle)

    def wheelEvent(self, e: QWheelEvent | None) -> None:  # noqa: N802 (Qt)
        if e is None:
            return
        if not self.hasFocus():
            e.ignore()           # la page défile
            return
        sens = 1 if e.angleDelta().y() > 0 else -1
        nouvelle = self._borner(self._valeur + sens * self.pas)
        if nouvelle != self._valeur:
            self._valeur = nouvelle
            self.update()
            self.choisi.emit(nouvelle)

    # ── dessin ──

    def _etiquettes(self, fm: QFontMetrics) -> list[tuple[float, str]]:
        """Les paliers dont le nom tient sans chevaucher : les deux bouts et Accio d'abord."""
        def priorite(item: tuple[float, str]) -> int:
            v = item[0]
            if v in (self.paliers[0][0], self.paliers[-1][0]):
                return 0
            return 1 if self.accio is not None and rc.meme_valeur(v, self.accio) else 2
        gardees: list[tuple[float, float, float, str]] = []   # (valeur, gauche, droite, nom)
        for v, nom in sorted(self.paliers, key=priorite):
            largeur = fm.horizontalAdvance(nom)
            centre = self._x(v)
            gauche = min(max(0.0, centre - largeur / 2), self.width() - largeur)
            if all(gauche > d + 6 or gauche + largeur < g - 6 for _v, g, d, _n in gardees):
                gardees.append((v, gauche, gauche + largeur, nom))
        return [(g, nom) for _v, g, _d, nom in sorted(gardees)]

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        actif = self.isEnabled()
        y = float(self._HAUT_PISTE)
        g, d = self._x(self.bas), self._x(self.haut)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(QRectF(g, y - 2, d - g, 4), 2, 2)
        # Le remplissage, depuis la valeur du jeu.
        x0, x1 = sorted((self._x(self.origine), self._x(self._valeur)))
        p.setBrush(accent_qcolor() if actif else QColor(120, 118, 140))
        p.drawRoundedRect(QRectF(x0, y - 2, max(0.0, x1 - x0), 4), 2, 2)
        # Graduations : dix petites, et une plus haute par palier nommé.
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        for k in range(11):
            x = g + k * (d - g) / 10
            p.drawLine(QPointF(x, y + 5), QPointF(x, y + 7))
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for v, _n in self.paliers:
            x = self._x(v)
            p.drawLine(QPointF(x, y + 5), QPointF(x, y + 9))
        if self.accio is not None:
            _Repere.accio(p, QPointF(self._x(self.accio), y - 8), 3.6)
        if self.jeu is not None:
            _Repere.jeu(p, QPointF(self._x(self.jeu), y + 12), 2.6)
        # La poignée.
        x = self._x(self._valeur)
        p.setPen(QPen(accent_qcolor() if self.hasFocus() else QColor(0, 0, 0, 120), 2 if self.hasFocus() else 1))
        p.setBrush(QColor(theme_courant().accent_light) if actif else QColor(140, 138, 160))
        p.drawEllipse(QPointF(x, y), self._RAYON, self._RAYON)
        # Les noms des paliers.
        fm = QFontMetrics(self.font())
        p.setFont(self.font())
        for gauche, nom in self._etiquettes(fm):
            atteint = any(rc.meme_valeur(v, self._valeur) and n == nom for v, n in self.paliers)
            p.setPen(QColor(theme_courant().accent_light) if atteint else QColor(ENCRE_DOUCE))
            p.drawText(QPointF(gauche, self.height() - 4), nom)
        p.end()


class _Fiche(QFrame):
    """La fiche du réglage survolé : ce qu'il fait, ses trois valeurs, ce qu'il coûte."""

    accio = pyqtSignal()
    jeu = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ficheImage")
        self.setFixedWidth(_LARGEUR_FICHE)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().Policy.Maximum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        self.titre = QLabel("")
        self.titre.setWordWrap(True)
        self.titre.setTextFormat(Qt.TextFormat.PlainText)
        self.titre.setFont(cinzel(12, bold=True))
        self.titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        lay.addWidget(self.titre)
        self.texte = QLabel("")
        self.texte.setWordWrap(True)
        self.texte.setTextFormat(Qt.TextFormat.RichText)
        self.texte.setFont(police(13))
        self.texte.setStyleSheet("color: #d8d6e6; background: transparent;")
        lay.addWidget(self.texte)
        self.valeurs = QLabel("")
        self.valeurs.setWordWrap(True)      # « Plein écran sans bordure » était coupé (2026-11-13)
        self.valeurs.setTextFormat(Qt.TextFormat.RichText)
        self.valeurs.setFont(police(13))
        self.valeurs.setStyleSheet("background: transparent;")
        lay.addWidget(self.valeurs)
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setTextFormat(Qt.TextFormat.RichText)
        self.notes.setFont(police(12))
        self.notes.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        lay.addWidget(self.notes)
        boutons = QHBoxLayout()
        boutons.setSpacing(8)
        self.bouton_accio = bouton(tr("Valeur Accio"))
        self.bouton_jeu = bouton(tr("Jeu d'origine"))
        for b, signal in ((self.bouton_accio, self.accio), (self.bouton_jeu, self.jeu)):
            b.setAutoDefault(False)
            b.clicked.connect(signal)
            boutons.addWidget(b)
        boutons.addStretch()
        lay.addLayout(boutons)
        lay.addStretch()


def _html_fiche(reglage: Reglage, aide: str, declares: set[str]) -> str:
    """La description, puis ce que la ligne ne dit pas : se voit, bêta, dépendances."""
    e = html.escape
    paragraphes = [e(aide)]
    if reglage.se_voit:
        paragraphes.append(f'<span style="color:{_COULEUR_SE_VOIT}">{e(tr("Se voit nettement à l’écran."))}</span>')
    if reglage.beta:
        paragraphes.append(e(_texte_beta()))

    def deja_dit(autre: Reglage) -> bool:
        return rc.textes(autre)[0].lower() in aide.lower()

    parent = rc.REGLAGES.get(reglage.depend_de)
    if parent is not None and parent.ident in declares and not deja_dit(parent):
        paragraphes.append(e(tr("Sans effet tant que « {} » est éteint.").format(rc.textes(parent)[0])))
    exclu = rc.REGLAGES.get(reglage.exclut)
    if exclu is not None and exclu.ident in declares and not deja_dit(exclu):
        paragraphes.append(e(tr("L'allumer éteint « {} », qui ne peut pas agir en même temps.").format(
            rc.textes(exclu)[0])))
    return "".join(f"<p>{p}</p>" for p in paragraphes)


def _html_cout(reglage: Reglage) -> str:
    e = html.escape
    if not reglage.cout:
        return e(tr("Sans coût notable."))
    return "<br>".join(f'{e(tr(_RESSOURCES.get(r, r)))} : <span style="color:{_COULEURS_COUT[n]}">'
                       f"{e(tr(_NIVEAUX[n]))} {'●' * n}</span>" for r, n in reglage.cout)


class _LigneImage(QFrame):
    """Une ligne : le nom (et « Bêta »), les points du coût, le contrôle dans sa colonne.

    `note` dit sous le nom ce qui la prive d'effet ; `survolee` part au survol et au focus de son
    contrôle : la fiche de droite suit.
    """

    survolee = pyqtSignal(str)

    def __init__(self, ident: str, nom: str, reglage: Reglage | None, controle: QWidget,
                 retrait: bool, fin: QWidget | None = None) -> None:
        super().__init__()
        self.setObjectName("ligneImage")
        # Sur la ligne elle-même : le « background: transparent » sans sélecteur des conteneurs
        # (plus proches que la page) écrasait la surbrillance posée par la feuille de la page.
        self.setStyleSheet(themed(_STYLE_LIGNE))
        self.ident = ident
        self.controle = controle
        # La fiche de droite est-elle là ? Alors l'infobulle répéterait sa description (Ludo,
        # 2026-11-13 : « inutile ») ; sous 860 px, sans fiche, elle reste le seul endroit du texte.
        self.fiche_ouverte: Callable[[], bool] = lambda: False
        v = QVBoxLayout(self)
        v.setContentsMargins(14 + (22 if retrait else 0), 6, 12, 6)
        v.setSpacing(2)
        self.haut = QWidget()
        self.haut.setStyleSheet("background: transparent;")
        h = QHBoxLayout(self.haut)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.libelle = QLabel(nom)
        self.libelle.setTextFormat(Qt.TextFormat.PlainText)
        self.libelle.setWordWrap(True)
        self.libelle.setMinimumWidth(1)
        self.libelle.setFont(police(14))
        self.libelle.setStyleSheet("color: #ecebf3; background: transparent;")
        h.addWidget(self.libelle, stretch=1)
        if reglage is not None and reglage.beta:
            h.addWidget(_etiquette_beta(), alignment=Qt.AlignmentFlag.AlignVCenter)
        niveau = max((n for _r, n in reglage.cout), default=0) if reglage is not None else 0
        self.points = _Points(niveau)
        if niveau and reglage is not None:
            detail = "\n".join(f"{tr(_RESSOURCES.get(r, r))} : {tr(_NIVEAUX[n])}" for r, n in reglage.cout)
            self.points.setToolTip(detail)
            self.points.setAccessibleName(detail)
        h.addWidget(self.points)
        case = QWidget()
        case.setObjectName("caseControle")
        case.setStyleSheet("background: transparent;")
        case.setFixedWidth(_LARGEUR_CONTROLE)
        hc = QHBoxLayout(case)
        hc.setContentsMargins(0, 0, 0, 0)
        hc.setSpacing(6)
        if not isinstance(controle, CurseurGradue):
            hc.addStretch()
        hc.addWidget(controle, stretch=1 if isinstance(controle, CurseurGradue) else 0)
        if fin is not None:
            hc.addWidget(fin)
        h.addWidget(case)
        v.addWidget(self.haut)
        self.note = QLabel("")
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setWordWrap(True)
        f = police(12)
        f.setItalic(True)
        self.note.setFont(f)
        self.note.setStyleSheet(f"color: {_COULEUR_NOTE}; background: transparent;")
        self.note.hide()
        v.addWidget(self.note)
        controle.setAccessibleName(nom)
        for w in [controle, *controle.findChildren(QWidget), self.points]:
            w.installEventFilter(self)

    def event(self, e: QEvent | None) -> bool:
        if e is not None and e.type() == QEvent.Type.ToolTip and self.fiche_ouverte():
            return True
        return super().event(e)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.survolee.emit(self.ident)
        super().enterEvent(event)

    def eventFilter(self, objet: QObject | None, event: QEvent | None) -> bool:  # noqa: N802 (Qt)
        if event is not None and event.type() == QEvent.Type.FocusIn:
            self.survolee.emit(self.ident)
        if objet is self.points and event is not None and event.type() == QEvent.Type.ToolTip:
            return self.fiche_ouverte()      # le coût est déjà en clair dans la fiche
        return False

    def marquer(self, active: bool) -> None:
        if self.property("active") != active:
            self.setProperty("active", active)
            self.style().unpolish(self)
            self.style().polish(self)


class _Onglet(QPushButton):
    """Une catégorie en haut de la page (sans pastille de compte : Ludo, 2026-11-13, « inutile et moche »)."""

    def __init__(self, nom: str) -> None:
        super().__init__(nom)
        self.setObjectName("categorie")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(police(14))
        # Jamais rogné : « airage et omb » à 980 px (HP6) ; la rangée passe à la ligne.
        self.setMinimumWidth(self.sizeHint().width())
        self.nom = nom


class PageImage(QWidget):
    """L'onglet Image d'un jeu à correctif. Voir le module.

    `montrer_erreur()` et `apres_ecriture()` sont ceux de la fenêtre : le message d'échec et le
    pied (« Rétablir » s'allume à la première retouche) vivent chez elle.
    """

    def __init__(self, game: GameData, config: Config, ini: Path, reglages: tuple[Reglage, ...],
                 montrer_erreur: Callable[[], None], apres_ecriture: Callable[[], None],
                 enregistrer_config: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.setStyleSheet(themed(_STYLE) + "PageImage { background: transparent; }")
        self.game, self.config, self.ini = game, config, ini
        self._montrer_erreur, self._apres_ecriture = montrer_erreur, apres_ecriture
        self._enregistrer_config = enregistrer_config
        self.reglages = {r.ident: r for r in reglages}
        self._declares = set(self.reglages)
        self._valeurs: dict[str, object] = {}
        self._accio: dict[str, object] = {}
        self._jeu: dict[str, object] = {}
        for r in reglages:
            self._relire(r)
            self._accio[r.ident] = rc.valeur_accio(ini, r)
            self._jeu[r.ident] = rc.valeur_du_jeu(r)
        # La résolution des jeux du correctif : réglée par le launcher, écrite au lancement.
        self._resolution = game.resolution is not None and resolution_jeu.du_correctif(game.resolution)
        self.categories = reglages_image.ranger(reglages)
        if self._resolution and not any(c.ident == "ecran" for c in self.categories):
            self.categories = (reglages_image.Categorie("ecran", tr("Écran"), (
                reglages_image.Groupe("Affichage", ()),)), *self.categories)
        self._prereglages = rc.prereglages_du_jeu(
            [r for r in reglages if reglages_image.place(r)[0] != "couleurs"])
        # Les lignes de chaque réglage (une dans sa catégorie, une autre dans la recherche).
        self._lignes: dict[str, list[_LigneImage]] = {}
        self._cartes_prereglage: dict[str, _CartePrereglage] = {}
        self._actif = ""
        self._construites: set[int] = set()
        self._construire()

    # ── lecture ──

    def _relire(self, r: Reglage) -> None:
        try:
            self._valeurs[r.ident] = rc.lire(self.ini, r).valeur
        except OSError:
            log.warning("Correctif : %s illisible", self.ini, exc_info=True)

    def valeur(self, ident: str) -> object:
        return self._valeurs.get(ident)

    def ligne(self, ident: str) -> _LigneImage:
        """La ligne d'un réglage dans sa catégorie, bâtie au besoin (la catégorie s'ouvre)."""
        if ident not in self._lignes or not self._lignes[ident]:
            rang = next(i for i, c in enumerate(self.categories)
                        if ident in {r.ident for r in c.reglages}
                        or (ident == RESOLUTION and c.ident == "ecran"))
            self.montrer(rang)
        return self._lignes[ident][0]

    def categorie_de(self, ident: str) -> str:
        return next(c.ident for c in self.categories if ident in {r.ident for r in c.reglages})

    def rafraichir(self) -> None:
        """Après une remise à l'origine : tout reprend ce que porte le fichier."""
        for r in self.reglages.values():
            self._relire(r)
        self._maj()

    # ── construction ──

    def _construire(self) -> None:
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(14)
        haut = QHBoxLayout()
        haut.setSpacing(18)
        # Les onglets passent à la ligne quand la place manque, la recherche garde la sienne :
        # à 980×660, les onglets de HP6 étaient coupés des deux côtés et la recherche
        # sortait de la page (audit UI, 2026-11-13).
        rangee = QWidget()
        transparent(rangee, "ongletsImage")
        flux = FlowLayout(rangee, spacing=18)
        self._groupe_onglets = QButtonGroup(self)
        self._groupe_onglets.setExclusive(True)
        self.onglets: dict[str, _Onglet] = {}
        for rang, cat in enumerate(self.categories):
            o = _Onglet(tr(cat.nom))
            o.clicked.connect(lambda _c=False, r=rang: self.montrer(r))
            self._groupe_onglets.addButton(o, rang)
            self.onglets[cat.ident] = o
            flux.addWidget(o)
        haut.addWidget(rangee, stretch=1)
        self.recherche = QLineEdit()
        self.recherche.setObjectName("recherche")
        self.recherche.setPlaceholderText(tr("Rechercher un réglage"))
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setFont(police(13))
        self.recherche.setFixedWidth(220)
        self.recherche.textChanged.connect(self._chercher)
        haut.addWidget(self.recherche, alignment=Qt.AlignmentFlag.AlignTop)
        racine.addLayout(haut)

        corps = QHBoxLayout()
        corps.setSpacing(20)
        self.pile = QStackedWidget()
        self.pile.setStyleSheet("background: transparent;")
        for _cat in self.categories:
            self.pile.addWidget(QWidget())     # bâtie à son premier affichage
        self._resultats = QWidget()
        self._resultats.setStyleSheet("background: transparent;")
        self._lay_resultats = QVBoxLayout(self._resultats)
        self._lay_resultats.setContentsMargins(0, 0, 0, 0)
        self._lay_resultats.setSpacing(12)
        self.pile.addWidget(zone_defilable(self._resultats))
        corps.addWidget(self.pile, stretch=1)
        self.fiche = _Fiche()
        self.fiche.accio.connect(lambda: self._vers(self._accio))
        self.fiche.jeu.connect(lambda: self._vers(self._jeu))
        # Dans sa propre zone : sur un petit écran, la fenêtre rapetisse et la fiche défile.
        self._zone_fiche = zone_defilable(self.fiche)
        self._zone_fiche.setFixedWidth(_LARGEUR_FICHE + 12)
        corps.addWidget(self._zone_fiche)
        racine.addLayout(corps, stretch=1)
        if self.categories:
            self.montrer(0)

    def montrer(self, rang: int) -> None:
        """Ouvre la catégorie `rang` ; elle se bâtit la première fois (70 lignes d'un coup ralentissaient
        l'ouverture de la fenêtre)."""
        if self.recherche.text():
            self.recherche.blockSignals(True)
            self.recherche.clear()
            self.recherche.blockSignals(False)
        if rang not in self._construites:
            ancienne = self.pile.widget(rang)
            page = zone_defilable(self._page(self.categories[rang]))
            self.pile.insertWidget(rang, page)
            if ancienne is not None:
                self.pile.removeWidget(ancienne)
                ancienne.deleteLater()
            self._construites.add(rang)
        self.pile.setCurrentIndex(rang)
        bouton_ = self._groupe_onglets.button(rang)
        if bouton_ is not None:
            bouton_.setChecked(True)
        premier = next(iter(self.categories[rang].reglages), None)
        if self._resolution and self.categories[rang].ident == "ecran":
            self._activer(RESOLUTION)
        elif premier is not None:
            self._activer(premier.ident)
        self._maj()

    def _page(self, cat: reglages_image.Categorie) -> QWidget:
        contenu = QWidget()
        contenu.setStyleSheet("background: transparent;")
        v = QVBoxLayout(contenu)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(0)
        if cat.ident == "qualite" and self._prereglages:
            v.addWidget(petit_titre(tr("Préréglages")))
            v.addSpacing(8)
            v.addWidget(self._bloc_prereglages())
            v.addSpacing(18)
        for groupe in cat.groupes:
            carte = QFrame()
            carte.setObjectName("carteImage")
            lay = QVBoxLayout(carte)
            lay.setContentsMargins(0, 6, 0, 6)
            lay.setSpacing(0)
            if cat.ident == "ecran" and groupe.nom == "Affichage" and self._resolution:
                lay.addWidget(self._ligne_resolution())
            presents = {r.ident for r in groupe.reglages}
            for r in groupe.reglages:
                lay.addWidget(self._ligne(r, retrait=r.depend_de in presents))
            if not lay.count():
                carte.deleteLater()
                continue
            v.addWidget(petit_titre(tr(groupe.nom)))
            v.addSpacing(6)
            v.addWidget(carte)
            v.addSpacing(16)
        v.addWidget(self._pied(cat))
        v.addStretch()
        return contenu

    def _bloc_prereglages(self) -> QWidget:
        bloc = QWidget()
        bloc.setStyleSheet("background: transparent;")
        grille = QGridLayout(bloc)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setSpacing(10)
        groupe = QButtonGroup(bloc)
        groupe.setExclusive(True)
        entrees = [(ident, nom, texte, rang + 1) for rang, (ident, nom, texte, _v) in enumerate(self._prereglages)]
        entrees.append(("", "Sur mesure", "Se choisit tout seul dès qu'un réglage change.", 0))
        for rang, (ident, nom, texte, niveau) in enumerate(entrees):
            repere = _Points(min(niveau, 3), largeur_segment=16) if niveau else None
            carte = _CartePrereglage(tr(nom), tr(texte), repere)
            if not ident:
                carte.setProperty("surMesure", True)
            carte.clicked.connect(lambda _c=False, i=ident: self.choisir_prereglage(i))
            groupe.addButton(carte)
            grille.addWidget(carte, rang // 2, rang % 2)
            self._cartes_prereglage[ident] = carte
        return bloc

    def _pied(self, cat: reglages_image.Categorie) -> QWidget:
        """« Remettre « Qualité » : valeurs Accio · jeu d'origine », pour la catégorie seule."""
        pied = QWidget()
        pied.setStyleSheet("background: transparent;")
        h = QHBoxLayout(pied)
        h.setContentsMargins(0, 4, 0, 8)
        h.setSpacing(8)
        lbl = QLabel(tr("Remettre « {} » :").format(tr(cat.nom)))
        lbl.setFont(police(13))
        lbl.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        h.addWidget(lbl)
        idents = [r.ident for r in cat.reglages]
        for texte, cible in ((tr("Valeurs Accio"), self._accio), (tr("Jeu d'origine"), self._jeu)):
            b = bouton(texte)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, c=cible, i=idents: self._remettre(i, c))
            h.addWidget(b)
        h.addStretch()
        return pied

    def _controle(self, r: Reglage) -> tuple[QWidget, QWidget | None]:
        """Le contrôle d'un réglage, et ce qui le suit dans sa colonne (valeur et ↺ d'un curseur)."""
        sorte = reglages_image.controle(r)
        accio, jeu, v = self._accio.get(r.ident), self._jeu.get(r.ident), self._valeurs.get(r.ident)
        if sorte == "inter":
            bascule = ToggleSwitch(bool(v))
            bascule.toggled.connect(lambda oui, i=r.ident: self.regler(i, oui))
            return bascule, None
        if sorte in ("boutons", "teinte"):
            boutons = Boutons(r, accio, jeu)
            boutons.poser(v)
            boutons.choisi.connect(lambda x, i=r.ident: self.regler(i, x))
            return boutons, None
        if sorte == "curseur":
            c = CurseurGradue(r, accio, jeu)
            c.poser(v)
            valeur = QLabel(_chiffre(r, v))
            valeur.setObjectName("valeurCurseur")
            valeur.setFont(police(12))
            valeur.setFixedWidth(58)
            valeur.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            valeur.setStyleSheet(themed("color: #f4e2a8; background: transparent;"))
            retour = QPushButton("↺")
            retour.setObjectName("retourAccio")
            retour.setFont(police(15))
            retour.setCursor(Qt.CursorShape.PointingHandCursor)
            retour.setFixedWidth(22)
            retour.setAutoDefault(False)
            retour.setToolTip(tr("Revenir à la valeur Accio ({})").format(_texte(r, accio)))
            retour.clicked.connect(lambda _c=False, i=r.ident: self.regler(i, self._accio.get(i)))
            c.glisse.connect(lambda x, lbl=valeur, rr=r: (lbl.setText(_chiffre(rr, x)), self._maj_fiche(x)))
            c.choisi.connect(lambda x, i=r.ident, rr=r: self.regler(i, rc.arrondir(rr, x)))
            fin = QWidget()
            fin.setStyleSheet("background: transparent;")
            hf = QHBoxLayout(fin)
            hf.setContentsMargins(0, 0, 0, 0)
            hf.setSpacing(2)
            hf.addWidget(valeur)
            hf.addWidget(retour)
            return c, fin
        liste = liste_deroulante()
        liste.setFont(police(13))
        liste.setCursor(Qt.CursorShape.PointingHandCursor)
        liste.setStyleSheet(themed(LISTE))
        for n in r.choix:
            texte = rc.libelle_choix(r, n)
            if rc.meme_valeur(n, accio):
                texte += "  ◆"
            liste.addItem(texte, n)
        self._poser_liste(liste, r, v)
        liste.currentIndexChanged.connect(lambda _i, lst=liste, i=r.ident: self.regler(i, lst.currentData()))
        liste.setFixedWidth(_LARGEUR_CONTROLE - 10)
        return liste, None

    @staticmethod
    def _poser_liste(liste: QComboBox, r: Reglage, v: object) -> None:
        index = next((i for i in range(liste.count()) if rc.meme_valeur(liste.itemData(i), v)), -1)
        if index < 0:
            # Une valeur posée à la main dans l'ini : montrée telle quelle, pas remplacée.
            for i in reversed(range(liste.count())):
                if liste.itemData(i) not in r.choix:
                    liste.removeItem(i)
            index = rc.rang_a_la_main(r, v)
            liste.insertItem(index, tr("{} (réglé à la main)").format(rc.texte_valeur(v)), v)
        liste.blockSignals(True)
        liste.setCurrentIndex(index)
        liste.blockSignals(False)

    def _ligne(self, r: Reglage, retrait: bool = False) -> _LigneImage:
        controle, fin = self._controle(r)
        libelle, aide = rc.textes(r)
        ligne = _LigneImage(r.ident, libelle, r, controle, retrait, fin)
        ligne.setToolTip(aide)
        ligne.fiche_ouverte = self._fiche_ouverte
        ligne.survolee.connect(self._activer)
        self._lignes.setdefault(r.ident, []).append(ligne)
        return ligne

    def _ligne_resolution(self) -> _LigneImage:
        """La taille de l'image : parmi les modes de l'écran, l'écran entier par défaut."""
        liste = liste_deroulante()
        liste.setFont(police(13))
        liste.setCursor(Qt.CursorShape.PointingHandCursor)
        liste.setStyleSheet(themed(LISTE))
        place = resolution_jeu.place_pour(self.game, self.config)
        modes = resolution_jeu.modes_pour(self.game)
        liste.addItem((tr("Remplir l'écran ({} × {})").format(*place) if place else tr("Remplir l'écran")) + "  ◆", "")
        for taille in resolution_jeu.proposees(place, modes):
            liste.addItem("{} × {}".format(*taille), resolution_jeu.ecrire(taille))
        courant = self.config.resolution_jeu.get(self.game.id, "")
        if courant and liste.findData(courant) < 0:
            taille = resolution_jeu.lire(courant)
            if taille is not None:
                liste.addItem(tr("{} × {} (plus grande que cet écran)").format(*taille), courant)
        liste.setCurrentIndex(max(0, liste.findData(courant)))
        liste.currentIndexChanged.connect(lambda _i: self._on_resolution(liste.currentData()))
        liste.setFixedWidth(_LARGEUR_CONTROLE - 10)
        self.liste_resolution = liste
        ligne = _LigneImage(RESOLUTION, tr("Résolution"), None, liste, False)
        ligne.setToolTip(self._aide_resolution())
        ligne.fiche_ouverte = self._fiche_ouverte
        ligne.survolee.connect(self._activer)
        self._lignes.setdefault(RESOLUTION, []).append(ligne)
        return ligne

    @staticmethod
    def _aide_resolution() -> str:
        return tr("La taille de l'image du jeu. Par défaut, celle de votre écran : l'image la plus nette. "
                  "Une taille plus petite allège le travail de la carte graphique. Le suréchantillonnage "
                  "s'ajoute par-dessus : il calcule l'image plus grande que cette taille, puis la réduit. "
                  "Appliquée à chaque lancement, même si le menu du jeu l'a changée.")

    def _on_resolution(self, valeur: str) -> None:
        resolutions = self.config.resolution_jeu
        if valeur:
            resolutions[self.game.id] = valeur
        else:
            resolutions.pop(self.game.id, None)
        (self._enregistrer_config or self.config.save)()
        self._maj_fiche()

    # ── écriture ──

    def regler(self, ident: str, valeur: object) -> None:
        """Écrit AUSSITÔT ; un échec remet la ligne sur ce que porte le fichier, et le dit."""
        r = self.reglages[ident]
        if valeur is None:
            return
        if r.choix and valeur not in r.choix and not rc.sur_le_curseur(r, valeur):
            return   # l'entrée « réglé à la main » : c'est déjà ce que porte le fichier
        try:
            rc.ecrire(self.ini, r, valeur)
        except (OSError, ValueError):
            log.warning("Correctif : %s non écrit", ident, exc_info=True)
            self._relire(r)
            self._montrer_erreur()
            self._maj()
            return
        self._relire(r)
        self._apres_ecriture()
        self._exclure(r)
        self._maj()

    def _exclure(self, r: Reglage) -> None:
        """Allumer un réglage éteint celui qu'il exclut (MSAA ↔ ombres de contact), dans l'ini aussi."""
        autre = self.reglages.get(r.exclut)
        if autre is None or not rc.allume(r, self._valeurs.get(r.ident)) \
                or not rc.allume(autre, self._valeurs.get(autre.ident)):
            return
        try:
            rc.ecrire(self.ini, autre, rc.eteint(autre))
        except (OSError, ValueError):
            log.warning("Correctif : %s non éteint", autre.ident, exc_info=True)
            self._montrer_erreur()
        self._relire(autre)

    def _remettre(self, idents: list[str], cible: dict[str, object]) -> None:
        """Toute une catégorie à ses valeurs Accio ou à celles du jeu ; ce qui n'en a pas ne bouge pas."""
        rates = False
        for ident in idents:
            voulue = cible.get(ident)
            r = self.reglages[ident]
            if voulue is None or rc.meme_valeur(voulue, self._valeurs.get(ident)):
                continue
            try:
                rc.ecrire(self.ini, r, voulue)
            except (OSError, ValueError):
                log.warning("Correctif : %s non remis", ident, exc_info=True)
                rates = True
            self._relire(r)
        if rates:
            self._montrer_erreur()
        else:
            self._apres_ecriture()
        self._maj()

    def _vers(self, cible: dict[str, object]) -> None:
        """Le bouton de la fiche : le réglage affiché à sa valeur Accio, ou à celle du jeu."""
        if self._actif == RESOLUTION:
            if cible is self._accio:
                self.liste_resolution.setCurrentIndex(0)
            return
        voulue = cible.get(self._actif)
        if voulue is not None:
            self.regler(self._actif, voulue)

    def choisir_prereglage(self, ident: str) -> None:
        if not ident:
            self._maj_prereglage()   # « Sur mesure » n'écrit rien
            return
        voulues = next(v for i, _n, _t, v in self._prereglages if i == ident)
        rates = False
        for cle, valeur in voulues.items():
            try:
                rc.ecrire(self.ini, self.reglages[cle], valeur)
            except (OSError, ValueError):
                log.warning("Correctif : préréglage %s non écrit", ident, exc_info=True)
                rates = True
            self._relire(self.reglages[cle])
        if rates:
            self._montrer_erreur()
        else:
            self._apres_ecriture()
        self._maj()

    # ── mise à jour de l'écran ──

    def _maj(self) -> None:
        for ident, lignes in self._lignes.items():
            if ident == RESOLUTION:
                continue
            for ligne in lignes:
                self._poser(ligne, self.reglages[ident])
        self._maj_dependances()
        self._maj_prereglage()
        self._maj_fiche()

    def _poser(self, ligne: _LigneImage, r: Reglage) -> None:
        v = self._valeurs.get(r.ident)
        c = ligne.controle
        c.blockSignals(True)
        if isinstance(c, ToggleSwitch):
            c.setChecked(bool(v))
        elif isinstance(c, (Boutons, CurseurGradue)):
            c.poser(v)
        elif isinstance(c, QComboBox):
            self._poser_liste(c, r, v)
        c.blockSignals(False)
        valeur = ligne.findChild(QLabel, "valeurCurseur")
        if valeur is not None:
            valeur.setText(_chiffre(r, v))
        retour = ligne.findChild(QPushButton, "retourAccio")
        if retour is not None:
            retour.setVisible(not rc.meme_valeur(v, self._accio.get(r.ident)))

    def _maj_dependances(self) -> None:
        """Grise ce qu'un réglage éteint prive d'effet, et DIT lequel sous son nom (sans réécrire la valeur)."""
        for ident, lignes in self._lignes.items():
            r = self.reglages.get(ident)
            bloquant = rc.bloque_par(r, self._valeurs) if r is not None else None
            for ligne in lignes:
                ligne.setEnabled(bloquant is None)
                if bloquant is None:
                    ligne.haut.setGraphicsEffect(None)
                    ligne.note.hide()
                    continue
                if ligne.haut.graphicsEffect() is None:
                    effet = QGraphicsOpacityEffect(ligne.haut)
                    effet.setOpacity(0.42)
                    ligne.haut.setGraphicsEffect(effet)
                ligne.note.setText(tr("Sans effet tant que « {} » est éteint.").format(rc.textes(bloquant)[0]))
                ligne.note.show()

    def _maj_prereglage(self) -> None:
        if not self._cartes_prereglage:
            return
        courant = rc.prereglage_courant(self._prereglages, self._valeurs)
        carte = self._cartes_prereglage.get(courant)
        if carte is not None:
            carte.setChecked(True)

    def _fiche_ouverte(self) -> bool:
        return self._zone_fiche.isVisible()

    def _activer(self, ident: str) -> None:
        if ident != self._actif:
            self._actif = ident
            for i, lignes in self._lignes.items():
                for ligne in lignes:
                    ligne.marquer(i == ident)
        self._maj_fiche()

    def _maj_fiche(self, en_cours: object = None) -> None:
        """La fiche du réglage actif ; `en_cours` : la valeur d'un curseur pendant le geste."""
        f = self.fiche
        e = html.escape
        if self._actif == RESOLUTION:
            f.titre.setText(tr("Résolution"))
            f.texte.setText(typo(f"<p>{e(self._aide_resolution())}</p>"))
            place = resolution_jeu.place_pour(self.game, self.config)
            ecran = "{} × {}".format(*place) if place else tr("Remplir l'écran")
            taille = resolution_jeu.lire(self.liste_resolution.currentData() or "")
            f.valeurs.setText(self._html_valeurs("640 × 480", ecran,
                                                 "{} × {}".format(*taille) if taille else ecran))
            f.notes.setText("")
            f.bouton_accio.setEnabled(self.liste_resolution.currentIndex() != 0)
            f.bouton_jeu.setEnabled(False)
            return
        r = self.reglages.get(self._actif)
        if r is None:
            return
        libelle, aide = rc.textes(r)
        f.titre.setText(libelle)
        f.texte.setText(typo(_html_fiche(r, aide, self._declares)))
        v = self._valeurs.get(r.ident) if en_cours is None else en_cours
        jeu = self._jeu.get(r.ident)
        accio = self._accio.get(r.ident)
        f.valeurs.setText(self._html_valeurs(
            _texte(r, jeu) if jeu is not None else tr("sans équivalent"),
            _texte(r, accio) if accio is not None else tr("inconnue"), _texte(r, v)))
        f.notes.setText(typo(_html_cout(r)))
        f.bouton_accio.setEnabled(accio is not None and not rc.meme_valeur(v, accio))
        f.bouton_jeu.setEnabled(jeu is not None and not rc.meme_valeur(v, jeu))

    @staticmethod
    def _html_valeurs(jeu: str, accio: str, actuel: str) -> str:
        e = html.escape
        lignes = ((f'<span style="color:{ARGENT}">●</span>', tr("Jeu d'origine"), jeu),
                  (f'<span style="color:{OR}">◆</span>', tr("Accio par défaut"), accio),
                  ("", tr("Actuel"), actuel))
        corps = "".join(
            f'<tr><td style="color:{ENCRE_DOUCE}; padding-right:12px; white-space:nowrap">{m}&nbsp;{e(nom)}</td>'
            f'<td style="color:{theme_courant().accent_light if nom == tr("Actuel") else "#ecebf3"}">{e(val)}</td></tr>'
            for m, nom, val in lignes)
        return f"<table width='100%' cellspacing='0' cellpadding='2'>{corps}</table>"

    # ── recherche ──

    def _chercher(self, texte: str) -> None:
        while self._lay_resultats.count():
            item = self._lay_resultats.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                for ident, lignes in self._lignes.items():
                    self._lignes[ident] = [li for li in lignes if not w.isAncestorOf(li) and li is not w]
                w.deleteLater()
        if not texte.strip():
            self.pile.setCurrentIndex(max(0, self._groupe_onglets.checkedId()))
            self._maj()
            return
        trouves = [r for cat in self.categories for r in cat.reglages
                   if reglages_image.correspond(r, *rc.textes(r), texte)]
        if not trouves:
            vide = QLabel(tr("Aucun réglage ne parle de « {} ».").format(texte))
            vide.setFont(police(13))
            vide.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
            self._lay_resultats.addWidget(vide)
        else:
            carte = QFrame()
            carte.setObjectName("carteImage")
            lay = QVBoxLayout(carte)
            lay.setContentsMargins(0, 6, 0, 6)
            for r in trouves:
                lay.addWidget(self._ligne(r))
            self._lay_resultats.addWidget(petit_titre(trn(len(trouves), "{} réglage", "{} réglages").format(len(trouves))))
            self._lay_resultats.addWidget(carte)
            self._activer(trouves[0].ident)
        self._lay_resultats.addStretch()
        self.pile.setCurrentIndex(self.pile.count() - 1)
        self._maj()

    # ── place ──

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._zone_fiche.setVisible(self.width() >= _SEUIL_FICHE)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(900, 600)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(_LARGEUR_CONTROLE + 220, 160)


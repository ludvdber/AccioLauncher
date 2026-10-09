"""Les pièces de la fenêtre de réglages d'un jeu : rail, lignes, repères, cartes.

Sorties de `game_settings_dialog` le 2026-10-09, à la refonte d'après la
maquette « Réglages du jeu » : la fenêtre garde la logique (lire, écrire,
dépendances, préréglages), ce module ce qu'on en voit.
"""


from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.config import ASSETS_DIR
from src.core.i18n import tr
from src.ui.composants import ENCRE_DOUCE, petit_titre, police
from src.ui.fonts import cinzel
from src.ui.reglages_rubriques import _COULEUR_NOTE, _COULEURS_COUT

_JAQUETTE = QSize(58, 80)

_STYLE = """
QDialog { background: #070712; }
QFrame#rail {
    background: #08081a; border: none;
    border-right: 1px solid rgba(214, 167, 44, 0.12);
}
QPushButton#retour {
    background: transparent; border: none; color: #a9a7c4;
    text-align: left; padding: 4px 2px;
}
QPushButton#retour:hover { color: #f2f2f4; }
QPushButton#retour[focusClavier="true"]:focus { color: #e8c547; }
QPushButton#rubrique {
    color: #a9a7c4; background: transparent; border: none;
    border-left: 2px solid transparent; border-radius: 8px;
    text-align: left; padding: 0 14px; min-height: 44px; max-height: 44px;
}
QPushButton#rubrique:hover { color: #f2f2f4; background: rgba(255, 255, 255, 0.04); }
QPushButton#rubrique:checked {
    color: #f2e6c4; background: rgba(214, 167, 44, 0.10);
    border-left: 2px solid #d6a72c;
}
QPushButton#rubrique[focusClavier="true"]:focus { color: #e8c547; }
QFrame#pied {
    background: #08081a; border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}
QFrame#effets {
    background: #0d0d1a;
    border: 1px solid rgba(214, 167, 44, 0.14);
    border-radius: 10px;
}
QPushButton#prereglage, QPushButton#choix {
    background: #0d0d1a; border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 9px; text-align: left;
}
QPushButton#prereglage:hover, QPushButton#choix:hover { border-color: rgba(214, 167, 44, 0.55); }
QPushButton#prereglage:checked, QPushButton#choix:checked {
    border-color: #d6a72c;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(214, 167, 44, 0.13), stop:1 rgba(214, 167, 44, 0.04));
}
QPushButton#prereglage[surMesure="true"] { border-style: dashed; }
QPushButton#prereglage[focusClavier="true"]:focus,
QPushButton#choix[focusClavier="true"]:focus { border: 2px solid #d6a72c; }
QPushButton#choix:disabled { border-color: rgba(255, 255, 255, 0.05); }
"""


class _Jaquette(QWidget):
    """La jaquette du jeu, recadrée « par expansion » (les carrées aussi)."""

    def __init__(self, nom_fichier: str) -> None:
        super().__init__()
        self.setFixedSize(_JAQUETTE)
        chemin = ASSETS_DIR / "covers" / nom_fichier
        self._pm = QPixmap(str(chemin)) if nom_fichier and chemin.is_file() else QPixmap()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        if self._pm.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cible = QRectF(self.rect())
        echelle = max(cible.width() / self._pm.width(), cible.height() / self._pm.height())
        larg, haut = cible.width() / echelle, cible.height() / echelle
        source = QRectF((self._pm.width() - larg) / 2, (self._pm.height() - haut) / 2, larg, haut)
        p.drawPixmap(cible, self._pm, source)
        p.end()


class _Points(QWidget):
    """Trois points : ce qu'un réglage demande à la machine, au plus fort de ses choix.

    Allumés à la couleur de leur niveau (vert, orange, rouge) ET en nombre :
    la couleur double l'information, elle ne la porte pas seule.
    """

    def __init__(self, niveau: int, diametre: int = 6, largeur_segment: int = 0) -> None:
        super().__init__()
        self.niveau = niveau
        self.couleur = _COULEURS_COUT.get(niveau, "")
        self._d = diametre
        self._seg = largeur_segment
        if largeur_segment:
            self.setFixedSize(3 * largeur_segment + 6, 4)
        else:
            self.setFixedSize(3 * diametre + 6, 18)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        if not self.niveau:
            return   # rien à dire : la place reste, les colonnes restent alignées
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            p.setBrush(QColor(self.couleur) if i < self.niveau else QColor(255, 255, 255, 33))
            if self._seg:
                p.drawRoundedRect(QRectF(i * (self._seg + 3), 0, self._seg, 4), 2, 2)
            else:
                y = (self.height() - self._d) / 2
                p.drawEllipse(QRectF(i * (self._d + 3), y, self._d, self._d))
        p.end()


class _CarteEffets(QFrame):
    """La carte « Chaque effet » : des familles nommées, des lignes serrées, sans filet."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("effets")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 2, 0, 10)
        self._lay.setSpacing(0)

    def famille(self, nom: str) -> None:
        titre = petit_titre(nom)
        titre.setContentsMargins(16, 12, 16, 4)
        self._lay.addWidget(titre)

    def ajouter(self, widget: QWidget) -> QWidget:
        self._lay.addWidget(widget)
        return widget


class _Ligne(QWidget):
    """Une ligne de réglage : le nom et son « ? », ses repères, le contrôle à droite.

    `note` dit, sous le nom, pourquoi la ligne est sans effet : grisée seule,
    elle laissait chercher quel réglage l'avait éteinte.
    """

    def __init__(self, serree: bool, retrait: bool) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        v = QVBoxLayout(self)
        gauche = 16 + (20 if retrait else 0)
        v.setContentsMargins(gauche, 5 if serree else 9, 16, 5 if serree else 9)
        v.setSpacing(1)
        self.haut = QWidget()
        self.haut.setStyleSheet("background: transparent;")
        self.rangee = QHBoxLayout(self.haut)
        self.rangee.setContentsMargins(0, 0, 0, 0)
        self.rangee.setSpacing(8)
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


class _CarteCliquable(QPushButton):
    """Une carte qui se choisit : titre, repère facultatif, phrase.

    Un `QPushButton` qui porte un layout ne se mesure pas tout seul : sa
    hauteur suit ici la phrase passée à la ligne (règles 38 et 39).
    """

    def __init__(self, nom_objet: str, titre: str, phrase: str, repere: QWidget | None = None) -> None:
        super().__init__()
        self.setObjectName(nom_objet)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        self.setAccessibleName(titre)
        self.setAccessibleDescription(phrase)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(7)
        self.titre = QLabel(titre.upper())
        self.titre.setTextFormat(Qt.TextFormat.PlainText)
        self.titre.setWordWrap(True)
        self.titre.setFont(cinzel(9, bold=True))
        self.titre.setStyleSheet("color: #ecebf3; background: transparent;")
        lay.addWidget(self.titre)
        if repere is not None:
            lay.addWidget(repere)
        self.phrase = QLabel(phrase)
        self.phrase.setTextFormat(Qt.TextFormat.PlainText)
        self.phrase.setWordWrap(True)
        self.phrase.setFont(police(12))
        self.phrase.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent;")
        lay.addWidget(self.phrase)
        lay.addStretch()
        for enfant in self.findChildren(QWidget):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        politique = self.sizePolicy()
        politique.setHeightForWidth(True)
        politique.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(politique)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt)
        return True

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802 (Qt)
        return self.layout().totalHeightForWidth(largeur)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        largeur = max(self.width(), 170)
        return QSize(170, self.heightForWidth(largeur))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(150, self.heightForWidth(max(self.width(), 150)))


class _Disposition(QWidget):
    """« Clavier d'origine » ou « ZQSD et souris » : deux cartes, un seul choix.

    Se manie comme l'interrupteur qu'elle remplace (`isChecked`, `setChecked`,
    `toggled`, `_basculer`) : la fenêtre la range avec les autres contrôles.
    """

    toggled = pyqtSignal(bool)

    def __init__(self, coche: bool, titre_zqsd: str, phrase_zqsd: str) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self._origine = _CarteCliquable("choix", tr("Clavier d'origine"), tr(
            "Les flèches pour se déplacer, une touche par sort : les touches que le jeu connaît."))
        self._zqsd = _CarteCliquable("choix", titre_zqsd, phrase_zqsd)
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        groupe.addButton(self._origine)
        groupe.addButton(self._zqsd)
        (self._zqsd if coche else self._origine).setChecked(True)
        self._zqsd.toggled.connect(self.toggled)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.addWidget(self._origine, 1)
        lay.addWidget(self._zqsd, 1)

    def isChecked(self) -> bool:  # noqa: N802 (Qt)
        return self._zqsd.isChecked()

    def setChecked(self, oui: bool) -> None:  # noqa: N802 (Qt)
        if oui != self.isChecked():
            (self._zqsd if oui else self._origine).setChecked(True)

    def _basculer(self) -> None:
        (self._origine if self.isChecked() else self._zqsd).click()


class _CartePrereglage(_CarteCliquable):
    def __init__(self, titre: str, phrase: str, repere: QWidget | None) -> None:
        super().__init__("prereglage", titre, phrase, repere)

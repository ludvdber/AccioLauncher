"""Composants communs des pages : surtitre, carte, ligne de réglage, boutons.

Refonte du 2026-10-09. Chaque page avait été dessinée seule, avec ses propres
tailles, marges et boutons : ouvrir les Paramètres après la fiche, c'était
changer d'application. Paramètres et À propos sont les premiers à s'en servir ;
les fenêtres d'erreur et l'assistant de premier lancement suivront.

Les couleurs sont écrites dans la palette Poudlard et passent par `themed()` :
une maison les remplace toutes d'un coup.
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from src.ui.fonts import body_font, cinzel
from src.ui.theme import themed

# Encres des pages, du plus lu au plus discret.
ENCRE = "#f2f2f4"
ENCRE_DOUCE = "#8f8db0"
ENCRE_DISCRETE = "#6f6d8e"

_STYLE = """
QFrame#carte {
    background: #0d0d1a;
    border: 1px solid rgba(214, 167, 44, 0.14);
    border-radius: 10px;
}
QFrame#separateur { background: rgba(255, 255, 255, 0.06); border: none; }
QPushButton#principal, QPushButton#secondaire {
    min-height: 34px; max-height: 34px; padding: 0 16px; border-radius: 7px;
}
QPushButton#principal {
    color: #ecdcb0; background: rgba(214, 167, 44, 0.06);
    border: 1px solid rgba(214, 167, 44, 0.35);
}
QPushButton#secondaire {
    color: #d9d6e8; background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.14);
}
QPushButton#principal:hover, QPushButton#secondaire:hover {
    border-color: #d6a72c;
}
QPushButton#principal:disabled, QPushButton#secondaire:disabled {
    color: #6f6d8e; border-color: rgba(255, 255, 255, 0.08);
}
QPushButton#principal[focusClavier="true"]:focus,
QPushButton#secondaire[focusClavier="true"]:focus {
    border: 2px solid #d6a72c; padding: 0 15px;
}
"""


def feuille_de_style() -> str:
    """À poser une fois sur la fenêtre qui accueille les composants."""
    return themed(_STYLE)


def police(px: int, gras: bool = False) -> QFont:
    """Gelasio à une taille en PIXELS : les maquettes sont cotées en px."""
    f = body_font()
    f.setPixelSize(px)
    if gras:
        f.setWeight(QFont.Weight.DemiBold)
    return f


def texte(contenu: str, px: int = 13, encre: str = ENCRE,
          retour: bool = False) -> QLabel:
    """Un libellé en texte BRUT : rien de ce qu'il reçoit n'est interprété."""
    lbl = QLabel(contenu)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setFont(police(px))
    lbl.setStyleSheet(f"color: {encre}; background: transparent;")
    lbl.setWordWrap(retour)
    return lbl


def surtitre(contenu: str) -> QLabel:
    """Le petit titre doré en capitales espacées qui annonce une carte."""
    lbl = QLabel(contenu.upper())
    f = cinzel(8, bold=True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
    lbl.setFont(f)
    lbl.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
    lbl.setContentsMargins(2, 0, 0, 0)
    return lbl


def petit_titre(contenu: str) -> QLabel:
    """Le titre gris DANS une carte (« SE DÉPLACER », « CONTOURS »)."""
    lbl = QLabel(contenu.upper())
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    f = cinzel(7, bold=True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {ENCRE_DOUCE}; background: transparent; border: none;")
    return lbl


class Rangee(QWidget):
    """Des blocs côte à côte, empilés quand la place manque.

    `seuil` est la largeur sous laquelle tout passe en une colonne : trois
    cartes de touches de 200 px ne tiennent pas dans une fenêtre réduite, et
    les écraser couperait leurs libellés. `etirements` donne la part de chaque
    colonne quand elles sont côte à côte.
    """

    def __init__(self, blocs: list[QWidget], colonnes: int, seuil: int,
                 etirements: tuple[int, ...] = (), ecart: int = 16) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self._blocs = list(blocs)
        self._colonnes = colonnes
        self._seuil = seuil
        self._etirements = etirements or (1,) * colonnes
        self._grille = QGridLayout(self)
        self._grille.setContentsMargins(0, 0, 0, 0)
        self._grille.setHorizontalSpacing(ecart)
        self._grille.setVerticalSpacing(ecart)
        self._n = 0
        self._poser(colonnes)

    def colonnes(self) -> int:
        return self._n

    def _poser(self, n: int) -> None:
        if n == self._n:
            return
        self._n = n
        for bloc in self._blocs:
            self._grille.removeWidget(bloc)
        for c in range(self._colonnes):
            self._grille.setColumnStretch(c, self._etirements[c] if n > 1 else (1 if c == 0 else 0))
        for rang, bloc in enumerate(self._blocs):
            ligne, col = divmod(rang, n)
            self._grille.addWidget(bloc, ligne, col, Qt.AlignmentFlag.AlignTop if n == 1 else
                                   Qt.AlignmentFlag(0))

    def _largeur_cote_a_cote(self) -> int:
        """Ce que demandent VRAIMENT les blocs côte à côte : jamais moins que le seuil."""
        mini = sum(b.minimumSizeHint().width() for b in self._blocs[:self._colonnes])
        return max(self._seuil, mini + self._grille.horizontalSpacing() * (self._colonnes - 1))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        """Le minimum d'UNE colonne : annoncer celui des blocs côte à côte
        bloquerait la zone défilante à cette largeur, et la rangée ne
        s'empilerait plus jamais."""
        largeur = max((b.minimumSizeHint().width() for b in self._blocs), default=0)
        return QSize(largeur, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        large = event.size().width() >= self._largeur_cote_a_cote()
        self._poser(self._colonnes if large else 1)


def bouton(libelle: str, principal: bool = False) -> QPushButton:
    """Bouton de page : bordé d'or s'il fait l'action de la ligne, gris sinon."""
    btn = QPushButton(libelle)
    btn.setObjectName("principal" if principal else "secondaire")
    btn.setFont(police(13, gras=True))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class Carte(QFrame):
    """Un bloc bordé qui empile des lignes, un filet entre chacune."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("carte")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

    def ajouter(self, widget: QWidget) -> QWidget:
        if self._lay.count():
            filet = QFrame()
            filet.setObjectName("separateur")
            filet.setFixedHeight(1)
            self._lay.addWidget(filet)
        self._lay.addWidget(widget)
        return widget


class LigneReglage(QWidget):
    """Titre, phrase d'aide facultative, et les commandes à droite.

    La phrase reste accessible (`description`) : certaines lignes la changent
    selon l'état (espace occupé, bandes-annonces présentes). Le titre peut être
    un widget déjà construit (le chemin coupé au milieu des Paramètres).
    """

    def __init__(self, titre: str | QWidget, description: str = "", *commandes: QWidget,
                 icone: QWidget | None = None) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(18)
        if icone is not None:
            lay.addWidget(icone, alignment=Qt.AlignmentFlag.AlignVCenter)
        colonne = QVBoxLayout()
        colonne.setSpacing(3)
        self.titre = titre if isinstance(titre, QWidget) else texte(titre, 14)
        self.titre.setMinimumWidth(1)
        colonne.addWidget(self.titre)
        self.description = texte(description, 13, ENCRE_DOUCE, retour=True)
        self.description.setVisible(bool(description))
        colonne.addWidget(self.description)
        lay.addLayout(colonne, stretch=1)
        for commande in commandes:
            lay.addWidget(commande, alignment=Qt.AlignmentFlag.AlignVCenter)

    def decrire(self, contenu: str) -> None:
        self.description.setText(contenu)
        self.description.setVisible(bool(contenu))

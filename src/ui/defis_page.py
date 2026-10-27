"""Les Défis du Carnet : les succès d'un jeu, en médailles (2026-10-26).

Troisième rubrique du Carnet (`carnet_page.py`). Les succès restaient au bas
du folio, en liste de texte ; ici chacun a sa médaille (`medailles.py`), dans
l'ordre du jeu : du bronze à l'or, on lit ce qui vient ensuite. Une médaille
non obtenue montre son emblème en creux, avec ce qu'elle demande.

Ce qui compte est ce que `succes.obtenus` rend : les sauvegardes de TOUT le
jeu, et la première date observée. Une date inconnue ne s'affiche pas.

« Recommencer les défis » (2026-10-27) remet un jeu à zéro (`succes.recommencer`),
ce que Steam ne permet pas ; une partie déjà avancée les redonne dès qu'on y
rejoue, la confirmation le dit.
"""

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from src.core import sauvegardes, succes
from src.core.i18n import tr
from src.ui.composants import bouton, feuille_de_style
from src.ui.fenetre_message import message
from src.ui.medailles import pixmap_medaille
from src.ui.stats_widgets import _DISCRET, _Paragraphe, _texte
from src.ui.succes_widgets import _jour
from src.ui.theme import themed

_MEDAILLE = 84
_COLONNES = 2

_STYLE = """
QWidget#defis, QWidget#defisCorps { background: transparent; }
QScrollArea { background: transparent; border: none; }
QFrame#defi {
    background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 10px;
}
QFrame#defi[obtenu="true"] { border-color: rgba(214, 167, 44, 0.32); }
QLabel#titreSection { color: #d6a72c; letter-spacing: 2px; }
"""


class _Defi(QFrame):
    """Une médaille, son nom, ce qu'elle demande, et le jour où elle est tombée."""

    def __init__(self, jeu: str, defi: succes.Succes, obtenu: succes.Obtenu | None) -> None:
        super().__init__()
        self.setObjectName("defi")
        self.setProperty("obtenu", obtenu is not None)
        self.ident = defi.ident
        self.obtenu = obtenu is not None
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 16, 12)
        h.setSpacing(14)
        image = QLabel()
        image.setFixedSize(_MEDAILLE, _MEDAILLE)
        image.setPixmap(pixmap_medaille(jeu, defi.ident, self.obtenu, _MEDAILLE, self.devicePixelRatioF()))
        h.addWidget(image, alignment=Qt.AlignmentFlag.AlignTop)
        pile = QVBoxLayout()
        pile.setContentsMargins(0, 4, 0, 0)
        pile.setSpacing(3)
        pile.addWidget(_texte(tr(defi.titre), 15, "#ffffff" if obtenu else "#c9c7da", gras=obtenu is not None))
        pile.addWidget(_Paragraphe(tr(defi.description), taille=13))
        quand = _jour(obtenu.date) if obtenu is not None else ""
        if quand:
            pile.addWidget(_texte(quand, 12, _DISCRET))
        pile.addStretch()
        h.addLayout(pile, stretch=1)


class DefisPage(QWidget):
    """Les médailles d'un jeu du folio ; un mot quand le jeu n'en a pas."""

    def __init__(self, game, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("defis")
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self.game = game
        self.defis: list[_Defi] = []
        self._racine = QVBoxLayout(self)
        self._racine.setContentsMargins(0, 0, 0, 0)
        self._remplir()

    def _remplir(self) -> None:
        game = self.game
        definitions = succes.du_jeu(game.id)
        presentes = [v.fichier for v in sauvegardes.vues(game.id, game.sauvegardes)] if definitions else []
        obtenus = succes.obtenus(game.id, presentes, game.sauvegardes) if definitions else {}
        self.defis = []

        racine = self._racine
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.Shape.NoFrame)
        corps = QWidget()
        corps.setObjectName("defisCorps")
        lay = QVBoxLayout(corps)
        lay.setContentsMargins(40, 26, 40, 30)
        lay.setSpacing(8)
        zone.setWidget(corps)
        racine.addWidget(zone)

        # Pas de titre « Défis » : la rubrique choisie en haut le dit déjà.
        if not definitions:
            lay.addWidget(_Paragraphe(tr("Ce jeu n'a pas encore de défis."), taille=14))
            lay.addStretch()
            return
        lay.addWidget(_Paragraphe(tr("{} sur {}").format(len(obtenus), len(definitions)), taille=14))
        lay.addSpacing(10)
        grille = QGridLayout()
        grille.setHorizontalSpacing(14)
        grille.setVerticalSpacing(14)
        for c in range(_COLONNES):
            grille.setColumnStretch(c, 1)
        for rang, defi in enumerate(definitions):
            carte = _Defi(game.id, defi, obtenus.get(defi.ident))
            grille.addWidget(carte, rang // _COLONNES, rang % _COLONNES)
            self.defis.append(carte)
        lay.addLayout(grille)
        if obtenus:
            lay.addSpacing(18)
            self.bouton_recommencer = bouton(tr("Recommencer les défis"))
            self.bouton_recommencer.clicked.connect(self.recommencer)
            lay.addWidget(self.bouton_recommencer, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addStretch()

    def recommencer(self) -> None:
        """Après confirmation, remet les défis du jeu à zéro et redessine la page."""
        choix = message(
            self, QMessageBox.Icon.Question, tr("Recommencer les défis"),
            tr("Les défis de {} repartent de zéro.").format(self.game.name) + "\n\n"
            + tr("Vos parties déjà avancées les redonnent dès que vous y rejouez : pour repartir "
                 "vraiment de zéro, commencez une nouvelle partie ou supprimez les anciennes "
                 "dans le jeu."),
            choix=(tr("Recommencer"), tr("Annuler")), defaut=1)
        if choix != 0:
            return
        succes.recommencer(self.game.id, datetime.now())
        ancienne = self._racine.takeAt(0)
        if ancienne is not None and (w := ancienne.widget()) is not None:
            w.hide()
            w.deleteLater()
        self._remplir()

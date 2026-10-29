"""Le Carnet : ce qui se lit dans les sauvegardes, en rubriques.

Rangement du 2026-10-24 (maquette « Collections », Ludo : « on ne peut pas
avoir des onglets à l'infini », puis « mes années ne signifie plus rien »).
L'onglet « Mes années » devient le Carnet : le Folio d'abord (Ludo : « le folio
en priorité »), puis le Relevé de scolarité. Une idée qui se lit dans les
sauvegardes (grimoire des sorts, cartes réunies) viendra ici en rubrique, pas
dans un onglet de plus.

Les deux rubriques sont les pages d'avant (`folio_jeux.page_folio`,
`stats_dialog.StatsDialog`), posées en mode intégré : le Carnet porte le
retour, le titre, les rubriques et le choix du jeu. Chacune est bâtie à la
première visite ; le folio est rebâti quand le jeu change.

Les Défis (2026-10-26) : les succès en médailles (`defis_page.py`), entre les
deux, sur le jeu choisi comme le Folio. Bâtis à la visite, oubliés quand le
jeu change.
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from src.core import folio
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.ui.composants import feuille_de_style, police, surtitre, texte
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel_decorative
from src.ui.choix_jeux import espacee, numeros, pastille
from src.ui.icon_button import pixmap_icone
from src.ui.theme import themed
from src.ui.title_bar import CARNET

FOLIO = "folio"
RELEVE = "releve"
DEFIS = "defis"
# Les rubriques qui suivent le jeu choisi en haut.
_PAR_JEU = (FOLIO, DEFIS)

_STYLE = """
QDialog#carnet { background: #070712; }
QWidget#transparent { background: transparent; }
QPushButton#retour {
    background: transparent; border: none; color: #a9a7c4; text-align: left; padding: 4px 2px;
}
QPushButton#retour:hover { color: #f2f2f4; }
QPushButton#rubrique, QPushButton#filtre {
    background: transparent; border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 15px;
    color: #c9c7da; padding: 6px 16px;
}
QPushButton#filtre { border-radius: 13px; padding: 5px 13px; }
QPushButton#rubrique:hover, QPushButton#filtre:hover { color: #f2f2f4; }
QPushButton#rubrique:checked, QPushButton#filtre:checked {
    background: rgba(214, 167, 44, 0.14); border-color: rgba(214, 167, 44, 0.6); color: #f2e6c4;
}
QPushButton#rubrique[focusClavier="true"]:focus, QPushButton#filtre[focusClavier="true"]:focus { border-color: #d6a72c; }
QFrame#filet { background: rgba(214, 167, 44, 0.12); border: none; }
"""


def _transparent(widget: QWidget) -> QWidget:
    widget.setObjectName("transparent")
    return widget


class CarnetPage(QDialog):
    """Le Carnet, en page : Folio, Défis et Relevé ; le jeu choisi en haut pour les deux premiers."""

    def __init__(self, manager: GameManager, parent: QWidget | None = None,
                 rubrique: str = FOLIO, jeu: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("carnet")
        # Ouvert depuis la fiche (lien FOLIO), il souligne quand même son onglet.
        self.setProperty("onglet", CARNET)
        self.setWindowTitle(tr("Carnet"))
        self.setMinimumSize(900, 560)
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self.manager = manager
        self._jeux = [e.game for e in manager.get_games()
                      if e.game.id in folio.JEUX and manager.is_installed(e.game.id)]
        self._folio: QDialog | None = None
        self._releve: QDialog | None = None
        self._defis: QWidget | None = None
        self.jeu = ""
        # La rubrique affichée, tenue ici : la DÉDUIRE de la pile se trompait.
        # Retirer l'ancien folio fait passer la pile sur le Relevé, et changer
        # de jeu dans le Folio montrait le Relevé (Ludo, 2026-10-24).
        self._rubrique = FOLIO

        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._entete())
        filet = QFrame()
        filet.setObjectName("filet")
        filet.setFixedHeight(1)
        racine.addWidget(filet)
        self._pile = QStackedWidget()
        self._vide = _transparent(QWidget())
        v = QVBoxLayout(self._vide)
        v.setContentsMargins(40, 28, 40, 28)
        v.addWidget(texte(tr("Installez un jeu pour ouvrir son folio."), 16, "#c9c7da", retour=True))
        v.addStretch()
        self._pile.addWidget(self._vide)
        racine.addWidget(self._pile, stretch=1)

        ids = [g.id for g in self._jeux]
        if jeu not in ids:
            dernier = manager.last_played_game_id()
            jeu = dernier if dernier in ids else (ids[0] if ids else "")
        if jeu:
            self.montrer(jeu)
        self.rubrique(rubrique if rubrique in self._rubriques else FOLIO)

    # ── Construction ──

    def _entete(self) -> QWidget:
        entete = _transparent(QWidget())
        e = QVBoxLayout(entete)
        e.setContentsMargins(40, 18, 40, 14)
        e.setSpacing(0)
        # Pas de « ← Bibliothèque » : l'onglet du haut le dit déjà, et Échap
        # ferme la page (Ludo, 2026-10-27 : « retire le bibliothèque répété »).
        e.addWidget(surtitre(tr("Vos parties, lues dans vos sauvegardes")))
        e.addSpacing(4)
        # Les rubriques JUSTE APRÈS le titre : tout à droite, on ne les voyait
        # pas (Ludo, 2026-10-24 : « pas bien indiqué le relevé et folio à droite »).
        ligne = QHBoxLayout()
        ligne.setSpacing(10)
        titre = QLabel(tr("Carnet"))
        titre.setFont(cinzel_decorative(22))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        ligne.addWidget(titre, alignment=Qt.AlignmentFlag.AlignVCenter)
        ligne.addSpacing(22)
        self._rubriques: dict[str, QPushButton] = {}
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        for cle, libelle, icone in ((FOLIO, tr("Folio"), "folio"), (DEFIS, tr("Défis"), "medaille"),
                                    (RELEVE, tr("Relevé"), "stats")):
            b = QPushButton(libelle)
            b.setObjectName("rubrique")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setFont(police(14))
            pictogramme, taille = espacee(pixmap_icone(icone, 18, QColor("#e6e4f0")), QSize(18, 18))
            b.setIcon(pictogramme)
            b.setIconSize(taille)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, r=cle: self.rubrique(r))
            groupe.addButton(b)
            ligne.addWidget(b, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._rubriques[cle] = b
        ligne.addStretch()
        e.addLayout(ligne)

        self._choix = _transparent(QWidget())
        flux = FlowLayout(self._choix, spacing=8)
        flux.setContentsMargins(0, 14, 0, 0)
        self._boutons: dict[str, QPushButton] = {}
        jeux = QButtonGroup(self)
        jeux.setExclusive(True)
        etiquettes = numeros(self._jeux)
        for game in self._jeux:
            b = pastille(game, etiquettes[game.id])
            b.clicked.connect(lambda _c=False, j=game.id: self.montrer(j))
            jeux.addButton(b)
            flux.addWidget(b)
            self._boutons[game.id] = b
        e.addWidget(self._choix)
        return entete

    def _poser(self, page: QDialog) -> QDialog:
        """Une page d'avant, en rubrique : sans cadre, et son Échap ferme le Carnet."""
        page.setWindowFlags(Qt.WindowType.Widget)
        page.setMinimumSize(0, 0)
        page.finished.connect(self._interne_fermee)
        self._pile.addWidget(page)
        return page

    def _interne_fermee(self, resultat: int) -> None:
        self.done(resultat)

    def done(self, resultat: int) -> None:
        """Le Carnet se ferme : le folio posé dedans aussi (audit du 2026-10-29)."""
        if self._folio is not None:
            self._folio.arreter()
        super().done(resultat)

    # ── Rubriques ──

    def montrer(self, jeu: str) -> None:
        """Le folio de `jeu` ; le Relevé, lui, ne dépend pas du jeu choisi."""
        game = next((g for g in self._jeux if g.id == jeu), None)
        if game is None:
            return
        if jeu != self.jeu or self._folio is None:
            from src.ui.folio_jeux import page_folio
            ancien = self._folio
            self._folio = self._poser(page_folio(game, self.manager.config.install_path, self,
                                                 integree=True, config=self.manager.config))
            if ancien is not None:
                ancien.finished.disconnect(self._interne_fermee)
                # Son `done` n'est jamais appelé ici : le fil de HP4 décodait
                # encore toutes les illustrations d'une page détruite.
                ancien.arreter()
                self._pile.removeWidget(ancien)
                ancien.deleteLater()
            self.jeu = jeu
            self._retirer_defis()
        self._boutons[jeu].setChecked(True)
        if self._rubrique == FOLIO:
            self._pile.setCurrentWidget(self._folio)
        elif self._rubrique == DEFIS:
            self._montrer_defis()

    def _retirer_defis(self) -> None:
        """Les défis d'un autre jeu : rebâtis à la prochaine visite."""
        if self._defis is not None:
            self._pile.removeWidget(self._defis)
            self._defis.deleteLater()
            self._defis = None

    def _montrer_defis(self) -> None:
        game = next((g for g in self._jeux if g.id == self.jeu), None)
        if game is None:
            self._pile.setCurrentWidget(self._vide)
            return
        if self._defis is None:
            from src.ui.defis_page import DefisPage
            self._defis = DefisPage(game)
            self._pile.addWidget(self._defis)
        self._pile.setCurrentWidget(self._defis)

    def _depuis_le_releve(self, jeu: str) -> None:
        self.montrer(jeu)
        self.rubrique(FOLIO)

    def rubrique(self, cle: str) -> None:
        self._rubrique = cle
        self._rubriques[cle].setChecked(True)
        self._choix.setVisible(cle in _PAR_JEU and bool(self._jeux))
        if cle == RELEVE:
            if self._releve is None:
                from src.ui.stats_dialog import StatsDialog
                self._releve = self._poser(StatsDialog(self.manager, self, folio=self._depuis_le_releve,
                                                       integree=True))
            self._pile.setCurrentWidget(self._releve)
        elif cle == DEFIS:
            self._montrer_defis()
        else:
            self._pile.setCurrentWidget(self._folio if self._folio is not None else self._vide)

    @property
    def rubrique_courante(self) -> str:
        return self._rubrique

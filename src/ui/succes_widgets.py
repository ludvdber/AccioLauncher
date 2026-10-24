"""La section « Succès » de la fiche d'un jeu, dans Mes années (`stats_dialog.py`).

Ceux qu'on a obtenus d'abord, dans l'ordre du jeu, avec la date de la partie
où ils sont tombés quand on l'a vue ; puis ceux qui restent, en retrait. Une
date inconnue (déjà là au premier regard, `succes.py`) ne s'affiche pas :
rien n'est deviné.
"""

from collections.abc import Callable
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from src.core import succes
from src.core.catalogue_blocs import Sauvegardes
from src.core.i18n import tr
from src.ui.stats_widgets import _DISCRET, _Paragraphe, _texte, _titre_section
from src.ui.toast import Toast


def annonce_succes(nom_du_jeu: str, obtenus: list[succes.Succes]) -> str:
    """Le texte du toast au retour de partie (`MainWindow._on_game_exited`). Le
    toast ne passe pas à la ligne seul : deux lignes, trois titres au plus."""
    if len(obtenus) == 1:
        return (tr("Succès dans {} : {}").format(nom_du_jeu, tr(obtenus[0].titre))
                + "\n" + tr(obtenus[0].description))
    titres = ", ".join(tr(s.titre) for s in obtenus[:3])
    if len(obtenus) > 3:
        titres += " " + tr("et {} autres").format(len(obtenus) - 3)
    return tr("{} succès dans {} :").format(len(obtenus), nom_du_jeu) + "\n" + titres


def annoncer_succes(toast: Toast, nom_du_jeu: str, obtenus: list[succes.Succes] | bool,
                    ouvrir: Callable[[], None]) -> bool:
    """Le toast des succès de la partie qui vient de finir ; vrai s'il y en avait.
    Un clic ouvre Mes années, ouverte sur le dernier jeu joué : celui-ci. La
    fenêtre passe `partie and succes_obtenus` : faux quand le jeu n'a pas démarré."""
    if not obtenus or obtenus is True:
        return False
    toast.show_message(annonce_succes(nom_du_jeu, obtenus), duration_ms=9000, on_click=ouvrir)
    return True


def _jour(quand: datetime | None) -> str:
    return quand.strftime("%d/%m/%Y") if quand else ""


class SectionSucces(QWidget):
    """Titre, compte, puis une ligne par succès : nom, ce qu'il demande, date."""

    def __init__(self, jeu: str, sauvegardes: list[str], spec: Sauvegardes | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        definitions = succes.du_jeu(jeu)
        self.obtenus = succes.obtenus(jeu, sauvegardes, spec)
        couche = QVBoxLayout(self)
        couche.setContentsMargins(0, 0, 0, 0)
        couche.setSpacing(8)
        couche.addWidget(_titre_section(tr("Succès")))
        couche.addWidget(_Paragraphe(
            tr("{} sur {}").format(len(self.obtenus), len(definitions)), taille=13))
        grille = QGridLayout()
        grille.setContentsMargins(0, 4, 0, 0)
        grille.setHorizontalSpacing(16)
        grille.setVerticalSpacing(10)
        grille.setColumnStretch(0, 1)
        ordre = ([s for s in definitions if s.ident in self.obtenus]
                 + [s for s in definitions if s.ident not in self.obtenus])
        self.lignes: list[str] = []
        for rang, s in enumerate(ordre):
            obtenu = self.obtenus.get(s.ident)
            texte = QWidget()
            pile = QVBoxLayout(texte)
            pile.setContentsMargins(0, 0, 0, 0)
            pile.setSpacing(2)
            pile.addWidget(_texte(tr(s.titre), 14, "#ffffff" if obtenu else _DISCRET, gras=obtenu is not None))
            pile.addWidget(_Paragraphe(tr(s.description), taille=12))
            grille.addWidget(texte, rang, 0)
            date = _texte(_jour(obtenu.date) if obtenu else "", 12, _DISCRET)
            grille.addWidget(date, rang, 1, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
            self.lignes.append(s.ident)
        couche.addLayout(grille)

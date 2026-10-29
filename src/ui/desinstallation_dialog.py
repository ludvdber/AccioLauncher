"""« Désinstaller Accio Launcher » : ce qui part, ce qui reste, puis on ferme.

Ouverte depuis Paramètres › Général. Les jeux restent par défaut : ce sont des
gigaoctets, et un launcher réinstallé les retrouve tout seul (l'assistant les
reprend tels quels). Les sauvegardes sont dans Documents : rien n'y touche.

L'effacement lui-même attend la fermeture (`src/core/desinstallation.py`).
"""

from pathlib import Path

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import desinstallation
from src.core.formatting import format_bytes
from src.core.i18n import tr
from src.ui.composants import Carte, LigneReglage, bouton, feuille_de_style, texte
from src.ui.fonts import cinzel_decorative
from src.ui.theme import themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import avertir

_STYLE = """
QDialog { background: #060611; }
QPushButton#danger {
    min-height: 34px; max-height: 34px; padding: 0 16px; border-radius: 7px;
    color: #f6d2cd; background: rgba(224, 88, 79, 0.10);
    border: 1px solid rgba(224, 88, 79, 0.60);
}
QPushButton#danger:hover { background: rgba(224, 88, 79, 0.20); border-color: #e0584f; }
QPushButton#danger[focusClavier="true"]:focus { border: 2px solid #f39a8f; padding: 0 15px; }
"""
_ORANGE = "#ecc896"


def _interrupteur(titre: str, coche: bool) -> tuple[LigneReglage, ToggleSwitch]:
    bascule = ToggleSwitch(coche)
    bascule.setAccessibleName(titre)
    return LigneReglage(titre, "", bascule), bascule


class DesinstallationDialog(QDialog):
    """Deux choix, tous deux « garder » par défaut, et un bouton qui dit ce qu'il fait."""

    def __init__(self, install_path: Path, octets_jeux: int, a_des_jeux: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._install_path = install_path
        self._octets = octets_jeux
        self.setWindowTitle(tr("Désinstaller Accio Launcher"))
        self.setMinimumWidth(600)
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(0)
        titre = QLabel(tr("Désinstaller Accio Launcher"))
        titre.setFont(cinzel_decorative(16))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        lay.addWidget(titre)
        lay.addSpacing(10)
        lay.addWidget(texte(tr(
            "Le launcher s'efface dès qu'il se ferme : son programme, ses réglages, "
            "ses journaux, son cache et les bandes-annonces."), 14, "#a9a7c4", retour=True))
        lay.addSpacing(20)

        carte = Carte()
        self._ligne_jeux, self.tgl_jeux = _interrupteur(tr("Garder mes jeux"), True)
        self.tgl_jeux.toggled.connect(self._regler)
        carte.ajouter(self._ligne_jeux)
        # Après l'ajout : sans parent, une ligne rendue visible est une FENÊTRE.
        self._ligne_jeux.setVisible(a_des_jeux)
        ligne_copies, self.tgl_copies = _interrupteur(tr("Garder les copies de sauvegardes"), True)
        ligne_copies.decrire(tr("Elles restent seules dans le dossier _Launcher."))
        carte.ajouter(ligne_copies)
        carte.ajouter(LigneReglage(tr("Vos sauvegardes"), tr(
            "Elles sont dans Documents : elles restent, quoi qu'il arrive.")))
        lay.addWidget(carte)
        lay.addSpacing(22)

        boutons = QHBoxLayout()
        boutons.addStretch()
        annuler = bouton(tr("Annuler"))
        annuler.clicked.connect(self.reject)
        boutons.addWidget(annuler)
        boutons.addSpacing(8)
        self.confirmer = bouton(tr("Désinstaller et fermer"))
        self.confirmer.setObjectName("danger")
        self.confirmer.clicked.connect(self.accept)
        boutons.addWidget(self.confirmer)
        lay.addLayout(boutons)
        annuler.setFocus()
        self._regler()

    @property
    def garder_jeux(self) -> bool:
        return self.tgl_jeux.isChecked() or not self._ligne_jeux.isVisibleTo(self)

    @property
    def garder_copies(self) -> bool:
        return self.tgl_copies.isChecked()

    def _regler(self) -> None:
        taille = format_bytes(self._octets) if self._octets else ""
        if self.tgl_jeux.isChecked():
            phrase = (tr("Vos jeux ({taille}) restent dans {dossier}. Un launcher réinstallé "
                         "les retrouve tout seul.") if taille else
                      tr("Vos jeux restent dans {dossier}. Un launcher réinstallé "
                         "les retrouve tout seul.")).format(taille=taille, dossier=self._install_path)
            encre = "#8f8db0"
        else:
            phrase = (tr("Vos jeux seront effacés : {taille} libérés.") if taille
                      else tr("Vos jeux seront effacés.")).format(taille=taille)
            encre = _ORANGE
        self._ligne_jeux.decrire(phrase)
        self._ligne_jeux.description.setStyleSheet(f"color: {encre}; background: transparent;")


def desinstaller(fenetre, parent: QWidget, garder_jeux: bool, garder_copies: bool) -> bool:
    """Programme l'effacement et ferme le launcher. False : rien n'a été lancé.

    `fenetre` est la MainWindow : une partie en cours ou une opération à
    interrompre se règlent AVANT d'écrire le script, qui attend la fin du
    processus et ne saurait plus être retenu.
    """
    if fenetre._session.nom_en_cours:
        avertir(parent, tr("Une partie est en cours"),
                tr("Fermez d'abord {}, puis recommencez.").format(fenetre._session.nom_en_cours))
        return False
    if not fenetre._confirmer_fermeture():
        return False
    manager = fenetre.manager
    dossiers = [p for p in (manager.get_game_path(e.game.id) for e in manager.get_games())
                if p is not None and p.is_dir()]
    inv = desinstallation.inventaire(fenetre.config.install_path, dossiers, garder_jeux,
                                     garder_copies, desinstallation.programme_courant())
    if not desinstallation.programmer(inv):
        avertir(parent, tr("Le launcher n'a pas été désinstallé"), tr(
            "Le script qui efface le launcher n'a pas pu démarrer. "
            "Le détail est dans le journal."))
        return False
    # Les Paramètres d'abord, comme pour « Redémarrer maintenant » : leur
    # boucle modale se referme avant la fenêtre qui les porte.
    if isinstance(parent, QDialog):
        parent.accept()
    fenetre._fermer_sans_demander()
    return True

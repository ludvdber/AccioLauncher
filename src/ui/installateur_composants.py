"""Cycle de vie de l'installation des composants Windows (ACT-054).

Le pendant Windows de `PreparateurWine`, avec le MÊME contrat : mêmes signaux,
mêmes méthodes. La fiche, la barre du bas et les handlers parlent donc à « la
préparation » sans savoir laquelle tourne. Ici, rien qui se voie : ce module
fait tourner `InstallationComposants`, compose le texte d'état et dit quand
c'est fini.
"""

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.composants_windows import ANNULEE, InstallationComposants, paquets_pour
from src.core.config import LOG_DIR
from src.core.game_data import GameData
from src.core.i18n import tr
from src.core.thread_utils import arreter_a_la_fermeture, liberer_apres_fin

log = logging.getLogger(__name__)


def noms_des_paquets(prerequis) -> str:
    """« Visual C++ 2005, DirectX » — noms de produits, non traduits."""
    return ", ".join(p.nom for p in paquets_pour(prerequis))


class InstallateurComposants(QObject):
    """Possède l'unique `InstallationComposants` en cours."""

    message = pyqtSignal(str)
    commencee = pyqtSignal(object)
    # (étape lisible, détail : le téléchargement en cours)
    progression = pyqtSignal(str, str)
    # (id du jeu, réussie, raison, puis_jouer)
    terminee = pyqtSignal(str, bool, str, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fil: InstallationComposants | None = None
        self._jeu_id = ""
        self._puis_jouer = False
        self._etape = ""

    @property
    def en_cours(self) -> bool:
        return self._fil is not None

    @property
    def journal(self):
        """Ce qui s'est passé est au journal du launcher (codes, signatures)."""
        return LOG_DIR

    def demarrer(self, game: GameData, prerequis, puis_jouer: bool) -> bool:
        """Lance l'installation pour ce jeu. False si rien à faire ou déjà en cours."""
        if self._fil is not None or not paquets_pour(prerequis):
            return False
        self._jeu_id = game.id
        self._puis_jouer = puis_jouer
        self._fil = InstallationComposants(prerequis, parent=self)
        self._fil.etape.connect(self._on_etape)
        self._fil.avancement.connect(self._on_avancement)
        self._fil.installation_terminee.connect(self._on_terminee)
        log.info("Composants Windows pour %s : %s", game.id, noms_des_paquets(prerequis))
        self._etape = tr("Composants Windows…")
        self.commencee.emit(game)
        self._fil.start()
        return True

    def annuler(self) -> None:
        """Arrête les téléchargements (bouton « Annuler » de la barre du bas)."""
        if self._fil is not None:
            self._fil.annuler()
            self.message.emit(tr("Installation des composants annulée."))

    def _on_etape(self, etape: str, noms: str) -> None:
        if etape == "telechargement":
            self._etape = tr("Téléchargement de {}").format(noms)
            texte = tr("Composants Windows : téléchargement de {} depuis Microsoft…").format(noms)
            detail = ""
        else:
            self._etape = tr("Installation de {}").format(noms)
            texte = tr("Composants Windows : installation de {}…").format(noms)
            detail = tr("Acceptez l'autorisation de Windows pour continuer.")
        self.message.emit(texte)
        self.progression.emit(self._etape, detail)

    def _on_avancement(self, ligne: str) -> None:
        self.progression.emit(self._etape, ligne)

    def _on_terminee(self, reussie: bool, raison: str) -> None:
        fil, self._fil = self._fil, None
        if fil is not None:
            try:
                fil.etape.disconnect(self._on_etape)
                fil.avancement.disconnect(self._on_avancement)
                fil.installation_terminee.disconnect(self._on_terminee)
            except TypeError:
                pass
            # Le signal part de run() juste avant son retour (règle 133).
            liberer_apres_fin(fil)
        if reussie:
            self.message.emit(tr("Composants Windows installés."))
        elif raison != ANNULEE:
            self.message.emit(tr("L'installation des composants Windows n'a pas abouti."))
        self.terminee.emit(self._jeu_id, reussie, raison, self._puis_jouer)

    def shutdown(self) -> None:
        """À la fermeture : arrête les téléchargements et attend le fil."""
        if self._fil is None:
            return
        self._fil.annuler()
        arreter_a_la_fermeture(self._fil, "Composants Windows")
        self._fil = None

"""Cycle de vie de la préparation du préfixe Wine (Linux).

Même contrat que `UpdateDispatcher` et `TrailerStore` : **ici, rien qui se
voie**. Ce module fait tourner `PreparationWine`, compose le texte d'état à
poser dans la barre de statut et dit quand c'est fini ; la fiche de jeu décide
du reste — rafraîchir le bandeau, lancer le jeu, ou expliquer un échec.

Une seule préparation à la fois : deux winetricks dans le même préfixe se
marcheraient dessus.
"""

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from src.core import compat
from src.core.game_data import GameData
from src.core.i18n import tr
from src.core.preparation_wine import PreparationWine
from src.core.thread_utils import arreter_a_la_fermeture

log = logging.getLogger(__name__)

# Nom lisible de chaque verbe, pour la barre de statut. Les verbes eux-mêmes
# viennent de `system_checks.VERBES_WINETRICKS`.
_NOMS_VERBES = {
    "vcrun2022": "Visual C++ 2015-2022",
    "vcrun2005": "Visual C++ 2005",
    "vcrun2008": "Visual C++ 2008",
}


def noms_des_verbes(verbes) -> str:
    """« Visual C++ 2005, Visual C++ 2015-2022 » — noms de produits, non traduits."""
    return ", ".join(_NOMS_VERBES.get(v, v) for v in verbes)


class PreparateurWine(QObject):
    """Possède l'unique `PreparationWine` en cours."""

    message = pyqtSignal(str)
    # (id du jeu, réussie, raison, puis_jouer)
    terminee = pyqtSignal(str, bool, str, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fil: PreparationWine | None = None
        self._jeu_id = ""
        self._famille = ""
        self._puis_jouer = False

    @property
    def en_cours(self) -> bool:
        return self._fil is not None

    @property
    def journal(self):
        """Journal de la dernière préparation (utile au message d'échec)."""
        return compat.dossier_journaux() / "wine-preparation.log"

    def demarrer(self, game: GameData, verbes, puis_jouer: bool) -> bool:
        """Lance la préparation pour ce jeu. False si impossible ou déjà en cours."""
        if self._fil is not None:
            return False
        lanceur = compat.lanceur()
        if lanceur is None:
            return False
        self._jeu_id = game.id
        self._famille = lanceur.famille
        self._puis_jouer = puis_jouer
        self._fil = PreparationWine(lanceur, compat.prefixe(lanceur.famille),
                                    tuple(verbes), self.journal, parent=self)
        self._fil.etape.connect(self._on_etape)
        self._fil.preparation_terminee.connect(self._on_terminee)
        log.info("Préparation de Wine pour %s (%s) : %s", game.id, lanceur.famille,
                 " ".join(verbes) or "préfixe seul")
        self._fil.start()
        return True

    def _on_etape(self, etape: str, verbes: str) -> None:
        if etape == "prefixe":
            if self._famille == "umu":
                self.message.emit(tr(
                    "Préparation de Wine : création du préfixe… (umu peut d'abord "
                    "télécharger Proton, plusieurs centaines de Mo)"))
            else:
                self.message.emit(tr("Préparation de Wine : création du préfixe…"))
        else:
            self.message.emit(tr("Préparation de Wine : installation de {}…").format(
                noms_des_verbes(verbes.split())))

    def _on_terminee(self, reussie: bool, raison: str) -> None:
        fil, self._fil = self._fil, None
        if fil is not None:
            try:
                fil.etape.disconnect(self._on_etape)
                fil.preparation_terminee.disconnect(self._on_terminee)
            except TypeError:
                pass
            fil.deleteLater()
        self.terminee.emit(self._jeu_id, reussie, raison, self._puis_jouer)

    def shutdown(self) -> None:
        """À la fermeture : arrête la préparation, processus compris.

        Le résultat de l'attente n'est pas jetable — un fil encore vivant serait
        détruit avec la fenêtre (cf. `thread_utils`). `annuler()` fait tuer le
        groupe de processus par le fil lui-même, à son prochain sondage.
        """
        if self._fil is None:
            return
        self._fil.annuler()
        arreter_a_la_fermeture(self._fil, "Préparation de Wine")
        self._fil = None

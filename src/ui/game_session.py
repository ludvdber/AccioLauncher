"""Une partie, du lancement au retour : surveillance, présence Discord, journal.

Extrait de `main_window.py` le 2026-08-28, sur le même contrat que
`UpdateDispatcher` et `TrailerStore` : **ici, rien qui se voie**. Ce module
surveille le processus, tient le journal des sessions et allume la présence
Discord ; la fenêtre, elle, décide de ce qui s'affiche — se mettre dans la zone
de notification, revenir, poser un message.

Le partage n'est pas arbitraire : `ProcessMonitor` et `DiscordPresence` étaient
créés par la fenêtre et n'étaient utilisés QUE par ces quatre méthodes. Ils
descendent donc ici avec elles, et la fenêtre cesse de porter deux objets dont
elle ne se sert pas.

**Ce que ce module garantit, et pourquoi il compte** : une session n'était
autrefois écrite qu'à la FERMETURE du jeu. Or c'est pendant la partie que le
launcher dort dans la zone de notification, donc qu'on le quitte par son menu ou
qu'une mise à jour le tue — si bien que **plus une partie était longue, plus
elle avait de chances d'être perdue**. Ce biais silencieux contaminait à la fois
la moyenne, le record, les séries et les plages horaires. D'où l'ouverture
immédiate (`stats.ouvrir_session`) et le battement d'une minute : la durée
rattrapée après une coupure est OBSERVÉE et non devinée.
"""

import logging
import subprocess
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from src.core import stats
from src.core.discord_presence import DiscordPresence
from src.core.game_manager import GameManager
from src.ui.process_monitor import ProcessMonitor

log = logging.getLogger(__name__)


class GameSession(QObject):
    """Le cycle de vie d'une partie. Ne montre rien, ne cache rien."""

    # Une partie commence — la fenêtre a de quoi se retirer et changer son
    # infobulle. Le nom seulement : rien de ce qui suit n'est son affaire.
    demarree = pyqtSignal(str)
    # Le jeu s'est fermé. Émis APRÈS l'enregistrement, pour que la fiche
    # rafraîchie par la fenêtre porte déjà le temps de cette partie. Le booléen
    # dit si c'était une VRAIE partie : un jeu mort en une demi-seconde ne doit
    # pas s'entendre souhaiter « bon jeu ». Le verdict vient d'`add_playtime`,
    # seul endroit où le seuil est arbitré.
    terminee = pyqtSignal(str, bool)

    def __init__(self, manager: GameManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._presence = DiscordPresence()  # no-op tant que DISCORD_CLIENT_ID est vide
        self._monitor = ProcessMonitor(self)
        self._monitor.game_exited.connect(self._on_game_exited)
        self._monitor.battement.connect(self._on_battement)
        self._game_id: str = ""
        self._debut: datetime | None = None

    @property
    def nom_en_cours(self) -> str:
        """Nom du jeu en cours, vide si aucun. Utile aux journaux."""
        return self._monitor.game_name

    def demarrer(self, process: subprocess.Popen, game_name: str, game_id: str) -> None:
        """Un jeu vient d'être lancé : ouvrir la session et surveiller."""
        self._game_id = game_id
        self._debut = datetime.now()
        # Notée DÈS MAINTENANT et non à la fin — raison dans l'en-tête du module.
        stats.ouvrir_session(game_id, self._debut)
        self._monitor.start(process, game_name)
        if self._manager.config.discord_presence:
            self._presence.set_playing(game_name)
        self.demarree.emit(game_name)

    def _on_battement(self) -> None:
        """Le jeu tourne encore : on rafraîchit le filet de reprise."""
        stats.battre_session(datetime.now())

    def _on_game_exited(self, game_name: str, code: object, duree: float) -> None:
        """Fin du jeu. `duree` est le temps OBSERVÉ, grâce exclue ; ce qui compte
        comme une vraie partie se décide dans `add_playtime`."""
        stats.fermer_session()
        # Sans session ouverte (relance de processus par UE1), on ne peut rien
        # affirmer : on suppose une partie plutôt que d'accuser à tort.
        partie = True
        if self._game_id:
            partie = self._manager.add_playtime(
                self._game_id, int(duree), self._debut, code)
        self._game_id = ""
        self._debut = None
        self._presence.clear()
        self.terminee.emit(game_name, partie)

    def shutdown(self) -> None:
        """Coupe la présence Discord à la fermeture du launcher.

        La session en cours n'est PAS fermée ici : le fichier de reprise doit
        survivre à la mort du launcher, c'est tout son intérêt. Le prochain
        démarrage la récupérera (`stats.recuperer_session_interrompue`) — sinon
        quitter le launcher pendant une partie effacerait cette partie, ce qui
        est exactement le biais que ce module existe pour corriger.
        """
        self._presence.shutdown()

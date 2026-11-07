"""Le toast « un réglage du correctif n'a pas pu s'appliquer », au retour d'une partie (`core/journal_correctif`).

Hors de `main_window.py` (plafond de lignes, `test_update_dispatcher`) : la fenêtre appelle `brancher` en
construisant sa session, et n'en sait pas plus.

Un toast et pas une boîte : le jeu a tourné, rien n'est cassé, mais un réglage est resté sans effet et le joueur
croirait le réglage inutile ; l'issue arrivait sans la preuve (#28). Une fois par panne (`Config.correctif_signale`) :
la même ligne à chaque lancement ne se redit pas. Un toast à la fois : un succès ou le merci annoncé passe d'abord,
et la panne, pas marquée dite, revient au retour suivant.
"""
from typing import TYPE_CHECKING

from src.core import journal_correctif
from src.core.i18n import tr
from src.core.liens import DISCORD_URL
from src.ui import game_detail_handlers
from src.ui.utils import open_url

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


def brancher(window: MainWindow) -> None:
    window._session.correctif_en_echec.connect(lambda gid, echecs: signaler(window, gid, echecs))


def message(nom: str) -> str:
    return tr("{} : un réglage du correctif n'a pas pu s'appliquer.").format(nom)


def signaler(window: MainWindow, game_id: str, echecs: object) -> None:
    game = window.manager.get_game_by_id(game_id)
    if game is None or window._session.nom_en_cours or not isinstance(echecs, tuple) or not echecs:
        return
    empreinte = journal_correctif.signature(echecs)
    config = window.manager.config
    if config.correctif_signale.get(game_id) == empreinte or window._toast.isVisible():
        return
    config.correctif_signale[game_id] = empreinte
    config.save()
    nom = game.name
    window._toast.show_message(
        message(nom) + "\n" + tr("Besoin d'aide ? Cliquez : rapport copié, Discord ouvert."),
        duration_ms=12000, on_click=lambda: aider(window, nom))


def aider(window: MainWindow, nom: str) -> None:
    """Clic sur le toast : le rapport (journal de la DLL compris) part avec le joueur, Discord s'ouvre."""
    game_detail_handlers.copier_le_rapport(window._detail, message(nom))
    open_url(DISCORD_URL)

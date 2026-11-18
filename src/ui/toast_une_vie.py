"""Le toast « votre vie s'est terminée », au retour d'une partie à une seule vie (`core/une_vie`).

Hors de `main_window.py` (plafond de lignes), comme `toast_correctif` : la fenêtre appelle `brancher` en construisant
sa session. La DLL a vidé le dossier du mode à la première mort ; le jeu, lui, l'a dit à sa façon (son menu, ou rien
s'il s'est fermé, `une_vie.MODES`). Le launcher dit le reste : la partie est effacée, et la suivante est une nouvelle
vie. Un toast déjà affiché (un succès) passe d'abord : celui-ci suit, il n'est jamais perdu.
"""
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

from src.core.i18n import tr

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow

# Le temps d'un toast de succès, plus une marge.
_APRES_UN_AUTRE_MS = 9000
DUREE_MS = 12000


def brancher(window: MainWindow) -> None:
    window._session.vie_terminee.connect(lambda gid: annoncer(window, gid))


def message(nom: str) -> str:
    return (tr("{} : votre vie s'est terminée, et sa partie est effacée.").format(nom) + "\n"
            + tr("La prochaine partie en commence une nouvelle."))


def annoncer(window: MainWindow, game_id: str, essais: int = 3) -> None:
    game = window.manager.get_game_by_id(game_id)
    if game is None or window._session.nom_en_cours:
        return
    if window._toast.isVisible() and essais > 0:
        QTimer.singleShot(_APRES_UN_AUTRE_MS, lambda: annoncer(window, game_id, essais - 1))
        return
    window._toast.show_message(message(game.name), duration_ms=DUREE_MS)

"""« Jouer à … » de l'icône du launcher dans la barre des tâches (`core/liste_saut`).

Hors de `main_window.py` (plafond de lignes, `test_update_dispatcher`) : main.py
branche ici l'instance unique et la fin de partie, la fenêtre n'en sait rien.
"""
from PyQt6.QtCore import QTimer

from src.core import liste_saut
from src.ui import game_detail_handlers
from src.ui.main_window import MainWindow
from src.ui.single_instance import SingleInstance


def brancher(window: MainWindow, guard: SingleInstance) -> None:
    """La demande relayée par une seconde instance, et la liste refaite après
    chaque partie : le jeu qu'on vient de quitter passe en tête."""
    guard.jouer_requested.connect(lambda game_id: jouer_demande(window, game_id))
    window._session.terminee.connect(lambda *_: liste_saut.mettre_a_jour(window.manager))
    liste_saut.activer()
    liste_saut.mettre_a_jour(window.manager)


def jouer_demande(window: MainWindow, game_id: str) -> None:
    """`--jouer` ou relayé par l'instance unique : la fiche du jeu, puis JOUER
    s'il est installé — les mêmes garde-fous qu'un clic."""
    window.bring_to_front()
    games = [entry.game for entry in window.manager.get_games()]
    idx = next((i for i, g in enumerate(games) if g.id == game_id), None)
    if idx is None:
        return
    window._carousel.select(idx)

    def jouer() -> None:
        detail = window._detail
        if detail.game is not None and detail.game.id == game_id and window.manager.is_installed(game_id):
            game_detail_handlers.on_play(detail)
    # La fiche s'ouvre avec une transition : JOUER une fois qu'elle montre ce jeu.
    QTimer.singleShot(400, jouer)

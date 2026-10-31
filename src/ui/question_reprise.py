"""La question d'après la première partie de HP1 à HP3 : ouvrir directement la partie ?

Ludo, 2026-10-27 : « j'aime pas trop que lancer HP1 skip le menu, si quelqu'un
voulait lancer une autre save ou une nouvelle partie ». « Reprendre » passe
donc par le menu du jeu tant que la personne n'a rien choisi ; après sa
première partie de chacun de ces jeux, une seule question pour CE jeu, et la
réponse se change dans ses réglages, onglet Jeu (« Reprendre ouvre la dernière
partie », par jeu depuis le 2026-10-31).

Hors de `main_window.py` (plafond de lignes) : main.py la branche sur la fin
de partie, la fenêtre n'en sait rien.
"""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from src.core import reprise
from src.core.i18n import tr
from src.ui.fenetre_message import message
from src.ui.main_window import MainWindow


def brancher(window: MainWindow) -> None:
    session = window._session
    # Après le retour de la fenêtre et le toast de fin de partie.
    session.terminee.connect(
        lambda _nom, partie, arret: QTimer.singleShot(
            800, lambda jeu=session.jeu_termine: demander(window, jeu, partie, arret)))


def a_demander(window: MainWindow, jeu: str, partie: bool, arret: bool) -> bool:
    """Une vraie partie d'un jeu qui sait reprendre, une sauvegarde à rouvrir,
    et jamais posée encore."""
    config = window.manager.config
    if arret or not partie or jeu not in reprise.JEUX or jeu in config.reprise:
        return False
    game = window.manager.get_game_by_id(jeu)
    return game is not None and bool(reprise.arguments(game))


def demander(window: MainWindow, jeu: str, partie: bool, arret: bool) -> None:
    if not a_demander(window, jeu, partie, arret):
        return
    game = window.manager.get_game_by_id(jeu)
    choix = message(
        window, QMessageBox.Icon.Question, tr("Reprendre votre partie"),
        tr("La prochaine fois, « Reprendre » peut ouvrir directement votre dernière partie de {}, "
           "sans passer par le menu du jeu.").format(game.name if game is not None else jeu)
        + "\n\n" + tr("Vous pourrez changer d'avis dans les réglages du jeu, onglet Jeu."),
        choix=(tr("Ouvrir directement"), tr("Garder le menu du jeu")))
    config = window.manager.config
    config.reprise[jeu] = choix == 0
    config.save()

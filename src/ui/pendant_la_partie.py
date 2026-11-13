"""Pendant une partie, le launcher se fait oublier (audit du 2026-11-13, règle 141).

Hors de `main_window.py` (plafond de lignes, `test_update_dispatcher`) : la fenêtre appelle `brancher` en
construisant sa session, et n'en sait pas plus.

- les fonds préchargés de la fiche (≈ 106 Mo pour les huit) sont rendus au jeu au lancement, et reviennent au retour ;
- la question « Mise à jour disponible » ne s'ouvre pas par-dessus le jeu (`_propose_launcher_update` se tait tant
  qu'un jeu tourne) : elle est reposée au retour, sauf après un arrêt fatal, dont la boîte passe d'abord.

Les paquets des jeux lus par le Carnet et les Collections, eux, sont rendus par `GameSession.demarrer`.
"""
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


def brancher(window: MainWindow) -> None:
    window._session.demarree.connect(lambda _nom: window._detail.fonds_pendant_la_partie(True))
    window._session.terminee.connect(lambda _nom, _partie, arret: au_retour(window, arret))


def au_retour(window: MainWindow, arret: bool) -> None:
    window._detail.fonds_pendant_la_partie(False)
    if window._updates.version and not arret:
        QTimer.singleShot(0, window._propose_launcher_update)

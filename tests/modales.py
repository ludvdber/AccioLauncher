"""Agir sur une boîte modale ouverte par `exec()`, qui bloque le test tant qu'elle vit.

Trois fichiers de tests en avaient chacun leur copie, et chacune pouvait geler la
suite : si l'action échouait (un bouton absent, une assertion), la boîte restait
ouverte, `exec()` ne rendait jamais la main, et le test attendait pour toujours.
Ici, la boîte est REFUSÉE quoi qu'il arrive à l'action, et l'erreur remonte au
test par pytest-qt ; si aucune boîte ne s'ouvre en 5 s, on cesse de la chercher.
"""

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog

from src.ui.fenetre_message import FenetreMessage

_DELAI_S = 5.0


def quand_ouverte(action, genre: type[QDialog] = FenetreMessage) -> None:
    """Appelle `action(boite)` dès qu'une boîte modale de `genre` s'affiche."""
    fin = time.monotonic() + _DELAI_S

    def essayer() -> None:
        boite = QApplication.activeModalWidget()
        if not isinstance(boite, genre):
            if time.monotonic() < fin:
                QTimer.singleShot(10, essayer)
            return
        try:
            action(boite)
        finally:
            if boite.isVisible():
                boite.reject()

    QTimer.singleShot(0, essayer)

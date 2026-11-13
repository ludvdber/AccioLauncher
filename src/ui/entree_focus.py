"""Entrée active le bouton qui a le focus clavier, pas le bouton par défaut.

Les boutons du launcher coupent `autoDefault` (sinon Qt dessine un cadre de
défaut et Entrée, dans un champ, cliquerait n'importe quel bouton). Mais un
`QPushButton` sans `autoDefault` IGNORE Entrée : l'événement remonte au
`QDialog`, qui clique son bouton PAR DÉFAUT. Le joueur va sur « Annuler » au
Tab, l'anneau s'y pose, il appuie sur Entrée… et c'est « Écrire et lancer »
qui part (audit du 2026-11-13, constat reproduit par un vérificateur).

Ce filtre, posé sur la fenêtre, rend Entrée au bouton focalisé. Hors d'un
bouton (champ, liste), il laisse Qt faire : le bouton par défaut répond.
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QPushButton, QWidget

_TOUCHES = (Qt.Key.Key_Return, Qt.Key.Key_Enter)


class EntreeSuitLeFocus(QObject):
    """Filtre d'événements : Entrée sur une fenêtre = clic du bouton focalisé."""

    def eventFilter(self, objet: QObject | None, event: QEvent | None) -> bool:  # noqa: N802 (Qt)
        if (event is None or event.type() != QEvent.Type.KeyPress
                or not isinstance(event, QKeyEvent) or event.key() not in _TOUCHES
                or event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier):
            return False
        fenetre = objet if isinstance(objet, QWidget) else None
        focus = fenetre.focusWidget() if fenetre is not None else None
        if isinstance(focus, QPushButton) and focus.isEnabled() and focus.isVisible() \
                and focus.window() is fenetre:
            focus.click()
            return True
        return False


def entree_suit_le_focus(fenetre: QWidget) -> None:
    """Pose le filtre sur `fenetre` (il vit aussi longtemps qu'elle)."""
    fenetre.installEventFilter(EntreeSuitLeFocus(fenetre))

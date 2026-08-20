"""Anneau de focus réservé au CLAVIER.

Qt ne connaît pas `:focus-visible` : la règle `:focus` du stylesheet global
s'applique aussi bien à un focus donné par le clavier qu'à celui que Qt pose
tout seul sur le premier bouton de la chaîne à l'ouverture de la fenêtre, ou à
celui d'un simple clic. Résultat : le bouton « Réduire » s'ouvrait cerclé d'or
alors que personne n'avait rien fait, et un clic sur JOUER laissait l'anneau
derrière lui — dans les deux cas, l'œil est attiré pour rien.

Supprimer l'anneau n'est pas une option : c'est le seul repère d'un utilisateur
au clavier. On distingue donc les deux cas par la RAISON du focus, et le
stylesheet ne cercle que les widgets marqués. Un widget jamais marqué n'a pas
la propriété, donc le sélecteur ne l'atteint pas : le défaut est « pas
d'anneau », ce qu'on veut.

Le filtre est posé sur QApplication : il couvre aussi les dialogues et
l'assistant de premier lancement, qui vivent avant MainWindow.
"""

import logging

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication, QWidget

log = logging.getLogger(__name__)

PROPRIETE = "focusClavier"

# Tab / Maj+Tab / raccourci mnémonique. Tout le reste (ouverture de la fenêtre,
# clic, popup, retour depuis une autre application) n'est PAS une intention de
# navigation au clavier.
_RAISONS_CLAVIER = frozenset({
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
    Qt.FocusReason.ShortcutFocusReason,
})


def _marque(widget: QWidget, actif: bool) -> None:
    """Pose la propriété et redemande le style — seulement si ça change."""
    if widget.property(PROPRIETE) == actif:
        return
    widget.setProperty(PROPRIETE, actif)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class _FiltreFocus(QObject):
    def eventFilter(self, obj, event) -> bool:
        type_ = event.type()
        if type_ == QEvent.Type.FocusIn and isinstance(obj, QWidget):
            _marque(obj, event.reason() in _RAISONS_CLAVIER)
        elif type_ == QEvent.Type.FocusOut and isinstance(obj, QWidget):
            _marque(obj, False)
        return False       # ne jamais consommer l'événement


_filtre: _FiltreFocus | None = None


def install(app: QApplication) -> None:
    """À appeler une fois, juste après la création de QApplication."""
    global _filtre
    if _filtre is not None:
        return
    _filtre = _FiltreFocus(app)
    app.installEventFilter(_filtre)
    log.debug("[A11Y] anneau de focus limité au clavier")

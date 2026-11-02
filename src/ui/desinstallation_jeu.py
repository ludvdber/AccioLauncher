"""Désinstaller un jeu sans figer la fenêtre.

Effacer un jeu de 1,6 Go (`shutil.rmtree`) figeait la fenêtre jusqu'au bout
(grand audit du 2026-11-02). Le dossier s'efface sur un fil à part
(`GameManager.effacer_dossier`, sans état) ; l'état se pose ensuite dans le fil
de l'interface (`finir_desinstallation`). Pendant ce temps la fiche est
désactivée : rien ne se lance ni ne s'installe dans un dossier à moitié effacé.
"""

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView


class _Relais(QObject):
    """Ramène la fin d'un travail de fil dans le fil de l'interface."""
    fini = pyqtSignal(object, object)        # fonction de fin, résultat

    def __init__(self) -> None:
        super().__init__()
        self.fini.connect(self._finir)

    def _finir(self, fin: Callable[[Any], None], resultat: object) -> None:
        fin(resultat)


_relais: _Relais | None = None


def _en_fond(travail: Callable[[], object], fin: Callable[[Any], None]) -> None:
    """`travail` sur un fil, puis `fin(résultat)` dans le fil de l'interface."""
    global _relais
    if _relais is None:
        _relais = _Relais()             # créé dans le fil de l'interface
    relais = _relais

    def lancer() -> None:
        relais.fini.emit(fin, travail())
    threading.Thread(target=lancer, name="desinstallation", daemon=True).start()


def desinstaller(view: GameDetailView) -> None:
    """Le « Désinstaller » confirmé de la fiche."""
    game = view.game
    if game is None:
        return
    dossier = view.manager.dossier_a_desinstaller(game.id)
    if dossier is None:
        _annoncer(view, game, False)
        return
    view.setEnabled(False)
    view.status_message.emit(tr("Désinstallation de {}…").format(game.name))
    _en_fond(lambda: GameManager.effacer_dossier(dossier), lambda efface: _finir(view, game, efface))


def _finir(view: GameDetailView, game: GameData, efface: bool) -> None:
    reussi = view.manager.finir_desinstallation(game.id, efface)
    try:
        view.setEnabled(True)
        _annoncer(view, game, reussi)
    except RuntimeError:                # la fenêtre a été fermée entre-temps
        pass


def _annoncer(view: GameDetailView, game: GameData, reussi: bool) -> None:
    # Le retour était ignoré : « désinstallé » s'affichait même sur un échec
    # (grand audit du 2026-11-02).
    view._refresh()
    view.state_changed.emit()
    view.status_message.emit(
        tr("{} désinstallé.").format(game.name) if reussi else
        tr("La désinstallation de {} n'a pas abouti : un de ses fichiers est encore utilisé. "
           "Fermez ce qui l'utilise, puis réessayez.").format(game.name))

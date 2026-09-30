"""Ce qu'affiche la barre du bas, et la progression sur l'icône de la barre des tâches.

Extrait de `main_window` (plafond de lignes, et un bloc qui ne touchait aucun
objet de la fenêtre). La barre suit DEUX sources, jamais en même temps : les
opérations de jeu (téléchargement → installation) et, sous Linux, la
préparation de Wine. Tant qu'une préparation l'occupe, les changements d'état
des opérations ne la reprennent pas (la fiche refuse d'ailleurs d'en lancer une).
"""

from PyQt6.QtCore import QObject

from src.core.game_manager import GameState
from src.core.win_taskbar import TaskbarProgress


class SuiviBarre(QObject):
    def __init__(self, barre, ops, wine, manager, identifiant_fenetre, parent=None) -> None:
        super().__init__(parent)
        self._barre = barre
        self._ops = ops
        self._manager = manager
        # `winId()` n'a de sens qu'une fois la fenêtre montrée : demandé au besoin.
        self._identifiant_fenetre = identifiant_fenetre
        self._taskbar: TaskbarProgress | None = None

        ops.download_progress.connect(barre.update_download_progress)
        ops.install_progress.connect(barre.update_install_progress)
        ops.part_info.connect(barre.update_part_info)
        ops.phase_changed.connect(barre.set_phase)
        ops.state_changed.connect(self.actualiser)
        barre.cancel_clicked.connect(ops.cancel_download)
        # Préparation de Wine (Linux) : même barre, son propre « Annuler ».
        wine.commencee.connect(barre.show_preparation)
        wine.progression.connect(barre.set_preparation)
        wine.terminee.connect(self._on_preparation_finie)
        barre.preparation_cancel_clicked.connect(wine.annuler)
        # Progression sur l'icône de la barre des tâches Windows
        ops.download_progress.connect(self._on_download_progress)
        ops.install_progress.connect(self._on_install_progress)

    def _taskbar_(self) -> TaskbarProgress:
        if self._taskbar is None:
            self._taskbar = TaskbarProgress(self._identifiant_fenetre())
        return self._taskbar

    def _on_download_progress(self, downloaded: int, total: int, _speed: float, _eta: float) -> None:
        self._taskbar_().set_progress(downloaded, max(total, 1))

    def _on_install_progress(self, pct: int) -> None:
        self._taskbar_().set_progress(pct, 100)

    def _on_preparation_finie(self, *_args) -> None:
        if self._barre.en_preparation:
            self._barre.hide_bar()
        self.actualiser()

    def actualiser(self) -> None:
        """Affiche/cache la barre selon l'état des opérations."""
        if self._barre.en_preparation:
            return   # la préparation de Wine occupe la barre jusqu'à sa fin
        ops = self._ops
        if ops.is_busy and ops.active_game is not None:
            game = ops.active_game
            state = self._manager.get_state(game.id)
            if state in (GameState.DOWNLOADING, GameState.INSTALLING):
                self._barre.show_for_game(game, state)
                return
        self._barre.hide_bar()
        self._taskbar_().clear()

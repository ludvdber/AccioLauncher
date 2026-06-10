"""Surveillance d'un processus de jeu lancé.

Gère deux modes :
1. Popen.poll() — tant que le process initial tourne.
2. tasklist par nom d'exe — si le jeu redémarre son propre process
   (ex: UE1 wizard → jeu — relance après chargement d'une save).

Émet `game_exited(game_name)` quand le jeu est vraiment fermé.
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger(__name__)

_POLL_MS = 2000
_GRACE_S = 10.0  # délai avant de chercher l'exe par nom (le temps que UE1 redémarre)


class ProcessMonitor(QObject):
    """Surveille la durée de vie du process d'un jeu lancé."""

    game_exited = pyqtSignal(str)  # game_name

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._game_name: str = ""
        self._exe_name: str = ""
        self._grace_until: float = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)

    @property
    def game_name(self) -> str:
        return self._game_name

    def start(self, process: subprocess.Popen, game_name: str) -> None:
        """Démarre la surveillance d'un nouveau process de jeu."""
        self._process = process
        self._game_name = game_name
        try:
            self._exe_name = Path(process.args[0]).name.lower()
        except (IndexError, TypeError):
            self._exe_name = ""
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._process = None
        self._game_name = ""
        self._exe_name = ""
        self._grace_until = 0.0

    @staticmethod
    def _is_exe_running(exe_name: str) -> bool:
        """Vérifie si un processus avec ce nom d'exe tourne (Windows uniquement)."""
        if not exe_name or sys.platform != "win32":
            return False
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return exe_name.lower() in result.stdout.lower()
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _poll(self) -> None:
        """Vérifie si le jeu tourne encore (toutes les 2s)."""
        if self._process is not None:
            ret = self._process.poll()
            if ret is None:
                return  # process initial vivant
            log.info("Process initial terminé (code %s), grâce de %ds…", ret, int(_GRACE_S))
            self._process = None
            self._grace_until = time.monotonic() + _GRACE_S
            return

        if self._exe_name and self._is_exe_running(self._exe_name):
            return  # le jeu tourne encore (process redémarré)

        if time.monotonic() < self._grace_until:
            return  # grâce post-exit pour laisser le jeu redémarrer

        # Vraiment fermé.
        name = self._game_name
        log.info("Jeu terminé : %s", name)
        self.stop()
        self.game_exited.emit(name)

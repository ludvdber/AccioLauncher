"""Surveillance d'un processus de jeu lancé.

Gère deux modes :
1. Popen.poll() — tant que le process initial tourne.
2. tasklist par nom d'exe — si le jeu redémarre son propre process
   (ex: UE1 wizard → jeu — relance après chargement d'une save).

Émet `game_exited(nom, code, durée)` quand le jeu est vraiment fermé, et
`battement()` régulièrement tant qu'il tourne (le launcher s'en sert pour
noter la partie en cours, cf. `src/core/stats.py`).

**La durée émise est celle qu'on a OBSERVÉE**, pas le temps écoulé jusqu'à la
détection : la fenêtre de grâce de 10 s était comptée comme du temps de jeu,
donc CHAQUE partie était surestimée de 10 à 12 s. Sur une session de quatre
minutes, c'est 5 %.
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
# Un battement par minute : assez fin pour qu'une partie interrompue ne perde
# qu'une minute, assez rare pour que le fichier de reprise ne soit pas réécrit
# en boucle. 30 sondages de 2 s.
_BATTEMENTS_TOUS_LES = 30


class ProcessMonitor(QObject):
    """Surveille la durée de vie du process d'un jeu lancé."""

    # (nom, code de sortie ou None, secondes réellement observées)
    game_exited = pyqtSignal(str, object, float)
    battement = pyqtSignal()       # le jeu tourne toujours

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._game_name: str = ""
        self._exe_name: str = ""
        self._grace_until: float = 0.0
        self._code: int | None = None
        self._debut: float = 0.0
        self._vu_vivant: float = 0.0   # dernier instant où le jeu tournait VRAIMENT
        self._sondages: int = 0
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
        self._code = None
        self._debut = self._vu_vivant = time.monotonic()
        self._sondages = 0
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._process = None
        self._game_name = ""
        self._exe_name = ""
        self._grace_until = 0.0
        self._sondages = 0

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

    def _vivant(self) -> None:
        """Le jeu tourne : on note l'instant, et on bat une fois par minute."""
        self._vu_vivant = time.monotonic()
        self._sondages += 1
        if self._sondages % _BATTEMENTS_TOUS_LES == 0:
            self.battement.emit()

    def _poll(self) -> None:
        """Vérifie si le jeu tourne encore (toutes les 2s)."""
        if self._process is not None:
            ret = self._process.poll()
            if ret is None:
                self._vivant()
                return  # process initial vivant
            log.info("Process initial terminé (code %s), grâce de %ds…", ret, int(_GRACE_S))
            # Le code de sortie était journalisé puis JETÉ. C'est pourtant la
            # seule trace d'un jeu qui refuse de démarrer — et ces huit jeux de
            # 2001-2011 sur Windows 11 échouent en silence, sortie 0 en une
            # demi-seconde, sans fenêtre ni entrée dans le journal Windows.
            self._code = ret
            self._process = None
            self._grace_until = time.monotonic() + _GRACE_S
            return

        if self._exe_name and self._is_exe_running(self._exe_name):
            self._vivant()
            return  # le jeu tourne encore (process redémarré)

        if time.monotonic() < self._grace_until:
            return  # grâce post-exit pour laisser le jeu redémarrer

        # Vraiment fermé. La durée s'arrête au dernier instant où on l'a vu
        # tourner, pas maintenant : la grâce n'est pas du temps de jeu.
        name, code = self._game_name, self._code
        duree = max(0.0, self._vu_vivant - self._debut)
        log.info("Jeu terminé : %s (code %s, %.0f s observées)", name, code, duree)
        self.stop()
        self.game_exited.emit(name, code, duree)

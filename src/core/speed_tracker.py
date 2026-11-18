"""Suivi de vitesse de téléchargement."""

import time
from collections import deque

SPEED_WINDOW = 5.0
UI_UPDATE_INTERVAL = 0.5


class SpeedTracker:
    """Calcule la vitesse moyenne glissante et le temps restant."""

    def __init__(self, window: float = SPEED_WINDOW) -> None:
        self._window = window
        self._samples: deque[tuple[float, int]] = deque()
        self._last_ui_update = 0.0

    def reset(self) -> None:
        self._samples.clear()
        self._last_ui_update = 0.0

    def update(self, downloaded: int) -> None:
        now = time.monotonic()
        self._samples.append((now, downloaded))
        cutoff = now - self._window
        # Jamais moins de deux échantillons : des mises à jour espacées de
        # plus que la fenêtre (connexion lente, gros paquets) affichaient une
        # vitesse nulle et aucun temps restant (audit du 2026-11-16).
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def should_update_ui(self) -> bool:
        now = time.monotonic()
        if now - self._last_ui_update >= UI_UPDATE_INTERVAL:
            self._last_ui_update = now
            return True
        return False

    @property
    def speed(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        oldest_t, oldest_b = self._samples[0]
        newest_t, newest_b = self._samples[-1]
        dt = newest_t - oldest_t
        if dt <= 0:
            return 0.0
        return (newest_b - oldest_b) / dt

    def eta(self, downloaded: int, total: int) -> float:
        s = self.speed
        if s <= 0 or total <= downloaded:
            return -1.0
        return (total - downloaded) / s

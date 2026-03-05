"""Utilitaires de téléchargement — formatage et suivi de vitesse."""

import time
from collections import deque

SPEED_WINDOW = 5.0
UI_UPDATE_INTERVAL = 0.5


def format_size(size_mb: int) -> str:
    if size_mb >= 1000:
        return f"{size_mb / 1000:.1f} Go"
    return f"{size_mb} Mo"


def format_bytes(b: int) -> str:
    mb = b / (1024 * 1024)
    if mb >= 1000:
        return f"{mb / 1000:.1f} Go"
    return f"{mb:.0f} Mo"


def format_speed(bytes_per_sec: float) -> str:
    mb = bytes_per_sec / (1024 * 1024)
    if mb >= 1.0:
        return f"{mb:.1f} Mo/s"
    kb = bytes_per_sec / 1024
    return f"{kb:.0f} Ko/s"


def format_eta(seconds: float) -> str:
    if seconds < 0 or seconds > 86400:
        return ""
    if seconds < 60:
        return f"~{int(seconds)}s restantes"
    minutes = seconds / 60
    if minutes < 60:
        return f"~{int(minutes)} min restantes"
    hours = minutes / 60
    return f"~{hours:.1f}h restantes"


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
        while self._samples and self._samples[0][0] < cutoff:
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

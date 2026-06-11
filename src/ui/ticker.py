"""Ticker partagé ~30 FPS pour toutes les animations décoratives.

Un seul QTimer pour les particules, les étoiles du carrousel et les GlowButtons,
au lieu d'un timer par widget. `pause()` / `resume()` globaux pilotés par
MainWindow (tray, perte de focus fenêtre).

Les abonnés se connectent/déconnectent du signal `tick` dans leurs
showEvent/hideEvent (ou pause/resume) et gardent leur check `isVisible()`.
"""

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

TICK_MS = 33  # ~30 FPS


class Ticker(QObject):
    """Horloge d'animation globale (singleton paresseux — créé après QApplication)."""

    tick = pyqtSignal()

    _instance: "Ticker | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.tick)
        self._timer.start()

    @classmethod
    def instance(cls) -> "Ticker":
        if cls._instance is None:
            cls._instance = Ticker()
        return cls._instance

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

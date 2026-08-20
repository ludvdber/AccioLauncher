"""Ticker partagé ~30 FPS pour toutes les animations décoratives.

Un seul QTimer pour les particules, les étoiles du carrousel et les GlowButtons,
au lieu d'un timer par widget. `pause()` / `resume()` globaux pilotés par
MainWindow (tray, perte de focus fenêtre).

Les abonnés se connectent/déconnectent du signal `tick` dans leurs
showEvent/hideEvent (ou pause/resume) et gardent leur check `isVisible()`.
"""

from PyQt6 import sip
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
        # `sip.isdeleted` : à l'extinction de l'application, Qt détruit l'objet
        # C++ mais l'enveloppe Python survit dans `_instance`. La rendre telle
        # quelle ferait lever RuntimeError au premier accès à `tick`.
        if cls._instance is None or sip.isdeleted(cls._instance):
            cls._instance = Ticker()
        return cls._instance

    @classmethod
    def detach(cls, slot) -> None:
        """Désabonne un slot sans jamais lever, même à l'extinction.

        À la fermeture, Qt détruit l'horloge AVANT que les widgets ne reçoivent
        leur `hideEvent` : le désabonnement tombait alors sur un objet C++
        disparu et remontait jusqu'au hook de crash, qui affichait un rapport à
        l'utilisateur au moment même où il fermait le launcher. Rien à réparer
        dans ce cas : l'horloge n'existe plus, donc l'abonnement non plus.
        """
        courant = cls._instance
        if courant is None or sip.isdeleted(courant):
            return
        try:
            courant.tick.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

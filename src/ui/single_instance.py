"""Instance unique du launcher via QLocalServer/QLocalSocket (cross-platform).

Premier lancement : ouvre un serveur local nommé. Lancement suivant : se
connecte au serveur existant, lui demande de remettre sa fenêtre au premier
plan, puis quitte immédiatement.
"""

import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

DEFAULT_KEY = "accio-launcher-single-instance"


class SingleInstance(QObject):
    """Verrou d'instance unique. Émet `activate_requested` quand un second
    lancement demande la mise au premier plan."""

    activate_requested = pyqtSignal()

    def __init__(self, key: str = DEFAULT_KEY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server: QLocalServer | None = None

    def try_acquire(self, timeout_ms: int = 500) -> bool:
        """True si nous sommes la première instance.

        Sinon, notifie l'instance existante (qui émettra `activate_requested`)
        et retourne False — l'appelant doit quitter.
        """
        sock = QLocalSocket()
        sock.connectToServer(self._key)
        if sock.waitForConnected(timeout_ms):
            sock.write(b"activate")
            sock.flush()
            sock.waitForBytesWritten(timeout_ms)
            sock.disconnectFromServer()
            log.info("Instance déjà ouverte — demande d'activation envoyée")
            return False

        # Pas d'instance vivante. Nettoyer un éventuel socket orphelin
        # (crash de la session précédente) avant d'écouter.
        QLocalServer.removeServer(self._key)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(self._key):
            # Improbable (course entre deux lancements simultanés) : on laisse
            # tourner sans verrou plutôt que d'empêcher l'utilisateur de jouer.
            log.warning("Impossible d'écouter sur %s : %s",
                        self._key, self._server.errorString())
        return True

    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
        log.info("Second lancement détecté — activation de la fenêtre")
        self.activate_requested.emit()

    def release(self) -> None:
        """Ferme le serveur (tests / arrêt propre)."""
        if self._server is not None:
            self._server.close()
            self._server = None

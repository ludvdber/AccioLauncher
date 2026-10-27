"""Instance unique du launcher via QLocalServer/QLocalSocket (cross-platform).

Premier lancement : ouvre un serveur local nommé. Lancement suivant : se
connecte au serveur existant, lui demande de remettre sa fenêtre au premier
plan, puis quitte immédiatement. Lancé par « Jouer à … » de l'icône Windows
(`liste_saut`), il demande en plus de lancer ce jeu (`jouer:<id>`).
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
    jouer_requested = pyqtSignal(str)

    def __init__(self, key: str = DEFAULT_KEY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server: QLocalServer | None = None

    def try_acquire(self, timeout_ms: int = 500, jouer: str | None = None) -> bool:
        """True si nous sommes la première instance.

        Sinon, notifie l'instance existante (qui émettra `activate_requested`)
        et retourne False — l'appelant doit quitter.
        """
        sock = QLocalSocket()
        sock.connectToServer(self._key)
        if sock.waitForConnected(timeout_ms):
            sock.write(f"jouer:{jouer}".encode("ascii") if jouer else b"activate")
            sock.flush()
            sock.waitForBytesWritten(timeout_ms)
            if jouer:
                # Sous Windows, ce qui reste dans le tube quand on raccroche se perd :
                # le jeu demandé attend que l'instance ouverte ait lu et raccroche
                # elle-même (une seconde au plus, puis tant pis : la fenêtre s'est montrée).
                sock.waitForDisconnected(1000)
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
        if conn is None:
            return
        conn.disconnected.connect(conn.deleteLater)
        log.info("Second lancement détecté — activation de la fenêtre")
        self.activate_requested.emit()
        # Un « jouer:<id> » suit la connexion : lu quand il arrive, sans attendre dans
        # ce slot ; déjà là, lu tout de suite (readyRead ne repartirait pas pour lui).
        conn.readyRead.connect(lambda: self._lire(conn))
        if conn.bytesAvailable():
            self._lire(conn)

    def _lire(self, conn: QLocalSocket) -> None:
        message = bytes(conn.readAll()).decode("ascii", errors="replace")
        if message.startswith("jouer:"):
            self.jouer_requested.emit(message[len("jouer:"):])
        conn.disconnectFromServer()   # le second lancement attend ce signe pour partir

    def release(self) -> None:
        """Ferme le serveur (tests / arrêt propre)."""
        if self._server is not None:
            self._server.close()
            self._server = None

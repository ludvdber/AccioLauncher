"""Instance unique du launcher via QLocalServer/QLocalSocket (cross-platform).

Premier lancement : ouvre un serveur local nommé. Lancement suivant : se
connecte au serveur existant, lui demande de remettre sa fenêtre au premier
plan, puis quitte immédiatement. Lancé par « Jouer à … » de l'icône Windows
(`liste_saut`), il demande en plus de lancer ce jeu (`jouer:<id>`).
"""

import getpass
import hashlib
import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from src.core.catalogue_blocs import _JETON_SUR

log = logging.getLogger(__name__)


def _cle_par_utilisateur() -> str:
    """Le nom du serveur, propre au compte : un nom fixe est COMMUN à tous les
    comptes d'un poste (sous Linux, un socket de `/tmp`). Le launcher d'un
    second compte s'y connectait, demandait l'activation… et quittait ; un
    autre compte pouvait aussi y envoyer « jouer:<id> » (audit du 2026-11-16)."""
    try:
        compte = getpass.getuser()
    except (OSError, KeyError):
        compte = ""
    return "accio-launcher-" + hashlib.sha256(compte.encode("utf-8")).hexdigest()[:12]


DEFAULT_KEY = _cle_par_utilisateur()


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
            # « \n » termine le message : l'instance ouverte sait qu'il est entier.
            sock.write((f"jouer:{jouer}\n" if jouer else "activate\n").encode("ascii"))
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
        # Le seul compte qui l'a ouvert peut s'y connecter (droits du socket
        # sous Linux, du tube sous Windows).
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
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
        # Accumulé jusqu'au « \n » (ou au raccroché d'un lancement plus ancien,
        # qui n'en mettait pas) : un message arrivé en deux morceaux se perdait,
        # le premier coupant la connexion (audit du 2026-11-16).
        tampon = bytearray()
        conn.readyRead.connect(lambda: self._lire(conn, tampon))
        conn.disconnected.connect(lambda: self._lire(conn, tampon, fin=True))
        if conn.bytesAvailable():
            self._lire(conn, tampon)

    def _lire(self, conn: QLocalSocket, tampon: bytearray, fin: bool = False) -> None:
        tampon += bytes(conn.readAll())
        if b"\n" not in tampon and not fin:
            return
        message = bytes(tampon).split(b"\n", 1)[0].decode("ascii", errors="replace")
        tampon.clear()
        if message.startswith("jouer:"):
            jeu = message[len("jouer:"):]
            if _JETON_SUR.match(jeu):
                self.jouer_requested.emit(jeu)
        if not fin:
            conn.disconnectFromServer()   # le second lancement attend ce signe pour partir

    def release(self) -> None:
        """Ferme le serveur (tests / arrêt propre)."""
        if self._server is not None:
            self._server.close()
            self._server = None

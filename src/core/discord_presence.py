r"""Discord Rich Presence via l'IPC local de Discord — sans dépendance externe.

Affiche « Joue à <jeu> » sur le profil Discord de l'utilisateur, avec un bouton
« Découvrir Accio Launcher » pointant vers le site. Protocole : trames JSON
(handshake op 0, commandes op 1) sur le named pipe Windows
`\\.\pipe\discord-ipc-N` (ou socket Unix `$XDG_RUNTIME_DIR/discord-ipc-N`
sous Linux — déjà géré pour l'objectif Linux).

⚠️ IMPORTANT (à faire une fois par Ludo) :
  1. https://discord.com/developers/applications → « New Application » nommée
     « Accio Launcher » (le nom affiché dans « Joue à … » vient de là).
  2. Copier l'« Application ID » dans DISCORD_CLIENT_ID ci-dessous.
  3. Optionnel : onglet Rich Presence → Art Assets → uploader les covers avec
     comme clé l'id du jeu (hp1…hp7b) + un asset « logo » pour la grande image.
Sans ID, la fonctionnalité se désactive silencieusement.

NB : les boutons d'activité ne sont PAS visibles sur son propre profil —
seuls les AUTRES utilisateurs Discord les voient (comportement Discord normal).

Tout le réseau vit dans un thread démon : Discord absent/fermé = no-op.
"""

import json
import logging
import os
import queue
import struct
import sys
import threading
import time
import uuid

from src.core.i18n import tr

log = logging.getLogger(__name__)

DISCORD_CLIENT_ID = "1524077874087330007"  # TODO(Ludo) : coller l'Application ID Discord ici
WEBSITE_URL = "https://acciolauncher.be/"

_OP_HANDSHAKE = 0
_OP_FRAME = 1


def _open_ipc():
    """Ouvre la connexion IPC Discord (pipe Windows ou socket Unix). None si absent."""
    if sys.platform == "win32":
        for i in range(10):
            try:
                return open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
            except OSError:
                continue
        return None
    # Linux / macOS : socket Unix dans XDG_RUNTIME_DIR (fallback /tmp)
    import socket
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    for i in range(10):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect(f"{base}/discord-ipc-{i}")
            return sock.makefile("rwb", buffering=0)
        except OSError:
            continue
    return None


class DiscordPresence:
    """Client Rich Presence minimal. Toutes les méthodes sont non bloquantes."""

    def __init__(self, client_id: str = DISCORD_CLIENT_ID) -> None:
        self._client_id = client_id
        self._queue: queue.Queue[tuple[str, dict | None]] = queue.Queue()
        self._thread: threading.Thread | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id)

    # ── API publique (thread-safe, jamais bloquante) ──

    def set_playing(self, game_name: str) -> None:
        """Affiche « Joue à <game_name> » avec le bouton vers le site.

        L'activité est composée ICI, sur le thread appelant, et non dans le
        worker : c'est la seule chaîne du launcher que des TIERS voient — elle
        s'affiche sur le profil Discord de l'utilisateur, devant sa liste
        d'amis. Elle était codée en français en dur, donc un joueur anglophone
        ou hispanophone diffusait « Joue à … » à tout son entourage. Traduire
        au point d'appel garde aussi `tr()` hors du thread réseau.
        """
        self._post(("set", {
            "details": tr("Joue à {}").format(game_name),
            "timestamps": {"start": int(time.time())},
            "buttons": [
                {"label": tr("Découvrir Accio Launcher"), "url": WEBSITE_URL},
            ],
        }))

    def clear(self) -> None:
        """Efface l'activité (le jeu est fermé)."""
        self._post(("clear", None))

    def shutdown(self) -> None:
        """Ferme la connexion (à la fermeture du launcher)."""
        if self._thread is not None and self._thread.is_alive():
            self._queue.put(("quit", None))

    def _post(self, cmd: tuple[str, dict | None]) -> None:
        if not self.is_configured:
            return
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._worker, name="discord-rpc", daemon=True,
            )
            self._thread.start()
        self._queue.put(cmd)

    # ── Worker (possède la connexion, peut bloquer sans gêner l'UI) ──

    def _worker(self) -> None:
        ipc = None
        try:
            while True:
                cmd, arg = self._queue.get()
                if cmd == "quit":
                    break
                if ipc is None:
                    ipc = self._connect()
                    if ipc is None:
                        continue  # Discord pas lancé — on réessaiera au prochain ordre
                try:
                    if cmd == "set":
                        self._send_activity(ipc, arg)
                    elif cmd == "clear":
                        self._send_activity(ipc, None)
                except OSError as exc:
                    log.debug("Discord IPC perdu (%s) — reconnexion au prochain ordre", exc)
                    self._close(ipc)
                    ipc = None
        finally:
            self._close(ipc)

    def _connect(self):
        ipc = _open_ipc()
        if ipc is None:
            log.debug("Discord non détecté (pas de pipe IPC)")
            return None
        try:
            self._write(ipc, _OP_HANDSHAKE, {"v": 1, "client_id": self._client_id})
            op, payload = self._read(ipc)
            if op == _OP_FRAME and payload.get("evt") != "ERROR":
                log.info("Discord Rich Presence connecté")
                return ipc
            log.warning("Handshake Discord refusé : %s", payload)
        except OSError as exc:
            log.debug("Handshake Discord impossible : %s", exc)
        self._close(ipc)
        return None

    def _send_activity(self, ipc, activity: dict | None) -> None:
        """Envoie l'activité déjà composée (cf. set_playing), ou l'efface."""
        self._write(ipc, _OP_FRAME, {
            "cmd": "SET_ACTIVITY",
            "args": {"pid": os.getpid(), "activity": activity},
            "nonce": str(uuid.uuid4()),
        })
        # Réponse lue pour ne pas laisser le buffer du pipe se remplir.
        self._read(ipc)

    @staticmethod
    def _write(ipc, op: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        ipc.write(struct.pack("<II", op, len(data)) + data)

    @staticmethod
    def _read_exact(ipc, n: int) -> bytes:
        """Lit EXACTEMENT n octets. Un pipe/socket en buffering=0 peut servir le
        message en plusieurs morceaux (surtout le READY de Discord, ~100+ octets) ;
        `read(n)` renvoie alors moins que n — sans cette boucle, on prenait ça pour
        un pipe fermé et on reconnectait en boucle (bug d'intermittence prouvé)."""
        buf = bytearray()
        while len(buf) < n:
            chunk = ipc.read(n - len(buf))
            if not chunk:
                raise OSError("pipe Discord fermé")
            buf += chunk
        return bytes(buf)

    @classmethod
    def _read(cls, ipc) -> tuple[int, dict]:
        op, length = struct.unpack("<II", cls._read_exact(ipc, 8))
        raw = cls._read_exact(ipc, length) if length else b"{}"
        try:
            return op, json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return op, {}

    @staticmethod
    def _close(ipc) -> None:
        if ipc is not None:
            try:
                ipc.close()
            except OSError:
                pass

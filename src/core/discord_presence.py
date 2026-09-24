r"""Discord Rich Presence via l'IPC local de Discord — sans dépendance externe.

Affiche « Joue à <jeu> » sur le profil Discord de l'utilisateur, avec la
jaquette, une ligne « maison · année » et deux boutons : le site et le Discord
de la communauté. Protocole : trames JSON
(handshake op 0, commandes op 1) sur le named pipe Windows
`\\.\pipe\discord-ipc-N`, ou un socket Unix sous Linux — là où le client
Discord l'a posé, qui dépend de la façon dont il est installé (voir
`dossiers_ipc`, et Discord en Flatpak, fréquent sur Bazzite).

⚠️ IMPORTANT (à faire une fois par Ludo) :
  1. https://discord.com/developers/applications → « New Application » nommée
     « Accio Launcher » (le nom affiché dans « Joue à … » vient de là).
  2. Copier l'« Application ID » dans DISCORD_CLIENT_ID ci-dessous.
  3. Onglet Rich Presence → Art Assets : la jaquette de chaque jeu sous la clé
     de son id (hp1…hp7b), et le logo sous la clé « logo » (petite pastille).
     Une clé absente du portail ne casse rien : Discord n'affiche pas d'image.
Sans ID, la fonctionnalité se désactive silencieusement.

NB : les boutons d'activité ne sont PAS visibles sur son propre profil —
seuls les AUTRES utilisateurs Discord les voient (comportement Discord normal).

Tout le réseau vit dans un thread démon : Discord absent/fermé = no-op.
"""

import json
import logging
import os
import queue
import re
import struct
import sys
import threading
import time
import uuid

from src.core.i18n import tr
from src.core.liens import DISCORD_URL, SITE_URL

log = logging.getLogger(__name__)

DISCORD_CLIENT_ID = "1524077874087330007"

# Clé de la petite pastille (Art Assets du portail). Celle de la grande image est
# l'id du jeu : `_cle_asset` le filtre, parce qu'il vient du catalogue DISTANT.
_ASSET_LOGO = "logo"
_CLE_SURE = re.compile(r"[a-z0-9_]{1,32}")


def _cle_asset(game_id: str) -> str:
    """L'id du jeu comme clé d'image, ou "" s'il n'en a pas la forme."""
    cle = (game_id or "").lower()
    return cle if _CLE_SURE.fullmatch(cle) else ""

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
    # Linux / macOS : socket Unix, dans le dossier que le client a choisi.
    import socket
    for dossier in dossiers_ipc():
        for i in range(10):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.settimeout(2.0)
                sock.connect(f"{dossier}/discord-ipc-{i}")
                return sock.makefile("rwb", buffering=0)
            except OSError:
                sock.close()
    return None


def dossiers_ipc(env=None) -> list[str]:
    """Où chercher le socket de Discord sous Linux, dans l'ordre. Pure.

    Discord installé en paquet le pose dans `$XDG_RUNTIME_DIR`. Mais sur
    Bazzite, Discord s'installe le plus souvent en **Flatpak**, dont le bac à
    sable le range dans `$XDG_RUNTIME_DIR/app/com.discordapp.Discord/` — un
    launcher qui ne cherchait qu'à la racine n'y trouvait rien, et la présence
    restait éteinte sans un mot. Même chose pour Discord Canary, pour Vesktop
    (client alternatif courant en Flatpak) et pour le paquet Snap.

    `/tmp` en dernier : c'est le repli du client lui-même quand
    `XDG_RUNTIME_DIR` n'existe pas. On s'y CONNECTE seulement, sans rien y
    créer.
    """
    env = os.environ if env is None else env
    # `/tmp` (ici et plus bas) : le repli du client lui-même, où l'on se
    # connecte sans rien y créer.
    base = env.get("XDG_RUNTIME_DIR") or "/tmp"  # nosec B108
    dossiers = [
        base,
        f"{base}/app/com.discordapp.Discord",
        f"{base}/app/com.discordapp.DiscordCanary",
        f"{base}/.flatpak/dev.vencord.Vesktop/xdg-run",
        f"{base}/snap.discord",
    ]
    if base != "/tmp":  # nosec B108
        dossiers.append("/tmp")  # nosec B108
    return dossiers


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

    def set_playing(self, game_name: str, game_id: str = "", ligne: str = "") -> None:
        """Affiche « Joue à <game_name> » avec le bouton vers le site.

        L'activité est composée ICI, sur le thread appelant, et non dans le
        worker : c'est la seule chaîne du launcher que des TIERS voient — elle
        s'affiche sur le profil Discord de l'utilisateur, devant sa liste
        d'amis. Elle était codée en français en dur, donc un joueur anglophone
        ou hispanophone diffusait « Joue à … » à tout son entourage. Traduire
        au point d'appel garde aussi `tr()` hors du thread réseau.

        `ligne` est la seconde ligne de la carte (« Serdaigle · 6ᵉ année »),
        composée par l'appelant : la maison vit dans le thème, donc côté `ui`.
        Vide, elle est omise plutôt qu'envoyée blanche.
        """
        activite = {
            "details": tr("Joue à {}").format(game_name),
            "timestamps": {"start": int(time.time())},
            "assets": {"small_image": _ASSET_LOGO, "small_text": "Accio Launcher"},
            # Deux boutons, le maximum de Discord. Ils ne sont vus que des
            # AUTRES : c'est le seul endroit où les amis d'un joueur croisent
            # le projet, d'où le Discord de la communauté à côté du site.
            "buttons": [
                {"label": tr("Découvrir Accio Launcher"), "url": SITE_URL},
                {"label": tr("Rejoindre la communauté"), "url": DISCORD_URL},
            ],
        }
        if ligne:
            activite["state"] = ligne
        # La jaquette en grande image, le logo en pastille : sans image, la
        # carte d'activité n'était qu'une ligne de texte grise.
        cle = _cle_asset(game_id)
        if cle:
            activite["assets"].update(large_image=cle, large_text=game_name)
        self._post(("set", activite))

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

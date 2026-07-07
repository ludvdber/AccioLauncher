"""Tests du client Discord Rich Presence — protocole IPC rejoué en mémoire.

L'ouverture du vrai pipe est prouvée manuellement contre un Discord réel ; ici
on rejoue le flux (handshake READY → SET_ACTIVITY) avec un faux serveur pour
verrouiller le framing et le bug des lectures partielles.
"""

import json
import struct
import time

import pytest

from src.core.discord_presence import DiscordPresence


class _FakeDiscord:
    """File-like bidirectionnel jouant le serveur Discord IPC (synchrone)."""

    def __init__(self, partial_reads: bool = False):
        self._to_client = bytearray()
        self.received: list[tuple[int, dict]] = []
        self._partial = partial_reads

    def write(self, data: bytes) -> None:
        op, length = struct.unpack("<II", data[:8])
        payload = json.loads(data[8:8 + length].decode("utf-8"))
        self.received.append((op, payload))
        if op == 0:  # handshake -> READY
            self._enqueue(1, {"cmd": "DISPATCH", "evt": "READY", "data": {}})
        elif op == 1:  # SET_ACTIVITY -> accusé
            self._enqueue(1, {"cmd": "SET_ACTIVITY", "evt": None,
                              "nonce": payload.get("nonce")})

    def _enqueue(self, op: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self._to_client += struct.pack("<II", op, len(raw)) + raw

    def read(self, n: int) -> bytes:
        for _ in range(200):
            if self._to_client:
                break
            time.sleep(0.002)
        if self._partial:
            n = 1  # sert 1 octet à la fois — piège du read tronqué
        chunk = bytes(self._to_client[:n])
        del self._to_client[:n]
        return chunk

    def close(self) -> None:
        pass


def _run_flow(monkeypatch, partial: bool) -> _FakeDiscord:
    fake = _FakeDiscord(partial_reads=partial)
    monkeypatch.setattr("src.core.discord_presence._open_ipc", lambda: fake)
    p = DiscordPresence(client_id="123456789012345678")
    p.set_playing("Harry Potter à l'école des sorciers")
    time.sleep(0.3)
    p.clear()
    time.sleep(0.2)
    p.shutdown()
    if p._thread:
        p._thread.join(timeout=2)
    return fake


class TestFlow:
    def test_full_flow_contiguous_reads(self, monkeypatch):
        fake = _run_flow(monkeypatch, partial=False)
        ops = [op for op, _ in fake.received]
        assert ops == [0, 1, 1]  # handshake, set_activity, clear
        activity = fake.received[1][1]["args"]["activity"]
        assert activity["details"].startswith("Joue à")
        assert activity["buttons"][0]["url"].startswith("https://")
        assert fake.received[2][1]["args"]["activity"] is None  # clear

    def test_full_flow_survives_partial_reads(self, monkeypatch):
        """Régression : un pipe qui sert le message en morceaux ne doit PAS
        déclencher une reconnexion en boucle (bug des reads tronqués)."""
        fake = _run_flow(monkeypatch, partial=True)
        ops = [op for op, _ in fake.received]
        assert ops == [0, 1, 1]  # et pas [0, 0, 0, …]


class TestConfiguration:
    def test_no_client_id_is_noop(self, monkeypatch):
        """Sans Application ID, aucune connexion n'est tentée (cause n°1 du
        « Discord ne marche pas » : DISCORD_CLIENT_ID vide)."""
        called = False

        def _boom():
            nonlocal called
            called = True
            return None

        monkeypatch.setattr("src.core.discord_presence._open_ipc", _boom)
        p = DiscordPresence(client_id="")
        assert p.is_configured is False
        p.set_playing("HP1")
        time.sleep(0.15)
        assert called is False  # jamais tenté d'ouvrir le pipe


def test_read_exact_reassembles_fragments():
    """_read_exact recolle des fragments et lève sur pipe fermé."""
    class Frag:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        def read(self, n):
            return self._chunks.pop(0) if self._chunks else b""

    got = DiscordPresence._read_exact(Frag([b"ab", b"c", b"def"]), 6)
    assert got == b"abcdef"
    with pytest.raises(OSError):
        DiscordPresence._read_exact(Frag([b"ab"]), 6)  # fermé avant la fin

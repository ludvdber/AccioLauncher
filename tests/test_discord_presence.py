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


def _run_flow(monkeypatch, partial: bool, ligne: str = "") -> _FakeDiscord:
    fake = _FakeDiscord(partial_reads=partial)
    monkeypatch.setattr("src.core.discord_presence._open_ipc", lambda: fake)
    p = DiscordPresence(client_id="123456789012345678")
    p.set_playing("Harry Potter à l'école des sorciers", "hp1", ligne)
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

    def test_jaquette_en_grande_image_logo_en_pastille(self, monkeypatch):
        fake = _run_flow(monkeypatch, partial=False)
        assets = fake.received[1][1]["args"]["activity"]["assets"]
        assert assets["large_image"] == "hp1"
        assert assets["large_text"] == "Harry Potter à l'école des sorciers"
        assert assets["small_image"] == "logo"

    def test_full_flow_survives_partial_reads(self, monkeypatch):
        """Régression : un pipe qui sert le message en morceaux ne doit PAS
        déclencher une reconnexion en boucle (bug des reads tronqués)."""
        fake = _run_flow(monkeypatch, partial=True)
        ops = [op for op, _ in fake.received]
        assert ops == [0, 1, 1]  # et pas [0, 0, 0, …]


class TestCarte:
    def test_deux_boutons_le_site_puis_la_communaute(self, monkeypatch):
        from src.core.liens import DISCORD_URL, SITE_URL
        fake = _run_flow(monkeypatch, partial=False)
        boutons = fake.received[1][1]["args"]["activity"]["buttons"]
        assert [b["url"] for b in boutons] == [SITE_URL, DISCORD_URL]

    def test_la_ligne_maison_annee_devient_le_state(self, monkeypatch):
        fake = _run_flow(monkeypatch, partial=False, ligne="Serdaigle · 6ᵉ année")
        assert fake.received[1][1]["args"]["activity"]["state"] == "Serdaigle · 6ᵉ année"

    def test_sans_ligne_aucun_state_blanc(self, monkeypatch):
        fake = _run_flow(monkeypatch, partial=False)
        assert "state" not in fake.received[1][1]["args"]["activity"]

    def test_libelles_de_bouton_sous_32_caracteres_dans_chaque_langue(self):
        """Discord refuse toute l'activité au-delà de 32 caractères : un
        libellé traduit trop long effacerait la carte entière, en silence."""
        from src.core import i18n
        avant = i18n.get_language()
        try:
            for langue in i18n.available_languages():
                i18n.set_language(langue.code)
                for cle in ("Découvrir Accio Launcher", "Rejoindre la communauté"):
                    assert len(i18n.tr(cle)) <= 32, (langue.code, i18n.tr(cle))
        finally:
            i18n.set_language(avant)


class TestCleAsset:
    """L'id du jeu vient du catalogue DISTANT : il ne devient une clé d'image
    que s'il en a la forme."""

    def test_id_du_catalogue_accepte(self):
        from src.core.discord_presence import _cle_asset
        assert _cle_asset("hp7b") == "hp7b"
        assert _cle_asset("HP7A") == "hp7a"

    def test_forme_inattendue_refusee(self):
        from src.core.discord_presence import _cle_asset
        for mauvais in ("", "../x", "hp 1", "a" * 33, "https://evil"):
            assert _cle_asset(mauvais) == ""


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

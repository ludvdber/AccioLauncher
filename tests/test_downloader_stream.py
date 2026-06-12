"""Tests de _download_stream / _run_single avec un faux httpx injecté.

L'import de httpx étant paresseux (dans les méthodes), on peut injecter un faux
module dans sys.modules et exécuter le VRAI code de streaming sans réseau :
hash incrémental, reprise HTTP 206, détection de corruption.
"""

import hashlib
import sys
import types

import pytest

pytest.importorskip("pytestqt")

from src.core.downloader import Downloader  # noqa: E402

PAYLOAD = b"abracadabra-accio-" * 1000  # ~18 Ko
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


def _make_fake_httpx(full_payload: bytes, *, honor_range: bool = True):
    """Faux module httpx : Client → stream → réponse rejouant `full_payload`."""
    mod = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, response):
            super().__init__("status")
            self.response = response

    class Timeout:
        def __init__(self, **kw):
            pass

    class _Response:
        def __init__(self, headers_in: dict):
            range_header = (headers_in or {}).get("Range")
            if range_header and honor_range:
                offset = int(range_header.split("=")[1].rstrip("-"))
                self._body = full_payload[offset:]
                self.status_code = 206
            else:
                self._body = full_payload
                self.status_code = 200
            self.headers = {"content-length": str(len(self._body))}

        def raise_for_status(self):
            pass

        def iter_bytes(self, chunk_size):
            for i in range(0, len(self._body), chunk_size):
                yield self._body[i:i + chunk_size]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Client:
        def __init__(self, **kw):
            pass

        def stream(self, method, url, headers=None):
            return _Response(headers or {})

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mod.Client = Client
    mod.Timeout = Timeout
    mod.HTTPError = HTTPError
    mod.HTTPStatusError = HTTPStatusError
    return mod


@pytest.fixture
def fake_httpx(monkeypatch):
    def install(payload: bytes = PAYLOAD, **kw):
        mod = _make_fake_httpx(payload, **kw)
        monkeypatch.setitem(sys.modules, "httpx", mod)
        return mod
    return install


class TestStreamIncrementalHash:
    def test_fresh_download_digest(self, tmp_path, fake_httpx, qtbot):
        fake_httpx()
        dest = tmp_path / "a.7z"
        dl = Downloader(url="https://x.test/a.7z", destination=dest,
                        expected_sha256=PAYLOAD_SHA)
        with qtbot.waitSignal(dl.download_finished, timeout=5000):
            dl.run()  # exécution synchrone du vrai code du thread
        assert dest.read_bytes() == PAYLOAD

    def test_resume_206_hashes_prefix_plus_stream(self, tmp_path, fake_httpx, qtbot):
        """Un .part existant est repris via Range ; le hash couvre préfixe + suite."""
        fake_httpx()
        dest = tmp_path / "a.7z"
        part = tmp_path / "a.7z.part"
        part.write_bytes(PAYLOAD[:5000])  # téléchargement interrompu
        dl = Downloader(url="https://x.test/a.7z", destination=dest,
                        expected_sha256=PAYLOAD_SHA)
        with qtbot.waitSignal(dl.download_finished, timeout=5000):
            dl.run()
        assert dest.read_bytes() == PAYLOAD  # complété, pas re-téléchargé en entier

    def test_corruption_detected_and_error(self, tmp_path, fake_httpx, qtbot):
        """Serveur qui renvoie un contenu inattendu → erreur après les retries."""
        fake_httpx(b"contenu corrompu" * 100)  # ≠ PAYLOAD_SHA attendu
        dest = tmp_path / "a.7z"
        dl = Downloader(url="https://x.test/a.7z", destination=dest,
                        expected_sha256=PAYLOAD_SHA)
        # Accélérer les retries (pas de vrai réseau, inutile d'attendre le backoff)
        import src.core.downloader as dmod
        old_backoff = dmod.BACKOFF_BASE
        dmod.BACKOFF_BASE = 0
        try:
            with qtbot.waitSignal(dl.error, timeout=5000):
                dl.run()
        finally:
            dmod.BACKOFF_BASE = old_backoff
        assert not dest.exists()

    def test_server_ignoring_range_restarts_hash(self, tmp_path, fake_httpx, qtbot):
        """Serveur qui répond 200 malgré le Range → reprise à zéro, hash correct."""
        fake_httpx(honor_range=False)
        dest = tmp_path / "a.7z"
        (tmp_path / "a.7z.part").write_bytes(b"prefixe-obsolete")
        dl = Downloader(url="https://x.test/a.7z", destination=dest,
                        expected_sha256=PAYLOAD_SHA)
        with qtbot.waitSignal(dl.download_finished, timeout=5000):
            dl.run()
        assert dest.read_bytes() == PAYLOAD

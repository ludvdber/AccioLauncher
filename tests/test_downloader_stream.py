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


class _URL:
    """Mime httpx.URL : expose .scheme et str()."""
    def __init__(self, s: str):
        self._s = s
        self.scheme = s.split(":", 1)[0]

    def __str__(self):
        return self._s


def _make_fake_httpx(full_payload: bytes, *, honor_range: bool = True,
                     final_url: str = "https://x.test/a.7z",
                     range_416: bool = False, couper_a: int | None = None):
    """Faux module httpx : Client → stream → réponse rejouant `full_payload`."""
    mod = types.ModuleType("httpx")
    # Octets servis depuis la creation du faux module, toutes tentatives
    # confondues (cf. `iter_bytes`).
    etat = {"servi": 0}

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
            if range_header and range_416:
                # Serveur qui déclare la plage insatisfaisable : c'est ce que
                # renvoie GitHub quand le .part local est plus gros que l'asset.
                self._body = b""
                self.status_code = 416
            elif range_header and honor_range:
                offset = int(range_header.split("=")[1].rstrip("-"))
                self._body = full_payload[offset:]
                self.status_code = 206
            else:
                self._body = full_payload
                self.status_code = 200
            self.headers = {"content-length": str(len(self._body))}
            self.url = _URL(final_url)  # httpx : URL finale après redirections

        def raise_for_status(self):
            if self.status_code >= 400:
                raise HTTPStatusError(self)

        def iter_bytes(self, chunk_size):
            for i in range(0, len(self._body), chunk_size):
                bloc = self._body[i:i + chunk_size]
                if couper_a is not None:
                    # Le compteur est CUMULÉ sur toutes les tentatives : sinon
                    # chaque reprise repart avec son quota, la troisième passe
                    # et le téléchargement RÉUSSIT — le test attend alors une
                    # erreur qui ne vient jamais (constaté). Et la coupure doit
                    # pouvoir tomber au MILIEU d'un bloc : `_download_stream`
                    # lit par 64 Ko, plus que la charge de test entière.
                    restant = couper_a - etat["servi"]
                    if restant <= 0:
                        raise HTTPError("connexion interrompue")
                    if len(bloc) > restant:
                        etat["servi"] += restant
                        yield bloc[:restant]
                        raise HTTPError("connexion interrompue")
                etat["servi"] += len(bloc)
                yield bloc

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    requetes: list[dict] = []

    class Client:
        def __init__(self, **kw):
            pass

        def stream(self, method, url, headers=None):
            requetes.append(dict(headers or {}))
            return _Response(headers or {})

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mod.Client = Client
    mod.requetes = requetes  # en-têtes de chaque GET, dans l'ordre
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


class TestSecurityGuards:
    """Régressions d'audit : cap de taille et rétrogradation https→http."""

    def test_redirect_to_http_is_refused(self, tmp_path, fake_httpx, qtbot):
        """Une réponse dont l'URL finale est http:// doit échouer (pas de fichier)."""
        fake_httpx(final_url="http://evil.test/a.7z")
        dest = tmp_path / "a.7z"
        dl = Downloader(url="https://x.test/a.7z", destination=dest)
        import src.core.downloader as dmod
        old = dmod.BACKOFF_BASE
        dmod.BACKOFF_BASE = 0
        try:
            with qtbot.waitSignal(dl.error, timeout=5000):
                dl.run()
        finally:
            dmod.BACKOFF_BASE = old
        assert not dest.exists()

    def test_size_cap_enforced_on_stream(self, tmp_path, fake_httpx, qtbot):
        """Un corps plus gros que expected*1.5 est refusé, même sans Content-Length fiable."""
        fake_httpx(b"x" * (5 * 1024 * 1024))  # 5 Mo
        dest = tmp_path / "big.7z"
        dl = Downloader(url="https://x.test/big.7z", destination=dest, expected_size_mb=1)
        import src.core.downloader as dmod
        old = dmod.BACKOFF_BASE
        dmod.BACKOFF_BASE = 0
        try:
            with qtbot.waitSignal(dl.error, timeout=5000):
                dl.run()
        finally:
            dmod.BACKOFF_BASE = old
        assert not dest.exists()


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


class TestReprise416:
    """Le `.part` local est plus gros que l'asset — GitHub répond 416.

    Ce chemin n'avait AUCUN test alors qu'il portait sa PROPRE copie de la
    boucle de téléchargement : plafond d'octets, hachage et cadence d'émission
    y étaient réécrits, donc libres de diverger du chemin nominal sans que rien
    ne le signale. La boucle est désormais partagée (`_ecrire_chunks`) ; ces
    tests couvrent ce qui reste propre au 416 — jeter le `.part` et repartir
    sans en-tête Range.
    """

    def test_part_trop_gros_est_jete_et_retelecharge(self, tmp_path, fake_httpx, qtbot):
        fake_httpx(range_416=True)
        dest = tmp_path / "a.7z"
        # Plus gros que l'asset : exactement le cas qui provoque un 416.
        (tmp_path / "a.7z.part").write_bytes(b"z" * (len(PAYLOAD) + 4096))
        dl = Downloader(url="https://x.test/a.7z", destination=dest,
                        expected_sha256=PAYLOAD_SHA)
        with qtbot.waitSignal(dl.download_finished, timeout=5000):
            dl.run()
        assert dest.read_bytes() == PAYLOAD

    def test_le_plafond_vaut_aussi_apres_un_416(self, tmp_path, fake_httpx, qtbot):
        """Le retry n'est pas une porte dérobée pour un fichier surdimensionné.

        C'est la garde que la duplication mettait en danger : elle existait des
        deux côtés par recopie, pas par construction.
        """
        faux = fake_httpx(b"x" * (5 * 1024 * 1024), range_416=True)
        dest = tmp_path / "big.7z"
        (tmp_path / "big.7z.part").write_bytes(b"z" * (6 * 1024 * 1024))
        dl = Downloader(url="https://x.test/big.7z", destination=dest,
                        expected_size_mb=1)
        import src.core.downloader as dmod
        old = dmod.BACKOFF_BASE
        dmod.BACKOFF_BASE = 0
        try:
            with qtbot.waitSignal(dl.error, timeout=5000):
                dl.run()
        finally:
            dmod.BACKOFF_BASE = old
        assert not dest.exists()
        # Sans cette vérification le test passerait AUSSI avec le 416 non
        # traité — il échouerait alors sur l'erreur HTTP, sans jamais exercer
        # la reprise qu'il prétend couvrir. Une requête sans en-tête Range
        # derrière une requête qui en portait un : c'est la reprise, et rien
        # d'autre ne produit cette séquence.
        assert any("Range" in q for q in faux.requetes)
        assert any("Range" not in q for q in faux.requetes)


class TestUnEchecNEstPasUnePerte:
    """Le téléchargeur GARDE ce qu'il a reçu — et le disait à personne.

    Mesuré le 2026-08-29 : câble coupé à 60 % d'une archive, le `.part`
    conserve ses 2,4 Mo sur 4 et la requête suivante repart en `Range`. Le seul
    mot affiché était pourtant « Échec du téléchargement après plusieurs
    tentatives. » — que personne ne lit comme « tout est encore là ».

    Sur 4,6 Go, c'est quelqu'un qui vient d'attendre vingt minutes et qui
    renonce alors qu'il ne lui manque rien. C'est la marche la plus chère de
    l'entonnoir, celle où l'on ne perd pas un curieux mais quelqu'un qui avait
    déjà payé l'attente (cf. `GameManager.octets_deja_telecharges`).
    """

    def _echouer(self, tmp_path, fake_httpx, qtbot, *, couper_a):
        fake_httpx(couper_a=couper_a)
        dest = tmp_path / "a.7z"
        dl = Downloader(url="https://x.test/a.7z", destination=dest,
                        expected_size_mb=1)
        import src.core.downloader as dmod
        old = dmod.BACKOFF_BASE
        dmod.BACKOFF_BASE = 0          # pas 3 s d'attente dans la suite
        vus = []
        dl.error.connect(vus.append)
        try:
            with qtbot.waitSignal(dl.error, timeout=5000):
                dl.run()
        finally:
            dmod.BACKOFF_BASE = old
        return vus[0], dest

    def test_le_message_annonce_ce_qui_est_conserve(self, tmp_path,
                                                    fake_httpx, qtbot):
        msg, dest = self._echouer(tmp_path, fake_httpx, qtbot, couper_a=8000)
        part = dest.with_suffix(dest.suffix + ".part")
        assert part.exists() and part.stat().st_size > 0, (
            "rien n'a été conservé : le test ne prouve rien")
        assert "conservés" in msg, (
            f"le joueur croit avoir tout perdu — message : {msg!r}")

    def test_rien_n_est_ajoute_quand_il_n_y_a_rien_a_reprendre(
            self, tmp_path, fake_httpx, qtbot):
        """Un état ne s'affiche que lorsqu'il DÉVIE : promettre une reprise
        quand le disque est vide serait un second mensonge."""
        msg, dest = self._echouer(tmp_path, fake_httpx, qtbot, couper_a=0)
        part = dest.with_suffix(dest.suffix + ".part")
        assert not part.exists() or part.stat().st_size == 0
        assert "conservés" not in msg, f"reprise promise à vide : {msg!r}"

    def test_les_messages_d_echec_passent_par_tr(self):
        """Ils étaient des littéraux français : un anglophone les recevait en
        français, et `TestCouverture` ne pouvait pas le voir puisqu'elle ne
        balaie que les appels à `tr()`."""
        import ast
        import pathlib
        src = pathlib.Path("src/core/downloader.py").read_text(encoding="utf-8")
        arbre = ast.parse(src)
        traduits = {
            n.args[0].value
            for n in ast.walk(arbre)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr"
            and n.args and isinstance(n.args[0], ast.Constant)
        }
        assert any("Échec du téléchargement" in t for t in traduits), (
            "les messages d'échec ne passent plus par tr()")

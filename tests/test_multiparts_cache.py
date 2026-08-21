"""Cache des archives multi-volumes : nommage, provenance, nettoyage.

Trois défauts prouvés le 2026-08-21, tous nés du même geste — la part était
rangée sous le nom de son asset (« hp5.7z.001 »), qui ne porte pas la version :

1. les deux versions de HP5 publient des assets de MÊME NOM, donc une part de la
   v1.0 restée en cache était servie pour la v1.1, et l'ancien jeu s'installait
   sous le numéro du nouveau, en silence ;
2. `cancel_download` supprimait `hp5_v1.1.7z.part`, un fichier qui n'existe
   jamais dans le chemin multi-parts — annuler HP5 après la première part
   laissait 2 Go dans le cache (`hp5.7z.001` pèse 2 097 152 000 octets) ;
3. et rien ne pouvait plus distinguer un fichier hérité fiable d'un périmé.

Le faux httpx sert un corps DIFFÉRENT par URL, sans quoi on ne verrait pas la
différence entre l'ancienne et la nouvelle version — c'est tout l'enjeu.
"""

import hashlib
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from src.core.downloader import Downloader, _numero_volume  # noqa: E402

BASE = "https://exemple.test/releases/download"
V1 = [f"{BASE}/hp7a-v1.0/hp7a.7z.001", f"{BASE}/hp7a-v1.0/hp7a.7z.002"]
V2 = [f"{BASE}/hp7a-v1.1/hp7a.7z.001", f"{BASE}/hp7a-v1.1/hp7a.7z.002"]
CORPS_V1 = {V1[0]: b"ANCIENNE-001-" * 200, V1[1]: b"ANCIENNE-002-" * 200}
CORPS_V2 = {V2[0]: b"NOUVELLE-001-" * 200, V2[1]: b"NOUVELLE-002-" * 200}


class _URL:
    def __init__(self, s: str):
        self._s = s
        self.scheme = s.split(":", 1)[0]

    def __str__(self):
        return self._s


def _installer_httpx(monkeypatch, corps_par_url: dict):
    """Faux httpx rejouant un corps par URL — le vrai code de streaming tourne."""
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
        def __init__(self, url, headers_in):
            corps = corps_par_url[url]
            plage = (headers_in or {}).get("Range")
            if plage:
                debut = int(plage.split("=")[1].rstrip("-"))
                self._body, self.status_code = corps[debut:], 206
            else:
                self._body, self.status_code = corps, 200
            self.headers = {"content-length": str(len(self._body))}
            self.url = _URL(url)

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
            return _Response(url, headers or {})

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mod.Client, mod.Timeout = Client, Timeout
    mod.HTTPError, mod.HTTPStatusError = HTTPError, HTTPStatusError
    monkeypatch.setitem(sys.modules, "httpx", mod)


def _telecharger(cache, nom_archive, parts, **kw):
    """Lance un vrai Downloader et retourne le chemin livré."""
    recu = []
    dl = Downloader(url=None, destination=cache / nom_archive, parts=parts,
                    expected_size_mb=0, **kw)
    dl.download_finished.connect(recu.append)
    dl.run()
    return recu[0] if recu else None


class TestNumeroDeVolume:
    def test_le_numero_de_l_asset_est_conserve(self):
        assert _numero_volume("https://x.test/jeu.7z.002", 0) == ".002"

    def test_une_url_sans_numero_retombe_sur_le_rang(self):
        """Il faut bien produire quelque chose de séquentiel : 7z.exe l'exige."""
        assert _numero_volume("https://x.test/archive", 0) == ".001"
        assert _numero_volume("https://x.test/archive.zip", 1) == ".002"


class TestVersionPerimee:
    """Le cœur du défaut : demander la v1.1 doit livrer la v1.1."""

    def test_les_parts_portent_la_version_dans_leur_nom(self, tmp_path, qtbot, monkeypatch):
        _installer_httpx(monkeypatch, CORPS_V1)
        _telecharger(tmp_path, "hp7a_v1.0.7z", V1)
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "hp7a_v1.0.7z.001", "hp7a_v1.0.7z.002"]

    def test_la_version_precedente_n_est_jamais_servie(self, tmp_path, qtbot, monkeypatch):
        """Sans empreinte disponible — le cas où rien d'autre ne rattrape l'erreur."""
        _installer_httpx(monkeypatch, CORPS_V1)
        _telecharger(tmp_path, "hp7a_v1.0.7z", V1)

        _installer_httpx(monkeypatch, CORPS_V2)
        livre = _telecharger(tmp_path, "hp7a_v1.1.7z", V2)

        assert livre is not None
        contenu = Path(livre).read_bytes()
        assert contenu.startswith(b"NOUVELLE-001-"), (
            "la part de la version précédente a été servie pour la nouvelle")


class TestPartHeritee:
    """Un fichier resté sous l'ancien nom : adopté s'il est prouvé, sinon effacé."""

    def test_adoptee_quand_son_empreinte_le_prouve(self, tmp_path, qtbot, monkeypatch):
        """Épargne jusqu'à 2 Go de retéléchargement — mais seulement sur preuve."""
        heritee = tmp_path / "hp7a.7z.001"
        heritee.write_bytes(CORPS_V2[V2[0]])
        empreintes = [hashlib.sha256(CORPS_V2[u]).hexdigest() for u in V2]

        _installer_httpx(monkeypatch, CORPS_V2)
        _telecharger(tmp_path, "hp7a_v1.1.7z", V2, expected_sha256_parts=empreintes)

        assert not heritee.exists(), "le fichier hérité aurait dû être renommé"
        assert (tmp_path / "hp7a_v1.1.7z.001").read_bytes() == CORPS_V2[V2[0]]

    def test_effacee_quand_sa_provenance_est_inconnue(self, tmp_path, qtbot, monkeypatch):
        """La réutiliser serait rejouer le défaut ; la garder, encombrer le cache."""
        heritee = tmp_path / "hp7a.7z.001"
        heritee.write_bytes(CORPS_V1[V1[0]])

        _installer_httpx(monkeypatch, CORPS_V2)
        _telecharger(tmp_path, "hp7a_v1.1.7z", V2)

        assert not heritee.exists()
        assert (tmp_path / "hp7a_v1.1.7z.001").read_bytes() == CORPS_V2[V2[0]]


class TestNettoyageAnnulation:
    """Ce que `cancel_download` doit balayer — et ce qu'il ne doit pas toucher."""

    def test_les_volumes_et_leurs_part_partent(self, tmp_path):
        from src.ui.game_operations import _supprimer_residus

        dest = tmp_path / "hp5_v1.1.7z"
        for nom in ("hp5_v1.1.7z.001", "hp5_v1.1.7z.002", "hp5_v1.1.7z.002.part",
                    "hp5_v1.1.7z.part"):
            (tmp_path / nom).write_bytes(b"x" * 10)
        voisin = tmp_path / "hp1_v1.0.7z.001"
        voisin.write_bytes(b"y" * 10)

        assert _supprimer_residus(dest) == 4
        assert voisin.exists(), "un autre jeu ne doit jamais être emporté"

    def test_l_archive_complete_est_epargnee(self, tmp_path):
        """Elle n'existe qu'après un succès, et l'installateur a sa propre règle."""
        from src.ui.game_operations import _supprimer_residus

        dest = tmp_path / "hp1_v1.1.7z"
        dest.write_bytes(b"archive complete")
        (tmp_path / "hp1_v1.1.7z.part").write_bytes(b"x")

        _supprimer_residus(dest)
        assert dest.exists()
        assert not (tmp_path / "hp1_v1.1.7z.part").exists()

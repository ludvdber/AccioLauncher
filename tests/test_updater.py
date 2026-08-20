"""Tests pour src/core/updater.py — agrégation des compteurs (pur) + interruption."""

import sys
import types

from src.core.updater import (
    UpdateChecker,
    _releases_api_from_catalog_url,
    aggregate_download_counts,
    extract_asset_digests,
)

_U = "https://github.com/o/r/releases/download"


def _release(*assets: tuple[str, int]) -> dict:
    return {"assets": [
        {"browser_download_url": url, "download_count": count} for url, count in assets
    ]}


class TestAggregateDownloadCounts:
    def test_single_file_single_version(self):
        releases = [_release((f"{_U}/hp1-v1.1/hp1.7z", 120))]
        games = {"hp1": [[f"{_U}/hp1-v1.1/hp1.7z"]]}
        assert aggregate_download_counts(releases, games) == {"hp1": 120}

    def test_multipart_takes_max_not_sum(self):
        """3 parts téléchargées par les mêmes utilisateurs ≠ 3× plus de téléchargements."""
        releases = [_release(
            (f"{_U}/hp5-v1.0/hp5.7z.001", 80),
            (f"{_U}/hp5-v1.0/hp5.7z.002", 78),
            (f"{_U}/hp5-v1.0/hp5.7z.003", 75),
        )]
        games = {"hp5": [[
            f"{_U}/hp5-v1.0/hp5.7z.001",
            f"{_U}/hp5-v1.0/hp5.7z.002",
            f"{_U}/hp5-v1.0/hp5.7z.003",
        ]]}
        assert aggregate_download_counts(releases, games) == {"hp5": 80}

    def test_versions_are_summed(self):
        """Plusieurs versions d'un même jeu → cumul (demande explicite de Ludo)."""
        releases = [
            _release((f"{_U}/hp1-v1.0/hp1.7z", 200)),
            _release((f"{_U}/hp1-v1.1/hp1.7z", 50)),
        ]
        games = {"hp1": [
            [f"{_U}/hp1-v1.0/hp1.7z"],
            [f"{_U}/hp1-v1.1/hp1.7z"],
        ]}
        assert aggregate_download_counts(releases, games) == {"hp1": 250}

    def test_unknown_game_absent(self):
        releases = [_release((f"{_U}/hp1-v1.0/hp1.7z", 10))]
        games = {"hp2": [[f"{_U}/hp2-v1.0/hp2.7z"]]}
        assert aggregate_download_counts(releases, games) == {}

    def test_empty_inputs(self):
        assert aggregate_download_counts([], {}) == {}
        assert aggregate_download_counts([{"assets": []}], {"hp1": [[]]}) == {}


class TestReleasesApiFromCatalogUrl:
    def test_derived_from_raw_url(self):
        url = _releases_api_from_catalog_url(
            "https://raw.githubusercontent.com/ludvdber/accio-launcher-games/main/games.json")
        assert url == "https://api.github.com/repos/ludvdber/accio-launcher-games/releases?per_page=100"

    def test_fallback_on_garbage(self):
        assert "api.github.com/repos/" in _releases_api_from_catalog_url("n'importe quoi")


def _stub_checker(interrupt_after: str | None) -> tuple[UpdateChecker, list[str]]:
    """UpdateChecker dont les 3 étapes réseau sont remplacées par des marqueurs.

    `isInterruptionRequested` est surchargé côté instance : la vraie méthode Qt
    ne fait rien tant que le thread n'est pas démarré, or on veut exercer `run()`
    de façon synchrone et déterministe.
    """
    steps: list[str] = []
    checker = UpdateChecker(catalog_url="", current_catalog_version="0", installed_versions={})
    state = {"interrupted": False}

    def _step(name: str):
        def _run() -> None:
            steps.append(name)
            if name == interrupt_after:
                state["interrupted"] = True
        return _run

    checker._check_catalog = _step("catalog")
    checker._check_launcher = _step("launcher")
    checker._check_download_counts = _step("counts")
    checker.isInterruptionRequested = lambda: state["interrupted"]
    return checker, steps


class TestInterruption:
    """Régression : sans ces contrôles, requestInterruption() était sans effet et
    la fermeture de la fenêtre pouvait détruire un QThread encore en cours."""

    def test_sans_interruption_les_trois_etapes_tournent(self):
        checker, steps = _stub_checker(interrupt_after=None)
        checker.run()
        assert steps == ["catalog", "launcher", "counts"]

    def test_interruption_apres_catalogue_arrete_la_suite(self):
        checker, steps = _stub_checker(interrupt_after="catalog")
        checker.run()
        assert steps == ["catalog"]

    def test_interruption_apres_launcher_arrete_les_compteurs(self):
        checker, steps = _stub_checker(interrupt_after="launcher")
        checker.run()
        assert steps == ["catalog", "launcher"]


class TestExtractAssetDigests:
    """GitHub publie l'empreinte de chaque asset — on la récupère au lieu de la
    recopier à la main dans games.json (oubli = vérification dormante)."""

    HEX = "0b" * 32

    def test_extraction_simple(self):
        releases = [{"assets": [
            {"browser_download_url": "https://x/a.7z", "digest": f"sha256:{self.HEX}"},
        ]}]
        assert extract_asset_digests(releases) == {"https://x/a.7z": self.HEX}

    def test_plusieurs_releases_et_parts(self):
        releases = [
            {"assets": [{"browser_download_url": "https://x/a.001",
                         "digest": "sha256:" + "ab" * 32}]},
            {"assets": [{"browser_download_url": "https://x/a.002",
                         "digest": "sha256:" + "cd" * 32}]},
        ]
        result = extract_asset_digests(releases)
        assert result["https://x/a.001"] == "ab" * 32
        assert result["https://x/a.002"] == "cd" * 32

    def test_majuscules_normalisees(self):
        releases = [{"assets": [{"browser_download_url": "https://x/a.7z",
                                 "digest": "sha256:" + "AB" * 32}]}]
        assert extract_asset_digests(releases) == {"https://x/a.7z": "ab" * 32}

    def test_algorithme_inconnu_ignore(self):
        releases = [{"assets": [{"browser_download_url": "https://x/a.7z",
                                 "digest": "md5:" + "ab" * 8}]}]
        assert extract_asset_digests(releases) == {}

    def test_longueur_invalide_ignoree(self):
        releases = [{"assets": [{"browser_download_url": "https://x/a.7z",
                                 "digest": "sha256:abcd"}]}]
        assert extract_asset_digests(releases) == {}

    def test_non_hexadecimal_ignore(self):
        releases = [{"assets": [{"browser_download_url": "https://x/a.7z",
                                 "digest": "sha256:" + "zz" * 32}]}]
        assert extract_asset_digests(releases) == {}

    def test_asset_sans_digest(self):
        releases = [{"assets": [{"browser_download_url": "https://x/a.7z"}]}]
        assert extract_asset_digests(releases) == {}

    def test_payload_aberrant_ne_leve_pas(self):
        """Réponse d'API trafiquée / tronquée : jamais de TypeError au boot."""
        assert extract_asset_digests([]) == {}
        assert extract_asset_digests(["pas un dict"]) == {}
        assert extract_asset_digests([{"assets": None}]) == {}
        assert extract_asset_digests([{"assets": ["pas un dict"]}]) == {}
        assert extract_asset_digests([{"assets": [{"browser_download_url": "https://x/a",
                                                   "digest": 42}]}]) == {}


class TestLauncherDigest:
    """L'auto-update télécharge un .exe : il doit être vérifié.

    L'empreinte vient de l'API GitHub (même release), ce qui évite de la coder
    en dur à chaque version — sans elle, `apply_update_and_restart` remplaçait
    l'exécutable par un fichier jamais contrôlé.
    """

    HEX = "b7" * 32

    @staticmethod
    def _fake_httpx(payload: dict, monkeypatch):
        mod = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class Timeout:
            def __init__(self, *a, **kw):
                pass

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return payload

        class Client:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, **kw):
                return _Resp()

        mod.HTTPError = HTTPError
        mod.Timeout = Timeout
        mod.Client = Client
        monkeypatch.setitem(sys.modules, "httpx", mod)

    def _run(self, payload, monkeypatch):
        self._fake_httpx(payload, monkeypatch)
        checker = UpdateChecker.__new__(UpdateChecker)
        UpdateChecker.__init__(checker, "", "0.0.1", {})
        recu = []
        checker.launcher_update.connect(lambda *a: recu.append(a))
        checker._check_launcher()
        return recu

    def test_empreinte_transmise(self, monkeypatch):
        recu = self._run({
            "tag_name": "v9.9.9",
            "html_url": "https://github.com/ludvdber/AccioLauncher/releases/tag/v9.9.9",
            "assets": [{"name": "AccioLauncher.exe",
                        "browser_download_url": "https://github.com/x/AccioLauncher.exe",
                        "digest": f"sha256:{self.HEX}"}],
        }, monkeypatch)
        assert len(recu) == 1
        version, _url, asset, sha = recu[0]
        assert version == "9.9.9"
        assert asset == "https://github.com/x/AccioLauncher.exe"
        assert sha == self.HEX

    def test_sans_digest_reste_vide(self, monkeypatch):
        """Pas d'empreinte publiée → on ne bloque pas la mise à jour."""
        recu = self._run({
            "tag_name": "v9.9.9",
            "html_url": "https://github.com/ludvdber/AccioLauncher/releases/tag/v9.9.9",
            "assets": [{"name": "AccioLauncher.exe",
                        "browser_download_url": "https://github.com/x/AccioLauncher.exe"}],
        }, monkeypatch)
        assert recu and recu[0][3] == ""

    def test_pas_de_maj_pas_de_signal(self, monkeypatch):
        recu = self._run({"tag_name": "v0.0.0", "html_url": "https://github.com/x",
                          "assets": []}, monkeypatch)
        assert recu == []


class TestDiagnosticReseau:
    """`network_status` : False UNIQUEMENT si plus rien ne répond.

    Un faux « hors ligne » grise le bouton « Télécharger » d'un utilisateur
    parfaitement connecté — c'est le seul échec inacceptable de cette
    fonctionnalité, d'où les deux garde-fous testés ici.
    """

    @staticmethod
    def _fake_httpx(monkeypatch, *, leve=None, status=200):
        """Faux httpx : soit `Client.get` lève `leve`, soit il rend `status`."""
        mod = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class TransportError(HTTPError):   # hiérarchie réelle de httpx
            pass

        class ConnectError(TransportError):
            pass

        class Timeout:
            def __init__(self, *a, **kw):
                pass

        class _Resp:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise HTTPError("HTTP %d" % status)

            def json(self):
                return {}

        class Client:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url):
                if leve is not None:
                    raise getattr(mod, leve)("boom")
                return _Resp()

        mod.HTTPError = HTTPError
        mod.TransportError = TransportError
        mod.ConnectError = ConnectError
        mod.Timeout = Timeout
        mod.Client = Client
        monkeypatch.setitem(sys.modules, "httpx", mod)

    @staticmethod
    def _checker():
        return UpdateChecker(
            catalog_url="https://raw.githubusercontent.com/o/r/main/games.json",
            current_catalog_version="0",
            installed_versions={},
            games_asset_urls={"hp1": [["https://x/hp1.7z"]]},
        )

    def _run(self, monkeypatch, **kw):
        self._fake_httpx(monkeypatch, **kw)
        checker = self._checker()
        recu = []
        checker.network_status.connect(recu.append)
        checker.run()
        return checker, recu

    def test_optimiste_avant_toute_tentative(self):
        """Rien ne prouve encore quoi que ce soit : on ne grise pas l'UI."""
        assert self._checker().is_online is True

    def test_hors_ligne_si_tout_echoue_au_transport(self, monkeypatch):
        checker, recu = self._run(monkeypatch, leve="ConnectError")
        assert recu == [False]
        assert checker.is_online is False

    def test_une_reponse_suffit_a_prouver_la_connexion(self, monkeypatch):
        checker, recu = self._run(monkeypatch)
        assert recu == [True]
        assert checker.is_online is True

    def test_erreur_http_n_est_pas_une_panne_de_reseau(self, monkeypatch):
        """403 (rate limit GitHub) ou 404 : le serveur a RÉPONDU, donc en ligne."""
        checker, recu = self._run(monkeypatch, status=403)
        assert recu == [True]
        assert checker._contact is True

    def test_l_etat_est_remis_a_zero_a_chaque_run(self, monkeypatch):
        """Sinon un `_contact` hérité du run précédent masquerait une coupure."""
        checker, _ = self._run(monkeypatch)
        assert checker.is_online is True
        self._fake_httpx(monkeypatch, leve="ConnectError")
        recu = []
        checker.network_status.connect(recu.append)
        checker.run()
        assert recu == [False]

    def test_interruption_n_emet_pas_de_verdict(self, monkeypatch):
        """Une vérification écourtée n'a rien constaté : elle se tait."""
        self._fake_httpx(monkeypatch, leve="ConnectError")
        checker = self._checker()
        checker.isInterruptionRequested = lambda: True
        recu = []
        checker.network_status.connect(recu.append)
        checker.run()
        assert recu == []

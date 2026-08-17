"""Tests pour src/core/updater.py — agrégation des compteurs (pur) + interruption."""

from src.core.updater import (
    UpdateChecker,
    _releases_api_from_catalog_url,
    aggregate_download_counts,
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

"""Tests pour src/core/updater.py — agrégation des compteurs de téléchargement (pur)."""

from src.core.updater import _releases_api_from_catalog_url, aggregate_download_counts

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

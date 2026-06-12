"""Vérification des mises à jour du catalogue et du launcher en arrière-plan."""

import json
import logging
import re

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import APP_VERSION, LOCAL_CATALOG_PATH
from src.core.game_data import _parse_catalog
from src.core.version_utils import compare_versions

log = logging.getLogger(__name__)

# httpx est importé paresseusement dans les méthodes du thread (~70 ms d'import
# évités au démarrage — partagé avec le Downloader, le premier des deux paie).
_TIMEOUT_KW = {"connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0}
_LAUNCHER_API = "https://api.github.com/repos/ludvdber/AccioLauncher/releases/latest"
_GAMES_RELEASES_API = "https://api.github.com/repos/ludvdber/accio-launcher-games/releases?per_page=100"
_LOCAL_CATALOG_PATH = LOCAL_CATALOG_PATH


def aggregate_download_counts(
    releases: list[dict], games_asset_urls: dict[str, list[list[str]]],
) -> dict[str, int]:
    """Compte les téléchargements GitHub par jeu, TOUTES versions confondues.

    `games_asset_urls` : game_id → liste de versions → liste d'URLs d'assets
    (download_url + download_parts). Une version multi-parts compte chaque part
    séparément côté GitHub : on prend le MAX des parts (≈ téléchargements
    complets de cette version), puis on SOMME les versions du jeu.
    """
    url_counts: dict[str, int] = {}
    for rel in releases:
        for asset in rel.get("assets", []):
            url = asset.get("browser_download_url", "")
            if url:
                url_counts[url] = int(asset.get("download_count", 0) or 0)

    totals: dict[str, int] = {}
    for game_id, versions in games_asset_urls.items():
        total = 0
        for urls in versions:
            counts = [url_counts.get(u, 0) for u in urls if u]
            if counts:
                total += max(counts)
        if total > 0:
            totals[game_id] = total
    return totals


def _releases_api_from_catalog_url(catalog_url: str) -> str:
    """Déduit l'API releases du repo des jeux depuis l'URL raw du catalogue."""
    m = re.search(r"raw\.githubusercontent\.com/([^/]+)/([^/]+)/", catalog_url or "")
    if m:
        return f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/releases?per_page=100"
    return _GAMES_RELEASES_API


class UpdateChecker(QThread):
    """Vérifie les mises à jour du catalogue et du launcher en arrière-plan."""

    catalog_updated = pyqtSignal(object)        # Catalog
    launcher_update = pyqtSignal(str, str, str) # (version, url_release, url_asset_exe ou "")
    update_counts = pyqtSignal(int)             # nombre de jeux avec mise à jour dispo
    download_counts = pyqtSignal(object)        # dict game_id → téléchargements GitHub cumulés

    def __init__(self, catalog_url: str, current_catalog_version: str,
                 installed_versions: dict[str, str],
                 games_asset_urls: dict[str, list[list[str]]] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._catalog_url = catalog_url
        self._current_version = current_catalog_version
        self._installed_versions = dict(installed_versions)  # snapshot thread-safe
        self._games_asset_urls = games_asset_urls or {}      # snapshot (compteur ⬇)

    def run(self) -> None:
        self._check_catalog()
        self._check_launcher()
        self._check_download_counts()

    def _check_download_counts(self) -> None:
        """Récupère les compteurs de téléchargement des releases du repo des jeux."""
        import httpx  # import différé (thread) — voir en-tête de module

        if not self._games_asset_urls:
            return
        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(**_TIMEOUT_KW)) as client:
                resp = client.get(_releases_api_from_catalog_url(self._catalog_url))
                if resp.status_code == 403:
                    log.warning("GitHub API rate limit atteint (compteurs ⬇)")
                    return
                resp.raise_for_status()
                releases = resp.json()
            if not isinstance(releases, list):
                return
            totals = aggregate_download_counts(releases, self._games_asset_urls)
            if totals:
                log.info("Compteurs de téléchargement : %s", totals)
                self.download_counts.emit(totals)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            log.warning("Impossible de récupérer les compteurs de téléchargement : %s", exc)

    def _check_catalog(self) -> None:
        """Télécharge et valide le catalogue distant."""
        import httpx  # import différé (thread) — voir en-tête de module

        if not self._catalog_url or not self._catalog_url.startswith("https://"):
            return
        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(**_TIMEOUT_KW)) as client:
                resp = client.get(self._catalog_url)
                resp.raise_for_status()
                raw = resp.json()

            catalog = _parse_catalog(raw)
            if not catalog.games:
                log.warning("Catalogue distant vide, ignoré")
                return

            if compare_versions(catalog.catalog_version, self._current_version) > 0:
                # Sauvegarder localement
                try:
                    _LOCAL_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                    _LOCAL_CATALOG_PATH.write_text(
                        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                except OSError as exc:
                    log.warning("Impossible de sauvegarder le catalogue local : %s", exc)

                log.info("Catalogue mis à jour : v%s → v%s",
                         self._current_version, catalog.catalog_version)
                self.catalog_updated.emit(catalog)

                # Compter les mises à jour disponibles
                count = 0
                for game in catalog.games:
                    installed = self._installed_versions.get(game.id)
                    if installed and installed != game.recommended_version:
                        count += 1
                if count > 0:
                    self.update_counts.emit(count)
            else:
                log.info("Catalogue à jour (v%s)", self._current_version)

        except (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError) as exc:
            log.warning("Impossible de vérifier le catalogue distant : %s", exc)

    def _check_launcher(self) -> None:
        """Vérifie si une nouvelle version du launcher est disponible."""
        import httpx  # import différé (thread) — voir en-tête de module

        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(**_TIMEOUT_KW)) as client:
                resp = client.get(_LAUNCHER_API)
                if resp.status_code == 403:
                    log.warning("GitHub API rate limit atteint")
                    return
                resp.raise_for_status()
                data = resp.json()

            tag = data.get("tag_name", "")
            if not tag:
                return

            if compare_versions(tag, APP_VERSION) > 0:
                html_url = data.get("html_url", "https://github.com/ludvdber/AccioLauncher/releases/latest")
                if not html_url.startswith("https://github.com/"):
                    log.warning("URL de release suspecte ignorée : %s", html_url)
                    html_url = "https://github.com/ludvdber/AccioLauncher/releases/latest"
                # Asset .exe pour l'auto-update (vide si introuvable → fallback page release)
                asset_url = ""
                for asset in data.get("assets", []):
                    url = asset.get("browser_download_url", "")
                    if asset.get("name", "").lower().endswith(".exe") and url.startswith("https://"):
                        asset_url = url
                        break
                log.info("Nouvelle version du launcher disponible : %s (actuelle: %s)", tag, APP_VERSION)
                self.launcher_update.emit(tag.lstrip("v"), html_url, asset_url)
            else:
                log.info("Launcher à jour (v%s)", APP_VERSION)

        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            log.warning("Impossible de vérifier la version du launcher : %s", exc)

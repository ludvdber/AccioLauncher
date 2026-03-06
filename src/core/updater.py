"""Vérification des mises à jour du catalogue et du launcher en arrière-plan."""

import json
import logging
from pathlib import Path

import httpx
from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import APP_VERSION, LOCAL_CATALOG_PATH
from src.core.game_data import Catalog, _parse_catalog
from src.core.version_utils import compare_versions

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)
_LAUNCHER_API = "https://api.github.com/repos/ludvdber/AccioLauncher/releases/latest"
_LOCAL_CATALOG_PATH = LOCAL_CATALOG_PATH


class UpdateChecker(QThread):
    """Vérifie les mises à jour du catalogue et du launcher en arrière-plan."""

    catalog_updated = pyqtSignal(object)   # Catalog
    launcher_update = pyqtSignal(str, str) # (version, url_release)
    update_counts = pyqtSignal(int)        # nombre de jeux avec mise à jour dispo

    def __init__(self, catalog_url: str, current_catalog_version: str,
                 installed_versions: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._catalog_url = catalog_url
        self._current_version = current_catalog_version
        self._installed_versions = dict(installed_versions)  # snapshot thread-safe

    def run(self) -> None:
        self._check_catalog()
        self._check_launcher()

    def _check_catalog(self) -> None:
        """Télécharge et valide le catalogue distant."""
        if not self._catalog_url:
            return
        try:
            with httpx.Client(follow_redirects=True, timeout=_TIMEOUT) as client:
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
        try:
            with httpx.Client(follow_redirects=True, timeout=_TIMEOUT) as client:
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
                log.info("Nouvelle version du launcher disponible : %s (actuelle: %s)", tag, APP_VERSION)
                self.launcher_update.emit(tag.lstrip("v"), html_url)
            else:
                log.info("Launcher à jour (v%s)", APP_VERSION)

        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            log.warning("Impossible de vérifier la version du launcher : %s", exc)

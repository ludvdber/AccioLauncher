import logging
import time
from pathlib import Path

import httpx
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1  # secondes
CHUNK_SIZE = 256 * 1024  # 256 Ko


class Downloader(QThread):
    """Télécharge une archive en arrière-plan via QThread."""

    progress = pyqtSignal(int, int)   # (octets_téléchargés, octets_total)
    finished = pyqtSignal(str)        # chemin du fichier téléchargé
    error = pyqtSignal(str)           # message d'erreur

    def __init__(self, url: str, destination: Path, parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.destination = destination
        self._cancelled = False

    def cancel(self) -> None:
        """Stoppe proprement le téléchargement."""
        self._cancelled = True
        log.info("Annulation du téléchargement demandée")

    def run(self) -> None:
        """Boucle principale du thread — télécharge avec retry + reprise."""
        part_path = self.destination.with_suffix(self.destination.suffix + ".part")
        part_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, MAX_RETRIES + 1):
            if self._cancelled:
                return

            try:
                self._download_stream(part_path)
                if self._cancelled:
                    return
                # Téléchargement complet → renommer .part → fichier final
                part_path.replace(self.destination)
                log.info("Téléchargement terminé : %s", self.destination)
                self.finished.emit(str(self.destination))
                return

            except (httpx.HTTPError, OSError) as exc:
                log.warning(
                    "Tentative %d/%d échouée : %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE * (2 ** (attempt - 1))
                    log.info("Nouvelle tentative dans %ds…", wait)
                    time.sleep(wait)

        self.error.emit("Échec du téléchargement après plusieurs tentatives.")

    def _download_stream(self, part_path: Path) -> None:
        """Télécharge en streaming avec reprise via HTTP Range."""
        downloaded = part_path.stat().st_size if part_path.exists() else 0
        headers: dict[str, str] = {}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            log.info("Reprise du téléchargement à %d octets", downloaded)

        with httpx.Client(follow_redirects=True, timeout=30) as client:
            with client.stream("GET", self.url, headers=headers) as response:
                response.raise_for_status()

                # Taille totale (gère 200 et 206 Partial Content)
                content_length = int(response.headers.get("content-length", 0))
                if response.status_code == 206:
                    total = downloaded + content_length
                else:
                    total = content_length
                    # Le serveur ne supporte pas Range → repartir de zéro
                    downloaded = 0

                mode = "ab" if response.status_code == 206 else "wb"
                with open(part_path, mode) as f:
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        if self._cancelled:
                            return
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)

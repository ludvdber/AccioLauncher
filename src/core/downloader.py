import logging
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1  # secondes
CHUNK_SIZE = 256 * 1024  # 256 Ko

_ALLOWED_SCHEMES = {"https"}
_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=10.0)


def _validate_url(url: str) -> None:
    """Vérifie que l'URL utilise un protocole autorisé."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Protocole non autorisé : {parsed.scheme!r} (attendu https)")
    if not parsed.hostname:
        raise ValueError(f"URL invalide (pas de hostname) : {url!r}")


class Downloader(QThread):
    """Télécharge une archive (simple ou multi-parts) en arrière-plan."""

    progress = pyqtSignal(int, int)   # (octets_téléchargés, octets_total)
    finished = pyqtSignal(str)        # chemin du fichier téléchargé
    error = pyqtSignal(str)           # message d'erreur
    part_info = pyqtSignal(int, int)  # (part_courante, total_parts) — multi-parts uniquement

    def __init__(
        self,
        url: str | None,
        destination: Path,
        parts: list[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.destination = destination
        self.parts = parts
        self._cancel_event = threading.Event()
        self._last_emit = 0.0

    @property
    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()
        log.info("Annulation du téléchargement demandée")

    def run(self) -> None:
        try:
            if self.parts:
                self._run_multipart()
            elif self.url:
                self._run_single()
            else:
                self.error.emit("Aucune URL de téléchargement.")
        except Exception as exc:
            log.exception("Erreur inattendue dans le downloader")
            self.error.emit(f"Erreur : {exc}")

    # ─── Téléchargement simple (fichier unique) ───

    def _run_single(self) -> None:
        try:
            _validate_url(self.url)
        except ValueError as exc:
            self.error.emit(str(exc))
            return

        part_path = self.destination.with_suffix(self.destination.suffix + ".part")
        part_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, MAX_RETRIES + 1):
            if self._cancelled:
                return
            try:
                self._download_stream(self.url, part_path, global_offset=0, global_total=0)
                if self._cancelled:
                    return
                part_path.replace(self.destination)
                log.info("Téléchargement terminé : %s", self.destination)
                self.finished.emit(str(self.destination))
                return
            except (httpx.HTTPError, OSError) as exc:
                log.warning("Tentative %d/%d échouée : %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(wait)

        self.error.emit("Échec du téléchargement après plusieurs tentatives.")

    # ─── Téléchargement multi-parts ───

    def _run_multipart(self) -> None:
        for url in self.parts:
            try:
                _validate_url(url)
            except ValueError as exc:
                self.error.emit(str(exc))
                return

        total_parts = len(self.parts)
        part_paths: list[Path] = []
        cache_dir = self.destination.parent
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Étape 1 : télécharger chaque part
        for i, url in enumerate(self.parts):
            if self._cancelled:
                return

            part_name = url.rsplit("/", 1)[-1]
            part_dest = cache_dir / part_name
            part_paths.append(part_dest)
            part_tmp = part_dest.with_suffix(part_dest.suffix + ".part")

            self.part_info.emit(i + 1, total_parts)

            for attempt in range(1, MAX_RETRIES + 1):
                if self._cancelled:
                    return
                # Si la part est déjà téléchargée complètement, skip
                if part_dest.exists():
                    log.info("Part déjà présente : %s", part_dest)
                    break
                try:
                    self._download_stream(
                        url, part_tmp,
                        global_offset=i, global_total=total_parts,
                    )
                    if self._cancelled:
                        return
                    part_tmp.replace(part_dest)
                    log.info("Part %d/%d terminée : %s", i + 1, total_parts, part_dest)
                    break
                except (httpx.HTTPError, OSError) as exc:
                    log.warning("Part %d tentative %d/%d échouée : %s", i + 1, attempt, MAX_RETRIES, exc)
                    if attempt < MAX_RETRIES:
                        wait = BACKOFF_BASE * (2 ** (attempt - 1))
                        time.sleep(wait)
            else:
                # Nettoyer le fichier .part temporaire de la part échouée
                part_tmp.unlink(missing_ok=True)
                self.error.emit(f"Échec du téléchargement de la partie {i + 1}/{total_parts}.")
                return

        if self._cancelled:
            return

        # Étape 2 : tester si py7zr peut lire directement le .001
        first_part = part_paths[0]
        if first_part.suffix == ".001":
            try:
                import py7zr
                with py7zr.SevenZipFile(first_part, mode="r") as _:
                    pass
                log.info("py7zr supporte les archives split — pas de concaténation nécessaire")
                self.finished.emit(str(first_part))
                return
            except Exception:
                log.info("py7zr ne supporte pas le split — concaténation des parts")

        # Étape 3 : concaténer les parts
        log.info("Concaténation de %d parts vers %s", len(part_paths), self.destination)
        try:
            with open(self.destination, "wb") as out:
                for pp in part_paths:
                    with open(pp, "rb") as inp:
                        shutil.copyfileobj(inp, out)
            # Supprimer les parts individuelles
            for pp in part_paths:
                pp.unlink(missing_ok=True)
        except OSError as exc:
            self.error.emit(f"Erreur lors de la concaténation : {exc}")
            return

        log.info("Téléchargement multi-parts terminé : %s", self.destination)
        self.finished.emit(str(self.destination))

    # ─── Streaming avec reprise ───

    def _download_stream(
        self, url: str, part_path: Path,
        global_offset: int = 0, global_total: int = 0,
    ) -> None:
        """Télécharge en streaming avec reprise via HTTP Range."""
        downloaded = part_path.stat().st_size if part_path.exists() else 0
        headers: dict[str, str] = {}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            log.info("Reprise du téléchargement à %d octets", downloaded)

        needs_retry = False
        with httpx.Client(follow_redirects=True, timeout=_TIMEOUT) as client:
            with client.stream("GET", url, headers=headers) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 416 and downloaded > 0:
                        log.warning("HTTP 416 : fichier .part corrompu, suppression et reprise")
                        part_path.unlink(missing_ok=True)
                        needs_retry = True
                    else:
                        raise

                if not needs_retry:
                    raw_length = response.headers.get("content-length", "")
                    try:
                        content_length = int(raw_length)
                    except (ValueError, TypeError):
                        content_length = 0

                    if response.status_code == 206:
                        total = downloaded + content_length
                    else:
                        total = content_length
                        downloaded = 0

                    mode = "ab" if response.status_code == 206 else "wb"
                    with open(part_path, mode) as f:
                        for chunk in response.iter_bytes(CHUNK_SIZE):
                            if self._cancelled:
                                return
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.monotonic()
                            if now - self._last_emit >= 0.1:
                                self.progress.emit(downloaded, total)
                                self._last_emit = now
                    self.progress.emit(downloaded, total)  # final
                    return  # succès

        if not needs_retry:
            return

        # Retry une seule fois après HTTP 416 (sans Range)
        with httpx.Client(follow_redirects=True, timeout=_TIMEOUT) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                raw_length = response.headers.get("content-length", "")
                try:
                    total = int(raw_length)
                except (ValueError, TypeError):
                    total = 0
                with open(part_path, "wb") as f:
                    downloaded = 0
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        if self._cancelled:
                            return
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if now - self._last_emit >= 0.1:
                            self.progress.emit(downloaded, total)
                            self._last_emit = now
                self.progress.emit(downloaded, total)  # final

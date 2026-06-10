"""Orchestrateur QThread d'installation : extraction → post-install → cleanup."""

import gc
import logging
import shutil
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.extractors import extract_7z, extract_zip
from src.core.post_install import apply_config_files, apply_registry, unblock_extracted

log = logging.getLogger(__name__)


class Installer(QThread):
    """Extrait une archive et installe un jeu en arrière-plan."""

    progress = pyqtSignal(int)         # pourcentage 0-100
    # NB : pas `finished` — ça masquerait le signal natif QThread.finished.
    install_finished = pyqtSignal(str)  # chemin du dossier d'installation
    error = pyqtSignal(str)             # message d'erreur

    def __init__(
        self,
        archive_path: Path,
        destination: Path,
        registry_entries: list[str] | None = None,
        config_files: list[tuple[str, str]] | None = None,
        game_dir: str | None = None,
        delete_archive: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.archive_path = archive_path
        self.destination = destination
        self.registry_entries = registry_entries or []
        self.config_files = config_files or []
        self.game_dir = game_dir
        self.delete_archive = delete_archive
        self._cancel_event = threading.Event()
        self._extracted_dirs: list[Path] = []

    @property
    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        """Demande l'arrêt de l'extraction."""
        self._cancel_event.set()
        log.info("Annulation de l'installation demandée")

    def run(self) -> None:
        """Boucle principale : extraction → post-install → nettoyage."""
        log.debug("Installation démarrée : archive=%s, destination=%s",
                  self.archive_path, self.destination)
        try:
            self.destination.mkdir(parents=True, exist_ok=True)
            existing_dirs = set(p.name for p in self.destination.iterdir() if p.is_dir())

            suffix = self.archive_path.suffix.lower()
            if suffix == ".001":
                suffix = Path(self.archive_path.stem).suffix.lower()

            match suffix:
                case ".7z":
                    extract_7z(self.archive_path, self.destination,
                               self.progress.emit, lambda: self._cancelled)
                case ".zip":
                    extract_zip(self.archive_path, self.destination,
                                self.progress.emit, lambda: self._cancelled)
                case _:
                    self.error.emit(f"Format d'archive non supporté : {suffix}")
                    return

            new_dirs = set(p.name for p in self.destination.iterdir() if p.is_dir()) - existing_dirs
            self._extracted_dirs = [self.destination / d for d in new_dirs]
            log.debug("Nouveaux dossiers extraits : %s", [str(d) for d in self._extracted_dirs])

            if self._cancelled:
                self._cleanup()
                return

            count = unblock_extracted(self._extracted_dirs)
            if count > 0:
                log.info("%d fichier(s) débloqué(s) (Zone.Identifier supprimé)", count)
            apply_registry(self.registry_entries)
            apply_config_files(self.destination, self.game_dir, self.config_files)

            if self.delete_archive:
                self._delete_archive()

            log.info("Installation terminée : %s", self.destination)
            self.install_finished.emit(str(self.destination))

        except Exception as exc:
            log.exception("Erreur pendant l'installation")
            # NE PAS cleanup en cas d'erreur d'extraction — laisser les fichiers pour debug
            self.error.emit(f"Erreur d'installation : {exc}")

    def _delete_archive(self) -> None:
        """Supprime l'archive avec retry (py7zr peut garder un handle ouvert)."""
        for attempt in range(3):
            try:
                gc.collect()
                self.archive_path.unlink(missing_ok=True)
                log.info("Archive supprimée : %s", self.archive_path)
                return
            except PermissionError:
                if attempt < 2:
                    time.sleep(1)
        log.warning("Impossible de supprimer l'archive (fichier verrouillé) : %s", self.archive_path)

    def _cleanup(self) -> None:
        """Nettoie UNIQUEMENT les dossiers créés pendant l'extraction.

        PROTECTION : ne supprime JAMAIS self.destination (le dossier d'installation racine).
        """
        if not self._extracted_dirs:
            log.debug("Rien à nettoyer (aucun dossier extrait)")
            return
        for d in self._extracted_dirs:
            if not d.exists():
                continue
            if d.resolve() == self.destination.resolve():
                log.critical("REFUS de supprimer le dossier d'installation racine : %s", d)
                continue
            try:
                shutil.rmtree(d)
                log.info("Fichiers partiels nettoyés : %s", d)
            except OSError as exc:
                log.error("Échec du nettoyage de %s : %s", d, exc)

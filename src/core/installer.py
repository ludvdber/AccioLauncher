import logging
import shutil
import sys
import zipfile
from pathlib import Path

import py7zr
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


class Installer(QThread):
    """Extrait une archive et installe un jeu en arrière-plan."""

    progress = pyqtSignal(int)    # pourcentage 0-100
    finished = pyqtSignal(str)    # chemin du dossier d'installation
    error = pyqtSignal(str)       # message d'erreur

    def __init__(
        self,
        archive_path: Path,
        destination: Path,
        registry_entries: list[str] | None = None,
        delete_archive: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.archive_path = archive_path
        self.destination = destination
        self.registry_entries = registry_entries or []
        self.delete_archive = delete_archive
        self._cancelled = False

    def cancel(self) -> None:
        """Demande l'arrêt de l'extraction."""
        self._cancelled = True
        log.info("Annulation de l'installation demandée")

    def run(self) -> None:
        """Boucle principale : extraction → post-install → nettoyage."""
        try:
            self.destination.mkdir(parents=True, exist_ok=True)
            suffix = self.archive_path.suffix.lower()

            match suffix:
                case ".7z":
                    self._extract_7z()
                case ".zip":
                    self._extract_zip()
                case _:
                    self.error.emit(f"Format d'archive non supporté : {suffix}")
                    return

            if self._cancelled:
                self._cleanup()
                return

            self._apply_registry()

            if self.delete_archive:
                self.archive_path.unlink(missing_ok=True)
                log.info("Archive supprimée : %s", self.archive_path)

            log.info("Installation terminée : %s", self.destination)
            self.finished.emit(str(self.destination))

        except Exception as exc:
            log.exception("Erreur pendant l'installation")
            self._cleanup()
            self.error.emit(f"Erreur d'installation : {exc}")

    def _extract_7z(self) -> None:
        """Extrait une archive .7z avec progression."""
        with py7zr.SevenZipFile(self.archive_path, mode="r") as archive:
            all_files = archive.getnames()
            total = len(all_files)
            if total == 0:
                return

            # py7zr ne supporte pas l'extraction fichier par fichier facilement,
            # on extrait tout et on émet la progression par batch
            archive.extractall(path=self.destination)

            # Émettre la progression linéairement pendant la vérification
            for i, _ in enumerate(all_files, 1):
                if self._cancelled:
                    return
                self.progress.emit(i * 100 // total)

    def _extract_zip(self) -> None:
        """Extrait une archive .zip avec progression."""
        with zipfile.ZipFile(self.archive_path, "r") as zf:
            members = zf.infolist()
            total = len(members)
            if total == 0:
                return

            for i, member in enumerate(members, 1):
                if self._cancelled:
                    return
                zf.extract(member, self.destination)
                self.progress.emit(i * 100 // total)

    def _apply_registry(self) -> None:
        """Applique les entrées de registre post-installation (Windows uniquement)."""
        if not self.registry_entries or sys.platform != "win32":
            return

        import winreg

        for entry in self.registry_entries:
            try:
                # Format attendu : "HKLM\\Software\\Key=Value"
                key_path, _, value = entry.partition("=")
                hive_name, _, sub_key = key_path.partition("\\")
                hive = getattr(winreg, hive_name, None)
                if hive is None:
                    log.warning("Ruche de registre inconnue : %s", hive_name)
                    continue
                with winreg.CreateKey(hive, sub_key) as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)
                log.info("Registre mis à jour : %s", entry)
            except OSError:
                log.warning("Impossible d'écrire dans le registre : %s", entry)

    def _cleanup(self) -> None:
        """Nettoie les fichiers partiellement extraits."""
        if self.destination.exists():
            shutil.rmtree(self.destination, ignore_errors=True)
            log.info("Fichiers partiels nettoyés : %s", self.destination)

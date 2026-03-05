import logging
import shutil
import sys
import zipfile
from pathlib import Path

import py7zr
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

# Préfixes de registre autorisés (whitelist)
_ALLOWED_REGISTRY_PREFIXES = ("Software\\",)


def _check_path_traversal(destination: Path, member_name: str) -> bool:
    """Vérifie qu'un fichier extrait ne sort pas du dossier de destination (Zip Slip)."""
    target = (destination / member_name).resolve()
    return target.is_relative_to(destination.resolve())


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

    def _validate_7z_paths(self, file_list: list) -> None:
        """Vérifie que toutes les entrées d'une archive 7z sont sûres."""
        for f_info in file_list:
            name = f_info.filename
            if not _check_path_traversal(self.destination, name):
                raise ValueError(f"Path traversal détecté dans l'archive 7z : {name}")

    def _extract_7z(self) -> None:
        """Extrait une archive .7z avec progression réelle basée sur la taille."""
        with py7zr.SevenZipFile(self.archive_path, mode="r") as archive:
            all_files = archive.list()

            # Sécurité : vérifier tous les chemins AVANT extraction
            self._validate_7z_paths(all_files)

            total_size = sum(getattr(f, "uncompressed", 0) or 0 for f in all_files)

            if total_size == 0:
                archive.extractall(path=self.destination)
                self.progress.emit(100)
                return

            archive.extractall(path=self.destination)

            # Progression post-extraction
            extracted_size = 0
            for f_info in all_files:
                if self._cancelled:
                    return
                extracted_size += getattr(f_info, "uncompressed", 0) or 0
                pct = min(100, int(extracted_size * 100 / total_size))
                self.progress.emit(pct)

    def _extract_zip(self) -> None:
        """Extrait une archive .zip avec progression et protection Zip Slip."""
        with zipfile.ZipFile(self.archive_path, "r") as zf:
            members = zf.infolist()
            total = len(members)
            if total == 0:
                return

            for i, member in enumerate(members, 1):
                if self._cancelled:
                    return
                # Protection Zip Slip
                if not _check_path_traversal(self.destination, member.filename):
                    log.warning("Zip Slip détecté, entrée ignorée : %s", member.filename)
                    continue
                zf.extract(member, self.destination)
                self.progress.emit(i * 100 // total)

    def _apply_registry(self) -> None:
        """Applique les entrées de registre post-installation (Windows uniquement).

        Utilise HKCU (current user) au lieu de HKLM pour éviter les problèmes
        de droits administrateur. Seules les clés sous Software\\ sont autorisées.
        """
        if not self.registry_entries or sys.platform != "win32":
            return

        import winreg

        _HIVE_MAP = {
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
            "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        }

        for entry in self.registry_entries:
            try:
                key_path, sep, value = entry.partition("=")
                if not sep:
                    log.warning("Format de registre invalide (pas de '=') : %s", entry)
                    continue
                hive_name, _, sub_key = key_path.partition("\\")
                hive = _HIVE_MAP.get(hive_name.upper())
                if hive is None:
                    log.warning("Ruche de registre non supportée : %s", hive_name)
                    continue

                # Whitelist : seules les clés sous Software\ sont autorisées
                if not any(sub_key.startswith(prefix) for prefix in _ALLOWED_REGISTRY_PREFIXES):
                    log.warning("Clé de registre hors whitelist ignorée : %s", sub_key)
                    continue

                # Toujours utiliser HKCU (droits utilisateur)
                if hive == winreg.HKEY_LOCAL_MACHINE:
                    log.info("HKLM demandé, redirection vers HKCU : %s", entry)
                    hive = winreg.HKEY_CURRENT_USER

                with winreg.CreateKey(hive, sub_key) as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)
                log.info("Registre mis à jour : %s", entry)
            except PermissionError:
                log.warning("Permission refusée pour écrire dans le registre : %s", entry)
            except OSError as exc:
                log.warning("Impossible d'écrire dans le registre : %s — %s", entry, exc)

    def _cleanup(self) -> None:
        """Nettoie les fichiers partiellement extraits."""
        if not self.destination.exists():
            return
        try:
            shutil.rmtree(self.destination)
            log.info("Fichiers partiels nettoyés : %s", self.destination)
        except OSError as exc:
            log.error("Échec du nettoyage de %s : %s", self.destination, exc)

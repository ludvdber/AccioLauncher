import gc
import logging
import shutil
import subprocess
import sys
import threading
import time
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


def _find_7z_exe() -> str | None:
    """Cherche 7z.exe sur le système (fallback quand py7zr ne supporte pas le format)."""
    candidates = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # Tenter le PATH
    try:
        subprocess.run(
            ["7z"], capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        # Si aucune exception, 7z est trouvé dans le PATH
        return "7z"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


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
        config_files: list[tuple[str, str]] | None = None,
        game_dir: str | None = None,
        delete_archive: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.archive_path = archive_path
        self.destination = destination
        self.registry_entries = registry_entries or []
        self.config_files = config_files or []  # [(source_rel, dest_with_tilde), ...]
        self.game_dir = game_dir  # ex: "HP3" — racine du jeu dans l'archive
        self.delete_archive = delete_archive
        self._cancel_event = threading.Event()
        self._extracted_dirs: list[Path] = []  # dossiers créés pendant l'extraction

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

            # Snapshot des dossiers existants avant extraction
            existing_dirs = set(p.name for p in self.destination.iterdir() if p.is_dir())

            suffix = self.archive_path.suffix.lower()
            # Gérer aussi .001 (split archives)
            if suffix == ".001":
                suffix = Path(self.archive_path.stem).suffix.lower()

            match suffix:
                case ".7z":
                    self._extract_7z()
                case ".zip":
                    self._extract_zip()
                case _:
                    self.error.emit(f"Format d'archive non supporté : {suffix}")
                    return

            # Identifier les nouveaux dossiers créés
            new_dirs = set(p.name for p in self.destination.iterdir() if p.is_dir()) - existing_dirs
            self._extracted_dirs = [self.destination / d for d in new_dirs]
            log.debug("Nouveaux dossiers extraits : %s", [str(d) for d in self._extracted_dirs])

            if self._cancelled:
                self._cleanup()
                return

            self._apply_registry()
            self._apply_config_files()

            if self.delete_archive:
                self._delete_archive()

            log.info("Installation terminée : %s", self.destination)
            self.finished.emit(str(self.destination))

        except Exception as exc:
            log.exception("Erreur pendant l'installation")
            # NE PAS cleanup en cas d'erreur d'extraction — laisser les fichiers pour debug
            self.error.emit(f"Erreur d'installation : {exc}")

    def _validate_7z_paths(self, file_list: list) -> None:
        """Vérifie que toutes les entrées d'une archive 7z sont sûres."""
        for f_info in file_list:
            name = f_info.filename
            if not _check_path_traversal(self.destination, name):
                raise ValueError(f"Path traversal détecté dans l'archive 7z : {name}")

    def _extract_7z(self) -> None:
        """Extrait une archive .7z — py7zr d'abord, fallback sur 7z.exe si non supporté."""
        try:
            self._extract_7z_py7zr()
        except py7zr.exceptions.UnsupportedCompressionMethodError as exc:
            log.warning("py7zr ne supporte pas cette archive (%s), fallback sur 7z.exe", exc)
            gc.collect()
            self._extract_7z_subprocess()

    def _extract_7z_py7zr(self) -> None:
        """Extraction via py7zr (rapide, mais ne supporte pas BCJ2)."""
        with py7zr.SevenZipFile(self.archive_path, mode="r") as archive:
            all_files = archive.list()
            self._validate_7z_paths(all_files)

            total = len(all_files)
            log.debug("Extraction py7zr : %d fichiers", total)

            # py7zr ne supporte pas de callback de progression.
            # On extrait tout d'un coup — la barre passera de 0 à 100.
            self.progress.emit(0)
            archive.extractall(path=self.destination)
            self.progress.emit(100)

    def _extract_7z_subprocess(self) -> None:
        """Extraction via 7z.exe (fallback pour BCJ2 et autres filtres non supportés)."""
        exe = _find_7z_exe()
        if exe is None:
            raise RuntimeError(
                "Cette archive nécessite 7-Zip pour être extraite (filtre BCJ2).\n"
                "Installez 7-Zip depuis https://7-zip.org puis réessayez."
            )

        log.info("Extraction via 7z.exe : %s → %s", self.archive_path, self.destination)
        cmd = [exe, "x", str(self.archive_path), f"-o{self.destination}", "-y", "-bsp1"]
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, **kwargs,
        )

        try:
            last_pct = 0
            for line in proc.stdout:
                if self._cancelled:
                    proc.kill()
                    return
                line = line.strip()
                # 7z affiche des lignes comme "42%" pendant l'extraction
                if line.endswith("%") or "%" in line:
                    try:
                        pct_str = line.split("%")[0].strip().split()[-1]
                        pct = int(pct_str)
                        if pct != last_pct:
                            self.progress.emit(pct)
                            last_pct = pct
                    except (ValueError, IndexError):
                        pass

            ret = proc.wait(timeout=300)  # 5 min max pour le cleanup final
            if ret != 0:
                raise RuntimeError(f"7z.exe a échoué (code {ret})")
            self.progress.emit(100)
            log.info("Extraction 7z.exe terminée")
        except subprocess.TimeoutExpired:
            log.error("7z.exe n'a pas terminé dans le délai imparti, kill du processus")
            proc.kill()
            proc.wait(timeout=10)
            raise RuntimeError("7z.exe a dépassé le temps d'extraction maximum (5 min)")
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)

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

    def _apply_config_files(self) -> None:
        """Copie les fichiers de configuration vers le dossier Mes Documents.

        Chaque fichier existant est backupé en .bak avant remplacement.
        Les erreurs ne bloquent pas l'installation.
        """
        if not self.config_files:
            return

        for source_rel, dest_tilde in self.config_files:
            try:
                # Résoudre le source par rapport au dossier du jeu
                base = self.destination / self.game_dir if self.game_dir else self.destination
                src = (base / source_rel).resolve()
                # Vérifier que le source ne sort pas du dossier d'installation
                if not src.is_relative_to(self.destination.resolve()):
                    log.warning("Config source hors du dossier d'installation : %s", source_rel)
                    continue
                if not src.exists():
                    log.warning("Fichier de config source introuvable : %s", src)
                    continue

                dest = Path(dest_tilde.replace("~", str(Path.home())))
                dest.parent.mkdir(parents=True, exist_ok=True)

                # Backup si le fichier existe déjà
                if dest.exists():
                    bak = dest.with_suffix(dest.suffix + ".bak")
                    shutil.copy2(dest, bak)
                    log.info("Backup de la config existante : %s → %s", dest, bak)

                shutil.copy2(src, dest)
                log.info("Config copiée : %s → %s", src, dest)
            except OSError as exc:
                log.warning("Impossible de copier le fichier de config %s : %s", source_rel, exc)

    def _cleanup(self) -> None:
        """Nettoie UNIQUEMENT les dossiers créés pendant l'extraction.

        PROTECTION : ne supprime JAMAIS self.destination (le dossier d'installation racine).
        Seuls les sous-dossiers identifiés comme nouveaux sont supprimés.
        """
        if not self._extracted_dirs:
            log.debug("Rien à nettoyer (aucun dossier extrait)")
            return
        for d in self._extracted_dirs:
            if not d.exists():
                continue
            # PROTECTION CRITIQUE : refuser de supprimer le dossier racine
            if d.resolve() == self.destination.resolve():
                log.critical("REFUS de supprimer le dossier d'installation racine : %s", d)
                continue
            try:
                shutil.rmtree(d)
                log.info("Fichiers partiels nettoyés : %s", d)
            except OSError as exc:
                log.error("Échec du nettoyage de %s : %s", d, exc)

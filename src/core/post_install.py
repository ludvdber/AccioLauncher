"""Étapes post-extraction : registre (DEAD CODE), fichiers de config, déblocage NTFS."""

import logging
import shutil
import sys
from pathlib import Path

from src.core.config import get_documents_dir
from src.core.win_utils import remove_zone_identifier

log = logging.getLogger(__name__)

# Préfixes de registre autorisés (whitelist) — DEAD CODE: aucun jeu n'utilise post_install.registry.
# Slated for removal — voir audit 2026-04-29 §3 #1.
_ALLOWED_REGISTRY_PREFIXES = ("Software\\",)


def unblock_extracted(extracted_dirs: list[Path]) -> int:
    """Supprime le flag NTFS Zone.Identifier des fichiers extraits."""
    return sum(remove_zone_identifier(d) for d in extracted_dirs)


def apply_registry(registry_entries: list[str]) -> None:
    """Applique les entrées de registre post-installation (Windows uniquement).

    DEAD CODE — conservé pour ne pas casser la signature publique de l'Installer
    pendant la transition. Aucun jeu du catalog n'utilise ce mécanisme.
    Suppression prévue dans une passe ultérieure.
    """
    if not registry_entries or sys.platform != "win32":
        return

    import winreg

    _HIVE_MAP = {
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    }

    for entry in registry_entries:
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

            if not any(sub_key.startswith(prefix) for prefix in _ALLOWED_REGISTRY_PREFIXES):
                log.warning("Clé de registre hors whitelist ignorée : %s", sub_key)
                continue

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


def apply_config_files(
    destination: Path, game_dir: str | None,
    config_files: list[tuple[str, str]],
) -> None:
    """Copie les fichiers de configuration vers Documents (avec backup .bak)."""
    if not config_files:
        return

    for source_rel, dest_tilde in config_files:
        try:
            base = destination / game_dir if game_dir else destination
            src = (base / source_rel).resolve()
            if not src.is_relative_to(destination.resolve()):
                log.warning("Config source hors du dossier d'installation : %s", source_rel)
                continue
            if not src.exists():
                log.warning("Fichier de config source introuvable : %s", src)
                continue

            docs_dir = get_documents_dir()
            dest_str = dest_tilde.replace("~/Documents", str(docs_dir)).replace("~", str(Path.home()))
            dest = Path(dest_str)
            if not (dest.resolve().is_relative_to(Path.home().resolve())
                    or dest.resolve().is_relative_to(docs_dir)):
                log.warning("Config destination hors du home directory : %s", dest_tilde)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists():
                bak = dest.with_suffix(dest.suffix + ".bak")
                shutil.copy2(dest, bak)
                log.info("Backup de la config existante : %s → %s", dest, bak)

            shutil.copy2(src, dest)
            log.info("Config copiée : %s → %s", src, dest)
        except OSError as exc:
            log.warning("Impossible de copier le fichier de config %s : %s", source_rel, exc)

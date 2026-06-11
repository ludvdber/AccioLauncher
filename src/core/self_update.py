"""Auto-mise à jour du launcher : remplacement de l'exe courant et relance.

Windows uniquement pour l'instant : un .bat détaché attend la fin du processus,
remplace l'exe et relance la nouvelle version. Sur les autres plateformes (objectif
Linux à terme), retourne False — l'appelant retombe sur la page de release.
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def can_self_update() -> bool:
    """True si l'auto-remplacement est possible (exe frozen sous Windows)."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def apply_update_and_restart(new_exe: Path) -> bool:
    """Programme le remplacement de l'exe courant par `new_exe`, à exécuter après la fermeture.

    Retourne True si le script de remplacement est lancé (l'appelant doit alors
    quitter l'application), False si non applicable (mode dev / non-Windows).
    """
    if not can_self_update():
        return False
    current = Path(sys.executable).resolve()
    pid = os.getpid()
    # `ping` sert de sleep : `timeout /t` refuse de tourner sans console.
    bat_content = (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (\r\n'
        "    ping -n 2 127.0.0.1 >nul\r\n"
        "    goto wait\r\n"
        ")\r\n"
        f'move /y "{new_exe}" "{current}" >nul\r\n'
        f'start "" "{current}"\r\n'
        'del "%~f0"\r\n'
    )
    try:
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="accio_update_")
        with os.fdopen(fd, "w", encoding="ascii", errors="replace") as f:
            f.write(bat_content)
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=(
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            ),
        )
    except OSError as exc:
        log.error("Impossible de programmer l'auto-update : %s", exc)
        return False
    log.info("Mise à jour programmée : %s → %s", new_exe, current)
    return True

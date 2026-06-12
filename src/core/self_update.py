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


def _clean_pyinstaller_env() -> dict[str, str]:
    """Environnement purgé de l'état du bootloader PyInstaller.

    Un processus relancé qui hérite des variables `_PYI_*` (ou `_MEIPASS2`
    pour les vieux bootloaders) se croit enfant onefile de l'instance mourante
    et cherche python*.dll dans son dossier `_MEIxxxxxx` déjà supprimé →
    « Failed to load Python DLL » (reproduit sur l'exe gelé le 2026-06-12).
    `PYINSTALLER_RESET_ENVIRONMENT=1` (PyInstaller ≥ 6.10) force en plus le
    nouveau processus à se considérer comme une instance indépendante.
    """
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("_PYI_") and k != "_MEIPASS2"
    }
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _spawn_after_exit_bat(body: str, prefix: str) -> bool:
    """Lance un .bat détaché qui attend la mort du processus courant puis exécute `body`.

    Le délai (boucle tasklist + ping-sleep) garantit que le verrou d'instance
    unique est libéré avant toute relance. `ping` sert de sleep : `timeout /t`
    refuse de tourner sans console.
    """
    pid = os.getpid()
    bat_content = (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (\r\n'
        "    ping -n 2 127.0.0.1 >nul\r\n"
        "    goto wait\r\n"
        ")\r\n"
        f"{body}"
        'del "%~f0"\r\n'
    )
    try:
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix=prefix)
        # newline="" : le contenu contient déjà des \r\n ; sans ça le mode texte
        # les transforme en \r\r\n et cmd ne sort JAMAIS de la boucle :wait
        # (bug historique de l'auto-update, reproduit par simulation le 2026-06-11).
        with os.fdopen(fd, "w", encoding="ascii", errors="replace", newline="") as f:
            f.write(bat_content)
        # NE PAS détacher complètement le process (pas de console du tout) :
        # le pipeline `tasklist | find` se bloque alors et la boucle :wait ne
        # sort jamais (reproduit par simulation le 2026-06-11). CREATE_NO_WINDOW
        # donne à cmd une console cachée — invisible ET fonctionnelle — et le
        # .bat survit à la mort du parent (vérifié par la même simulation).
        # env nettoyé : le .bat (puis le `start` qu'il contient) ne doit PAS
        # transmettre l'état du bootloader PyInstaller au processus relancé.
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_clean_pyinstaller_env(),
        )
    except OSError as exc:
        log.error("Impossible de lancer le script détaché : %s", exc)
        return False
    return True


def apply_update_and_restart(new_exe: Path) -> bool:
    """Programme le remplacement de l'exe courant par `new_exe`, à exécuter après la fermeture.

    Retourne True si le script de remplacement est lancé (l'appelant doit alors
    quitter l'application), False si non applicable (mode dev / non-Windows).
    """
    if not can_self_update():
        return False
    current = Path(sys.executable).resolve()
    ok = _spawn_after_exit_bat(
        f'move /y "{new_exe}" "{current}" >nul\r\n'
        f'start "" "{current}"\r\n',
        prefix="accio_update_",
    )
    if ok:
        log.info("Mise à jour programmée : %s → %s", new_exe, current)
    return ok


def relaunch_after_exit() -> bool:
    """Programme une relance du launcher une fois le processus courant terminé.

    Utilisé par le bouton « Redémarrer maintenant » (changement de thème/langue)
    et par le dialogue de crash. L'appelant doit ensuite fermer l'application.
    Hors Windows : Popen direct, best effort (objectif Linux à terme).
    """
    if sys.platform == "win32":
        exe = Path(sys.executable).resolve()
        if getattr(sys, "frozen", False):
            body = f'start "" "{exe}"\r\n'
        else:
            # En dev, préférer pythonw.exe : pas de console parasite à la relance.
            pythonw = exe.with_name("pythonw.exe")
            if pythonw.exists():
                exe = pythonw
            main_py = Path(__file__).resolve().parents[2] / "main.py"
            body = f'start "" "{exe}" "{main_py}"\r\n'
        ok = _spawn_after_exit_bat(body, prefix="accio_relaunch_")
        if ok:
            log.info("Relance du launcher programmée")
        return ok
    try:
        subprocess.Popen([sys.executable] + sys.argv, env=_clean_pyinstaller_env())
        return True
    except OSError as exc:
        log.error("Impossible de relancer le launcher : %s", exc)
        return False

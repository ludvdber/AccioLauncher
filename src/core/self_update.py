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


# Drapeaux de création du process détaché, résolus À L'IMPORT et sous garde.
# `subprocess.CREATE_NEW_PROCESS_GROUP` et `CREATE_NO_WINDOW` n'existent QUE
# sous Windows : les nommer dans l'appel faisait lever `AttributeError` sur
# Linux avant même que `Popen` ne soit atteint — y compris dans un test qui
# remplace `Popen`. Le portage Linux étant un objectif déclaré, ce module doit
# rester appelable partout ; hors Windows il échouera plus loin, proprement,
# sur l'absence de `cmd` (OSError, déjà rattrapée).
if sys.platform == "win32":
    _DRAPEAUX_DETACHE = (subprocess.CREATE_NEW_PROCESS_GROUP
                         | subprocess.CREATE_NO_WINDOW)
else:
    _DRAPEAUX_DETACHE = 0


def _spawn_after_exit_bat(body: str, prefix: str,
                          variables: dict[str, str] | None = None) -> bool:
    """Lance un .bat détaché qui attend la mort du processus courant puis exécute `body`.

    Le délai (boucle tasklist + ping-sleep) garantit que le verrou d'instance
    unique est libéré avant toute relance. `ping` sert de sleep : `timeout /t`
    refuse de tourner sans console.

    **`body` doit être en ASCII pur, et tout chemin doit passer par
    `variables`**, référencé dans le corps sous la forme `%NOM%`. Raison : un
    fichier de commandes est relu par cmd.exe dans la page de codes OEM (cp850
    ici), qui ne sait pas écrire `Frédéric`, encore moins `Дмитрий` ou `ハリー`.
    L'ancienne version écrivait le .bat en `ascii` avec `errors="replace"` :
    `C:\\Users\\Frédéric\\` devenait `C:\\Users\\Fr?d?ric\\`, `move` et `start`
    échouaient, et l'auto-update comme les deux boutons « Redémarrer »
    s'arrêtaient sans un mot (mesuré le 2026-08-20, avec témoin sans accent).
    Le bloc d'environnement, lui, est transmis en Unicode par CreateProcessW :
    les trois écritures passent (vérifié à l'exécution).
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
        # errors="strict" et non "replace" : le corps est censé être en ASCII
        # pur. Un caractère hors ASCII est désormais une ERREUR franche (le
        # script ne part pas, l'appelant retombe sur son plan B) plutôt qu'un
        # « ? » silencieux qui produisait un chemin inexistant.
        with os.fdopen(fd, "w", encoding="ascii", errors="strict", newline="") as f:
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
            creationflags=_DRAPEAUX_DETACHE,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_clean_pyinstaller_env() | (variables or {}),
        )
    except UnicodeEncodeError as exc:
        log.error("Corps de script non-ASCII (les chemins doivent passer par "
                  "`variables`) : %s", exc)
        return False
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
    # Les deux chemins voyagent par l'environnement, pas dans le corps du .bat
    # (cf. _spawn_after_exit_bat : un chemin accentué y était mutilé).
    ok = _spawn_after_exit_bat(
        'move /y "%ACCIO_NOUVEL_EXE%" "%ACCIO_EXE%" >nul\r\n'
        'start "" "%ACCIO_EXE%"\r\n',
        prefix="accio_update_",
        variables={"ACCIO_NOUVEL_EXE": str(new_exe), "ACCIO_EXE": str(current)},
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
        variables = {}
        if getattr(sys, "frozen", False):
            body = 'start "" "%ACCIO_EXE%"\r\n'
        else:
            # En dev, préférer pythonw.exe : pas de console parasite à la relance.
            pythonw = exe.with_name("pythonw.exe")
            if pythonw.exists():
                exe = pythonw
            main_py = Path(__file__).resolve().parents[2] / "main.py"
            body = 'start "" "%ACCIO_EXE%" "%ACCIO_MAIN%"\r\n'
            variables["ACCIO_MAIN"] = str(main_py)
        variables["ACCIO_EXE"] = str(exe)
        ok = _spawn_after_exit_bat(body, prefix="accio_relaunch_", variables=variables)
        if ok:
            log.info("Relance du launcher programmée")
        return ok
    try:
        subprocess.Popen([sys.executable] + sys.argv, env=_clean_pyinstaller_env())
        return True
    except OSError as exc:
        log.error("Impossible de relancer le launcher : %s", exc)
        return False

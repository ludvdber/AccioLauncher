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

from src.core.win_utils import commande_systeme, dossier_systeme

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
        f'"%ACCIO_SYS%\\tasklist.exe" /FI "PID eq {pid}" 2>nul'
        f' | "%ACCIO_SYS%\\find.exe" "{pid}" >nul && (\r\n'
        '    "%ACCIO_SYS%\\PING.EXE" -n 2 127.0.0.1 >nul\r\n'
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
        # cmd.exe par son chemin système, et `%ACCIO_SYS%` pour ce que le .bat
        # appelle lui-même : un programme nommé seul est cherché dans le
        # dossier de l'exe appelant, puis dans le dossier courant, avant
        # System32 — souvent Téléchargements (cf. `commande_systeme`). `move`,
        # `start` et `del` sont internes à cmd : rien à résoudre. Liste
        # d'arguments, aucun shell.
        variables = {"ACCIO_SYS": dossier_systeme(), **(variables or {})}
        subprocess.Popen(  # nosec B603
            [commande_systeme("cmd.exe"), "/c", bat_path],
            creationflags=_DRAPEAUX_DETACHE,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_clean_pyinstaller_env() | variables,
        )
    except UnicodeEncodeError as exc:
        log.error("Corps de script non-ASCII (les chemins doivent passer par "
                  "`variables`) : %s", exc)
        return False
    except OSError as exc:
        log.error("Impossible de lancer le script détaché : %s", exc)
        return False
    return True


# Remplacement de l'exe, RÉESSAYÉ jusqu'à ~30 s avant de relancer.
#
# L'exe est un onefile PyInstaller, donc DEUX processus : le bootloader (qui
# tient l'image de l'exe) lance un enfant, et c'est l'enfant que voit
# `os.getpid()`. La boucle :wait attend donc l'enfant, et le bootloader, lui,
# vit encore le temps d'effacer son dossier `_MEI` : mesuré le 2026-09-24 sur un
# onefile de 23 Mo, **5 remplacements sur 5 refusés** (accès refusé, code 5) juste
# après la mort de l'enfant, bootloader mort 340 à 390 ms plus tard. L'ancien
# `move` unique échouait donc en silence dès que l'enfant mourait juste avant un
# tour de :wait, ou qu'un antivirus retenait le fichier : le .bat relançait
# l'ANCIEN exe, qui reproposait la même mise à jour, le nouveau restant dans le
# cache (signalé par un joueur, 1.0.4 → 1.0.6). Au bout des essais, on relance
# quand même l'exe en place : un launcher qui ne revient pas serait pire.
_CORPS_REMPLACEMENT = (
    "set ACCIO_ESSAIS=0\r\n"
    ":remplace\r\n"
    'move /y "%ACCIO_NOUVEL_EXE%" "%ACCIO_EXE%" >nul 2>&1 && goto relance\r\n'
    "set /a ACCIO_ESSAIS+=1\r\n"
    "if %ACCIO_ESSAIS% geq 30 goto relance\r\n"
    '"%ACCIO_SYS%\\PING.EXE" -n 2 127.0.0.1 >nul\r\n'
    "goto remplace\r\n"
    ":relance\r\n"
)


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
        _CORPS_REMPLACEMENT + 'start "" "%ACCIO_EXE%"\r\n',
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
        # Mode développement : l'interpréteur courant, par son chemin absolu.
        subprocess.Popen([sys.executable] + sys.argv,  # nosec B603
                         env=_clean_pyinstaller_env())
        return True
    except OSError as exc:
        log.error("Impossible de relancer le launcher : %s", exc)
        return False

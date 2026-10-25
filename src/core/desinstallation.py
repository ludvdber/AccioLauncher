"""Désinstaller le launcher, en gardant les jeux ou non (Ludo, 2026-10-09).

Rien ne s'efface tant que le launcher tourne : ses journaux sont ouverts, et
le programme ne peut pas se supprimer lui-même. Un script détaché attend la
fin du processus, comme pour une mise à jour (`self_update`), puis efface.

Ce qui part : les dossiers `_Launcher` (réglages, journaux, cache, catalogue,
bandes-annonces, préfixes Wine), le programme, et les jeux si on le demande.
Ce qui reste, toujours : les sauvegardes des jeux, dans Documents (le
catalogue y range aussi celles de HP1 et HP2). Les COPIES que le launcher en
fait vivent, elles, dans `_Launcher/copies_sauvegardes` : gardées par défaut,
seules dans un `_Launcher` vidé du reste.

**Garde-fous** : un dossier de jeu n'est effacé que s'il est un enfant DIRECT
du dossier d'installation ; un dossier de données que s'il s'appelle
`_Launcher`. Le dossier d'installation lui-même n'est retiré que VIDE
(`rmdir` sans récursion) : un fichier à vous qui y traîne le garde en vie.
"""

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.core.config import LAUNCHER_DIR_NAME
from src.core.copies_sauvegardes import DOSSIER as DOSSIER_COPIES

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Inventaire:
    """Ce que la désinstallation efface, dans l'ordre."""

    dossiers: tuple[Path, ...]          # effacés en entier
    programme: Path | None              # l'exe ou l'AppImage ; None depuis les sources
    si_vides: tuple[Path, ...] = ()     # retirés seulement s'ils sont vides
    fichiers: tuple[Path, ...] = ()     # effacés un par un


def donnees_du_launcher() -> Path:
    """`_Launcher/`, résolu À L'APPEL : les tests le déplacent (`conftest`)."""
    from src.core import config
    return config.CONFIG_FILE_PATH.parent


def _profond(chemin: Path) -> bool:
    """Jamais une racine de disque ni un dossier de premier niveau."""
    return len(chemin.resolve().parts) >= 3


def programme_courant() -> Path | None:
    """Le fichier du launcher, s'il en a un à effacer.

    Depuis les sources, rien : ce serait l'interpréteur Python.
    """
    if sys.platform != "win32":
        from src.core.self_update import appimage_courante
        return appimage_courante()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def inventaire(install_path: Path, dossiers_de_jeux: list[Path], garder_jeux: bool,
               garder_copies: bool = True, programme: Path | None = None) -> Inventaire:
    """Ce qui partira. Rien n'est modifié ici : on ne fait que lister."""
    install_path = Path(install_path)
    dossiers: list[Path] = []
    fichiers: list[Path] = []
    racine_donnees = donnees_du_launcher()
    for donnees in dict.fromkeys((racine_donnees, install_path / LAUNCHER_DIR_NAME)):
        if donnees.name != LAUNCHER_DIR_NAME or not _profond(donnees):
            continue
        copies = donnees / DOSSIER_COPIES
        if garder_copies and copies.is_dir():
            # Tout SAUF les copies : le dossier entier ne peut pas partir.
            for enfant in sorted(donnees.iterdir()):
                if enfant != copies:
                    (dossiers if enfant.is_dir() else fichiers).append(enfant)
        else:
            dossiers.append(donnees)
    if not garder_jeux:
        for jeu in dossiers_de_jeux:
            jeu = Path(jeu)
            if jeu.parent == install_path and jeu.name != LAUNCHER_DIR_NAME and _profond(jeu):
                dossiers.append(jeu)
    # Toujours proposés, jamais forcés : un jeu gardé, ou un fichier à vous,
    # les laisse en place.
    si_vides = [install_path]
    if racine_donnees.parent != install_path:
        si_vides.append(racine_donnees.parent)
    return Inventaire(tuple(dossiers), programme, tuple(p for p in si_vides if _profond(p)),
                      tuple(fichiers))


# Le corps du script Windows : ASCII pur, chaque chemin dans une variable
# d'environnement (règle 79 : cmd.exe relit le .bat en page OEM).
_FIN = "\r\n"


def corps_windows(inv: Inventaire) -> tuple[str, dict[str, str]]:
    corps, variables = [], {}
    for i, dossier in enumerate(inv.dossiers):
        variables[f"ACCIO_D{i}"] = str(dossier)
        corps.append(f'rmdir /s /q "%ACCIO_D{i}%" >nul 2>&1{_FIN}')
    for i, fichier in enumerate(inv.fichiers):
        variables[f"ACCIO_F{i}"] = str(fichier)
        corps.append(f'del /f /q "%ACCIO_F{i}%" >nul 2>&1{_FIN}')
    if inv.programme is not None:
        # Le chargeur d'un exe onefile tient encore le fichier ~400 ms après la
        # fin de son enfant (cf. `self_update._CORPS_REMPLACEMENT`) : on réessaie.
        variables["ACCIO_EXE"] = str(inv.programme)
        boucle = (
            "set ACCIO_ESSAIS=0", ":efface",
            'del /f /q "%ACCIO_EXE%" >nul 2>&1',
            'if not exist "%ACCIO_EXE%" goto suite',
            "set /a ACCIO_ESSAIS+=1",
            "if %ACCIO_ESSAIS% geq 30 goto suite",
            '"%ACCIO_SYS%\\PING.EXE" -n 2 127.0.0.1 >nul',
            "goto efface", ":suite",
        )
        corps += [ligne + _FIN for ligne in boucle]
    for i, dossier in enumerate(inv.si_vides):
        variables[f"ACCIO_V{i}"] = str(dossier)
        corps.append(f'rmdir "%ACCIO_V{i}%" >nul 2>&1{_FIN}')
    return "".join(corps), variables


# Linux : chemins en arguments, jamais dans le script ; « V: » marque un
# dossier à ne retirer que vide.
_SCRIPT_SH = ('while kill -0 "$ACCIO_PID" 2>/dev/null; do sleep 0.5; done; '
              'for c in "$@"; do case "$c" in V:*) rmdir -- "${c#V:}" 2>/dev/null;; '
              '*) rm -rf -- "$c";; esac; done')


def programmer(inv: Inventaire) -> bool:
    """Lance le script qui efface après la fermeture. True : l'appelant ferme."""
    if sys.platform == "win32":
        from src.core.self_update import executer_apres_la_fin
        corps, variables = corps_windows(inv)
        ok = executer_apres_la_fin(corps, "accio_desinstallation_", variables)
    else:
        ok = _programmer_sh(inv)
    if ok:
        log.info("Désinstallation programmée : %s ; programme : %s",
                 ", ".join(str(d) for d in (*inv.dossiers, *inv.fichiers)), inv.programme)
    return ok


def _programmer_sh(inv: Inventaire) -> bool:
    from src.core.compat import environnement_hote
    cibles = [str(d) for d in (*inv.dossiers, *inv.fichiers)]
    if inv.programme is not None:
        cibles.append(str(inv.programme))
    cibles += [f"V:{d}" for d in inv.si_vides]
    env = environnement_hote() | {"ACCIO_PID": str(os.getpid())}
    try:
        # `/bin/sh` par son chemin absolu ; script constant, arguments en liste.
        subprocess.Popen(  # nosec B603
            ["/bin/sh", "-c", _SCRIPT_SH, "accio-desinstallation", *cibles],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except OSError as exc:
        log.error("Désinstallation impossible à programmer : %s", exc)
        return False
    return True

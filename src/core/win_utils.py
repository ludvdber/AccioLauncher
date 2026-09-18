"""Utilitaires Windows partagés (NTFS Zone.Identifier, ...)."""

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def dossier_systeme() -> str:
    """Le dossier système de Windows (`System32`), en chemin absolu.

    Demandé à `GetSystemDirectoryW` plutôt que reconstruit depuis
    `%SystemRoot%`, qu'un parent peut fixer à ce qu'il veut. Repli sur la
    variable, puis sur l'emplacement standard, si l'API ne répond pas (ou
    hors Windows, où rien ne l'appelle pour de bon).
    """
    if sys.platform == "win32":
        import ctypes
        tampon = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetSystemDirectoryW(tampon, len(tampon)):
            return tampon.value
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")


def commande_systeme(nom: str) -> str:
    """Chemin ABSOLU d'un programme de Windows (`tasklist.exe`, `cmd.exe`…).

    Jamais son seul nom : un programme lancé par son nom est cherché d'abord
    dans le dossier de l'exécutable APPELANT, avant `System32` — c'est l'ordre
    de `CreateProcess`, et `subprocess` le suit. Pour le launcher, ce dossier
    est celui où l'utilisateur a enregistré AccioLauncher.exe : très souvent
    Téléchargements. Un `tasklist.exe` qui s'y trouverait serait exécuté à la
    place de celui de Windows, à chaque partie. Relevé par Bandit (B607) le
    2026-09-18 ; vérifié ensuite dans la documentation de `CreateProcess`, pas
    supposé d'après le seul avertissement.

    Hors Windows, rend le nom tel quel : ces programmes n'y existent pas, et
    les appelants sont déjà gardés par `sys.platform`.
    """
    if sys.platform != "win32":
        return nom
    return str(Path(dossier_systeme()) / nom)


def remove_zone_identifier(root: Path, pattern: str = "*") -> int:
    """Supprime le flag NTFS Zone.Identifier des fichiers sous `root` matchant `pattern`.

    Windows pose ce flag sur tout fichier extrait d'archive téléchargée, ce qui
    bloque le chargement de DLL et déclenche des erreurs UE1 type
    "Can't find file for package".

    Retourne le nombre de fichiers traités.
    """
    if sys.platform != "win32" or not root.exists():
        return 0
    count = 0
    for f in root.rglob(pattern):
        if not f.is_file():
            continue
        try:
            os.remove(str(f) + ":Zone.Identifier")
            count += 1
        except OSError:
            pass
    return count

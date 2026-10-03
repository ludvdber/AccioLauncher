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


def dossier_windows() -> str:
    """Le dossier de Windows (`C:\\Windows`), en chemin absolu.

    Là vit `regedit.exe`, ABSENT de System32. Même source que
    `dossier_systeme` : l'API, pas `%SystemRoot%`.
    """
    if sys.platform == "win32":
        import ctypes
        tampon = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetSystemWindowsDirectoryW(tampon, len(tampon)):
            return tampon.value
    return os.environ.get("SystemRoot", r"C:\Windows")


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


# Où Windows range l'onglet « Compatibilité » des propriétés d'un exe : une
# valeur par exe, nommée par son chemin COMPLET, contenant les couches
# (« ~ RUNASADMIN WINXPSP3 »). HKCU = « ce compte », HKLM = « tous les
# utilisateurs ». Lu, jamais écrit.
_CLE_COUCHES = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"


def couches_de_compatibilite(exe: Path) -> dict[str, list[str]]:
    """Les couches posées sur `exe`, par ruche (`{"HKCU": ["RUNASADMIN"]}`).

    Né d'un rapport du 2026-10-01 : « Exécuter ce programme en tant
    qu'administrateur » coché sur `Game.exe` de HP2, et chaque clic sur JOUER
    finissait en `WinError 740` sans que rien à l'écran ne dise pourquoi. Le
    nom de la valeur est comparé sans la casse (Windows ne la garde pas
    forcément). Hors Windows, ou registre illisible : rien.
    """
    if sys.platform != "win32":
        return {}
    import winreg
    cible = os.path.normcase(str(exe))
    trouve: dict[str, list[str]] = {}
    for nom, ruche in (("HKCU", winreg.HKEY_CURRENT_USER),
                       ("HKLM", winreg.HKEY_LOCAL_MACHINE)):
        try:
            cle = winreg.OpenKey(ruche, _CLE_COUCHES, 0,
                                 winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            continue
        with cle:
            i = 0
            while True:
                try:
                    valeur, donnee, _ = winreg.EnumValue(cle, i)
                except OSError:
                    break
                i += 1
                if os.path.normcase(valeur) == cible and isinstance(donnee, str):
                    trouve[nom] = [c for c in donnee.split() if c not in ("~", "$")]
    return trouve


def exige_l_administrateur(couches: dict[str, list[str]]) -> list[str]:
    """Les ruches où la case « administrateur » est cochée (pure)."""
    return [ruche for ruche, liste in couches.items() if "RUNASADMIN" in liste]

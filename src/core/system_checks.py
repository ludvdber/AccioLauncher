"""Vérifications système — VC++ Redistributable, DirectX 11, etc."""

import functools
import os
import sys
from pathlib import Path

# Page officielle du redistribuable manquant. Elle vit ici, à côté du test qui
# le détecte : le correctif et le diagnostic ne doivent pas pouvoir diverger.
VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x86.exe"

# HP7 partie 1 exige Visual C++ 2005, la partie 2 le 2008 : runtimes DISTINCTS
# du 2015-2022. Sans eux, le jeu se refermait aussitôt, sans message.
VCREDIST_2005_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=26347"
VCREDIST_2008_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=26368"

# Runtime DirectX 9.0c de juin 2010, jamais livré par Windows : HP7 importe
# `d3dx9_37` (le seul que le catalogue déclare encore ; `xinput1_3.dll` est livrée
# dans l'archive, `d3dx9_43` datait de l'ancien wrapper d3d9). Une DLL par
# identifiant : le catalogue déclare ce que CHAQUE jeu charge. Un seul installeur
# Microsoft pour toutes.
DIRECTX9_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=35"
DLL_DIRECTX9 = ("d3dx9_43", "d3dx9_37", "xinput1_3")

# Compilateur d'effets du même runtime : `d3d11drv.dll` (HP1, HP2) compile
# `ASSAO.fx` à chaque démarrage. Sous Wine il faut les DEUX DLL natives
# (chacune seule échoue sur « Error compiling effects file ») ; pour
# `DLL_DIRECTX9`, celles de Wine suffisent.
DLL_COMPILATEUR = ("d3dx11_43", "d3dcompiler_43")

# Visual C++ 2010, importé par le même `d3d11drv.dll` (`msvcr100.dll`,
# `msvcp100.dll`). Pas d'assembly WinSxS pour ce runtime : ses DLL vont
# directement dans le dossier système.
VCREDIST_2010_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=26999"
DLL_VCREDIST_2010 = ("msvcr100", "msvcp100")


def dll_x86_presente(systeme: Path, nom: str) -> bool:
    """La DLL `nom` du runtime DirectX est-elle dans ce dossier système ? Pure."""
    return (systeme / f"{nom}.dll").is_file()


def _systeme_x86() -> Path:
    """Dossier où le chargeur trouve les DLL SYSTÈME d'un programme 32 bits.

    Jeux 32 bits : SysWOW64 sur un Windows 64 bits, sinon System32.
    """
    racine = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    wow64 = racine / "SysWOW64"
    return wow64 if wow64.is_dir() else racine / "System32"


@functools.cache
def check_directx9(nom: str) -> bool:
    """Vérifie si la DLL `nom` du runtime DirectX de juin 2010 est installée.

    Sous Linux, oui : celles de Wine suffisent.
    """
    if sys.platform != "win32":
        return True
    return dll_x86_presente(_systeme_x86(), nom)


def dll_native_dans_le_prefixe(pfx: Path, nom: str) -> bool:
    """La VRAIE DLL `nom` est-elle en place dans ce préfixe Wine, et choisie ? Pure.

    Comme winetricks : le fichier (pas celui de Wine) dans le dossier système
    32 bits, ET une surcharge « native » dans `HKCU\\Software\\Wine\\DllOverrides`.
    """
    from src.core import compat

    systeme = "syswow64" if compat.architecture(pfx) == "win64" else "system32"
    dll = pfx / "drive_c" / "windows" / systeme / f"{nom}.dll"
    if not dll.is_file() or compat.est_dll_interne_wine(dll):
        return False
    surcharges = compat.lire_valeurs(pfx, "HKCU", r"Software\Wine\DllOverrides",
                                     [f"*{nom}", nom], vue=64)
    return any(isinstance(v, str) and v.strip().lower().startswith("n")
               for v in surcharges.values())


@functools.cache
def check_dll_native(nom: str) -> bool:
    """Vérifie si la DLL `nom` du compilateur d'effets (`DLL_COMPILATEUR`) est installée.

    Sous Windows, comme `check_directx9`. Sous Linux, dans le préfixe : le
    verbe au journal de winetricks, ou la DLL native réellement en place.
    """
    if sys.platform != "win32":
        return _dans_le_prefixe({nom}, lambda pfx: dll_native_dans_le_prefixe(pfx, nom))
    return dll_x86_presente(_systeme_x86(), nom)


@functools.cache
def check_vcredist_2010_x86() -> bool:
    """Vérifie si le Visual C++ 2010 Redistributable x86 est installé (HP1, HP2).

    Sous Linux, oui : celles de Wine suffisent (HP1 atteint son menu).
    """
    if sys.platform != "win32":
        return True
    systeme = _systeme_x86()
    return all(dll_x86_presente(systeme, nom) for nom in DLL_VCREDIST_2010)

# Jeton de clé publique des assemblies CRT de Microsoft (le même pour VC8 et
# VC9). Il fait partie de l'identité forte de l'assembly : c'est ce qui
# distingue le vrai redistribuable d'un dossier homonyme.
_CRT_JETON = "1fc8b3b9a1e18e3b"


# Coussin sur le besoin calculé : le catalogue déclare une taille installée qui
# dérive de la réalité, et le système de fichiers a ses propres frais.
_MARGE = 1.05


def needed_space_mb(size_mb: int, archive_mb: int = 0) -> int:
    """Place à prévoir pour installer un jeu, en Mo. Pure.

    Pic = taille INSTALLÉE + archive (elles cohabitent jusqu'au nettoyage),
    plus `_MARGE` (la taille déclarée dérive : HP5 +2,4 %). Sans `archive_mb`,
    le double. Fonction unique pour le clic et l'avertissement en amont.
    """
    if archive_mb <= 0:
        return size_mb * 2
    return int((size_mb + archive_mb) * _MARGE)


def crt_x86_present(winsxs: Path, version: str) -> bool:
    """True si l'assembly CRT x86 de `version` ("vc80", "vc90") est installée. Pure.

    Le DOSSIER d'assembly WinSxS, pas le registre (les clés varient selon
    Windows) : l'assembly est là où le chargeur la cherche.
    """
    numero = version.removeprefix("vc")          # "80" / "90"
    try:
        motif = f"x86_microsoft.{version}.crt_{_CRT_JETON}_*/msvcr{numero}.dll"
        return any(winsxs.glob(motif))
    except OSError:
        return False


def crt_x86_reel(winsxs: Path, version: str) -> bool:
    """Comme `crt_x86_present`, mais dans un préfixe WINE. Pure.

    Un préfixe neuf a DÉJÀ des assemblies VC80/VC90 remplies des DLL de Wine,
    au même endroit que les vraies : on écarte celles qui portent sa marque.
    Casse ignorée à la main (Linux ne l'ignore pas).
    """
    from src.core.compat import est_dll_interne_wine

    numero = version.removeprefix("vc")
    debut = f"x86_microsoft.{version}.crt_{_CRT_JETON}_"
    try:
        dossiers = [d for d in winsxs.iterdir() if d.name.lower().startswith(debut)]
    except OSError:
        return False
    for dossier in dossiers:
        for dll in (dossier / f"msvcr{numero}.dll", dossier / f"MSVCR{numero}.DLL"):
            if dll.is_file() and not est_dll_interne_wine(dll):
                return True
    return False


def _winsxs() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "WinSxS"


# Sous Linux, un prérequis s'installe DANS LE PRÉFIXE, par winetricks : le
# verbe à demander, pour chaque identifiant que le catalogue peut déclarer.
VERBES_WINETRICKS = {
    "vcredist_x86": "vcrun2022",
    "vcredist2005_x86": "vcrun2005",
    "vcredist2008_x86": "vcrun2008",
    # Les DLL natives du compilateur d'effets (HP1, HP2) : celles de Wine
    # échouent, il faut les verbes.
    "d3dx11_43": "d3dx11_43",
    "d3dcompiler_43": "d3dcompiler_43",
    # Jamais demandés en pratique (Wine a ses propres DLL, voir check_directx9),
    # mais chaque identifiant garde son verbe : la table reste complète.
    "d3dx9_43": "d3dx9_43",
    "d3dx9_37": "d3dx9_37",
    "xinput1_3": "xinput",
    "vcredist2010_x86": "vcrun2010",
}

# Tout runtime 14.x satisfait le socle, comme le test Windows (clé 14.0)
# l'accepte : un préfixe où l'on a installé vcrun2019 n'a pas à recommencer.
_VERBES_VC14 = frozenset({"vcrun2015", "vcrun2017", "vcrun2019", "vcrun2022"})
_CLE_VC14_X86 = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86"


def _dans_le_prefixe(verbes, test) -> bool:
    """Un prérequis est-il présent dans le préfixe Wine ?

    Sans lanceur : oui (c'est l'absence de Wine qu'on signale, une fois).
    Préfixe pas créé : non. Sinon, le journal de winetricks OU le composant
    réellement en place.
    """
    from src.core import compat

    if compat.lanceur() is None:
        return True
    pfx = compat.prefixe()
    if not compat.pret(pfx):
        return False
    if compat.verbes_installes(pfx) & set(verbes):
        return True
    return bool(test(pfx))


@functools.cache
def check_vcredist_2005_x86() -> bool:
    """Vérifie si le Visual C++ 2005 Redistributable x86 est installé (HP7 partie 1)."""
    if sys.platform != "win32":
        return _dans_le_prefixe({"vcrun2005"}, lambda pfx: crt_x86_reel(
            pfx / "drive_c" / "windows" / "winsxs", "vc80"))
    return crt_x86_present(_winsxs(), "vc80")


@functools.cache
def check_vcredist_2008_x86() -> bool:
    """Vérifie si le Visual C++ 2008 Redistributable x86 est installé (HP7 partie 2)."""
    if sys.platform != "win32":
        return _dans_le_prefixe({"vcrun2008"}, lambda pfx: crt_x86_reel(
            pfx / "drive_c" / "windows" / "winsxs", "vc90"))
    return crt_x86_present(_winsxs(), "vc90")


# Prérequis déclarables par le catalogue : identifiant → (test, page d'aide).
# Un identifiant inconnu est ignoré : un catalogue en avance ne bloque jamais
# un launcher plus ancien.
PREREQUIS = {
    "vcredist_x86": (lambda: check_vcredist_x86(), VCREDIST_URL),
    "vcredist2005_x86": (lambda: check_vcredist_2005_x86(), VCREDIST_2005_URL),
    "vcredist2008_x86": (lambda: check_vcredist_2008_x86(), VCREDIST_2008_URL),
    "vcredist2010_x86": (lambda: check_vcredist_2010_x86(), VCREDIST_2010_URL),
    **{nom: (lambda nom=nom: check_directx9(nom), DIRECTX9_URL) for nom in DLL_DIRECTX9},
    **{nom: (lambda nom=nom: check_dll_native(nom), DIRECTX9_URL) for nom in DLL_COMPILATEUR},
}


def prerequis_manquants(requis) -> list[str]:
    """Identifiants des prérequis déclarés qui ne sont PAS satisfaits."""
    return [nom for nom in requis
            if nom in PREREQUIS and not PREREQUIS[nom][0]()]


def invalidate_vcredist_cache() -> None:
    """Oublie les résultats mémorisés de TOUS les prérequis (et, sous Linux,
    du lanceur), au retour dans la fenêtre après « Installer » : sinon le
    bandeau mentirait. `cache_clear` cherché : ne jamais casser ici."""
    for verification in (check_vcredist_x86, check_vcredist_2005_x86,
                         check_vcredist_2008_x86, check_vcredist_2010_x86,
                         check_directx9, check_dll_native):
        vider = getattr(verification, "cache_clear", None)
        if vider is not None:
            vider()
    if sys.platform != "win32":
        from src.core import compat
        compat.oublier()


@functools.cache
def check_vcredist_x86() -> bool:
    """Vérifie si le Visual C++ Redistributable x86 (2015-2022) est installé."""
    if sys.platform != "win32":
        from src.core import compat
        return _dans_le_prefixe(_VERBES_VC14, lambda pfx: compat.lire_valeurs(
            pfx, "HKLM", _CLE_VC14_X86, ["Installed"], vue=32).get("Installed") == 1)
    import winreg
    for sub_key in (
        r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_key) as key:
                val, _ = winreg.QueryValueEx(key, "Installed")
                if val == 1:
                    return True
        except OSError:
            continue
    return False


@functools.cache
def check_d3d11_feature_level() -> bool:
    """Vérifie si le GPU supporte DirectX 11 (feature level 11_0).

    Crée un device D3D11 temporaire pour tester le support matériel.
    Retourne False si le GPU ne supporte pas DX11 ou en cas d'erreur.
    Le résultat est mis en cache (invariant pour la session).

    Hors Windows, True : DXVK ou wined3d le fournissent ; False enverrait
    tout le monde sur le `fallback` d'INI, que HP1/HP2 ne livrent pas.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        d3d11 = ctypes.WinDLL("d3d11")
        device = ctypes.c_void_p()
        feature_level = ctypes.c_uint()
        context = ctypes.c_void_p()
        # D3D_DRIVER_TYPE_HARDWARE=1, D3D11_SDK_VERSION=7
        hr = d3d11.D3D11CreateDevice(
            None, 1, None, 0, None, 0, 7,
            ctypes.byref(device), ctypes.byref(feature_level), ctypes.byref(context),
        )
        if hr < 0:
            return False
        supported = feature_level.value >= 0xb000  # D3D_FEATURE_LEVEL_11_0
        # Libérer les objets COM (IUnknown::Release = vtable index 2)
        for obj in (context, device):
            if obj.value:
                vtable = ctypes.cast(
                    ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0],
                    ctypes.POINTER(ctypes.c_void_p),
                )
                release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
                release(obj)
        return supported
    except Exception:
        return False

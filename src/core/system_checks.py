"""Vérifications système — VC++ Redistributable, DirectX 11, etc."""

import functools
import os
import sys
from pathlib import Path

# Page officielle du redistribuable manquant. Elle vit ici, à côté du test qui
# le détecte : le correctif et le diagnostic ne doivent pas pouvoir diverger.
VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x86.exe"

# Runtimes hérités exigés par les deux parties des Reliques de la Mort
# (Ludo, 2026-08-20) : la PARTIE 1 réclame Visual C++ 2005, la PARTIE 2
# Visual C++ 2008. Ce sont trois runtimes DISTINCTS avec le 2015-2022 : en
# avoir un n'implique jamais d'avoir les autres. Sans ces contrôles, HP7 se
# lançait puis se refermait aussitôt, sans message — le pire cas pour
# l'utilisateur, qui n'a alors rien à quoi se raccrocher.
VCREDIST_2005_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=26347"
VCREDIST_2008_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=26368"

# Le runtime DirectX 9.0c de juin 2010, que Windows n'a JAMAIS livré (ni 10 ni
# 11 : ils portent xinput1_4 et xinput9_1_0, aucune d3dx9). Relevé dans les
# binaires le 2026-09-26 : HP5 et HP6 importent `xinput1_3.dll`, les deux
# Reliques `d3dx9_37.dll` et `xinput1_3.dll`, et le wrapper d3d9 de HP4 à HP7b
# `d3dx9_43.dll` — aucune archive ne les livre. Sur un Windows neuf, sans jeu
# plus ancien pour les avoir apportées, ces jeux s'arrêtent avant leur première
# image sur « xinput1_3.dll est introuvable ». Une DLL par identifiant : le
# catalogue déclare ce que CHAQUE jeu charge, et HP4 n'a pas à attendre une
# xinput qu'il n'ouvre pas. Le même installeur de Microsoft les pose toutes.
DIRECTX9_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=35"
DLL_DIRECTX9 = ("d3dx9_43", "d3dx9_37", "xinput1_3")

# Le compilateur d'effets du même runtime de juin 2010. `d3d11drv.dll` de HP1 et
# HP2 importe `d3dx11_43.dll` et `d3dcompiler_43.dll`, et compile
# `System/d3d11drv/ASSAO.fx` à CHAQUE démarrage (`D3DX11CompileFromMemory`).
# Sous Wine, ses propres DLL échouent sur cet effet : « Error compiling effects
# file » puis « Initializing Direct3D failed » (HP.log, Bazzite, 2026-09-30).
# Il faut les DEUX natives : chacune seule échoue à l'identique, les deux
# ensemble mènent au menu (essais sur trois copies du préfixe). C'est la
# différence avec `DLL_DIRECTX9` : là, les DLL de Wine suffisent.
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

    Les jeux sont 32 bits : sur un Windows 64 bits c'est SysWOW64 (le launcher,
    64 bits, verrait dans System32 les DLL 64 bits, que le jeu ne peut pas
    charger) ; sur un Windows 32 bits, System32.
    """
    racine = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    wow64 = racine / "SysWOW64"
    return wow64 if wow64.is_dir() else racine / "System32"


@functools.cache
def check_directx9(nom: str) -> bool:
    """Vérifie si la DLL `nom` du runtime DirectX de juin 2010 est installée.

    Sous Linux, oui : Wine a les siennes (d3dx9_24 à 43, xinput1_3), et c'est
    avec elles que tournent déjà les jeux. Seule `d3d9` reçoit une surcharge
    (`dll_overrides`), pour que le wrapper du jeu passe devant celle de Wine.
    """
    if sys.platform != "win32":
        return True
    return dll_x86_presente(_systeme_x86(), nom)


def dll_native_dans_le_prefixe(pfx: Path, nom: str) -> bool:
    """La VRAIE DLL `nom` est-elle en place dans ce préfixe Wine, et choisie ? Pure.

    Deux conditions, comme ce que pose winetricks : le fichier dans le dossier
    système 32 bits (`syswow64` d'un préfixe 64 bits), qui ne soit pas la DLL
    de Wine rangée au même endroit, ET une surcharge « native » dans
    `HKCU\\Software\\Wine\\DllOverrides` — sans elle, Wine charge la sienne
    et le fichier ne sert à rien.
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

    Sous Linux, oui : les `msvcr100`/`msvcp100` de Wine suffisent, VU le
    2026-09-30 — HP1 atteint son menu avec elles (chargées depuis
    `lib/wine/i386-windows` de Proton, relevé dans `/proc/<pid>/maps`).
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

    `size_mb` est ce que déclare le catalogue, c'est-à-dire la taille du jeu une
    fois INSTALLÉ ; `archive_mb` le poids réel du téléchargement, que GitHub
    publie et que `GameManager.archive_size_mb` va chercher. Le pic
    d'occupation est leur SOMME : l'archive cohabite avec les fichiers extraits
    jusqu'au nettoyage final.

    Sans `archive_mb` (API injoignable, archive hébergée ailleurs) on garde le
    double, seule approximation possible quand on ne connaît qu'un des deux
    chiffres. Elle était généreuse : mesuré le 2026-08-21, elle réclamait
    2 001 Mo de trop pour HP5 — de quoi annoncer un blocage qui n'arrive pas.

    La somme, elle, serait trop juste sans `_MARGE` : `size_mb` est une valeur
    DÉCLARÉE, qui dérive de la réalité (HP5 annonce 4 600 Mo pour 4 709 mesurés
    sur disque, soit +2,4 %). Sans marge, l'exigence passait 109 Mo SOUS le pic
    réel — et une vérification d'espace qui se trompe dans ce sens-là laisse
    l'extraction échouer, ce qui est bien pire que de demander un peu trop.

    Fonction unique, partagée par la vérification au clic et par
    l'avertissement affiché en amont : deux chiffres différents feraient
    prévenir d'un blocage qui n'arrive pas (ou l'inverse).
    """
    if archive_mb <= 0:
        return size_mb * 2
    return int((size_mb + archive_mb) * _MARGE)


def crt_x86_present(winsxs: Path, version: str) -> bool:
    """True si l'assembly CRT x86 de `version` ("vc80", "vc90") est installée. Pure.

    On cherche le DOSSIER d'assembly côte-à-côte et sa DLL, et non une clé de
    registre : les emplacements de registre de ces redistribuables varient
    d'une version de Windows à l'autre (vérifié : les clés
    `SideBySide\\Winners` attendues n'existent pas sur Windows 11), alors que
    l'assembly, elle, est par définition là où le chargeur va la chercher.
    """
    numero = version.removeprefix("vc")          # "80" / "90"
    try:
        motif = f"x86_microsoft.{version}.crt_{_CRT_JETON}_*/msvcr{numero}.dll"
        return any(winsxs.glob(motif))
    except OSError:
        return False


def crt_x86_reel(winsxs: Path, version: str) -> bool:
    """Comme `crt_x86_present`, mais dans un préfixe WINE. Pure.

    Un préfixe neuf contient DÉJÀ des dossiers d'assembly VC80 et VC90, remplis
    des DLL internes de Wine — rangées exactement là où irait le vrai
    redistribuable, jusqu'au jeton de clé publique (vérifié sur Wine 9.0 le
    2026-09-24). Le test Windows y verrait un Visual C++ installé. On écarte
    donc toute DLL qui porte la marque de Wine ; le nom de dossier ne suffit
    pas non plus à trancher, puisque Wine range aussi les VRAIS
    redistribuables sous un suffixe `_none_deadbeef`. La casse est ignorée :
    le système de fichiers de Linux, lui, ne l'ignore pas.
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

    Sans lanceur de compatibilité, on répond oui : rien ne peut démarrer de
    toute façon, et c'est l'absence de Wine qu'on signale — en premier, et
    une seule fois — plutôt qu'une cascade de composants « manquants » dans un
    préfixe qui n'existe pas. Un préfixe pas encore créé, lui, n'a rien :
    c'est la préparation qui le crée et y installe les composants.

    Deux preuves acceptées : le journal de winetricks (ce qu'il a mené à bien)
    ou le composant réellement en place — quelqu'un qui a lancé l'installeur
    de Microsoft à la main dans le préfixe n'a pas à recommencer.
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
# Le catalogue se met à jour à distance, donc un jeu ajouté peut annoncer son
# runtime sans qu'on republie l'exécutable ; un identifiant inconnu est ignoré
# plutôt que bloquant, pour qu'un catalogue en avance ne verrouille jamais un
# launcher plus ancien.
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
    """Oublie le résultat mémorisé de `check_vcredist_x86`.

    Le cache existe parce que le test est appelé à chaque lancement de jeu.
    Mais depuis que l'absence du redistribuable est AFFICHÉE (bandeau sur la
    fiche du jeu), un résultat figé mentirait : l'utilisateur installe le
    paquet, revient dans le launcher, et l'avertissement serait toujours là.
    Appelé au retour dans la fenêtre après un clic sur « Installer ». Vide les
    caches de TOUS les redistribuables vérifiés, pas seulement du premier : un
    jeu peut en exiger un second (HP7 et son Visual C++ 2005).

    Le `cache_clear` est cherché plutôt qu'appelé d'autorité : une vérification
    de prérequis n'a pas l'obligation d'être mémoïsée, et cette fonction ne
    doit jamais être ce qui casse au retour dans la fenêtre.

    Sous Linux, la détection du lanceur de compatibilité est oubliée aussi :
    le lien « En savoir plus » du bandeau « Wine introuvable » mène au même
    aller-retour que « Installer », et quelqu'un qui vient d'installer umu
    n'a pas à redémarrer le launcher pour qu'on le voie.
    """
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

    Hors Windows, True : sous Wine, Direct3D 11 est fourni par DXVK (Proton)
    ou wined3d, pas par un pilote qu'on pourrait interroger d'ici. Rendre
    False, comme avant le portage, aurait envoyé TOUT le monde sur le
    `fallback` d'INI — un renderer que HP1 et HP2 ne livrent pas (CLAUDE.md,
    « UE1 engine quirks »).
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

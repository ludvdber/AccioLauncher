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

# Jeton de clé publique des assemblies CRT de Microsoft (le même pour VC8 et
# VC9). Il fait partie de l'identité forte de l'assembly : c'est ce qui
# distingue le vrai redistribuable d'un dossier homonyme.
_CRT_JETON = "1fc8b3b9a1e18e3b"


def needed_space_mb(size_mb: int) -> int:
    """Place à prévoir pour installer une archive de `size_mb` Mo.

    Le double : l'archive téléchargée cohabite avec les fichiers extraits
    jusqu'au nettoyage final. Fonction pure, partagée par la vérification au
    clic et par l'avertissement affiché en amont — les deux doivent annoncer
    le même chiffre, sinon le bandeau prévient d'un blocage qui n'arrive pas
    (ou l'inverse).
    """
    return size_mb * 2


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


def _winsxs() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "WinSxS"


@functools.cache
def check_vcredist_2005_x86() -> bool:
    """Vérifie si le Visual C++ 2005 Redistributable x86 est installé (HP7 partie 1)."""
    if sys.platform != "win32":
        return True
    return crt_x86_present(_winsxs(), "vc80")


@functools.cache
def check_vcredist_2008_x86() -> bool:
    """Vérifie si le Visual C++ 2008 Redistributable x86 est installé (HP7 partie 2)."""
    if sys.platform != "win32":
        return True
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
    """
    for verification in (check_vcredist_x86, check_vcredist_2005_x86,
                         check_vcredist_2008_x86):
        vider = getattr(verification, "cache_clear", None)
        if vider is not None:
            vider()


@functools.cache
def check_vcredist_x86() -> bool:
    """Vérifie si le Visual C++ Redistributable x86 (2015-2022) est installé."""
    if sys.platform != "win32":
        return True
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
    """
    if sys.platform != "win32":
        return False
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

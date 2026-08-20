"""Vérifications système — VC++ Redistributable, DirectX 11, etc."""

import functools
import sys

# Page officielle du redistribuable manquant. Elle vit ici, à côté du test qui
# le détecte : le correctif et le diagnostic ne doivent pas pouvoir diverger.
VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x86.exe"


def needed_space_mb(size_mb: int) -> int:
    """Place à prévoir pour installer une archive de `size_mb` Mo.

    Le double : l'archive téléchargée cohabite avec les fichiers extraits
    jusqu'au nettoyage final. Fonction pure, partagée par la vérification au
    clic et par l'avertissement affiché en amont — les deux doivent annoncer
    le même chiffre, sinon le bandeau prévient d'un blocage qui n'arrive pas
    (ou l'inverse).
    """
    return size_mb * 2


def invalidate_vcredist_cache() -> None:
    """Oublie le résultat mémorisé de `check_vcredist_x86`.

    Le cache existe parce que le test est appelé à chaque lancement de jeu.
    Mais depuis que l'absence du redistribuable est AFFICHÉE (bandeau sur la
    fiche du jeu), un résultat figé mentirait : l'utilisateur installe le
    paquet, revient dans le launcher, et l'avertissement serait toujours là.
    Appelé au retour dans la fenêtre après un clic sur « Installer ».
    """
    check_vcredist_x86.cache_clear()


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

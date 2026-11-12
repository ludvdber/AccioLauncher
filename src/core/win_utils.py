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


def noms_commencant_par(dossier: Path, debut: str) -> list[str]:
    """Les noms des entrées de `dossier` qui commencent par `debut`, casse ignorée.

    Sous Windows, c'est le système qui filtre (un motif `debut*`) : WinSxS a
    quelque 25 000 entrées, et les parcourir en Python figeait la fiche 90 ms
    au premier affichage de HP5 ou de HP7 (mesuré le 2026-10-14 ; 0,2 ms par
    le système). Ailleurs, ou si l'appel échoue, `os.scandir`. Dossier absent : [].
    """
    if sys.platform == "win32" and not any(c in debut for c in "*?"):
        try:
            noms = _noms_par_le_systeme(dossier, debut)
        except OSError:
            log.debug("Recherche par motif refusée dans %s", dossier, exc_info=True)
        else:
            # Le motif voit aussi les noms courts (8.3) : on ne garde que les longs.
            return [n for n in noms if n.lower().startswith(debut.lower())]
    try:
        with os.scandir(dossier) as entrees:
            return [e.name for e in entrees if e.name.lower().startswith(debut.lower())]
    except OSError:
        return []


def _noms_par_le_systeme(dossier: Path, debut: str) -> list[str]:
    """`FindFirstFileExW` sur `dossier\\debut*` ; OSError si l'API refuse."""
    if sys.platform != "win32":     # aussi pour mypy --platform linux
        raise OSError("Windows seulement")
    import ctypes
    from ctypes import wintypes

    class _Trouve(ctypes.Structure):          # WIN32_FIND_DATAW
        _fields_ = [("attributs", wintypes.DWORD), ("creation", wintypes.FILETIME),
                    ("acces", wintypes.FILETIME), ("ecriture", wintypes.FILETIME),
                    ("taille_haute", wintypes.DWORD), ("taille_basse", wintypes.DWORD),
                    ("reserve0", wintypes.DWORD), ("reserve1", wintypes.DWORD),
                    ("nom", wintypes.WCHAR * 260), ("nom_court", wintypes.WCHAR * 14)]

    # Une instance À NOUS : poser `argtypes` sur `ctypes.windll.kernel32`
    # changerait ces fonctions pour tout le processus.
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.FindFirstFileExW.restype = wintypes.HANDLE
    k32.FindFirstFileExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p,
                                     ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.FindNextFileW.restype = wintypes.BOOL
    k32.FindNextFileW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    k32.FindClose.argtypes = [wintypes.HANDLE]
    trouve = _Trouve()
    # 1 = FindExInfoBasic (pas de nom court à calculer), 0 = FindExSearchNameMatch.
    poignee = k32.FindFirstFileExW(str(Path(dossier) / f"{debut}*"), 1,
                                   ctypes.byref(trouve), 0, None, 0)
    if poignee in (None, wintypes.HANDLE(-1).value):
        erreur = ctypes.get_last_error()
        if erreur in (2, 3):           # rien ne correspond, ou dossier absent
            return []
        raise ctypes.WinError(erreur)
    noms = []
    try:
        while True:
            noms.append(trouve.nom)
            if not k32.FindNextFileW(poignee, ctypes.byref(trouve)):
                break
    finally:
        k32.FindClose(poignee)
    return noms


def processus_lance(nom_exe: str) -> bool:
    """Un processus nommé `nom_exe` (casse ignorée) tourne-t-il ? OSError si
    le système refuse la liste.

    La liste des processus du système (`CreateToolhelp32Snapshot`), en moins
    d'une milliseconde : `tasklist`, lancé toutes les 2 s pendant HP1 et HP2,
    figeait chaque fois le fil de l'interface (grand audit du 2026-11-02).
    """
    if sys.platform != "win32":     # aussi pour mypy --platform linux
        raise OSError("Windows seulement")
    import ctypes
    from ctypes import wintypes

    class _Entree(ctypes.Structure):
        _fields_ = [("taille", wintypes.DWORD), ("usage", wintypes.DWORD),
                    ("pid", wintypes.DWORD), ("tas", ctypes.c_size_t),
                    ("module", wintypes.DWORD), ("fils", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priorite", ctypes.c_long),
                    ("drapeaux", wintypes.DWORD), ("exe", wintypes.WCHAR * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.restype = k32.Process32NextW.restype = wintypes.BOOL
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_Entree)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    liste = k32.CreateToolhelp32Snapshot(2, 0)      # 2 = TH32CS_SNAPPROCESS
    if liste in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    voulu = nom_exe.casefold()
    entree = _Entree()
    entree.taille = ctypes.sizeof(_Entree)
    try:
        ok = k32.Process32FirstW(liste, ctypes.byref(entree))
        while ok:
            if entree.exe.casefold() == voulu:
                return True
            ok = k32.Process32NextW(liste, ctypes.byref(entree))
    finally:
        k32.CloseHandle(liste)
    return False


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


# DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND, DWMWA_BORDER_COLOR (dwmapi.h).
_DWM_COINS, _DWM_ROND, _DWM_BORDURE = 33, 2, 34


def couleur_dwm(r: int, g: int, b: int) -> int:
    """Un COLORREF : 0x00BBGGRR. Pure."""
    return (b << 16) | (g << 8) | r


def habiller_fenetre(hwnd: int, bordure: tuple[int, int, int]) -> bool:
    """Coins arrondis et trait de bord natifs de Windows 11 sur une fenêtre sans cadre.

    Une fenêtre sans cadre perd l'arrondi de Windows 11 : elle tombait en
    angles vifs à côté de toutes les autres. Le trait d'un pixel du launcher
    (`window_chrome.poser_lisere`) reste dessiné par Qt, pour Windows 10 et
    Linux ; ici, DWM dessine le sien de la même couleur, qui suit l'arrondi.
    Windows 10 refuse ces deux attributs : rien ne change, False.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    try:
        dwm = ctypes.WinDLL("dwmapi")
        coins = ctypes.c_int(_DWM_ROND)
        couleur = ctypes.c_uint(couleur_dwm(*bordure))
        rc1 = dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), _DWM_COINS,
                                        ctypes.byref(coins), ctypes.sizeof(coins))
        rc2 = dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), _DWM_BORDURE,
                                        ctypes.byref(couleur), ctypes.sizeof(couleur))
    except (OSError, AttributeError):
        return False
    return bool(rc1 == 0 and rc2 == 0)


def zone_de_travail_principale() -> tuple[int, int, float] | None:
    """Zone de travail de l'écran principal en pixels PHYSIQUES, et son échelle.

    `(largeur, hauteur, échelle)` — 1,75 à 175 % —, ou None hors Windows ou si
    une API refuse. Appelée AVANT `QApplication` (`main._plafonner_echelle`) :
    le processus n'a pas encore déclaré sa prise en charge du DPI, et Windows
    lui rendrait des coordonnées virtualisées à 96 ppp. D'où une bascule du
    SEUL fil courant en « par écran v2 » (Windows 10 1703 et après), le temps
    de la mesure, puis le retour à l'état d'avant. L'échelle est le DPI
    « effectif » de l'écran : celui que Qt lit lui-même.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class _InfoEcran(ctypes.Structure):       # MONITORINFO
        _fields_ = [("taille", wintypes.DWORD), ("ecran", wintypes.RECT),
                    ("travail", wintypes.RECT), ("drapeaux", wintypes.DWORD)]

    try:
        # Instances À NOUS, comme `_noms_par_le_systeme` : `argtypes` reste local.
        u32 = ctypes.WinDLL("user32")
        shcore = ctypes.WinDLL("shcore")
        u32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        u32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        u32.MonitorFromPoint.restype = wintypes.HMONITOR
        u32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        u32.GetMonitorInfoW.restype = wintypes.BOOL
        u32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
        shcore.GetDpiForMonitor.restype = ctypes.c_long
        shcore.GetDpiForMonitor.argtypes = [wintypes.HMONITOR, ctypes.c_int,
                                            ctypes.c_void_p, ctypes.c_void_p]
    except (OSError, AttributeError):
        return None
    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = (HANDLE)-4.
    avant = u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not avant:
        return None                    # refusé : la mesure serait virtualisée
    try:
        # 1 = MONITOR_DEFAULTTOPRIMARY : l'écran où la fenêtre s'ouvre.
        ecran = u32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
        info = _InfoEcran()
        info.taille = ctypes.sizeof(_InfoEcran)
        dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
        if not ecran or not u32.GetMonitorInfoW(ecran, ctypes.byref(info)):
            return None
        # 0 = MDT_EFFECTIVE_DPI.
        if shcore.GetDpiForMonitor(ecran, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) != 0:
            return None
    finally:
        u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(avant))
    travail = info.travail
    largeur, hauteur = travail.right - travail.left, travail.bottom - travail.top
    if largeur <= 0 or hauteur <= 0 or dpi_x.value <= 0:
        return None
    return largeur, hauteur, dpi_x.value / 96

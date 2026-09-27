"""La barre lumineuse des manettes PlayStation, aux couleurs de la maison.

Le Choixpeau répartit le joueur, le thème suit sa maison — et la manette aussi :
la DualShock 4 (et la DualSense) portent une barre de lumière que l'ordinateur
peut colorer. La manette voit qu'elle est reconnue, et sait où elle est rangée.

Ce qu'on fait, et rien d'autre : un rapport de SORTIE HID (le même que celui
qu'envoient les jeux), avec la couleur, sans vibration ni clignotement. La
manette garde la couleur jusqu'à ce qu'on la débranche ou qu'un jeu la change.

Sans pilote ni programme à installer : l'interface HID de Windows (`hid.dll`,
`setupapi.dll`), et sous Linux `/dev/hidraw*` — accessible seulement si le
système donne la manette à l'utilisateur (règles udev de Steam, courantes) ;
sinon on s'abstient en silence. Tout passe sur un fil à part et rien n'y lève :
une manette absente, occupée ou refusée n'est jamais une erreur.

Seul le rapport USB de la DualShock 4 a été VU (manette de Ludo, `054C:09CC`,
2026-09-27). DualSense et Bluetooth : écrits d'après leur format public, pas vus.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from src.core import reglages_correctif

log =logging.getLogger(__name__)

SONY = 0x054C
# DualShock 4 v1, v2, adaptateur sans fil USB ; DualSense, DualSense Edge.
DUALSHOCK4 = frozenset({0x05C4, 0x09CC, 0x0BA0})
DUALSENSE = frozenset({0x0CE6, 0x0DF2})

# Une LED n'est pas un écran : des couleurs franches, sinon le jaune vire au
# vert et l'or au blanc. Les identifiants sont ceux des thèmes (et des maisons).
COULEURS = {
    "gryffondor": (255, 16, 0),
    "serpentard": (0, 190, 40),
    "serdaigle": (0, 60, 255),
    "poufsouffle": (255, 160, 0),
    "poudlard": (255, 110, 0),
}


@dataclass(frozen=True)
class Manette:
    chemin: str        # chemin du périphérique (Windows) ou /dev/hidrawN
    pid: int
    sortie: int        # taille du rapport de sortie, en octets (identifiant compris)


def couleur(theme: str) -> tuple[int, int, int]:
    return COULEURS.get(theme, COULEURS["poudlard"])


def rapport(manette: Manette, rgb: tuple[int, int, int]) -> bytes | None:
    """Le rapport de sortie qui colore la barre, ou None si on ne sait pas le faire. Pur."""
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    if manette.pid in DUALSHOCK4 and manette.sortie == 32:
        # USB : 0x05, drapeaux (0x02 barre, 0x04 clignotement), vibrations à 0,
        # rouge vert bleu, clignotement allumé/éteint à 0 = fixe.
        buf = bytearray(32)
        buf[0], buf[1] = 0x05, 0x02 | 0x04
        buf[6], buf[7], buf[8] = r, g, b
        return bytes(buf)
    if manette.pid in DUALSENSE and manette.sortie == 48:
        # USB : 0x02 ; valid_flag1 0x04 = barre lumineuse (format de hid-playstation).
        buf = bytearray(48)
        buf[0], buf[2] = 0x02, 0x04
        buf[45], buf[46], buf[47] = r, g, b
        return bytes(buf)
    # Bluetooth (rapports 0x11 / 0x31, sommés d'un CRC) : pas encore — rien plutôt qu'un rapport faux.
    return None


# ── Windows ──

class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


class _InterfaceData(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("guid", _GUID), ("flags", ctypes.c_uint32),
                ("reserved", ctypes.c_size_t)]


class _Caps(ctypes.Structure):
    _fields_ = [("usage", ctypes.c_ushort), ("usage_page", ctypes.c_ushort), ("entree", ctypes.c_ushort),
                ("sortie", ctypes.c_ushort), ("fonction", ctypes.c_ushort), ("reserve", ctypes.c_ushort * 17),
                ("n", ctypes.c_ushort * 10)]


def _vid_pid(chemin: str) -> tuple[int, int] | None:
    bas = chemin.lower()
    try:
        vid = int(bas.split("vid_", 1)[1][:4], 16)
        pid = int(bas.split("pid_", 1)[1][:4], 16)
    except (IndexError, ValueError):
        # Bluetooth : « vid&0002054c_pid&09cc »
        try:
            vid = int(bas.split("vid&", 1)[1][4:8], 16)
            pid = int(bas.split("pid&", 1)[1][:4], 16)
        except (IndexError, ValueError):
            return None
    return vid, pid


def _manettes_windows() -> list[Manette]:
    from ctypes import wintypes as w
    hid = ctypes.WinDLL("hid")
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    setupapi.SetupDiGetClassDevsW.restype = w.HANDLE
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(_GUID), w.LPCWSTR, w.HWND, w.DWORD]
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.POINTER(_GUID), w.DWORD,
                                                      ctypes.POINTER(_InterfaceData)]
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [w.HANDLE, ctypes.POINTER(_InterfaceData), ctypes.c_void_p,
                                                           w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [w.HANDLE]
    k32.CreateFileW.restype = w.HANDLE
    k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    k32.CloseHandle.argtypes = [w.HANDLE]
    hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Caps)]

    guid = _GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    liste = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x02 | 0x10)  # PRESENT | DEVICEINTERFACE
    if not liste or liste == w.HANDLE(-1).value:
        return []
    trouvees: list[Manette] = []
    try:
        i = 0
        while True:
            data = _InterfaceData(cbSize=ctypes.sizeof(_InterfaceData))
            if not setupapi.SetupDiEnumDeviceInterfaces(liste, None, ctypes.byref(guid), i, ctypes.byref(data)):
                break
            i += 1
            taille = w.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(liste, ctypes.byref(data), None, 0, ctypes.byref(taille), None)
            if taille.value < 8:
                continue
            tampon = ctypes.create_string_buffer(taille.value)
            # cbSize de SP_DEVICE_INTERFACE_DETAIL_DATA_W : 8 en 64 bits, 6 en 32 bits.
            ctypes.c_uint32.from_buffer(tampon).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(liste, ctypes.byref(data), tampon, taille, None, None):
                continue
            chemin = ctypes.wstring_at(ctypes.addressof(tampon) + 4)
            ids = _vid_pid(chemin)
            if ids is None or ids[0] != SONY or ids[1] not in DUALSHOCK4 | DUALSENSE:
                continue
            h = k32.CreateFileW(chemin, 0x80000000 | 0x40000000, 0x1 | 0x2, None, 3, 0, None)
            if not h or h == w.HANDLE(-1).value:
                continue
            try:
                pp = ctypes.c_void_p()
                if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                    caps = _Caps()
                    hid.HidP_GetCaps(pp, ctypes.byref(caps))
                    hid.HidD_FreePreparsedData(pp)
                    trouvees.append(Manette(chemin, ids[1], caps.sortie))
            finally:
                k32.CloseHandle(h)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(liste)
    return trouvees


def _ecrire_windows(manette: Manette, donnees: bytes) -> bool:
    from ctypes import wintypes as w
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = w.HANDLE
    k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    k32.WriteFile.argtypes = [w.HANDLE, ctypes.c_char_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    k32.CloseHandle.argtypes = [w.HANDLE]
    h = k32.CreateFileW(manette.chemin, 0x40000000, 0x1 | 0x2, None, 3, 0, None)
    if not h or h == w.HANDLE(-1).value:
        return False
    try:
        ecrits = w.DWORD()
        return bool(k32.WriteFile(h, donnees, len(donnees), ctypes.byref(ecrits), None)) and ecrits.value == len(donnees)
    finally:
        k32.CloseHandle(h)


# ── Linux ──

# Taille du rapport de sortie par modèle : hidraw ne la donne pas sans analyser
# le descripteur, et elle ne dépend que du modèle et du bus.
_SORTIE_USB = {**{pid: 32 for pid in DUALSHOCK4}, **{pid: 48 for pid in DUALSENSE}}


def _manettes_linux(racine: Path = Path("/sys/class/hidraw")) -> list[Manette]:
    trouvees: list[Manette] = []
    try:
        noeuds = sorted(racine.iterdir())
    except OSError:
        return []
    for noeud in noeuds:
        try:
            uevent = (noeud / "device" / "uevent").read_text(encoding="ascii", errors="replace")
        except OSError:
            continue
        for ligne in uevent.splitlines():
            if not ligne.startswith("HID_ID="):
                continue
            try:
                bus, vid, pid = (int(x, 16) for x in ligne[7:].split(":"))
            except ValueError:
                break
            if vid == SONY and pid in _SORTIE_USB:
                # Bus 3 = USB ; en Bluetooth (5) le rapport change : pas encore géré.
                trouvees.append(Manette(f"/dev/{noeud.name}", pid, _SORTIE_USB[pid] if bus == 3 else 78))
    return trouvees


def _ecrire_linux(manette: Manette, donnees: bytes) -> bool:
    try:
        with open(manette.chemin, "wb", buffering=0) as f:
            return f.write(donnees) == len(donnees)
    except OSError:
        return False   # pas le droit (pas de règle udev) : on s'abstient


# ── Ce qu'appelle le lanceur ──

def manettes() -> list[Manette]:
    """Les manettes PlayStation branchées que l'on sait colorer."""
    try:
        return _manettes_windows() if sys.platform == "win32" else _manettes_linux()
    except (OSError, AttributeError, ValueError):
        log.debug("Manettes : énumération impossible", exc_info=True)
        return []


def colorer(theme: str) -> int:
    """Colore chaque manette aux couleurs de `theme`. Rend le nombre colorées ; ne lève jamais."""
    faites = 0
    for m in manettes():
        donnees = rapport(m, couleur(theme))
        if donnees is None:
            log.info("Manette %04X (rapport de %d octets) : barre lumineuse non gérée", m.pid, m.sortie)
            continue
        try:
            ok = _ecrire_windows(m, donnees) if sys.platform == "win32" else _ecrire_linux(m, donnees)
        except OSError:
            ok = False
        faites += ok
    if faites:
        log.info("Manette : barre lumineuse aux couleurs de « %s » (%d)", theme, faites)
    return faites


def colorer_en_fond(theme: str) -> None:
    """Même chose sur un fil à part : l'énumération HID ne doit jamais retenir la fenêtre."""
    threading.Thread(target=colorer, args=(theme,), name="barre-lumineuse", daemon=True).start()


# ── En jeu : le correctif garde la couleur ──
# Un jeu qui parle à la manette peut changer sa barre. Le `xinput1_3.dll` du
# correctif (HP5, HP6, les Reliques) lit `LightBar` dans le `d3d9.ini` du jeu et
# la repose à chaque manette qu'il ouvre — même branchée en cours de partie.

_SECTION = "Accio.Controller"


def texte_couleur(theme: str | None) -> str:
    """La valeur de `LightBar` : « r,g,b », ou vide (le correctif n'y touche pas)."""
    return ",".join(str(v) for v in couleur(theme)) if theme else ""


def preparer(executable_dir: Path, theme: str | None) -> bool:
    """Au lancement : pose la couleur de `theme` (None = ne pas toucher) dans le
    `d3d9.ini` du jeu. Seulement si le correctif a une section manette : HP4 et
    l'ancien correctif n'en ont pas, et ce n'est pas une erreur. Rend True si
    l'ini a été écrit ; ne lève jamais — le jeu démarre de toute façon."""
    ini =reglages_correctif.chemin_ini(executable_dir)
    if not ini.is_file():
        return False
    try:
        return reglages_correctif.poser_valeur(ini, _SECTION, "LightBar", texte_couleur(theme))
    except ValueError:
        return False   # pas de section [Accio.Controller]
    except OSError:
        log.warning("Manette : couleur non transmise au correctif (%s)", ini, exc_info=True)
        return False

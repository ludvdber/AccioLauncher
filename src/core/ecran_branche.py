"""L'écran branché sur la puce graphique du processeur alors qu'une vraie carte est là.

Cas réel (2026-11-18) : PC de bureau, GTX 970 + i7-6700 (Intel HD 530) sur une
carte mère qui a ses propres sorties vidéo ; HP1 et HP2 à 5 images/s, les autres
jeux corrects. Le câble de l'écran était sur la carte mère : tout passait par la
puce Intel, et la GTX 970 ne dessinait rien.

Windows seulement : DXGI dit quelle carte porte chaque écran (`EnumOutputs`).
La lecture tourne EN FOND, une fois par session (`lancer`, au démarrage) ; le
bandeau lit le résultat gardé (`carte_ignoree`), None tant qu'il n'est pas là.
Une ligne au journal dans tous les cas : les cartes vues, celle qui porte chaque
écran, la décision.

On n'avertit que si TOUS les écrans actifs sont sur une puce intégrée ET qu'une
carte dédiée n'en porte aucun. Jamais sur un portable (batterie présente) : la
puce intégrée y porte toujours l'écran et Windows bascule seul. Les adaptateurs
virtuels et logiciels ne comptent pas (`diagnostic.carte_virtuelle`).
"""

import logging
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.core import diagnostic

log = logging.getLogger(__name__)

# Sous ce seuil de mémoire propre, une carte est une puce intégrée (Intel HD : 128 Mo ;
# une APU AMD réserve jusqu'à 512 Mo) ; au-dessus, une carte dédiée (GTX 970 : 4 Go).
_DEDIEE_MIN = 1024 ** 3


@dataclass(frozen=True)
class Carte:
    nom: str
    memoire: int            # mémoire vidéo propre, en octets
    ecrans: int             # sorties branchées sur le bureau
    logicielle: bool = False


def decider(cartes: list[Carte], portable: bool) -> Carte | None:
    """La carte dédiée laissée sans écran, quand il faut avertir ; None sinon (pure)."""
    if portable:
        return None
    reelles = [c for c in cartes if not c.logicielle and not diagnostic.carte_virtuelle(c.nom)]
    avec_ecran = [c for c in reelles if c.ecrans]
    sans_ecran = [c for c in reelles if not c.ecrans and c.memoire >= _DEDIEE_MIN]
    if not avec_ecran or not sans_ecran:
        return None
    if any(c.memoire >= _DEDIEE_MIN for c in avec_ecran):
        return None
    return max(sans_ecran, key=lambda c: c.memoire)


def signature(carte: Carte | None) -> str:
    """Ce qui identifie la situation : « fermé » ne vaut que tant qu'elle ne change pas."""
    return "" if carte is None else carte.nom


_resultat: Carte | None = None
_fini = False
_fil: threading.Thread | None = None


def carte_ignoree() -> Carte | None:
    """Le résultat de la détection en fond ; None tant qu'elle n'a pas fini, ou si tout va bien."""
    return _resultat


def terminee() -> bool:
    """La détection a-t-elle rendu son verdict ? (None d'avant n'est alors plus « pas encore »)."""
    return _fini


def lancer() -> None:
    """Démarre la détection en fond, une seule fois par session. Rien hors Windows."""
    global _fil
    if sys.platform != "win32" or _fil is not None:
        return
    _fil = threading.Thread(target=_detecter, daemon=True, name="ecran-branche")
    _fil.start()


def _detecter() -> None:
    global _resultat, _fini
    try:
        cartes = _cartes_dxgi()
        portable = _sur_batterie_possible()
    except OSError as exc:
        # Sans lecture, on ne sait pas : rien à dire, et rien à oublier non plus.
        log.info("Écran et carte graphique : lecture impossible (%s), rien à signaler", exc)
        return
    _resultat = decider(cartes, portable)
    _fini = True
    vues = " ; ".join(
        f"{c.nom} ({c.memoire // 1024 ** 2} Mo, {c.ecrans} écran(s)"
        f"{', logicielle' if c.logicielle else ''}"
        f"{', virtuelle' if diagnostic.carte_virtuelle(c.nom) else ''})" for c in cartes)
    decision = (f"écran sur la puce intégrée, {_resultat.nom} sans écran : avertir"
                if _resultat is not None
                else "portable : rien" if portable else "rien à signaler")
    log.info("Écran et carte graphique : %s ; décision : %s", vues or "aucune carte", decision)


def _sur_batterie_possible() -> bool:
    """Une batterie est-elle présente ? (portable). Non si Windows ne sait pas."""
    if sys.platform != "win32":
        return False
    import ctypes

    class _Etat(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    etat = _Etat()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(etat)):
        return False
    # 128 : pas de batterie ; 255 : état inconnu.
    return etat.BatteryFlag not in (128, 255)


def _cartes_dxgi() -> list[Carte]:
    """Chaque adaptateur DXGI : nom, mémoire propre, écrans branchés. OSError si DXGI manque."""
    if sys.platform != "win32":
        raise OSError("DXGI : Windows seulement")
    import ctypes
    from ctypes import wintypes

    class _Guid(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort),
                    ("d", ctypes.c_ubyte * 8)]

    class _DescAdaptateur(ctypes.Structure):     # DXGI_ADAPTER_DESC1
        _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", ctypes.c_uint),
                    ("DeviceId", ctypes.c_uint), ("SubSysId", ctypes.c_uint),
                    ("Revision", ctypes.c_uint), ("DedicatedVideoMemory", ctypes.c_size_t),
                    ("DedicatedSystemMemory", ctypes.c_size_t),
                    ("SharedSystemMemory", ctypes.c_size_t), ("LuidBas", wintypes.DWORD),
                    ("LuidHaut", ctypes.c_long), ("Flags", ctypes.c_uint)]

    class _DescSortie(ctypes.Structure):          # DXGI_OUTPUT_DESC
        _fields_ = [("DeviceName", ctypes.c_wchar * 32), ("Coordonnees", wintypes.RECT),
                    ("AttachedToDesktop", wintypes.BOOL), ("Rotation", ctypes.c_uint),
                    ("Monitor", wintypes.HANDLE)]

    def methode(objet: ctypes.c_void_p, rang: int, *types: Any) -> Callable[..., int]:
        vtable = ctypes.cast(objet, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vtable[rang])

    def liberer(objet: ctypes.c_void_p) -> None:
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
            ctypes.cast(objet, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[2])(objet)

    # IID_IDXGIFactory1 {770aae78-f26f-4dba-a829-253c83d1b387}
    iid = _Guid(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(
        0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    fabrique = ctypes.c_void_p()
    try:
        dxgi = ctypes.WinDLL("dxgi.dll")
    except OSError as exc:
        raise OSError(f"dxgi.dll : {exc}") from exc
    if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(fabrique)) != 0 or not fabrique:
        raise OSError("CreateDXGIFactory1 a échoué")
    _LOGICIELLE = 2                               # DXGI_ADAPTER_FLAG_SOFTWARE
    cartes: list[Carte] = []
    try:
        for i in range(16):
            adaptateur = ctypes.c_void_p()
            # IDXGIFactory1::EnumAdapters1 (rang 12) ; DXGI_ERROR_NOT_FOUND à la fin.
            enum_adapt = methode(fabrique, 12, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
            if enum_adapt(fabrique, i, ctypes.byref(adaptateur)) != 0 or not adaptateur:
                break
            try:
                desc = _DescAdaptateur()
                # IDXGIAdapter1::GetDesc1 (rang 10)
                if methode(adaptateur, 10, ctypes.POINTER(_DescAdaptateur))(
                        adaptateur, ctypes.byref(desc)) != 0:
                    continue
                ecrans = 0
                for j in range(16):
                    sortie = ctypes.c_void_p()
                    # IDXGIAdapter::EnumOutputs (rang 7)
                    if methode(adaptateur, 7, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(
                            adaptateur, j, ctypes.byref(sortie)) != 0 or not sortie:
                        break
                    try:
                        dsortie = _DescSortie()
                        # IDXGIOutput::GetDesc (rang 7)
                        if methode(sortie, 7, ctypes.POINTER(_DescSortie))(
                                sortie, ctypes.byref(dsortie)) == 0 and dsortie.AttachedToDesktop:
                            ecrans += 1
                    finally:
                        liberer(sortie)
                cartes.append(Carte(nom=desc.Description.strip(),
                                    memoire=int(desc.DedicatedVideoMemory), ecrans=ecrans,
                                    logicielle=bool(desc.Flags & _LOGICIELLE)))
            finally:
                liberer(adaptateur)
    finally:
        liberer(fabrique)
    return cartes

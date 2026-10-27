"""« Jouer à … » dans la liste de raccourcis de l'icône Windows (clic droit sur la barre des tâches).

Les jeux installés joués en dernier, cinq au plus : un clic lance le launcher avec
`--jouer <id>` (ou le relaie à celui qui est ouvert, `single_instance`), qui ouvre
la fiche et appuie sur JOUER. Écrit avec ICustomDestinationList, en appels COM
bruts par ctypes comme `win_taskbar` ; rien hors Windows, et aucune erreur COM
ne remonte : une liste qui ne s'écrit pas laisse l'icône comme elle était.

`entrees` est pure (testée) ; `ecrire` fait le COM.
"""

import logging
import sys
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.game_manager import GameManager

log = logging.getLogger(__name__)

ARGUMENT = "--jouer"
MAX_ENTREES = 5
APP_ID = "ASTeam.AccioLauncher"   # celui de main.py (SetCurrentProcessExplicitAppUserModelID)


@dataclass(frozen=True)
class Entree:
    titre: str
    programme: str
    arguments: str
    icone: str


def commande(game_id: str, executable: str, gele: bool, script: Path | None) -> tuple[str, str]:
    """(programme, arguments) qui relancent le launcher sur ce jeu.

    L'exe de PyInstaller se relance lui-même ; depuis les sources, Python et
    `main.py`. Chaque chemin entre guillemets : `Program Files` a un espace.
    """
    if gele or script is None:
        return executable, f"{ARGUMENT} {game_id}"
    return executable, f'"{script}" {ARGUMENT} {game_id}'


def entrees(jeux: Iterable[tuple[str, str, str | None]], titre: Callable[[str], str], executable: str,
            gele: bool, script: Path | None) -> list[Entree]:
    """Les entrées de la liste, les plus récentes d'abord.

    `jeux` : (id, nom, dernière partie au format ISO ou None) des jeux INSTALLÉS.
    Un jeu jamais lancé ne vient qu'après ceux qui l'ont été, dans l'ordre du
    catalogue. `titre` met le nom en phrase (« Jouer à {} », traduit).
    """
    tous = list(jeux)
    # Tri stable, même à l'envers : à date égale, l'ordre du catalogue reste.
    joues = sorted((j for j in tous if j[2]), key=lambda j: j[2] or "", reverse=True)
    choisis = (joues + [j for j in tous if not j[2]])[:MAX_ENTREES]
    icone = executable if gele else ""
    return [Entree(titre(nom), *commande(gid, executable, gele, script), icone) for gid, nom, _ in choisis]


def id_demande(argv: list[str]) -> str | None:
    """L'identifiant passé après `--jouer`, s'il est sain (lettres, chiffres, tirets)."""
    if ARGUMENT not in argv:
        return None
    i = argv.index(ARGUMENT)
    if i + 1 >= len(argv):
        return None
    gid = argv[i + 1]
    return gid if gid and len(gid) <= 32 and all(c.isalnum() or c in "-_" for c in gid) else None


_actif = False


def activer() -> None:
    """Par main.py seulement : la suite de tests construit des fenêtres et ne doit jamais écrire sur l'icône."""
    global _actif
    _actif = True


def mettre_a_jour(manager: GameManager) -> None:
    """Réécrit la liste d'après les jeux installés, dans un fil : le COM du Shell ne retient pas l'interface."""
    if not _actif or sys.platform != "win32":
        return
    from src.core.i18n import tr

    jeux = [(e.game.id, e.game.name, manager.last_played(e.game.id))
            for e in manager.get_games() if manager.is_installed(e.game.id)]
    gele = bool(getattr(sys, "frozen", False))
    script = None if gele else Path(sys.argv[0]).resolve()
    liste = entrees(jeux, lambda nom: tr("Jouer à {}").format(nom), sys.executable, gele, script)
    threading.Thread(target=ecrire, args=(liste,), name="liste-saut", daemon=True).start()


# ── COM ──

_CLSID_DESTINATION_LIST = "{77F10CF0-3DB5-4966-B520-B7C54FD35ED6}"
_IID_ICUSTOM_DESTINATION_LIST = "{6332DEBF-87B5-4670-90C0-5E57B408A49E}"
_CLSID_COLLECTION = "{2D3468C1-36A7-43B6-AC24-D3F02FD9607A}"
_IID_IOBJECT_COLLECTION = "{5632B1A4-E38A-400A-928A-D4CD63230295}"
_IID_IOBJECT_ARRAY = "{92CA9DCD-5622-4BBA-A805-5E9F541BD8C9}"
_CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
_IID_ISHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPROPERTY_STORE = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
_FMTID_TITRE = "{F29F85E0-4FF9-1068-AB91-08002B27B3D9}"   # PKEY_Title, pid 2

# Entrées de vtable (0-2 : IUnknown).
_LISTE_SET_APP_ID, _LISTE_BEGIN, _LISTE_TACHES, _LISTE_COMMIT = 3, 4, 7, 8
_LIEN_DESCRIPTION, _LIEN_ARGUMENTS, _LIEN_ICONE, _LIEN_CHEMIN = 7, 11, 17, 20
_PROPRIETES_SET, _PROPRIETES_COMMIT = 6, 7
_COLLECTION_AJOUTER = 5


def ecrire(liste: list[Entree]) -> bool:
    """Remplace la liste de l'icône par ces entrées ; False si Windows a refusé, sans lever."""
    if sys.platform != "win32":
        return False
    try:
        _ecrire(liste)
        return True
    except Exception as exc:  # COM peut échouer de mille façons — jamais bloquant
        log.debug("Liste de raccourcis non écrite : %s", exc)
        return False


def _ecrire(liste: list[Entree]) -> None:
    import ctypes

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]

    class _PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]

    class _PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                    ("r3", ctypes.c_ushort), ("pwsz", ctypes.c_wchar_p), ("pad", ctypes.c_void_p)]

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)

    def guid(texte: str) -> _GUID:
        g = _GUID()
        ole32.CLSIDFromString(texte, ctypes.byref(g))
        return g

    def methode(objet: ctypes.c_void_p, index: int, *types: type) -> Callable[..., int]:
        vtable = ctypes.cast(ctypes.c_void_p(ctypes.cast(objet, ctypes.POINTER(ctypes.c_void_p))[0]),
                             ctypes.POINTER(ctypes.c_void_p))
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vtable[index])

    def verifier(hr: int, quoi: str) -> None:
        if hr != 0:
            raise OSError(f"{quoi} → HRESULT {hr & 0xFFFFFFFF:#010x}")

    def creer(clsid: str, iid: str) -> ctypes.c_void_p:
        objet = ctypes.c_void_p()
        verifier(ole32.CoCreateInstance(ctypes.byref(guid(clsid)), None, 1, ctypes.byref(guid(iid)),
                                        ctypes.byref(objet)), f"CoCreateInstance {clsid}")
        return objet

    def demander(objet: ctypes.c_void_p, iid: str) -> ctypes.c_void_p:
        autre = ctypes.c_void_p()
        verifier(methode(objet, 0, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(
            objet, ctypes.byref(guid(iid)), ctypes.byref(autre)), f"QueryInterface {iid}")
        return autre

    def liberer(objet: ctypes.c_void_p) -> None:
        if objet.value:
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
                ctypes.cast(ctypes.c_void_p(ctypes.cast(objet, ctypes.POINTER(ctypes.c_void_p))[0]),
                            ctypes.POINTER(ctypes.c_void_p))[2])(objet)

    a_liberer: list[ctypes.c_void_p] = []
    try:
        dest = creer(_CLSID_DESTINATION_LIST, _IID_ICUSTOM_DESTINATION_LIST)
        a_liberer.append(dest)
        verifier(methode(dest, _LISTE_SET_APP_ID, ctypes.c_wchar_p)(dest, APP_ID), "SetAppID")
        places, retires = ctypes.c_uint(), ctypes.c_void_p()
        verifier(methode(dest, _LISTE_BEGIN, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(_GUID),
                         ctypes.POINTER(ctypes.c_void_p))(
            dest, ctypes.byref(places), ctypes.byref(guid(_IID_IOBJECT_ARRAY)), ctypes.byref(retires)), "BeginList")
        a_liberer.append(retires)
        collection = creer(_CLSID_COLLECTION, _IID_IOBJECT_COLLECTION)
        a_liberer.append(collection)
        for e in liste:
            lien = creer(_CLSID_SHELL_LINK, _IID_ISHELL_LINK_W)
            a_liberer.append(lien)
            verifier(methode(lien, _LIEN_CHEMIN, ctypes.c_wchar_p)(lien, e.programme), "SetPath")
            verifier(methode(lien, _LIEN_ARGUMENTS, ctypes.c_wchar_p)(lien, e.arguments), "SetArguments")
            verifier(methode(lien, _LIEN_DESCRIPTION, ctypes.c_wchar_p)(lien, e.titre), "SetDescription")
            if e.icone:
                verifier(methode(lien, _LIEN_ICONE, ctypes.c_wchar_p, ctypes.c_int)(lien, e.icone, 0),
                         "SetIconLocation")
            proprietes = demander(lien, _IID_IPROPERTY_STORE)
            a_liberer.append(proprietes)
            cle = _PROPERTYKEY(guid(_FMTID_TITRE), 2)
            valeur = _PROPVARIANT(31, 0, 0, 0, e.titre, None)   # VT_LPWSTR, la chaîne reste à Python
            verifier(methode(proprietes, _PROPRIETES_SET, ctypes.POINTER(_PROPERTYKEY),
                             ctypes.POINTER(_PROPVARIANT))(proprietes, ctypes.byref(cle), ctypes.byref(valeur)),
                     "SetValue(Title)")
            verifier(methode(proprietes, _PROPRIETES_COMMIT)(proprietes), "Commit")
            verifier(methode(collection, _COLLECTION_AJOUTER, ctypes.c_void_p)(collection, lien), "AddObject")
        tableau = demander(collection, _IID_IOBJECT_ARRAY)
        a_liberer.append(tableau)
        if liste:
            verifier(methode(dest, _LISTE_TACHES, ctypes.c_void_p)(dest, tableau), "AddUserTasks")
        verifier(methode(dest, _LISTE_COMMIT)(dest), "CommitList")
    finally:
        for objet in reversed(a_liberer):
            liberer(objet)

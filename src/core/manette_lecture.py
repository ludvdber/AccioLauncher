"""Lire la manette pour naviguer dans le launcher, sans se lever pour la souris.

Le launcher se pilote déjà au clavier (flèches, Tab, Entrée, Échap) : la
manette n'invente rien, elle PRODUIT ces touches (`src/ui/manette_nav.py`).
Ce module-ci ne fait que lire, et ne touche à aucun widget : la logique se
teste sans manette ni Qt.

Lecture, sans pilote ni programme à installer :
- Windows : WinMM (`joyGetPosEx`), qui voit TOUTES les manettes, PlayStation
  comprises, là où XInput ne voit que les Xbox. Mesuré le 2026-10-03 sur la DS4
  de Ludo : 2 µs par appel, 17 ms au tout premier (d'où `prechauffer`) ; un
  emplacement vide répond `JOYERR_UNPLUGGED` en 16 µs.
- Linux : `/dev/input/js*`, lu sans attendre. Les numéros de boutons y suivent
  l'ordre des codes evdev (sud, est, nord, ouest, L1, R1…) pour `xpad` comme
  pour `hid-playstation` : croix et A valent 0 tous les deux. Les axes se
  retrouvent par leur code (`JSIOCGAXMAP`), pas par leur rang. Un périphérique
  refusé (droits) : abstention muette.

Numéros WinMM VUS sur la DS4 de Ludo (054C:09CC, 2026-10-03) : carré 1, croix 2,
rond 3, triangle 4, L1 5, R1 6 ; croix directionnelle sur le POV ; stick droit
vertical sur R. Une manette Xbox (disposition documentée de Windows, PAS VUE) :
A 1, B 2, LB 5, RB 6. Toute autre manette suit la disposition Xbox : le bouton 1
valide, le 2 revient.
"""

from __future__ import annotations

import ctypes
import logging
import os
import struct
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Les actions, dans les mots du launcher. Les directions répètent quand on les
# tient (comme une touche du clavier) ; les autres ne partent qu'à l'appui.
VALIDER = "valider"
RETOUR = "retour"
HAUT, BAS, GAUCHE, DROITE = "haut", "bas", "gauche", "droite"
PRECEDENT, SUIVANT = "precedent", "suivant"
DIRECTIONS = frozenset({HAUT, BAS, GAUCHE, DROITE})

SONY = 0x054C

# Stick : une direction s'allume au-delà de 60 % de la course et ne s'éteint
# qu'en deçà de 40 % — sans cet écart, un stick tenu près du seuil
# clignoterait et ferait défiler les jeux tout seul.
SEUIL_ALLUME = 0.60
SEUIL_ETEINT = 0.40
# Stick droit : rien sous 25 % (un stick au repos n'est jamais à zéro : la DS4
# de Ludo reposait à 31 743 sur 65 535, soit -3 %).
ZONE_MORTE_DEFILEMENT = 0.25


@dataclass(frozen=True)
class Etat:
    """Ce que la manette dit À L'INSTANT, dans les mots du launcher."""
    appuis: frozenset[str] = frozenset()
    stick_x: float = 0.0          # stick gauche, -1 (gauche) … 1 (droite)
    stick_y: float = 0.0          # stick gauche, -1 (haut) … 1 (bas)
    defilement: float = 0.0       # stick droit vertical, -1 (haut) … 1 (bas)


def fusionner(etats: list[Etat]) -> Etat:
    """Plusieurs manettes branchées : chacune peut naviguer."""
    if not etats:
        return Etat()
    if len(etats) == 1:
        return etats[0]

    def plus_fort(valeurs):
        return max(valeurs, key=abs)
    return Etat(
        appuis=frozenset().union(*(e.appuis for e in etats)),
        stick_x=plus_fort(e.stick_x for e in etats),
        stick_y=plus_fort(e.stick_y for e in etats),
        defilement=plus_fort(e.defilement for e in etats),
    )


def directions_du_stick(x: float, y: float, avant: frozenset[str]) -> frozenset[str]:
    """La direction que montre le stick gauche, une seule à la fois.

    L'axe le plus poussé l'emporte : en diagonale, le launcher ne saurait pas
    quoi faire de deux flèches à la fois. `avant` donne l'hystérésis.
    """
    axe_x = abs(x) >= abs(y)
    valeur = x if axe_x else y
    direction = (DROITE if valeur > 0 else GAUCHE) if axe_x else (BAS if valeur > 0 else HAUT)
    seuil = SEUIL_ETEINT if direction in avant else SEUIL_ALLUME
    return frozenset({direction}) if abs(valeur) >= seuil else frozenset()


def defilement_utile(valeur: float) -> float:
    """Le stick droit, zone morte retirée, rendu entre -1 et 1."""
    if abs(valeur) < ZONE_MORTE_DEFILEMENT:
        return 0.0
    signe = 1.0 if valeur > 0 else -1.0
    return signe * (abs(valeur) - ZONE_MORTE_DEFILEMENT) / (1.0 - ZONE_MORTE_DEFILEMENT)


@dataclass
class Repetition:
    """Transforme des états successifs en actions, comme un clavier.

    Une action part à l'APPUI (jamais au relâchement) ; une direction tenue
    repart après `DELAI`, puis toutes les `CADENCE` secondes. `reprendre`
    oublie ce qui est déjà enfoncé : au retour d'un jeu, le bouton qu'on tenait
    encore ne doit pas agir dans le launcher.
    """
    DELAI = 0.40
    CADENCE = 0.11
    _tenus: frozenset[str] = frozenset()
    _stick: frozenset[str] = frozenset()
    _prochaine: dict[str, float] = field(default_factory=dict)

    def reprendre(self, etat: Etat) -> None:
        self._stick = directions_du_stick(etat.stick_x, etat.stick_y, frozenset())
        # Noté comme déjà tenu : pas de front, et sans échéance, pas de répétition.
        self._tenus = etat.appuis | self._stick
        self._prochaine = {}

    def actions(self, etat: Etat, maintenant: float) -> list[str]:
        self._stick = directions_du_stick(etat.stick_x, etat.stick_y, self._stick)
        tenus = etat.appuis | self._stick
        faites: list[str] = []
        for action in sorted(tenus):
            if action not in self._tenus:
                faites.append(action)
                if action in DIRECTIONS:
                    self._prochaine[action] = maintenant + self.DELAI
            elif action in DIRECTIONS and maintenant >= self._prochaine.get(action, maintenant + 1):
                faites.append(action)
                self._prochaine[action] = maintenant + self.CADENCE
        for action in self._tenus - tenus:
            self._prochaine.pop(action, None)
        self._tenus = tenus
        return faites


# ──────────────────── Windows : WinMM ────────────────────

JOY_RETURNALL = 0xFF
JOYERR_NOERROR = 0
POV_CENTRE = 0xFFFF


class _JOYINFOEX(ctypes.Structure):
    _fields_ = [(nom, ctypes.c_uint32) for nom in (
        "dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos", "dwUpos", "dwVpos",
        "dwButtons", "dwButtonNumber", "dwPOV", "dwReserved1", "dwReserved2")]


class _JOYCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", ctypes.c_uint16), ("wPid", ctypes.c_uint16),
        ("szPname", ctypes.c_wchar * 32),
        ("wXmin", ctypes.c_uint32), ("wXmax", ctypes.c_uint32),
        ("wYmin", ctypes.c_uint32), ("wYmax", ctypes.c_uint32),
        ("wZmin", ctypes.c_uint32), ("wZmax", ctypes.c_uint32),
        ("wNumButtons", ctypes.c_uint32),
        ("wPeriodMin", ctypes.c_uint32), ("wPeriodMax", ctypes.c_uint32),
        ("wRmin", ctypes.c_uint32), ("wRmax", ctypes.c_uint32),
        ("wUmin", ctypes.c_uint32), ("wUmax", ctypes.c_uint32),
        ("wVmin", ctypes.c_uint32), ("wVmax", ctypes.c_uint32),
        ("wCaps", ctypes.c_uint32), ("wMaxAxes", ctypes.c_uint32),
        ("wNumAxes", ctypes.c_uint32), ("wMaxButtons", ctypes.c_uint32),
        ("szRegKey", ctypes.c_wchar * 32), ("szOEMVxD", ctypes.c_wchar * 260),
    ]


@dataclass(frozen=True)
class Disposition:
    """Quels bits de `dwButtons` portent quelle action."""
    valider: int
    retour: int
    precedent: int = 4      # L1 / LB
    suivant: int = 5        # R1 / RB


PLAYSTATION = Disposition(valider=1, retour=2)    # croix 2, rond 3 (bits 1, 2)
XBOX = Disposition(valider=0, retour=1)           # A 1, B 2


def _normaliser(valeur: int, mini: int, maxi: int) -> float:
    if maxi <= mini:
        return 0.0
    return max(-1.0, min(1.0, (valeur - mini) * 2.0 / (maxi - mini) - 1.0))


def directions_du_pov(pov: int) -> frozenset[str]:
    """La croix directionnelle, en centièmes de degré depuis le haut (0xFFFF : rien).

    Une diagonale compte pour la direction la plus proche (un pouce posé de
    travers ne doit pas changer de jeu ET de bouton) ; 45° pile vont au sens
    des aiguilles d'une montre.
    """
    if pov == POV_CENTRE or pov >= 36000:
        return frozenset()
    return frozenset({(HAUT, DROITE, BAS, GAUCHE)[((pov + 4500) // 9000) % 4]})


def etat_winmm(info: _JOYINFOEX, caps: _JOYCAPSW, disposition: Disposition) -> Etat:
    """Un relevé WinMM rendu dans les mots du launcher. Pur : testable sans manette."""
    boutons = info.dwButtons
    appuis = set(directions_du_pov(info.dwPOV))
    for action, bit in ((VALIDER, disposition.valider), (RETOUR, disposition.retour),
                        (PRECEDENT, disposition.precedent), (SUIVANT, disposition.suivant)):
        if boutons & (1 << bit):
            appuis.add(action)
    return Etat(
        appuis=frozenset(appuis),
        stick_x=_normaliser(info.dwXpos, caps.wXmin, caps.wXmax),
        stick_y=_normaliser(info.dwYpos, caps.wYmin, caps.wYmax),
        defilement=_normaliser(info.dwRpos, caps.wRmin, caps.wRmax),
    )


class LecteurWindows:
    """Les manettes WinMM. Les emplacements sont re-sondés chaque seconde
    (une manette branchée en cours de route) ; entre-temps, seuls les
    emplacements occupés sont lus."""
    EMPLACEMENTS = 16
    RESONDE = 1.0

    def __init__(self) -> None:
        self._winmm = ctypes.WinDLL("winmm")
        self._manettes: dict[int, tuple[_JOYCAPSW, Disposition]] = {}
        self._sonde_a = -1.0
        self._verrou = threading.Lock()

    def _lire_un(self, ident: int) -> _JOYINFOEX | None:
        info = _JOYINFOEX(ctypes.sizeof(_JOYINFOEX), JOY_RETURNALL)
        if self._winmm.joyGetPosEx(ident, ctypes.byref(info)) != JOYERR_NOERROR:
            return None
        return info

    def _sonder(self) -> None:
        trouvees: dict[int, tuple[_JOYCAPSW, Disposition]] = {}
        for ident in range(self.EMPLACEMENTS):
            if self._lire_un(ident) is None:
                continue
            connue = self._manettes.get(ident)
            if connue is not None:
                trouvees[ident] = connue
                continue
            caps = _JOYCAPSW()
            if self._winmm.joyGetDevCapsW(ident, ctypes.byref(caps), ctypes.sizeof(caps)):
                continue
            disposition = PLAYSTATION if caps.wMid == SONY else XBOX
            log.info("Manette %d : %04X:%04X, %d boutons, navigation %s", ident, caps.wMid,
                     caps.wPid, caps.wNumButtons,
                     "PlayStation" if disposition is PLAYSTATION else "Xbox")
            trouvees[ident] = (caps, disposition)
        self._manettes = trouvees

    def prechauffer(self) -> None:
        """Le premier appel de WinMM coûte 17 ms : à payer hors du fil de l'interface."""
        with self._verrou:
            self._sonder()

    def nombre(self) -> int:
        return len(self._manettes)

    def lire(self, maintenant: float) -> Etat:
        with self._verrou:
            if maintenant - self._sonde_a >= self.RESONDE:
                self._sonde_a = maintenant
                self._sonder()
            etats = []
            for ident, (caps, disposition) in list(self._manettes.items()):
                info = self._lire_un(ident)
                if info is None:
                    del self._manettes[ident]   # débranchée : le prochain sondage la reverra
                    continue
                etats.append(etat_winmm(info, caps, disposition))
            return fusionner(etats)


# ──────────────────── Linux : /dev/input/js* ────────────────────

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
_EVENEMENT = struct.Struct("<IhBB")        # temps, valeur, type, numéro
JSIOCGAXMAP = 0x80406A32                   # _IOR('j', 0x32, __u8[ABS_CNT = 0x40])
ABS_X, ABS_Y, ABS_RY = 0x00, 0x01, 0x04
ABS_HAT0X, ABS_HAT0Y = 0x10, 0x11
# Boutons dans l'ordre evdev : BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR.
_BOUTONS_JS = {0: VALIDER, 1: RETOUR, 4: PRECEDENT, 5: SUIVANT}


@dataclass
class ManetteJs:
    """Une manette `/dev/input/jsN` : ce qu'on en sait, mis à jour à chaque événement."""
    axes: dict[int, int]                 # rang de l'axe → code ABS_*
    boutons: dict[int, bool] = field(default_factory=dict)
    valeurs: dict[int, int] = field(default_factory=dict)     # code ABS_* → valeur

    def appliquer(self, donnees: bytes) -> None:
        """Des événements bruts, tels que `read` les rend. Pur : testable sans manette."""
        utile = len(donnees) - len(donnees) % _EVENEMENT.size
        for _temps, valeur, type_, numero in _EVENEMENT.iter_unpack(donnees[:utile]):
            type_ &= ~JS_EVENT_INIT
            if type_ == JS_EVENT_BUTTON:
                self.boutons[numero] = bool(valeur)
            elif type_ == JS_EVENT_AXIS and numero in self.axes:
                self.valeurs[self.axes[numero]] = valeur

    def etat(self) -> Etat:
        appuis = {action for numero, action in _BOUTONS_JS.items() if self.boutons.get(numero)}
        hat_x, hat_y = self.valeurs.get(ABS_HAT0X, 0), self.valeurs.get(ABS_HAT0Y, 0)
        if hat_x:                       # une diagonale : l'horizontale l'emporte
            appuis.add(DROITE if hat_x > 0 else GAUCHE)
        elif hat_y:
            appuis.add(BAS if hat_y > 0 else HAUT)
        return Etat(
            appuis=frozenset(appuis),
            stick_x=self.valeurs.get(ABS_X, 0) / 32767,
            stick_y=self.valeurs.get(ABS_Y, 0) / 32767,
            defilement=self.valeurs.get(ABS_RY, 0) / 32767,
        )


class LecteurLinux:
    RESONDE = 1.0

    def __init__(self, dossier: Path = Path("/dev/input")) -> None:
        self._dossier = dossier
        self._ouvertes: dict[str, tuple[int, ManetteJs]] = {}
        self._refusees: set[str] = set()
        self._sonde_a = -1.0
        self._verrou = threading.Lock()

    def _ouvrir(self, chemin: Path) -> None:
        try:
            # O_BINARY : sans effet sous Linux, mais la suite lit aussi un faux js sous Windows.
            fd = os.open(chemin, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        except OSError:
            self._refusees.add(str(chemin))     # droits : on n'insiste pas
            return
        axes: dict[int, int] = {}
        try:
            import fcntl
            carte = bytearray(0x40)
            fcntl.ioctl(fd, JSIOCGAXMAP, carte)
            axes = {rang: code for rang, code in enumerate(carte)}
        except (OSError, ImportError):
            axes = {0: ABS_X, 1: ABS_Y}         # sans la carte, le stick gauche suffit
        log.info("Manette %s ouverte pour la navigation", chemin.name)
        self._ouvertes[str(chemin)] = (fd, ManetteJs(axes=axes))

    def _sonder(self) -> None:
        try:
            presents = {str(p) for p in self._dossier.glob("js*")}
        except OSError:
            presents = set()
        for chemin in list(self._ouvertes):
            if chemin not in presents:
                os.close(self._ouvertes.pop(chemin)[0])
        self._refusees &= presents
        for chemin in sorted(presents - set(self._ouvertes) - self._refusees):
            self._ouvrir(Path(chemin))

    def prechauffer(self) -> None:
        with self._verrou:
            self._sonder()

    def nombre(self) -> int:
        return len(self._ouvertes)

    def lire(self, maintenant: float) -> Etat:
        with self._verrou:
            if maintenant - self._sonde_a >= self.RESONDE:
                self._sonde_a = maintenant
                self._sonder()
            etats = []
            for chemin, (fd, manette) in list(self._ouvertes.items()):
                try:
                    while donnees := os.read(fd, _EVENEMENT.size * 64):
                        manette.appliquer(donnees)
                except BlockingIOError:
                    pass
                except OSError:                 # débranchée entre deux sondages
                    os.close(fd)
                    del self._ouvertes[chemin]
                    continue
                etats.append(manette.etat())
            return fusionner(etats)


class LecteurMuet:
    """Ni WinMM ni /dev/input : aucune manette, jamais d'erreur."""
    def prechauffer(self) -> None:
        pass

    def nombre(self) -> int:
        return 0

    def lire(self, maintenant: float) -> Etat:
        return Etat()


def lecteur():
    """Le lecteur de la plateforme. Ne lève jamais."""
    try:
        if sys.platform == "win32":
            return LecteurWindows()
        if sys.platform.startswith("linux"):
            return LecteurLinux()
    except OSError as exc:
        log.info("Navigation à la manette indisponible : %s", exc)
    return LecteurMuet()

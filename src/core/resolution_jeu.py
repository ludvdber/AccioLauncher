"""La taille de l'image de HP1, HP2 et HP4 à HP6 : la plus grande que l'écran permet, ou celle
choisie. Et le plein écran de HP3 à la taille de l'écran entier (`appliquer_plein_ecran`).

HP4 à HP6 (2026-11-13) : la taille va dans l'ini de leur correctif, choisie parmi les
modes de l'écran (`modes_ecran` : HP5 et HP6 s'arrêtent au démarrage sur une taille
que la carte n'affiche pas), et le rang de résolution du menu de HP5 et HP6 est remis
à 0 dans le registre (`Resolution.registre`). Leur correctif suréchantillonne ENSUITE
cette taille (`SSAAFactor`) : la taille choisie ici est celle de l'écran, le
suréchantillonnage n'y change rien.

Règles (mesures et récit : ARCHITECTURE_CORE.md) :

- les clés viennent du CATALOGUE (`resolution`, `[WinDrv.WindowsClient]
  WindowedViewportX/Y` chez HP1 et HP2), pas d'ici ;
- **écrite à CHAQUE lancement**, comme les `ini_patches` : Alt+Entrée et le
  menu vidéo du jeu changent ces clés ;
- **jamais le plein écran** (`StartupFullscreen` n'est pas touché) ;
- par défaut, l'écran entier quand le correctif remplit l'écran (`FillScreen`,
  `place_pour`), sinon la zone de travail moins le cadre de la fenêtre
  (`AdjustWindowRectExForDpi`) ;
- **jamais plus grand que la place disponible** : on replie, sans effacer le
  choix, qui revaudra sur le grand écran.
"""

import logging
import re
import sys
from collections.abc import Iterable
from pathlib import Path, PureWindowsPath

from src.core import game_registry as registre
from src.core import reglages_correctif
from src.core.config import Config
from src.core.catalogue_blocs import ChoixRegistre, IniPatch, Resolution
from src.core.game_data import GameData
from src.core.pre_launch import ecrire_cle_ini, resolve_safe_path

log = logging.getLogger(__name__)

# Les tailles proposées en plus de « celle de l'écran », de la plus grande à la
# plus petite. Seules celles qui tiennent dans l'écran sont montrées.
COURANTES: tuple[tuple[int, int], ...] = (
    (3840, 2160), (3440, 1440), (2560, 1600), (2560, 1440), (2560, 1080),
    (1920, 1200), (1920, 1080), (1680, 1050), (1600, 900), (1440, 900),
    (1366, 768), (1280, 720),
)
# En deçà, les menus de HP2 (GUIScale réglé par le catalogue) ne tiennent plus.
_MINIMUM = (1024, 600)
_FORMAT = re.compile(r"^(\d{3,5})x(\d{3,5})$")


def lire(choix: str) -> tuple[int, int] | None:
    """« 2560x1440 » → (2560, 1440) ; None si ce n'est pas une taille plausible."""
    m = _FORMAT.match(choix.strip()) if isinstance(choix, str) else None
    if m is None:
        return None
    taille = int(m.group(1)), int(m.group(2))
    if taille[0] < _MINIMUM[0] or taille[1] < _MINIMUM[1] or max(taille) > 16384:
        return None
    return taille


def ecrire(taille: tuple[int, int]) -> str:
    return f"{taille[0]}x{taille[1]}"


def tient(taille: tuple[int, int], place: tuple[int, int] | None) -> bool:
    return place is None or (taille[0] <= place[0] and taille[1] <= place[1])


def voulue(choix: str, place: tuple[int, int] | None,
           modes: Iterable[tuple[int, int]] | None = None) -> tuple[int, int] | None:
    """La taille à écrire : le choix s'il tient dans la place (et, `modes` donnés, si
    l'écran sait l'afficher), sinon la place.

    None : ni choix valable, ni place connue — on ne touche à rien plutôt que
    d'écrire une taille inventée.
    """
    taille = lire(choix)
    if taille is not None and tient(taille, place) and (modes is None or taille in set(modes)):
        return taille
    return place


def proposees(place: tuple[int, int] | None,
              modes: Iterable[tuple[int, int]] | None = None) -> list[tuple[int, int]]:
    """Les tailles qui tiennent dans la place, sans la place elle-même, de la plus grande à la plus petite.

    `modes` : les seules tailles que le jeu accepte (HP4-HP6 : les modes de l'écran,
    `modes_ecran`) ; sans eux, les tailles courantes.
    """
    candidates = COURANTES if modes is None else sorted(set(modes), reverse=True)
    return [t for t in candidates if t != place and tient(t, place)
            and t[0] >= _MINIMUM[0] and t[1] >= _MINIMUM[1]]


def modes_ecran() -> list[tuple[int, int]] | None:
    """Les tailles d'image que l'écran principal sait afficher, en couleurs 32 bits.

    HP5 et HP6 cherchent leur taille de départ parmi les modes de la carte et
    s'ARRÊTENT au démarrage s'ils ne la trouvent pas (« Couldn't find base display
    mode », lu dans hp6.exe le 2026-11-13) : seules celles-ci se proposent. None
    hors de Windows (sous Wine, la liste est celle de Wine, lue par le jeu).
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _DevMode(ctypes.Structure):
            # DEVMODEW jusqu'à dmDisplayFrequency : assez pour la taille et la profondeur.
            _fields_ = [("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
                        ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
                        ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
                        ("dmPosition", wintypes.LONG * 2), ("dmDisplayOrientation", wintypes.DWORD),
                        ("dmDisplayFixedOutput", wintypes.DWORD), ("dmColor", ctypes.c_short),
                        ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                        ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
                        ("dmFormName", wintypes.WCHAR * 32), ("dmLogPixels", wintypes.WORD),
                        ("dmBitsPerPel", wintypes.DWORD), ("dmPelsWidth", wintypes.DWORD),
                        ("dmPelsHeight", wintypes.DWORD), ("dmDisplayFlags", wintypes.DWORD),
                        ("dmDisplayFrequency", wintypes.DWORD)]

        mode = _DevMode()
        mode.dmSize = ctypes.sizeof(_DevMode)
        tailles: set[tuple[int, int]] = set()
        i = 0
        while ctypes.windll.user32.EnumDisplaySettingsW(None, i, ctypes.byref(mode)):
            if mode.dmBitsPerPel == 32:
                tailles.add((int(mode.dmPelsWidth), int(mode.dmPelsHeight)))
            i += 1
    except (AttributeError, OSError):
        return None
    return sorted(tailles, reverse=True) or None


def du_correctif(spec: Resolution) -> bool:
    """La taille va-t-elle dans l'ini du correctif de HP4 à HP6 (`d3d9.ini`, `[Accio.Game]`) ?"""
    return PureWindowsPath(spec.file).name.lower() == reglages_correctif.NOM_INI


# WS_OVERLAPPEDWINDOW : le cadre que le moteur donne à sa fenêtre.
_STYLE_FENETRE = 0x00CF0000


def cadre(dpi: int) -> tuple[int, int]:
    """(largeur, hauteur) qu'ajoute le cadre d'une fenêtre, à cette mise à l'échelle.

    Demandé à Windows ; ailleurs (Wine n'est pas appelé d'ici), le cadre de
    Windows 11 mesuré à 96 ppp (16 × 39), mis à l'échelle.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT(0, 0, 1000, 1000)
            if ctypes.windll.user32.AdjustWindowRectExForDpi(
                    ctypes.byref(r), _STYLE_FENETRE, False, 0, dpi):
                return r.right - r.left - 1000, r.bottom - r.top - 1000
        except (AttributeError, OSError):
            pass
    return round(16 * dpi / 96), round(39 * dpi / 96)


def dans_le_cadre(travail: tuple[int, int], dpi: int) -> tuple[int, int] | None:
    """La plus grande image dont la fenêtre, cadre compris, tient dans `travail`."""
    marge = cadre(dpi)
    taille = travail[0] - marge[0], travail[1] - marge[1]
    return taille if taille[0] >= _MINIMUM[0] and taille[1] >= _MINIMUM[1] else None


_REMPLIT = re.compile(r"^\s*FillScreen\s*=\s*(\d+)", re.IGNORECASE | re.MULTILINE)


def remplit_l_ecran(game: GameData, config: Config) -> bool:
    """Le correctif du jeu ôte-t-il le cadre d'une image à la taille de l'écran ?

    Le `winmm.dll` du correctif (HP1, HP2 ; `FillScreen=1` par défaut) retire
    le cadre de la fenêtre quand l'image couvre l'écran, et la pose sur
    l'écran entier, barre des tâches cachée (VU sur HP1 le 2026-10-07). Avec
    lui, la taille par défaut est celle de l'ÉCRAN ; sans lui (archive
    d'avant), celle qui tient avec le cadre. Lu dans le dossier du jeu, et
    non déclaré au catalogue : c'est l'archive installée qui décide.
    """
    if sys.platform != "win32":
        return False                      # sous Wine, la fenêtre est celle de Wine
    dossier = config.install_path / Path(game.executable).parent
    if not (dossier / "winmm.dll").is_file():
        return False
    try:
        texte = (dossier / "winmm.ini").read_bytes().decode("cp1252", errors="replace")
    except OSError:
        return True                       # sans ini, la DLL prend ses défauts
    m = _REMPLIT.search(texte)
    return m is None or int(m.group(1)) != 0


def ecran_entier() -> tuple[int, int] | None:
    """La taille de l'écran principal entier, en pixels réels ; None sans affichage."""
    try:
        from PyQt6.QtGui import QGuiApplication
    except ImportError:
        return None
    ecran = QGuiApplication.primaryScreen() if QGuiApplication.instance() is not None else None
    if ecran is None:
        return None
    g, ratio = ecran.geometry(), ecran.devicePixelRatio()
    taille = round(g.width() * ratio), round(g.height() * ratio)
    return taille if taille[0] > 0 and taille[1] > 0 else None


def place_pour(game: GameData, config: Config) -> tuple[int, int] | None:
    """La plus grande image pour CE jeu : l'écran entier si son correctif le remplit."""
    if game.resolution is not None and du_correctif(game.resolution):
        return ecran_entier() if sans_bordure(game, config) else place_disponible()
    return ecran_entier() if remplit_l_ecran(game, config) else place_disponible()


# WindowStyle du correctif de HP4 à HP6 : 1 = sans bordure sur tout l'écran (livré), 4 = sans
# bordure à la taille de l'image ; 2 et 3 = une fenêtre à cadre.
_STYLE = re.compile(r"^\s*WindowStyle\s*=\s*(\d+)", re.IGNORECASE | re.MULTILINE)


def sans_bordure(game: GameData, config: Config) -> bool:
    """Le correctif de ce jeu ouvre-t-il une fenêtre SANS cadre (la place est alors l'écran entier) ?"""
    ini = config.install_path / Path(game.executable).parent / reglages_correctif.NOM_INI
    try:
        texte = ini.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return True                       # sans ini, le correctif prend son défaut : 1
    m = _STYLE.search(texte)
    return m is None or int(m.group(1)) in (1, 4)


def modes_pour(game: GameData) -> list[tuple[int, int]] | None:
    """Les seules tailles que ce jeu accepte : les modes de l'écran pour HP4 à HP6, sinon toutes."""
    if game.resolution is not None and du_correctif(game.resolution):
        return modes_ecran()
    return None


def place_disponible() -> tuple[int, int] | None:
    """La plus grande image qui tient à l'écran principal, en PIXELS RÉELS.

    Zone de travail (sans la barre des tâches) moins le cadre de la fenêtre.
    Pixels réels et non logiques : le jeu est lancé avec la couche DPI (règle
    104), il voit donc l'écran tel qu'il est. À 150 %, Qt annonce 1707×960 pour
    un écran 2560×1440. None sans affichage.
    """
    try:
        from PyQt6.QtGui import QGuiApplication
    except ImportError:
        return None
    if QGuiApplication.instance() is None:
        return None
    ecran = QGuiApplication.primaryScreen()
    if ecran is None:
        return None
    g, ratio = ecran.availableGeometry(), ecran.devicePixelRatio()
    travail = round(g.width() * ratio), round(g.height() * ratio)
    if travail[0] <= 0 or travail[1] <= 0:
        return None
    return dans_le_cadre(travail, round(96 * ratio))


def appliquer_plein_ecran(game: GameData, config: Config,
                          ecran: tuple[int, int] | None) -> tuple[int, int] | None:
    """HP3 : la taille de l'écran entier dans les clés du plein écran (`fullscreen_size`).

    Le moteur se rabat sur 800×600 après un plantage de `SetRes` et l'écrit dans
    son ini ; le catalogue y remet donc 1920×1080 à chaque lancement (patchs
    d'ini). Sur un écran plus grand, l'image restait en 1920×1080 (Ludo,
    2026-11-04, écran 2560×1440). Écrite APRÈS les patchs : la taille de
    l'écran l'emporte, le 1920×1080 ne reste qu'écran inconnu. Rend la taille
    écrite, ou None.
    """
    spec = game.plein_ecran
    if spec is None or ecran is None:
        return None
    ok = all(ecrire_cle_ini(IniPatch(file=spec.file, section=spec.section, key=cle,
                                     value=str(valeur)), game, config)
             for cle, valeur in ((spec.width, ecran[0]), (spec.height, ecran[1])))
    return ecran if ok else None


def taille_pour(choix: str, place: tuple[int, int] | None,
                modes: Iterable[tuple[int, int]] | None) -> tuple[int, int] | None:
    """La taille à écrire pour un jeu qui n'accepte que `modes` (None : tout) : le choix, sinon la
    place, sinon le plus grand mode qui tient dans la place (une fenêtre à cadre n'a pas la
    taille d'un mode)."""
    taille = voulue(choix, place, modes)
    if modes is None or taille is None:
        return taille
    connus = set(modes)
    if taille in connus:
        return taille
    return next((t for t in sorted(connus, reverse=True) if tient(t, place)), None)


def appliquer(game: GameData, config: Config, place: tuple[int, int] | None,
              confirmer: registre.Confirmer | None = None) -> tuple[int, int] | None:
    """Écrit la taille voulue dans l'ini du jeu ; rend celle écrite, ou None.

    HP4 à HP6 (2026-11-13, Ludo : « HP6 était flou, je n'étais pas en 1440p ») : la
    taille va dans `[Accio.Game] Width/Height` du correctif, choisie parmi les modes
    de l'écran ; HP5 et HP6 ont aussi leur rang de résolution remis à 0 dans le
    registre (`Resolution.registre`), sans quoi le choix de leur menu l'emporte.
    """
    spec = game.resolution
    if spec is None:
        return None
    correctif = du_correctif(spec)
    taille = taille_pour(config.resolution_jeu.get(game.id, ""), place,
                         modes_ecran() if correctif else None)
    if taille is None:
        log.info("Résolution de %s non réglée : écran inconnu", game.id)
        return None
    if correctif:
        ok = _ecrire_correctif(game, config, spec, taille)
        if ok and spec.registre is not None:
            _remettre_rang(spec.registre, confirmer)
        return taille if ok else None
    ok = all(ecrire_cle_ini(IniPatch(file=spec.file, section=spec.section, key=cle,
                                     value=str(valeur)), game, config)
             for cle, valeur in ((spec.width, taille[0]), (spec.height, taille[1])))
    return taille if ok else None


def _ecrire_correctif(game: GameData, config: Config, spec: Resolution, taille: tuple[int, int]) -> bool:
    """La taille dans l'ini du correctif, en place (ses commentaires, ses CRLF et le dossier des
    captures en UTF-8 restent tels quels) ; seulement si elle change."""
    ini = resolve_safe_path(spec.file, game, config)
    if ini is None or not ini.is_file():
        return False
    try:
        for cle, valeur in ((spec.width, taille[0]), (spec.height, taille[1])):
            reglages_correctif.poser_valeur(ini, spec.section, cle, str(valeur))
    except (OSError, ValueError):
        log.warning("Résolution de %s non écrite dans %s", game.id, ini, exc_info=True)
        return False
    return True


def _remettre_rang(choix: ChoixRegistre, confirmer: registre.Confirmer | None) -> None:
    """Le rang de résolution du menu du jeu remis à celui de la taille du correctif.

    Le registre n'est écrit que si le rang diffère, et en prévenant (règle 69) ;
    un refus laisse le jeu à la taille de son menu, rien de plus.
    """
    if not registre.disponible():
        return
    actuel = registre.lire_valeurs(choix.root, choix.key, [choix.value], choix.view).get(choix.value)
    if actuel is None or actuel == choix.valeur:
        return    # jamais choisi dans le menu : le jeu prend déjà la taille du correctif
    if not registre.ecrire_valeurs(choix.root, choix.key, {choix.value: choix.valeur}, choix.view,
                                   confirmer=confirmer):
        log.info("Rang de résolution laissé à %s (%s)", actuel, choix.key)

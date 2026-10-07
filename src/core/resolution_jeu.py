"""La taille de l'image de HP1 et HP2 : la plus grande que l'écran permet, ou celle choisie.

Idée validée par Ludo (2026-10-01, puis 2026-10-03 : « la résolution de l'écran
par défaut dans le ini avec possibilité de modifier par la suite »). Le modèle
livré met HP2 en 1024×768 ou 1920×1080 selon l'archive, quel que soit l'écran :
sur un écran 1440p, le jeu tournait dans un coin, ou étiré par Windows.

**Ce que le moteur lit, VU en jeu le 2026-10-01** : HP1 et HP2 prennent la
taille de leur image dans `[WinDrv.WindowsClient] WindowedViewportX/Y` (HP.ini /
Game.ini). Les clés viennent du CATALOGUE (`resolution`), pas d'ici : un jeu
qui en déclare d'autres n'a pas besoin d'une release.

**La fenêtre a un CADRE, VU le 2026-10-07** (HP1, écran 2560×1440 à 125 %) :
`Borderless=True` n'est pas lu par ce `d3d11drv.dll` (le mot n'y figure pas),
et le moteur ouvre une fenêtre à barre de titre en (0, 0). Une image à la
taille de l'écran donnait une fenêtre de 2578×1487 : 47 px sous le bas de
l'écran, la barre des tâches par-dessus. La taille par défaut est donc la
ZONE DE TRAVAIL (l'écran moins la barre des tâches) moins le cadre, que
Windows calcule lui-même pour la mise à l'échelle de l'écran
(`AdjustWindowRectExForDpi` : +18 × +47 à 125 %, exactement la mesure) :
2542×1345 sur cet écran. Le format n'est plus 16:9, et ce n'est pas un
problème : le rendu D3D11 ajuste le champ de vision (`AutoFOV=True`).

**Écrite à CHAQUE lancement**, comme les `ini_patches`. C'est voulu, pour deux
raisons mesurées : Alt+Entrée dans HP2 écrit 2560×1440 dans Game.ini (fenêtre
de 2578×1487, sous la barre des tâches, 2026-10-01), et le menu vidéo du jeu
change ces clés. Le lancement suivant remet ce que la personne a choisi ICI.

**Jamais le plein écran** : `StartupFullscreen` n'est pas touché (CLAUDE.md :
ne jamais passer `StartupFullscreen=True`), à cause du changement de mode qui
plante HP1 à l'Alt+Tab.

**Jamais plus grand que la place disponible** : un choix fait sur un écran 4K
et relu sur un portable 1080p ouvrirait une fenêtre qui déborde. On replie
alors sur la place disponible, sans effacer le choix — il revaudra sur le
grand écran.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from src.core.config import Config
from src.core.game_data import GameData, IniPatch
from src.core.pre_launch import ecrire_cle_ini

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


def voulue(choix: str, place: tuple[int, int] | None) -> tuple[int, int] | None:
    """La taille à écrire : le choix s'il tient dans la place, sinon la place.

    None : ni choix valable, ni place connue — on ne touche à rien plutôt que
    d'écrire une taille inventée.
    """
    taille = lire(choix)
    if taille is not None and tient(taille, place):
        return taille
    return place


def proposees(place: tuple[int, int] | None) -> list[tuple[int, int]]:
    """Les tailles courantes qui tiennent dans la place, sans la place elle-même."""
    return [t for t in COURANTES if t != place and tient(t, place)]


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
    return ecran_entier() if remplit_l_ecran(game, config) else place_disponible()


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


def appliquer(game: GameData, config: Config,
              place: tuple[int, int] | None) -> tuple[int, int] | None:
    """Écrit la taille voulue dans l'ini du jeu ; rend celle écrite, ou None."""
    spec = game.resolution
    if spec is None:
        return None
    taille = voulue(config.resolution_jeu.get(game.id, ""), place)
    if taille is None:
        log.info("Résolution de %s non réglée : écran inconnu", game.id)
        return None
    ok = all(ecrire_cle_ini(IniPatch(file=spec.file, section=spec.section, key=cle,
                                     value=str(valeur)), game, config)
             for cle, valeur in ((spec.width, taille[0]), (spec.height, taille[1])))
    return taille if ok else None

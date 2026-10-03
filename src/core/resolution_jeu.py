"""La taille de fenêtre de HP1 et HP2 : celle de l'écran, ou celle qu'on a choisie.

Idée validée par Ludo (2026-10-01, puis 2026-10-03 : « la résolution de l'écran
par défaut dans le ini avec possibilité de modifier par la suite »). Le modèle
livré met HP2 en 1024×768 ou 1920×1080 selon l'archive, quel que soit l'écran :
sur un écran 1440p, le jeu tournait dans un coin, ou étiré par Windows.

**Ce que le moteur lit, VU en jeu le 2026-10-01** : HP1 et HP2 ouvrent leur
fenêtre sans bordure à `[WinDrv.WindowsClient] WindowedViewportX/Y` (HP.ini /
Game.ini). Au démarrage direct en 2560×1440, le menu de HP2 est juste. Les
clés viennent du CATALOGUE (`resolution`), pas d'ici : un jeu qui en déclare
d'autres n'a pas besoin d'une release.

**Écrite à CHAQUE lancement**, comme les `ini_patches`. C'est voulu, pour deux
raisons mesurées : Alt+Entrée dans HP2 écrit 2560×1440 dans Game.ini (fenêtre
de 2578×1487, sous la barre des tâches, 2026-10-01), et le menu vidéo du jeu
change ces clés. Le lancement suivant remet ce que la personne a choisi ICI.

**Jamais le plein écran** : `StartupFullscreen` n'est pas touché (CLAUDE.md :
ne jamais passer `StartupFullscreen=True`). Une fenêtre sans bordure à la taille
de l'écran en a l'aspect, sans le changement de mode qui plante HP1 à l'Alt+Tab.

**Jamais plus grand que l'écran** : un choix fait sur un écran 4K et relu sur
un portable 1080p ouvrirait une fenêtre qui déborde. On replie alors sur
l'écran, sans effacer le choix — il revaudra sur le grand écran.
"""

from __future__ import annotations

import logging
import re

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


def tient(taille: tuple[int, int], ecran: tuple[int, int] | None) -> bool:
    return ecran is None or (taille[0] <= ecran[0] and taille[1] <= ecran[1])


def voulue(choix: str, ecran: tuple[int, int] | None) -> tuple[int, int] | None:
    """La taille à écrire : le choix s'il tient dans l'écran, sinon l'écran.

    None : ni choix valable, ni écran connu — on ne touche à rien plutôt que
    d'écrire une taille inventée.
    """
    taille = lire(choix)
    if taille is not None and tient(taille, ecran):
        return taille
    return ecran


def proposees(ecran: tuple[int, int] | None) -> list[tuple[int, int]]:
    """Les tailles courantes qui tiennent dans l'écran, sans l'écran lui-même."""
    return [t for t in COURANTES if t != ecran and tient(t, ecran)]


def ecran_principal() -> tuple[int, int] | None:
    """La taille de l'écran principal en PIXELS RÉELS, None sans affichage.

    Pixels réels et non logiques : le jeu est lancé avec la couche DPI (règle
    104), il voit donc l'écran tel qu'il est. À 150 %, Qt annonce 1707×960 pour
    un écran 2560×1440 ; c'est 2560×1440 que le jeu doit recevoir.
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
    g, ratio = ecran.geometry(), ecran.devicePixelRatio()
    taille = round(g.width() * ratio), round(g.height() * ratio)
    return taille if taille[0] > 0 and taille[1] > 0 else None


def appliquer(game: GameData, config: Config,
              ecran: tuple[int, int] | None) -> tuple[int, int] | None:
    """Écrit la taille voulue dans l'ini du jeu ; rend celle écrite, ou None."""
    spec = game.resolution
    if spec is None:
        return None
    taille = voulue(config.resolution_jeu.get(game.id, ""), ecran)
    if taille is None:
        log.info("Résolution de %s non réglée : écran inconnu", game.id)
        return None
    ok = all(ecrire_cle_ini(IniPatch(file=spec.file, section=spec.section, key=cle,
                                     value=str(valeur)), game, config)
             for cle, valeur in ((spec.width, taille[0]), (spec.height, taille[1])))
    return taille if ok else None

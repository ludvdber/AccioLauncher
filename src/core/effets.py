"""Effets animés du launcher : particules, zoom lent du fond, parallaxe, étoiles
du carrousel, rotation au repos des modèles 3D (audit UI f116).

Le joueur choisit dans Paramètres > Son et image : « Selon ce PC » (défaut),
« Oui » ou « Non ». Selon ce PC, ils se coupent d'office dans deux cas qui se
lisent sans rien mesurer :

- Windows a éteint ses propres animations (Accessibilité > Effets visuels >
  Effets d'animation) : le joueur a déjà dit qu'il n'en veut pas ;
- aucune carte graphique n'a de pilote (seul l'adaptateur de base de
  Microsoft) : tout est alors dessiné par le processeur, 15 % d'un cœur au
  repos mesurés en rendu logiciel.

Un « PC modeste » (puce intégrée, peu de mémoire) n'en fait PAS partie : il
faudrait des seuils mesurés sur une vraie puce, et deviner ôterait ses effets
à un portable qui les tient très bien.

Décidé UNE fois au démarrage (`decider`), comme le thème : changer le réglage
demande de redémarrer. Les widgets lisent `animes()`.
"""

import functools
import sys

from src.core import diagnostic
from src.core.season import resolve as resoudre_saison

MODES = ("auto", "oui", "non")

# SystemParametersInfo : « Effets d'animation » de Windows (winuser.h).
_SPI_GETCLIENTAREAANIMATION = 0x1042

_animes = True


def animations_windows() -> bool:
    """Windows anime-t-il ses propres fenêtres ? Vrai hors Windows, et si la lecture échoue."""
    if sys.platform != "win32":
        return True
    import ctypes
    valeur = ctypes.c_int(1)
    try:
        lu = ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(valeur), 0)
    except (AttributeError, OSError):
        return True
    return not lu or bool(valeur.value)


@functools.cache
def sans_pilote() -> bool:
    """Aucune carte graphique n'a de pilote ? Lu une fois : le registre ne change pas en route."""
    return diagnostic.sans_pilote_graphique()


def choisir(mode: str, animations: bool, pilote_absent: bool) -> bool:
    """La règle, pure : « oui » et « non » forcent ; sinon les deux cas du module."""
    if mode == "oui":
        return True
    if mode == "non":
        return False
    return animations and not pilote_absent


def selon(mode: str) -> bool:
    """Ce que `mode` donnerait sur ce PC (les Paramètres : redémarrer changerait-il quelque chose ?)."""
    return choisir(mode, animations_windows(), sans_pilote())


def decider(mode: str) -> bool:
    """Pose la décision pour toute la session et la rend."""
    global _animes
    _animes = selon(mode)
    return _animes


def saison_des_particules(valeur_config: str) -> str:
    """L'ambiance à semer : celle de l'Almanach, ou aucune particule quand les effets sont coupés."""
    return resoudre_saison(valeur_config) if _animes else "aucune"


def animes() -> bool:
    """Les effets animés tournent-ils ? Vrai tant que rien n'a été décidé."""
    return _animes

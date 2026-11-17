"""Un petit fichier (sauvegarde, textes d'un jeu) lu UNE fois tant qu'il ne change pas.

Banc de rapidité du 2026-11-16, un parcours du Carnet et des Collections : la
sauvegarde de HP5 ouverte 9 fois (son en-tête par `sauvegardes`, son contenu
par `folio_hp5`), celle de HP4 7 fois, chaque `GameSaveInfo` de HP1 7 fois,
`HPMenu.fre` de HP2 7 fois. Chaque page relisait ce que la précédente venait
de lire.

Les octets sont gardés par chemin, date et taille (`signature.fiable` : un
fichier écrit il y a moins de 2 s se relit sans être gardé, le jeu peut être en
train de sauvegarder). Un fichier de plus de 256 Ko n'est pas gardé ; un jeu
qui démarre reprend tout (`liberer`).
"""

import threading
from collections import OrderedDict
from pathlib import Path

from src.core.signature import Signature, fiable

_PLAFOND = 256 * 1024
_NOMBRE = 48

_gardes: OrderedDict[tuple[str, int | None], tuple[Signature, bytes]] = OrderedDict()
_verrou = threading.Lock()


def lire(chemin: Path, au_plus: int | None = None) -> bytes:
    """Les octets du fichier, ou ses `au_plus` premiers. Lève OSError s'il ne se lit pas."""
    signature = fiable(chemin.stat())
    cle = (str(chemin), au_plus)
    with _verrou:
        garde = _gardes.get(cle)
        if signature is not None and garde is not None and garde[0] == signature:
            _gardes.move_to_end(cle)
            return garde[1]
    with open(chemin, "rb") as f:
        octets = f.read() if au_plus is None else f.read(au_plus)
    with _verrou:
        if signature is None or len(octets) > _PLAFOND:
            _gardes.pop(cle, None)
        else:
            _gardes[cle] = (signature, octets)
            _gardes.move_to_end(cle)
            while len(_gardes) > _NOMBRE:
                _gardes.popitem(last=False)
    return octets


def liberer() -> None:
    """Rend tout ce qui est gardé : un jeu démarre."""
    with _verrou:
        _gardes.clear()

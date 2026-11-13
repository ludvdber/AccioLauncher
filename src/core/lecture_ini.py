"""Un fichier de réglages lu UNE fois tant qu'il ne change pas.

Audit du 2026-11-13 (banc de rapidité) : chaque ligne de réglage relisait
l'ini en entier. Une seule ouverture des réglages de HP6 lisait `d3d9.ini`
62 fois et sa copie d'origine 26 fois ; un changement de jeu relisait l'ini
du correctif 3 fois ; `dgVoodoo.conf` de HP3, 7 fois. Sur 75 lectures du même
fichier pendant un parcours, une seule servait.

Ici, une lecture garde les lignes tant que la date de modification et la
taille du fichier ne bougent pas : un `stat` suffit pour savoir s'il faut
relire (`signature.fiable` : pas pour un fichier écrit il y a moins de 2 s). Un fichier changé à la main entre deux ouvertures est donc relu,
et ce que le launcher écrit passe par `oublier`. Chaque appel rend une COPIE
des lignes : les appelants les retouchent avant d'écrire.

Borné à `_TAILLE` fichiers (l'ini du jeu, sa copie d'origine, le fichier
des réglages graphiques de HP3 : quelques Ko chacun) ; le plus ancien sort.
"""

import threading
from collections import OrderedDict
from pathlib import Path

from src.core.signature import Signature, fiable

_TAILLE = 16
_cache: OrderedDict[str, tuple[Signature, tuple[str, ...], str]] = OrderedDict()
_verrou = threading.Lock()


def lire_lignes(chemin: Path) -> tuple[list[str], str]:
    """Lignes SANS fin de ligne, et la fin de ligne du fichier. Lève OSError s'il est illisible."""
    etat = chemin.stat()
    cle = str(chemin)
    signature = fiable(etat)
    with _verrou:
        garde = _cache.get(cle)
        if signature is not None and garde is not None and garde[0] == signature:
            _cache.move_to_end(cle)
            return list(garde[1]), garde[2]
    brut = chemin.read_bytes().decode("utf-8", errors="surrogateescape")
    fin = "\r\n" if "\r\n" in brut else "\n"
    lignes = brut.split(fin)
    with _verrou:
        if signature is None:
            _cache.pop(cle, None)
        else:
            _cache[cle] = (signature, tuple(lignes), fin)
            _cache.move_to_end(cle)
            while len(_cache) > _TAILLE:
                _cache.popitem(last=False)
    return lignes, fin


def oublier(chemin: Path) -> None:
    """À appeler après avoir écrit `chemin` : la prochaine lecture repart du disque."""
    with _verrou:
        _cache.pop(str(chemin), None)


def differe(fichier: Path, origine: Path) -> bool:
    """`origine` existe et ne porte pas les mêmes lignes que `fichier` (absent compris).

    Remplace deux `read_bytes` complets à chaque question « y a-t-il quelque chose à
    remettre ? ». Lève OSError si l'un des deux existe mais ne se lit pas."""
    if not origine.is_file():
        return False
    if not fichier.is_file():
        return True
    return lire_lignes(origine) != lire_lignes(fichier)

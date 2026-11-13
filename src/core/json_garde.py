"""Un fichier JSON de données lu UNE fois tant qu'il ne change pas.

Banc de rapidité, 2026-11-13 : `discographie.json` lu cinq fois au démarrage
(les morceaux, les crédits, les jeux qui ont de la musique, le fond sonore),
`cinematiques.json` deux fois. Le contenu rendu est PARTAGÉ : les appelants
le lisent et en bâtissent leurs propres objets, jamais ne le modifient.
"""

import json
from functools import lru_cache
from pathlib import Path


def lire(chemin: Path) -> object:
    """Le contenu décodé. Lève OSError si le fichier ne se lit pas, ValueError s'il est mal formé."""
    etat = chemin.stat()
    return _lire(str(chemin), etat.st_mtime_ns, etat.st_size)


@lru_cache(maxsize=8)
def _lire(chemin: str, _date: int, _taille: int) -> object:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))

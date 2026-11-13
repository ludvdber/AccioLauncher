"""Un fichier JSON de données lu UNE fois tant qu'il ne change pas.

Banc de rapidité, 2026-11-13 : `discographie.json` lu cinq fois au démarrage
(les morceaux, les crédits, les jeux qui ont de la musique, le fond sonore),
`cinematiques.json` deux fois. Le contenu rendu est PARTAGÉ : les appelants
le lisent et en bâtissent leurs propres objets, jamais ne le modifient.
Un fichier écrit il y a moins de 2 s est relu sans être gardé (`signature.fiable`).
"""

import json
from functools import lru_cache
from pathlib import Path

from src.core.signature import fiable


def lire(chemin: Path) -> object:
    """Le contenu décodé. Lève OSError si le fichier ne se lit pas, ValueError s'il est mal formé."""
    signature = fiable(chemin.stat())
    if signature is None:
        return _decoder(str(chemin))
    return _garde(str(chemin), *signature)


def _decoder(chemin: str) -> object:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def _garde(chemin: str, _date: int, _taille: int) -> object:
    return _decoder(chemin)

"""Trouver un fichier du jeu sans tenir compte de la casse, sans relister le dossier.

HP3 écrit « textures », HP1 « Textures » ; Linux ne pardonne pas. D'où un
`iterdir` à chaque recherche, recopié dans six modules : le banc de rapidité
du 2026-11-13 a compté le dossier `HP3/textures` listé 234 fois et `HP3`
220 fois sur un parcours (une fois par carte du folio), `HP2/system` 65 fois.

Ici, un dossier se liste UNE fois tant que sa date de modification ne bouge
pas (elle change quand une entrée y est créée, retirée ou renommée ; pas
pour un dossier changé il y a moins de 2 s, `signature.fiable`), et les
anciens sites passent tous par `trouver` / `entrees`. Borné à 64 dossiers.
"""

from functools import lru_cache
from pathlib import Path

from src.core.signature import fiable


def entrees(dossier: Path) -> dict[str, Path]:
    """Nom en minuscules → chemin, pour chaque entrée du dossier ; {} s'il ne se lit pas."""
    try:
        signature = fiable(dossier.stat())
    except OSError:
        return {}
    if signature is None:
        return _lister(str(dossier))
    return _garde(str(dossier), signature[0])


@lru_cache(maxsize=64)
def _garde(dossier: str, _date: int) -> dict[str, Path]:
    return _lister(dossier)


def _lister(dossier: str) -> dict[str, Path]:
    try:
        return {p.name.lower(): p for p in Path(dossier).iterdir()}
    except OSError:
        return {}


def trouver(dossier: Path, relatif: str) -> Path | None:
    """`relatif` (« textures/HP3_Menu.utx ») sous `dossier`, quelle que soit la casse ; None sinon."""
    courant = dossier
    for partie in relatif.split("/"):
        suivant = entrees(courant).get(partie.lower())
        if suivant is None:
            return None
        courant = suivant
    return courant

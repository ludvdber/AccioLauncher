"""Reprendre en un clic (HP1 à HP3) : les arguments qui ouvrent la dernière
partie sans passer par le menu du jeu.

Relevé en jeu le 2026-10-15 (atelier, `notes/HP1.md`, `HP2.md`, `HP3.md`) :

    HP1, HP3   `SaveN.usa`        → `?load=N`            (N = numéro du fichier)
    HP2        `SlotK/Save0.usa`  → `-LOADGAME=0 -SAVESLOT=K`

HP2 a besoin des deux : `?load=0` seul ouvre la boîte « Menu principal ». Avec
eux, un seul processus, sans cette boîte (le menu de démarrage de HP2 ne se
passe pas à la manette).

La partie ouverte est celle que la fiche montre (`folio.la_derniere_jouee`
parmi les lisibles) ET la plus récente de toutes : si le jeu a écrit plus tard
un emplacement que le folio ne lit pas, on passe par le menu plutôt que
d'ouvrir une autre partie que celle annoncée.
"""

import logging
import re
from collections.abc import Sequence
from pathlib import Path

from src.core import folio, folio_hp2, folio_hp3, sauvegardes
from src.core.game_data import GameData

log = logging.getLogger(__name__)

JEUX = frozenset(folio.RESUMES)


def arguments_pour(jeu: str, chemin: Path) -> tuple[str, ...]:
    """Les arguments qui ouvrent ce fichier de sauvegarde ; () s'il n'a pas la forme attendue."""
    if jeu in ("hp1", "hp3"):
        n = re.fullmatch(r"save(\d+)\.usa", chemin.name, re.IGNORECASE)
        return (f"?load={int(n.group(1))}",) if n else ()
    if jeu == "hp2":
        k = re.fullmatch(r"slot(\d+)", chemin.parent.name, re.IGNORECASE)
        if k and chemin.name.lower() == "save0.usa":
            return ("-LOADGAME=0", f"-SAVESLOT={int(k.group(1))}")
    return ()


def _releves(game: GameData) -> Sequence[folio.PartieLue]:
    if game.id == "hp2":
        return folio_hp2.emplacements(game.sauvegardes)
    fichiers = sauvegardes.fichiers(game.sauvegardes)
    if game.id == "hp3":
        return folio_hp3.emplacements(fichiers)
    return folio.emplacements_hp1(fichiers)


def arguments(game: GameData) -> tuple[str, ...]:
    """Ce qu'il faut ajouter à la ligne de commande pour reprendre ; () pour le menu du jeu."""
    if game.id not in JEUX or game.sauvegardes is None:
        return ()
    try:
        releves = _releves(game)
    except Exception:  # une sauvegarde qu'on ne sait pas lire n'empêche pas de jouer : le menu du jeu
        log.warning("Reprise directe de %s : sauvegardes illisibles, menu du jeu", game.id, exc_info=True)
        return ()
    derniere = max(releves, key=lambda r: r.modifie, default=None)
    if derniere is None or not derniere.lu:
        return ()
    return arguments_pour(game.id, derniere.chemin)

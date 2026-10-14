"""La galerie : toutes les captures d'écran, de tous les jeux, les plus récentes d'abord.

Maquette « Galerie, Discord et vitrine » validée par Ludo le 2026-10-14. Les
captures existaient déjà, rangées par jeu dans Images › Accio Launcher
(`captures.py`), mais on ne les voyait qu'en ouvrant ce dossier, un jeu à la
fois. La galerie les montre ensemble, par mois, et propose de les partager.

Rien n'est copié ni indexé : la galerie relit les dossiers à chaque ouverture.
Une capture effacée à la main dans l'Explorateur disparaît donc d'elle-même.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core import captures
from src.core.game_data import GameData


@dataclass(frozen=True)
class Capture:
    chemin: Path
    jeu: str          # id du jeu
    quand: datetime


def _quand(chemin: Path) -> datetime:
    """La date d'écriture du fichier : c'est celle de la prise de vue (le
    correctif écrit au moment de F12, `captures.ramasser` déplace sans toucher
    à la date)."""
    try:
        return datetime.fromtimestamp(chemin.stat().st_mtime)
    except OSError:
        return datetime.fromtimestamp(0)


def lister(jeux: list[GameData]) -> list[Capture]:
    """Toutes les captures des jeux du catalogue, les plus récentes d'abord."""
    trouvees: list[Capture] = []
    vus: set[Path] = set()
    for jeu in jeux:
        dossier = captures.dossier(jeu)
        # Deux parties d'un même jeu ne partagent pas de dossier, mais un nom
        # identique dans deux langues le pourrait : jamais deux fois la même image.
        if dossier in vus:
            continue
        vus.add(dossier)
        trouvees += [Capture(p, jeu.id, _quand(p)) for p in captures.images(dossier)]
    return sorted(trouvees, key=lambda c: c.quand, reverse=True)


def par_mois(liste: list[Capture]) -> list[tuple[tuple[int, int], list[Capture]]]:
    """[((année, mois), captures)] dans l'ordre de `liste`."""
    groupes: list[tuple[tuple[int, int], list[Capture]]] = []
    for c in liste:
        cle = (c.quand.year, c.quand.month)
        if not groupes or groupes[-1][0] != cle:
            groupes.append((cle, []))
        groupes[-1][1].append(c)
    return groupes


def compte_par_jeu(liste: list[Capture]) -> dict[str, int]:
    compte: dict[str, int] = {}
    for c in liste:
        compte[c.jeu] = compte.get(c.jeu, 0) + 1
    return compte


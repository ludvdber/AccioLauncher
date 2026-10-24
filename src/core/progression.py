"""Où en est une sauvegarde : de quoi voir qu'un emplacement a été RECOMMENCÉ.

Les statistiques par sauvegarde (`sauvegardes.py`) suivent un emplacement ;
or un emplacement réutilisé pour une nouvelle partie continuait de cumuler
sur l'ancienne. Le signe d'une nouvelle partie, c'est une CHUTE : des
compteurs qui ne baissent jamais au cours d'une même aventure (cartes
trouvées, étape de l'histoire, boucliers, écussons) et qui retombent.

`mesure` rend ces compteurs, toujours dans le même ordre pour un même jeu,
ou None quand la sauvegarde ne se lit pas : sans mesure, on ne conclut rien.
Aucun pourcentage n'en est tiré, aucune estimation : seulement « plus bas
qu'avant ».

Ce qui n'y est PAS, exprès :
- les dragées, qu'on dépense (HP2 et suivants) et que HP1 relit mal après
  `?load` ;
- les points de maison, qu'on perd ;
- le niveau en cours, qu'on revisite.
"""

import re
import struct
from pathlib import Path

from src.core.catalogue_blocs import Sauvegardes

Mesure = tuple[int, ...]


def _etape(histoire: str) -> int:
    """« GSTATE010 » (HP2) ou « GState010 » (HP3) → 10 ; 0 si illisible."""
    trouve = re.search(r"(\d+)$", histoire)
    return int(trouve.group(1)) if trouve else 0


def _debut(chemin: Path, acteur: str | None) -> bool:
    """Vrai si la sauvegarde s'ouvre mais que le jeu n'y a encore rien écrit.

    Les lecteurs du folio rendent « rien » dans deux cas : le fichier ne se
    lit pas, ou c'est le tout début d'une partie (HP1 : l'acteur d'Harry est
    là, sans aucune de ses valeurs ; relevé sur `Save1.usa` et `Save2.usa`
    de Ludo le 2026-10-17). Le second est une mesure, zéro, et c'est justement
    celle d'une aventure qu'on vient de recommencer.
    """
    from src.core import textures_ue1
    try:
        paquet = textures_ue1.Paquet(chemin.read_bytes())
        return acteur is None or paquet.proprietes(acteur) is not None
    except (OSError, ValueError, IndexError, struct.error):
        return False


def _hp1(chemin: Path, _n: int) -> Mesure | None:
    from src.core import folio
    r = folio.releve_hp1(chemin)
    if r is None:
        return None
    if r.lu:
        return (len(r.cartes),)
    return (0,) if _debut(chemin, "Harry") else None


def _hp2(chemin: Path, n: int) -> Mesure | None:
    from src.core import folio_hp2
    r = folio_hp2.releve(chemin, n)
    return (_etape(r.histoire), len(r.cartes)) if r is not None and r.lu else None


def _hp3(chemin: Path, _n: int) -> Mesure | None:
    from src.core import folio_hp3
    r = folio_hp3.releve(chemin)
    if r is None:
        return None
    if r.lu:
        return (_etape(r.histoire), len(r.cartes))
    return (0, 0) if _debut(chemin, None) else None


def _hp4(chemin: Path, n: int) -> Mesure | None:
    from src.core import folio_hp4
    for p in folio_hp4.releve(chemin):
        if p.emplacement == n:
            return (len(p.cartes), p.boucliers)
    return None


def _hp5(chemin: Path, n: int) -> Mesure | None:
    from src.core import folio_hp5
    for p in folio_hp5.releve(chemin):
        if p.emplacement == n and (p.pourcentage is not None or p.decouverte is not None):
            return (p.pourcentage or 0, p.decouverte or 0)
    return None


def _hp6(chemin: Path, _n: int) -> Mesure | None:
    from src.core import folio_hp6
    p = folio_hp6.releve(chemin)
    return (p.chapitre, p.ecussons, len(p.sorts)) if p is not None else None


_LECTEURS = {"hp1": _hp1, "hp2": _hp2, "hp3": _hp3, "hp4": _hp4, "hp5": _hp5, "hp6": _hp6}


def mesure(jeu: str, spec: Sauvegardes | None, rel: str) -> Mesure | None:
    """Les compteurs de la sauvegarde `rel` (clé de `sauvegardes.releve`)."""
    lire = _LECTEURS.get(jeu)
    ou = cible(spec, rel) if lire is not None else None
    if lire is None or ou is None:
        return None
    try:
        return lire(*ou)
    except (OSError, ValueError, IndexError):
        return None


def cible(spec: Sauvegardes | None, rel: str) -> tuple[Path, int] | None:
    """Le fichier et l'emplacement que désigne `rel` (« HPGOF#2 », « Save1.usa »)."""
    from src.core import sauvegardes
    racine = sauvegardes.dossier(spec) if spec is not None else None
    if racine is None or spec is None:
        return None
    fichier, _, emplacement = rel.partition("#")
    n = int(emplacement) if emplacement.isdigit() else (
        sauvegardes.numero(fichier, spec, 2) or 1)
    return racine / fichier, n


def recommencee(avant: Mesure | None, apres: Mesure | None) -> bool:
    """Vrai si un compteur a BAISSÉ : ce n'est plus la même aventure.

    Deux mesures de longueur différente (lecteur changé entre deux versions)
    ne se comparent pas : rien n'est conclu.
    """
    if avant is None or apres is None or len(avant) != len(apres):
        return False
    return any(b < a for a, b in zip(avant, apres))

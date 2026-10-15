"""Le folio de HP5 : ce que `HPOOTP` dit de chacune des trois parties.

Relevé le 2026-10-15 sur la sauvegarde de Ludo, en LECTURE seule, et VU contre
l'écran du jeu (`Harry-Potter-PC-Fix/notes/HP5.md`, « Mission d'analyse ») :

- l'en-tête porte trois fiches (date, pourcentage) : `sauvegardes.emplacements_hp5` ;
- le corps de chaque partie commence par « PTOO30.1 » à 0x484 + k × 0x400 ;
  ses **points de découverte** sont un entier 32 bits petit-boutiste à +0x108
  (330 / 75 / 0 pour les parties à 14 / 6 / 1 %, « 330 / 4 360 » à l'écran
  « Informations sur le jeu »).

Le reste de l'écran (fantômes, statues, insignes…) est dans des champs de bits
pas encore décodés : À VÉRIFIER avant d'en afficher quoi que ce soit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core import sauvegardes

log = logging.getLogger(__name__)

DECOUVERTE_MAX = 4360        # le « / 4 360 » de l'écran du jeu
_CORPS = 0x484
_TAILLE_CORPS = 0x400
_DECOUVERTE = 0x108
_TAILLE_MAX = 1024 * 1024    # 4 Ko chez Ludo


@dataclass(frozen=True)
class Partie:
    emplacement: int
    ecrite: datetime | None
    pourcentage: int | None
    decouverte: int | None    # None : corps absent ou pas comme relevé


def lire(contenu: bytes) -> list[Partie]:
    parties = []
    for numero, ecrite, pourcent in sauvegardes.emplacements_hp5(contenu[:0x500]):
        corps = _CORPS + (numero - 1) * _TAILLE_CORPS
        decouverte = None
        if contenu[corps:corps + 8] == b"PTOO30.1" and len(contenu) >= corps + _DECOUVERTE + 4:
            valeur = int.from_bytes(contenu[corps + _DECOUVERTE:corps + _DECOUVERTE + 4], "little")
            decouverte = valeur if valeur <= DECOUVERTE_MAX else None
        parties.append(Partie(numero, datetime.fromtimestamp(ecrite) if ecrite else None,
                              pourcent, decouverte))
    return parties


def releve(chemin: Path) -> list[Partie]:
    try:
        if chemin.stat().st_size > _TAILLE_MAX:
            return []
        return lire(chemin.read_bytes())
    except OSError:
        log.warning("Folio HP5 : %s illisible", chemin, exc_info=True)
        return []

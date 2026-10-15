"""Le folio de HP5 : ce que `HPOOTP` dit de chacune des trois parties.

Relevé le 2026-10-15 sur la sauvegarde de Ludo, en LECTURE seule, et VU contre
l'écran du jeu (`Harry-Potter-PC-Fix/notes/HP5.md`, « Mission d'analyse ») :

- l'en-tête porte trois fiches (date, pourcentage) : `sauvegardes.emplacements_hp5` ;
- le corps de chaque partie commence par « PTOO30.1 » à 0x484 + k × 0x400 ;
  ses **points de découverte** sont un entier 32 bits petit-boutiste à +0x108
  (330 / 75 / 0 pour les parties à 14 / 6 / 1 %, « 330 / 4 360 » à l'écran
  « Informations sur le jeu »).

Le reste de cet écran est LU dans `hp.exe` (2026-10-15, sans lancer le jeu) :
le corps se découpe en morceaux (« BOLG », « CSID », « IRCS » : GLOB, DISC,
SCRI à l'envers), chacun annoncé par (étiquette, taille, décalage) à +0x18.
GLOB est le champ de bits des drapeaux de la partie (drapeau n = bit n), et
l'écran (fonction à 0x4DF4C0) compte les bits posés de [premier, premier +
nombre) pour chaque ligne, en appelant 0x518940. Les bornes de `COMPTEURS` sont
celles du code ; les noms des drapeaux viennent de la table de `hp.exe`
(`GHOST_NHN_FOUND`…). Vérifié sur la partie 1 de Ludo contre l'écran : les
17 lignes concordent (19 personnages, 1 fantôme, 1 statue, 5 / 66 rangés…).
"""

from __future__ import annotations

import logging
import struct
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
_GLOB = (b"BOLG", 0xCC)       # étiquette et taille du morceau des drapeaux


@dataclass(frozen=True)
class Compteur:
    libelle: str          # en français, passé à `tr()` par la page
    premier: int          # premier drapeau de la ligne
    total: int
    en_pourcentage: bool = False   # le jeu l'affiche ainsi (mots de passe)


# Dans l'ordre de l'écran « Informations sur le jeu » (et du code qui le remplit).
COMPTEURS = (
    Compteur("Mots de passe de portraits", 15, 12, en_pourcentage=True),
    Compteur("Fantômes", 235, 4),
    Compteur("Créatures volantes", 104, 5),
    Compteur("Personnages rencontrés", 38, 58),
    Compteur("Joueurs d'échecs battus", 376, 3),
    Compteur("Joueurs de bataille explosive battus", 380, 2),
    Compteur("Joueurs de Bavboules battus", 382, 4),
    Compteur("Affaires de Luna", 386, 5),
    Compteur("Paquets de Fred et George", 147, 12),
    Compteur("Statues de pièces d'échiquier", 120, 12),
    Compteur("Plaques de sorcier", 132, 15),
    Compteur("Traces d'animaux", 239, 3),
    Compteur("Insignes de Poudlard", 242, 12),
    Compteur("Poudlard rangé", 464, 66),
    Compteur("Sorts défensifs en une rencontre", 449, 6),
    Compteur("Quêtes de professeurs", 577, 4),
    Compteur("Meilleure note dans chaque matière", 392, 3),
)


@dataclass(frozen=True)
class Partie:
    emplacement: int
    ecrite: datetime | None
    pourcentage: int | None
    decouverte: int | None    # None : corps absent ou pas comme relevé
    compteurs: tuple[int, ...] | None = None   # un par ligne de COMPTEURS


def _drapeaux(corps: bytes) -> bytes | None:
    """Le morceau GLOB du corps, s'il est annoncé comme relevé."""
    for k in range(3):
        etiquette, taille, decalage = struct.unpack_from("<4sII", corps, 0x18 + 12 * k)
        if (etiquette, taille) == _GLOB and decalage + taille <= len(corps):
            return corps[decalage:decalage + taille]
    return None


def _compter(drapeaux: bytes) -> tuple[int, ...]:
    def pose(n: int) -> int:
        return drapeaux[n >> 3] >> (n & 7) & 1
    return tuple(sum(pose(c.premier + i) for i in range(c.total)) for c in COMPTEURS)


def lire(contenu: bytes) -> list[Partie]:
    parties = []
    for numero, ecrite, pourcent in sauvegardes.emplacements_hp5(contenu[:0x500]):
        debut = _CORPS + (numero - 1) * _TAILLE_CORPS
        corps = contenu[debut:debut + _TAILLE_CORPS]
        decouverte = compteurs = None
        if corps[:8] == b"PTOO30.1" and len(corps) >= _DECOUVERTE + 4:
            valeur = int.from_bytes(corps[_DECOUVERTE:_DECOUVERTE + 4], "little")
            decouverte = valeur if valeur <= DECOUVERTE_MAX else None
            drapeaux = _drapeaux(corps)
            if drapeaux is not None:
                compteurs = _compter(drapeaux)
        parties.append(Partie(numero, datetime.fromtimestamp(ecrite) if ecrite else None,
                              pourcent, decouverte, compteurs))
    return parties


def releve(chemin: Path) -> list[Partie]:
    try:
        if chemin.stat().st_size > _TAILLE_MAX:
            return []
        return lire(chemin.read_bytes())
    except OSError:
        log.warning("Folio HP5 : %s illisible", chemin, exc_info=True)
        return []

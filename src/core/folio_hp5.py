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
from functools import lru_cache
from pathlib import Path

from src.core import images_ea, sauvegardes

log = logging.getLogger(__name__)

DECOUVERTE_MAX = 4360        # le « / 4 360 » de l'écran du jeu
_CORPS = 0x484
_TAILLE_CORPS = 0x400
_DECOUVERTE = 0x108
_TAILLE_MAX = 1024 * 1024    # 4 Ko chez Ludo
_GLOB = (b"BOLG", 0xCC)       # étiquette et taille du morceau des drapeaux
_FICHE, _TAILLE_FICHE, _CHAPITRE = 0x20, 0x178, 0x6C

# La vignette de l'écran « Continuer aventure » : le jeu la choisit d'après le
# numéro de chapitre de la fiche (entier à +0x6C, 4 / 3 / 2 chez Ludo), par la
# fonction à 0x5F1C00 de `hp.exe` (relevé le 2026-10-17) ; image
# `tf_chapter_<nom>` de `game.str`, 64 × 64. VU le 2026-10-15 sans le savoir :
# deux silhouettes (4, Salle sur Demande), Dumbledore (3, Poudlard), Sirius
# (2, square Grimmaurd).
CHAPITRES = ("LittleWhinging", "LittleWhinging", "GrimmauldPlace", "Hogwarts",
             "Room_of_Requirement", "Occlumency", "GrimmauldPlaceXmas",
             "Dumbledores_last_days", "UmbridgesHogwarts", "MM_Hall_of_Prophecy",
             "MM_Atrium", "MM_Atrium")


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
    chapitre: int | None = None                # rang dans CHAPITRES


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
        fiche = _FICHE + (numero - 1) * _TAILLE_FICHE + _CHAPITRE
        chapitre = int.from_bytes(contenu[fiche:fiche + 4], "little")
        parties.append(Partie(numero, datetime.fromtimestamp(ecrite) if ecrite else None,
                              pourcent, decouverte, compteurs,
                              chapitre if chapitre < len(CHAPITRES) else None))
    return parties


def releve(chemin: Path) -> list[Partie]:
    try:
        if chemin.stat().st_size > _TAILLE_MAX:
            return []
        return lire(chemin.read_bytes())
    except OSError:
        log.warning("Folio HP5 : %s illisible", chemin, exc_info=True)
        return []


def image_chapitre(system: Path, chapitre: int | None) -> tuple[int, int, bytes] | None:
    """La vignette du chapitre (64 × 64, B V R A) dans le jeu installé, ou None."""
    if chapitre is None or not 0 <= chapitre < len(CHAPITRES):
        return None
    return _images_chapitres(str(system)).get(CHAPITRES[chapitre].lower())


@lru_cache(maxsize=2)
def _images_chapitres(system_txt: str) -> dict[str, tuple[int, int, bytes]]:
    images: dict[str, tuple[int, int, bytes]] = {}
    try:
        for archive in ("data.big", "data2.big", "data3.big", "data4.big"):
            chemin = Path(system_txt) / archive
            flux = images_ea.entree_big(chemin, "game.str") if chemin.is_file() else b""
            if flux:
                break
        # « Room_Of_Requirement » dans l'archive, « Room_of_Requirement » dans le code
        for nom, q in images_ea.images_nommees(flux).items():
            if nom.lower().startswith("tf_chapter_"):
                image = images_ea.image(flux, q)
                if image is not None:
                    images[nom.lower().removeprefix("tf_chapter_")] = image
    except (OSError, struct.error):
        log.warning("Folio HP5 : vignettes des chapitres illisibles", exc_info=True)
    return images

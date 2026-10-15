"""Le folio de HP6 : ce que `HPHBP0` dit de la partie du Prince de sang-mêlé.

Relevé le 2026-10-15 sur la sauvegarde de Ludo, en LECTURE seule, et VU contre
le menu de pause du jeu (« écussons 7 / 125 », « mini-écussons 3 / 25 (372) ») :
`Harry-Potter-PC-Fix/notes/HP6.md`, « Mission d'analyse ».

    0x00   « 20CM », taille, 0x38, taille du corps
    0x20   année, mois, jour de la semaine, jour, heure, minute, seconde
           (entiers 32 bits petit-boutistes), écrits par le jeu
    0x54   corps « HPHB2.00WN32 », entiers GROS-boutistes
    0x60   nombre de sections, puis (clé, décalage, nombre) par section
    corps + décalage : `nombre` paires (clé, valeur) de 8 octets

Les décalages partent du DÉBUT DU CORPS (0x54) : c'est la seule base où toutes
les sections se lisent en paires (clé, valeur), celles d'une seule entrée
comprises (`Minicrestometer` = (« MiniCrestsCollected », 372)). Lu depuis
0x58, chaque paire chevauchait la suivante, d'où les deux appariements
possibles notés le 2026-10-15 ; tranché le même soir par cette structure, et
c'est l'appariement vraisemblable (prologue fini, chapitre 2 en cours).

Une clé est le hachage ELF (PJW) du nom en minuscules (« spellunlock_lumos »),
une valeur d'état vaut 15 (fini), 5 (en cours ou acquis) ou 0. Dans
`CrestsCollected`, la clé est le rang de l'écusson (0 à 124) et la valeur
son identifiant d'objet, 0 s'il reste à trouver. Une seule partie par fichier.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

ECUSSONS = 125            # le « / 125 » du menu de pause
FINI, EN_COURS = 15, 5
_CORPS = 0x54
_TAILLE_MAX = 1024 * 1024  # 20 Ko chez Ludo

# Les sorts du jeu, dans l'ordre du folio (noms de `hp6.exe`,
# `SpellUnlock_<nom>`) ; les améliorations (Stupefy1 à 4, ChargedStupefy,
# LeviosaThrow) ne sont pas des sorts à part.
SORTS = ("Expelliarmus", "Stupefy", "Lumos", "Reparo", "Leviosa", "Accio", "Incendio",
         "Protego", "Petrificus", "LeviCorpus", "Depulso")

# Les paliers du « Minicrestometer », LUS dans `hp6.exe` (table à 0x8748F0,
# 2026-10-15) : le jeu affiche le nombre de seuils atteints sur 25 (« 3 / 25 »
# pour 372 chez Ludo, VU) et remplit sa barre du palier atteint au suivant
# (fonction à 0x45AD20).
PALIERS = (100, 200, 300, 450, 600, 800, 1000, 1250, 1500, 2000, 2500, 3250, 4000, 5000,
           6250, 7500, 9000, 10500, 12250, 14000, 16000, 18000, 20250, 22500, 25000)


def palier(mini_ecussons: int) -> tuple[int, float]:
    """(paliers atteints, part du chemin vers le suivant ; 1.0 une fois tout atteint)."""
    atteints = sum(1 for s in PALIERS if mini_ecussons >= s)
    if atteints == len(PALIERS):
        return atteints, 1.0
    bas = PALIERS[atteints - 1] if atteints else 0
    return atteints, (mini_ecussons - bas) / (PALIERS[atteints] - bas)


def hachage(nom: str) -> int:
    """Le hachage ELF (PJW) du nom en minuscules, comme le jeu l'écrit."""
    h = 0
    for c in nom.lower().encode("ascii"):
        h = ((h << 4) + c) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xFFFFFFFF
    return h


@dataclass(frozen=True)
class Partie:
    ecrite: datetime | None
    ecussons: int                 # écussons trouvés, sur ECUSSONS
    mini_ecussons: int            # le « (372) » du menu de pause
    chapitre: int = 0             # `CurrentChapterId`, 1 = le prologue au Terrier
    sorts: tuple[str, ...] = ()   # appris, dans l'ordre de SORTS
    badges: int = 0
    badges_total: int = 0

    @property
    def emplacement(self) -> int:
        return 1    # une seule partie par fichier


def _sections(d: bytes) -> dict[int, dict[int, int]]:
    """clé de section → {clé : valeur}."""
    nombre = struct.unpack_from(">I", d, 0x60)[0]
    if not 0 < nombre <= 64 or 0x64 + 12 * nombre > len(d):
        raise ValueError("répertoire de sections illisible")
    sections = {}
    for k in range(nombre):
        cle, decalage, compte = struct.unpack_from(">III", d, 0x64 + 12 * k)
        position = _CORPS + decalage
        if compte > 4096 or position + 8 * compte > len(d):
            raise ValueError("section hors du fichier")
        sections[cle] = dict(struct.unpack_from(">II", d, position + 8 * i) for i in range(compte))
    return sections


def _date(d: bytes) -> datetime | None:
    annee, mois, _, jour, heure, minute, seconde = struct.unpack_from("<7I", d, 0x20)
    try:
        ecrite = datetime(annee, mois, jour, heure, minute, seconde)
    except (ValueError, OverflowError):
        return None
    return ecrite if 2000 <= annee <= 2100 else None


def lire(contenu: bytes) -> Partie | None:
    """La partie ; None si ce n'est pas une sauvegarde de HP6 telle que relevée."""
    if len(contenu) < 0x130 or contenu[:4] != b"20CM" or contenu[0x54:0x60] != b"HPHB2.00WN32":
        return None
    try:
        sections = _sections(contenu)
    except (ValueError, struct.error):
        log.warning("Folio HP6 : sauvegarde illisible", exc_info=True)
        return None
    ecussons = sections.get(hachage("CrestsCollected"))
    jauge = sections.get(hachage("Minicrestometer"))
    if ecussons is None or jauge is None:
        return None
    missions = sections.get(hachage("MissionId"), {})
    chapitre = sections.get(hachage("CurrentChapterId"), {})
    badges = sections.get(hachage("Badges"), {})
    sorts = tuple(s for s in SORTS if missions.get(hachage(f"SpellUnlock_{s}")))
    return Partie(
        _date(contenu),
        min(sum(1 for v in ecussons.values() if v), ECUSSONS),
        jauge.get(hachage("MiniCrestsCollected"), 0),
        next(iter(chapitre.values()), 0),
        sorts,
        sum(1 for v in badges.values() if v), len(badges))


def releve(chemin: Path) -> Partie | None:
    try:
        if chemin.stat().st_size > _TAILLE_MAX:
            return None
        return lire(chemin.read_bytes())
    except OSError:
        log.warning("Folio HP6 : %s illisible", chemin, exc_info=True)
        return None

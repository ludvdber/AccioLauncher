"""Le folio de HP6 : ce que `HPHBP0` dit de la partie du Prince de sang-mêlé.

Relevé le 2026-10-15 sur la sauvegarde de Ludo, en LECTURE seule, et VU contre
le menu de pause du jeu (« écussons 7 / 125 », « (372) ») :
`Harry-Potter-PC-Fix/notes/HP6.md`, « Mission d'analyse ».

    0x00   « 20CM », taille, 0x38, taille du corps
    0x20   année, mois, jour de la semaine, jour, heure, minute, seconde
           (entiers 32 bits petit-boutistes), écrits par le jeu
    0x54   corps « HPHB2.00WN32 », entiers GROS-boutistes
    0x60   nombre de sections, puis (clé, décalage, nombre) par section ;
           le décalage part de 0x58 ; la clé est le hachage ELF (PJW) du nom
           de la section en minuscules (« crestscollected »)

Seules les valeurs VUES à l'écran sont lues ici. Les sorts appris et les
chapitres sont dans la sauvegarde mais leur lecture reste À VÉRIFIER en jeu :
deux façons d'apparier clés et valeurs donnent deux réponses, l'écran « Liste
des sorts » tranchera (Ludo, 2026-10-15). Une seule partie par fichier.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

ECUSSONS = 125            # le « / 125 » du menu de pause
_BASE = 0x58
_TAILLE_MAX = 1024 * 1024  # 20 Ko chez Ludo


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
    ecussons: int            # écussons trouvés, sur ECUSSONS
    mini_ecussons: int       # la jauge du menu de pause (« (372) »)


def _sections(d: bytes) -> dict[int, tuple[int, int]]:
    """clé → (position absolue, nombre d'entrées)."""
    nombre = struct.unpack_from(">I", d, 0x60)[0]
    if not 0 < nombre <= 64 or 0x64 + 12 * nombre > len(d):
        raise ValueError("répertoire de sections illisible")
    sections = {}
    for k in range(nombre):
        cle, decalage, compte = struct.unpack_from(">III", d, 0x64 + 12 * k)
        position = _BASE + decalage
        if position + 8 * compte > len(d) + 4:
            raise ValueError("section hors du fichier")
        sections[cle] = (position, compte)
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
        ecussons = sections.get(hachage("CrestsCollected"))
        jauge = sections.get(hachage("Minicrestometer"))
        if ecussons is None or jauge is None:
            return None
        position, compte = ecussons
        # Une entrée remplie porte l'identifiant de l'écusson trouvé (VU : 7 sur 125).
        trouves = sum(1 for i in range(compte)
                      if struct.unpack_from(">I", contenu, position + 8 * i)[0])
        mini = struct.unpack_from(">I", contenu, jauge[0])[0]
    except (ValueError, struct.error):
        log.warning("Folio HP6 : sauvegarde illisible", exc_info=True)
        return None
    return Partie(_date(contenu), min(trouves, ECUSSONS), mini)


def releve(chemin: Path) -> Partie | None:
    try:
        if chemin.stat().st_size > _TAILLE_MAX:
            return None
        return lire(chemin.read_bytes())
    except OSError:
        log.warning("Folio HP6 : %s illisible", chemin, exc_info=True)
        return None

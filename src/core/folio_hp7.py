"""Le folio de HP7 et HP8 : ce que `auto.sav` des Reliques de la Mort dit de la partie.

Relevé le 2026-10-16 sur les deux sauvegardes de Ludo, en LECTURE seule
(`Harry-Potter-PC-Fix/notes/HP7a.md`, « auto.sav : des variables NOMMÉES ») :
une table de noms (nombre, puis `nom\\0` suivi de l'indice du suivant, à
partir de `LastSaveCheckpoint`), puis des valeurs typées, chacune avec
l'indice de son nom :

    F32____\\0  indice (4)  réel (4)
    S32____\\0  indice (4)  entier (4)
    STRING_\\0  indice (4)  chaîne terminée par zéro

Seules les valeurs ENTIÈRES et RÉELLES sont lues ; elles sont cherchées par
leur étiquette, pas en chaîne : une chaîne de longueur inattendue ne décale
rien. Noms communs aux deux parties : `Completed_ns01` … `Completed_ns27`
(22 missions annexes, numérotées avec des trous), `PlayerLevel`,
`PlayerXP` ; la partie 1 compte aussi ses combats (`KillCount`,
`HeadShotCount`, `StealthKillCount`, `ProtegoDeflects`, `AcroKillCount`,
`DemKillCount`). Les deux parties de Ludo datent du tout début : les valeurs
non nulles sont à revoir sur une partie avancée.
"""

from __future__ import annotations

import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_TAILLE_MAX = 1024 * 1024        # 7,5 et 11 Ko chez Ludo
_PREMIER = b"LastSaveCheckpoint"
_ENTIER, _REEL = b"S32____\x00", b"F32____\x00"
_MISSION = re.compile(r"Completed_ns\d\d")

# Les combats de la partie 1, dans l'ordre de la page : nom dans la
# sauvegarde → libellé (passé à `tr()` à l'affichage).
COMBATS = (
    ("KillCount", "Ennemis vaincus"),
    ("HeadShotCount", "Tirs à la tête"),
    ("StealthKillCount", "Éliminations discrètes"),
    ("ProtegoDeflects", "Sorts renvoyés par Protego"),
    ("AcroKillCount", "Acromantules vaincues"),
    ("DemKillCount", "Détraqueurs repoussés"),
)


@dataclass(frozen=True)
class Partie:
    chemin: Path
    ecrite: datetime | None
    emplacement: int = 1
    lu: bool = False
    valeurs: dict[str, float] = field(default_factory=dict)
    missions: tuple[str, ...] = ()        # les noms `Completed_ns…` de CE jeu

    @property
    def missions_terminees(self) -> int:
        return sum(1 for m in self.missions if self.valeurs.get(m, 0) > 0)

    def entier(self, nom: str) -> int | None:
        """La valeur, ou None si ce jeu n'a pas ce nom (HP8 n'a pas de combats)."""
        v = self.valeurs.get(nom)
        return None if v is None else max(0, int(v))


def _noms(contenu: bytes) -> list[str]:
    debut = contenu.find(_PREMIER)
    if debut < 8:
        return []
    nombre = struct.unpack_from("<i", contenu, debut - 8)[0]
    if not 0 < nombre <= 4096:
        return []
    noms, pos = [], debut
    for k in range(nombre):
        fin = contenu.find(b"\x00", pos)
        if fin < 0 or fin - pos > 128:
            return []
        noms.append(contenu[pos:fin].decode("latin-1"))
        pos = fin + 1 + (4 if k < nombre - 1 else 0)
    return noms


def lire(contenu: bytes) -> tuple[dict[str, float], tuple[str, ...]] | None:
    """(valeurs par nom, noms des missions annexes) ; None sans table de noms."""
    try:
        noms = _noms(contenu)
    except struct.error:
        return None
    if not noms:
        return None
    valeurs: dict[str, float] = {}
    for etiquette, format_ in ((_ENTIER, "<i"), (_REEL, "<f")):
        pos = contenu.find(etiquette)
        while 0 <= pos <= len(contenu) - 16:
            indice = struct.unpack_from("<i", contenu, pos + 8)[0]
            if 0 <= indice < len(noms):
                valeurs.setdefault(noms[indice], struct.unpack_from(format_, contenu, pos + 12)[0])
            pos = contenu.find(etiquette, pos + 16)
    # Un nom de la table sans valeur lue vaut zéro ; un nom ABSENT de la table
    # (les combats, dans HP8) reste absent : `Partie.entier` rend None.
    for nom in noms:
        valeurs.setdefault(nom, 0)
    return valeurs, tuple(n for n in noms if _MISSION.fullmatch(n))


def releve(chemin: Path) -> Partie | None:
    """La partie de `auto.sav` ; None si le fichier ne se lit pas."""
    try:
        infos = chemin.stat()
        if infos.st_size > _TAILLE_MAX:
            return None
        contenu = chemin.read_bytes()
    except OSError:
        log.warning("Folio HP7 : %s illisible", chemin, exc_info=True)
        return None
    ecrite = datetime.fromtimestamp(infos.st_mtime)
    lu = lire(contenu)
    if lu is None:
        return Partie(chemin, ecrite)
    return Partie(chemin, ecrite, 1, True, lu[0], lu[1])

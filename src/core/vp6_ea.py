"""Sauter dans une cinématique `.vp6` d'EA (HP4 à HP8) sans la casser.

Le conteneur d'EA est une suite de blocs : `MVhd` (l'en-tête), puis une image
par bloc, `MV0K` pour une image complète, `MV0F` pour une image qui ne dit que
ce qui change depuis la précédente. Il n'a pas d'index : le lecteur (FFmpeg)
qui saute au milieu tombe sur une image partielle et décode du bruit, des
pavés verts et roses jusqu'à la fin (Ludo, 2026-10-27, reproduit sur
`ns01.vp6` de HP6). Les images complètes sont espacées de 4 s chez HP5 et
HP6, de 0,4 s chez HP4 ; HP7 et HP8 n'en ont qu'une, la première.

Le remède : une copie qui commence à l'image complète la plus proche AVANT le
point voulu, jouée depuis son début. Le lecteur rattrape le reste en avance
rapide sans rien montrer (`VideoPlayer`).
"""

import struct
from dataclasses import dataclass
from pathlib import Path

_ENTETE = b"MVhd"
_COMPLETE = b"MV0K"
_PARTIELLE = b"MV0F"


@dataclass(frozen=True)
class Index:
    entete: bytes                         # le bloc MVhd tel quel
    images_par_seconde: float
    nombre: int                           # images du fichier
    completes: tuple[tuple[int, int], ...]  # (numéro d'image, position du bloc)

    def ms(self, image: int) -> int:
        return round(image * 1000 / self.images_par_seconde)

    @property
    def duree_ms(self) -> int:
        return self.ms(self.nombre)


def indexer(chemin: str | Path) -> Index | None:
    """Les images complètes et leur place ; None si ce n'est pas un `.vp6` d'EA.

    En-têtes de blocs seulement, lus en sautant : une cinématique de HP8 pèse
    jusqu'à 330 Mo pour 5 500 blocs.
    """
    try:
        with open(chemin, "rb") as f:
            entete = f.read(32)
            if len(entete) < 32 or entete[:4] != _ENTETE:
                return None
            taille_entete = struct.unpack_from("<I", entete, 4)[0]
            num, den = struct.unpack_from("<II", entete, 24)
            if taille_entete < 32 or not num or not den:
                return None
            f.seek(0)
            entete = f.read(taille_entete)
            completes: list[tuple[int, int]] = []
            pos, numero = taille_entete, 0
            while len(bloc := f.read(8)) == 8:
                taille = struct.unpack_from("<I", bloc, 4)[0]
                if taille < 8:
                    break
                if bloc[:4] == _COMPLETE:
                    completes.append((numero, pos))
                if bloc[:4] in (_COMPLETE, _PARTIELLE):
                    numero += 1
                pos += taille
                f.seek(pos)
    except OSError:
        return None
    if not completes:
        return None
    return Index(entete, num / den, numero, tuple(completes))


def copie_depuis(chemin: str | Path, index: Index, ms: int, cible: Path) -> int:
    """Écrit dans `cible` la cinématique à partir de l'image complète qui
    précède `ms` ; rend l'instant de cette image, en millisecondes."""
    image, position = index.completes[0]
    for numero, pos in index.completes:
        if index.ms(numero) > ms:
            break
        image, position = numero, pos
    entete = bytearray(index.entete)
    struct.pack_into("<I", entete, 16, index.nombre - image)
    with open(chemin, "rb") as source, open(cible, "wb") as sortie:
        sortie.write(entete)
        source.seek(position)
        while morceau := source.read(1 << 20):
            sortie.write(morceau)
    return index.ms(image)

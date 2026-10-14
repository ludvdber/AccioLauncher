"""Lire une texture dans un paquet Unreal 1 du jeu INSTALLÉ (HP1 à HP3).

Premier usage : les cartes de sorciers du folio HP1 (`folio.py`), qui vivent
dans `System/HPMenu.u` sous les noms `WizCard<Nom>BigTexture` (256 × 256) et
`WizCard<Nom>SmallTexture` (128 × 128), en 256 couleurs avec palette. Relevé
le 2026-10-14 sur le HP1 de Ludo : paquet de version 76.

Lecture SEULE et bornée : aucun octet n'est écrit, un paquet de plus de 64 Mo
n'est pas lu, et tout ce qui ne ressemble pas à ce qui a été relevé (autre
format que la palette, taille absurde, table tronquée) rend None au lieu
d'une image fausse. Aucune image du jeu n'est recopiée dans le launcher : elle
est lue chez la personne, dans SA copie.

Format (paquets Unreal 1, version ≥ 63) : en-tête, table des noms, des
imports et des exports ; un objet commence par ses propriétés « étiquetées »
terminées par le nom `None`, puis ses données propres. Une texture y range
ses niveaux de détail (le premier est le plein format), une palette ses
couleurs en RVBA.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

_SIGNATURE = 0x9E2A83C1
_TAILLE_MAX = 64 * 1024 * 1024
_COTE_MAX = 2048
# Taille des données d'une propriété selon son code (bits 4 à 6 de l'octet d'info).
_TAILLES = (1, 2, 4, 12, 16)
_STRUCT, _BOOL, _OBJET, _OCTET = 10, 3, 5, 1


@dataclass(frozen=True)
class TexturePaletee:
    largeur: int
    hauteur: int
    indices: bytes                                  # un octet par pixel
    palette: tuple[tuple[int, int, int, int], ...]  # (r, v, b, a)
    masquee: bool                                   # l'indice 0 est transparent


class _Lecteur:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.d = data
        self.p = pos

    def octet(self) -> int:
        v = self.d[self.p]
        self.p += 1
        return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def index(self) -> int:
        """L'entier compact d'Unreal : signe et 6 bits, puis 7 bits par octet."""
        b = self.octet()
        negatif, valeur, decalage = b & 0x80, b & 0x3F, 6
        suite = b & 0x40
        while suite:
            if decalage > 27:
                raise ValueError("entier compact trop long")
            b = self.octet()
            valeur |= (b & 0x7F) << decalage
            decalage += 7
            suite = b & 0x80
        return -valeur if negatif else valeur


class Paquet:
    """Les tables d'un paquet ; les objets se lisent à la demande."""

    def __init__(self, data: bytes) -> None:
        lec = _Lecteur(data)
        signature = lec.i32() & 0xFFFFFFFF
        if signature != _SIGNATURE:
            raise ValueError("pas un paquet Unreal")
        version = lec.i32() & 0xFFFF
        if version < 63:
            raise ValueError(f"version {version} non prise en charge")
        lec.i32()   # drapeaux
        nb_noms, pos_noms, nb_exports, pos_exports, nb_imports, pos_imports = (
            lec.i32() for _ in range(6))
        self._d = data
        self.noms: list[str] = []
        lec.p = pos_noms
        for _ in range(nb_noms):
            taille = lec.index()
            if not 0 <= taille <= 1024:
                raise ValueError("nom illisible")
            self.noms.append(data[lec.p:lec.p + taille].rstrip(b"\0").decode("latin-1"))
            lec.p += taille + 4
        self._imports: list[str] = []
        lec.p = pos_imports
        for _ in range(nb_imports):
            lec.index()
            lec.index()
            lec.i32()
            self._imports.append(self.noms[lec.index()])
        self._exports: list[tuple[int, str, int, int]] = []   # classe, nom, taille, position
        self._par_nom: dict[str, int] = {}
        lec.p = pos_exports
        for _ in range(nb_exports):
            classe = lec.index()
            lec.index()
            lec.i32()
            nom = self.noms[lec.index()]
            lec.i32()
            taille = lec.index()
            position = lec.index() if taille > 0 else 0
            self._par_nom.setdefault(nom, len(self._exports))
            self._exports.append((classe, nom, taille, position))

    def _classe(self, ref: int) -> str:
        if ref < 0:
            return self._imports[-ref - 1]
        return self._exports[ref - 1][1] if ref > 0 else ""

    def _proprietes(self, lec: _Lecteur, fin: int) -> dict[str, bytes | bool]:
        props: dict[str, bytes | bool] = {}
        while lec.p < fin:
            nom = self.noms[lec.index()]
            if nom == "None":
                return props
            info = lec.octet()
            genre, code, tableau = info & 0x0F, (info >> 4) & 7, info & 0x80
            if genre == _STRUCT:
                lec.index()
            if code < 5:
                taille = _TAILLES[code]
            elif code == 5:
                taille = lec.octet()
            elif code == 6:
                taille = struct.unpack_from("<H", lec.d, lec.p)[0]
                lec.p += 2
            else:
                taille = lec.i32()
            if genre == _BOOL:
                # La valeur est le bit « tableau » ; pas d'octets (taille 0, relevé).
                props[nom] = bool(tableau)
                lec.p += taille
                continue
            if tableau:
                b = lec.d[lec.p]
                lec.p += 1 if b & 0x80 == 0 else 2 if b & 0xC0 == 0x80 else 4
            props.setdefault(nom, lec.d[lec.p:lec.p + taille])
            lec.p += taille
        raise ValueError("propriétés sans fin")

    def texture(self, nom: str) -> TexturePaletee | None:
        rang = self._par_nom.get(nom)
        if rang is None:
            return None
        classe, _, taille, position = self._exports[rang]
        if self._classe(classe) != "Texture" or taille <= 0:
            return None
        fin = position + taille
        lec = _Lecteur(self._d, position)
        props = self._proprietes(lec, fin)
        format_ = props.get("Format")
        if isinstance(format_, bytes) and format_ and format_[0] != 0:
            return None   # seul le 256 couleurs (P8) a été relevé
        if lec.octet() < 1:
            return None
        lec.i32()   # position de fin du niveau
        octets = lec.index()
        indices = self._d[lec.p:lec.p + octets]
        lec.p += octets
        largeur, hauteur = lec.i32(), lec.i32()
        if not (0 < largeur <= _COTE_MAX and 0 < hauteur <= _COTE_MAX
                and len(indices) == largeur * hauteur and lec.p <= fin):
            return None
        palette = self._palette(props.get("Palette"))
        if palette is None:
            return None
        return TexturePaletee(largeur, hauteur, bytes(indices), palette,
                              props.get("bMasked") is True)

    def _palette(self, ref: object) -> tuple[tuple[int, int, int, int], ...] | None:
        if not isinstance(ref, bytes) or not ref:
            return None
        rang = _Lecteur(ref).index()
        if rang <= 0 or rang > len(self._exports):
            return None
        classe, _, taille, position = self._exports[rang - 1]
        if self._classe(classe) != "Palette":
            return None
        lec = _Lecteur(self._d, position)
        self._proprietes(lec, position + taille)
        nombre = lec.index()
        if not 0 < nombre <= 256:
            return None
        brut = self._d[lec.p:lec.p + 4 * nombre]
        if len(brut) != 4 * nombre:
            return None
        couleurs = [tuple(brut[i:i + 4]) for i in range(0, len(brut), 4)]
        couleurs += [(0, 0, 0, 255)] * (256 - nombre)
        return tuple(couleurs)


@lru_cache(maxsize=2)
def _ouvrir(chemin: str, _mtime: float, _taille: int) -> Paquet | None:
    try:
        return Paquet(Path(chemin).read_bytes())
    except (OSError, ValueError, IndexError, struct.error):
        log.warning("Paquet Unreal illisible : %s", chemin, exc_info=True)
        return None


def paquet(chemin: Path) -> Paquet | None:
    """Le paquet lu une fois (gardé tant que le fichier ne change pas)."""
    try:
        infos = chemin.stat()
    except OSError:
        return None
    if infos.st_size > _TAILLE_MAX:
        return None
    return _ouvrir(str(chemin), infos.st_mtime, infos.st_size)


def texture(chemin: Path, nom: str) -> TexturePaletee | None:
    """La texture `nom` du paquet ; None si absente ou pas comme relevé."""
    p = paquet(chemin)
    if p is None:
        return None
    try:
        return p.texture(nom)
    except (ValueError, IndexError, struct.error):
        log.warning("Texture %s illisible dans %s", nom, chemin, exc_info=True)
        return None

"""Lire une texture dans un paquet Unreal 1 du jeu INSTALLÉ (HP1 à HP3).

Et les propriétés d'un objet de sauvegarde (`proprietes`) : l'acteur Harry de
HP1, les gestionnaires de HP3 (paquet Unreal 2, version 129). Dans un paquet
Unreal 2, les structures et les tableaux de structures sont eux-mêmes des
propriétés étiquetées, imbriquées : `proprietes(..., decoder=True)` les rend
en valeurs Python (relevé le 2026-10-15 sur les sauvegardes HP3 de Ludo).

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

import logging
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.core import images_ea

log =logging.getLogger(__name__)

_SIGNATURE = 0x9E2A83C1
_TAILLE_MAX = 64 * 1024 * 1024
_COTE_MAX = 2048
# Taille des données d'une propriété selon son code (bits 4 à 6 de l'octet d'info).
_TAILLES = (1, 2, 4, 12, 16)
_STRUCT, _BOOL, _OBJET, _OCTET = 10, 3, 5, 1
_OCTET_, _ENTIER, _REEL, _NOM, _CLASSE, _TABLEAU, _CHAINE = 1, 2, 4, 6, 8, 9, 13
_PROFONDEUR_MAX = 8   # structures dans des tableaux dans des structures…
# Drapeau d'objet : un cadre d'état (script en cours) précède ses propriétés.
# Les acteurs d'une sauvegarde le portent, jamais une texture.
_RF_HAS_STACK = 0x02000000
# `ETextureFormat` d'Unreal 2 lus par `texture_32` → octets par bloc de 4 × 4.
_DXT1, _RGBA8, _DXT5 = 3, 5, 8
_FORMATS_32 = {_DXT1: 8, _RGBA8: 64, _DXT5: 16}

Propriete = tuple[str, int, "bytes | bool"]   # nom, indice de tableau, valeur brute
# nom, indice, valeur décodée : int, float, str, bool, liste de propriétés
# (structure), liste de listes (tableau de structures), ou bytes si inconnue.
ProprieteLue = tuple[str, int, object]


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
        v: int = struct.unpack_from("<i", self.d, self.p)[0]
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
        # Chaque entrée occupe au moins un octet : un compteur plus grand que le
        # fichier ne peut être que faux (sinon des millions de tours avant l'erreur).
        if not all(0 <= n <= len(data) for n in (nb_noms, nb_exports, nb_imports)):
            raise ValueError("tables plus grandes que le paquet")
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
        # classe, nom, taille, position, drapeaux
        self._exports: list[tuple[int, str, int, int, int]] = []
        self._par_nom: dict[str, int] = {}
        self._parents: list[int] = []   # la classe parente (super) de chaque export
        lec.p = pos_exports
        for _ in range(nb_exports):
            classe = lec.index()
            self._parents.append(lec.index())
            lec.i32()
            nom = self.noms[lec.index()]
            drapeaux = lec.i32() & 0xFFFFFFFF
            taille = lec.index()
            position = lec.index() if taille > 0 else 0
            self._par_nom.setdefault(nom, len(self._exports))
            self._exports.append((classe, nom, taille, position, drapeaux))

    def _classe(self, ref: int) -> str:
        if ref < 0:
            return self._imports[-ref - 1]
        return self._exports[ref - 1][1] if ref > 0 else ""

    def _proprietes(self, lec: _Lecteur, fin: int) -> dict[str, bytes | bool]:
        """Par nom ; d'un tableau, le premier élément écrit seulement."""
        props: dict[str, bytes | bool] = {}
        for nom, _, valeur in self._etiquettes(lec, fin):
            props.setdefault(nom, valeur)
        return props

    def _etiquettes(self, lec: _Lecteur, fin: int) -> list[Propriete]:
        """Les propriétés étiquetées jusqu'au nom `None`, dans l'ordre écrit."""
        return [(nom, indice, valeur) for nom, indice, _, valeur in self._brutes(lec, fin)]

    def _brutes(self, lec: _Lecteur, fin: int) -> list[tuple[str, int, int, bytes | bool]]:
        """(nom, indice, genre, valeur brute), jusqu'au nom `None`."""
        props: list[tuple[str, int, int, bytes | bool]] = []
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
            if taille < 0:
                # Elle ferait RECULER la lecture : boucle sans fin.
                raise ValueError("taille de propriété négative")
            if genre == _BOOL:
                # La valeur est le bit « tableau » ; pas d'octets (taille 0, relevé).
                props.append((nom, 0, genre, bool(tableau)))
                lec.p += taille
                continue
            indice = 0
            if tableau:
                # Indice sur 1, 2 ou 4 octets, poids fort d'abord, marqué par
                # ses deux bits hauts.
                b = lec.d[lec.p]
                if b & 0x80 == 0:
                    indice, lec.p = b, lec.p + 1
                elif b & 0xC0 == 0x80:
                    indice, lec.p = ((b & 0x3F) << 8) | lec.d[lec.p + 1], lec.p + 2
                else:
                    indice = int.from_bytes(lec.d[lec.p:lec.p + 4], "big") & 0x3FFFFFFF
                    lec.p += 4
            props.append((nom, indice, genre, lec.d[lec.p:lec.p + taille]))
            lec.p += taille
        raise ValueError("propriétés sans fin")

    def _lues(self, brut: bytes, debut: int, profondeur: int) -> tuple[list[ProprieteLue], int]:
        """Des propriétés imbriquées dans `brut` ; (liste, position après `None`)."""
        if profondeur > _PROFONDEUR_MAX:
            raise ValueError("imbrication trop profonde")
        lec = _Lecteur(brut, debut)
        brutes = self._brutes(lec, len(brut))   # laisse `lec` juste après le `None`
        return [(nom, indice, self._valeur(genre, valeur, profondeur + 1))
                for nom, indice, genre, valeur in brutes], lec.p

    def _valeur(self, genre: int, brut: bytes | bool, profondeur: int) -> object:
        if isinstance(brut, bool):
            return brut
        try:
            if genre == _ENTIER and len(brut) == 4:
                return int.from_bytes(brut, "little", signed=True)
            if genre == _OCTET_ and len(brut) == 1:
                return brut[0]
            if genre == _REEL and len(brut) == 4:
                return struct.unpack("<f", brut)[0]
            if genre == _NOM:
                return self.noms[_Lecteur(brut).index()]
            if genre in (_OBJET, _CLASSE):
                return self._classe(_Lecteur(brut).index())
            if genre == _CHAINE:
                lec = _Lecteur(brut)
                n = lec.index()
                if n < 0:
                    return brut[lec.p:lec.p - 2 * n].decode("utf-16-le").rstrip("\0")
                return brut[lec.p:lec.p + n].decode("latin-1").rstrip("\0")
            if genre == _STRUCT:
                props, fin = self._lues(brut, 0, profondeur)
                return props if fin == len(brut) else brut
            if genre == _TABLEAU:
                lec = _Lecteur(brut)
                nombre = lec.index()
                if not 0 <= nombre <= len(brut):
                    return brut
                elements, pos = [], lec.p
                for _ in range(nombre):
                    props, pos = self._lues(brut, pos, profondeur)
                    elements.append(props)
                return elements if pos == len(brut) else brut
        except (ValueError, IndexError, struct.error, UnicodeDecodeError):
            # Un tableau d'entiers (pas de structures) ou un format non relevé :
            # la valeur brute, jamais une lecture inventée.
            return brut
        return brut

    def proprietes(self, classe: str) -> list[Propriete] | None:
        """Les propriétés du premier objet de classe `classe`, indices de
        tableau compris ; None s'il n'y en a pas.

        Unreal n'écrit que ce qui diffère de la valeur par défaut : une
        propriété absente de la liste vaut son défaut.
        """
        debut = self._debut_objet(classe)
        if debut is None:
            return None
        return self._etiquettes(_Lecteur(self._d, debut[0]), debut[1])

    def lues(self, classe: str) -> list[ProprieteLue] | None:
        """Comme `proprietes`, valeurs décodées (structures et tableaux de
        structures d'un paquet Unreal 2 compris)."""
        debut = self._debut_objet(classe)
        if debut is None:
            return None
        return [(nom, indice, self._valeur(genre, valeur, 0))
                for nom, indice, genre, valeur in self._brutes(_Lecteur(self._d, debut[0]), debut[1])]

    def classes(self, prefixe: str) -> dict[str, bytes]:
        """Les classes définies dans ce paquet dont le nom commence par
        `prefixe`, avec leurs octets (propriétés par défaut comprises)."""
        return {nom: self._d[position:position + taille]
                for genre, nom, taille, position, _ in self._exports
                # Unreal ignore la casse des noms : `wc_ThaddeusThurkell` est une carte.
                if genre == 0 and nom.lower().startswith(prefixe.lower()) and taille > 0}

    def parent(self, nom: str) -> str:
        """La classe dont hérite l'export `nom` (`WCStarkey` → `BronzeCards`) ;
        vide s'il n'y en a pas."""
        rang = self._par_nom.get(nom)
        return self._classe(self._parents[rang]) if rang is not None else ""

    def indice_nom(self, nom: str) -> int | None:
        try:
            return self.noms.index(nom)
        except ValueError:
            return None

    def _debut_objet(self, classe: str) -> tuple[int, int] | None:
        """(début des propriétés, fin de l'objet) du premier objet de `classe`."""
        for genre, _, taille, position, drapeaux in self._exports:
            if taille <= 0 or self._classe(genre) != classe:
                continue
            lec = _Lecteur(self._d, position)
            if drapeaux & _RF_HAS_STACK:
                # Nœud, nœud d'état, masque (8 octets), action latente (4),
                # puis la position dans le code si un nœud est en cours.
                noeud = lec.index()
                lec.index()
                lec.p += 12
                if noeud:
                    lec.index()
            return lec.p, position + taille
        return None

    def texture(self, nom: str) -> TexturePaletee | None:
        rang = self._par_nom.get(nom)
        if rang is None:
            return None
        classe, _, taille, position, _ = self._exports[rang]
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

    def texture_32(self, nom: str) -> tuple[int, int, bytes] | None:
        """Une texture d'Unreal 2 en (largeur, hauteur, pixels B V R A) :
        `Format` 5 (RGBA8, rangé B V R A), 3 (DXT1) ou 8 (DXT5). Les boucliers
        et les étoiles de défi du menu de HP3 sont en RGBA8, les icônes des
        friandises (`Beans`, `PumpkinPasties`…) en DXT5 (relevé le 2026-10-17).
        Un même nom peut porter deux textures : la première lisible l'emporte."""
        if nom not in self._par_nom:
            return None
        for classe, nom_, taille, position, _ in self._exports[self._par_nom[nom]:]:
            if nom_ == nom and taille > 0 and self._classe(classe) == "Texture":
                image = self._texture_32(position, position + taille)
                if image is not None:
                    return image
        return None

    def _texture_32(self, position: int, fin: int) -> tuple[int, int, bytes] | None:
        lec = _Lecteur(self._d, position)
        format_ = self._proprietes(lec, fin).get("Format")
        code = format_[0] if isinstance(format_, bytes) and format_ else None
        if code not in _FORMATS_32 or lec.octet() < 1:
            return None
        lec.i32()
        octets = lec.index()
        donnees = self._d[lec.p:lec.p + octets]
        lec.p += octets
        largeur, hauteur = lec.i32(), lec.i32()
        if not (0 < largeur <= _COTE_MAX and 0 < hauteur <= _COTE_MAX and lec.p <= fin):
            return None
        if code == _RGBA8:
            return (largeur, hauteur, bytes(donnees)) if len(donnees) == 4 * largeur * hauteur else None
        if largeur % 4 or hauteur % 4 or len(donnees) != _FORMATS_32[code] * largeur * hauteur // 16:
            return None
        decode = images_ea.dxt1 if code == _DXT1 else images_ea.dxt5
        return largeur, hauteur, decode(bytes(donnees), largeur, hauteur)

    def _palette(self, ref: object) -> tuple[tuple[int, int, int, int], ...] | None:
        if not isinstance(ref, bytes) or not ref:
            return None
        rang = _Lecteur(ref).index()
        if rang <= 0 or rang > len(self._exports):
            return None
        classe, _, taille, position, _ = self._exports[rang - 1]
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
        couleurs = [(brut[i], brut[i + 1], brut[i + 2], brut[i + 3])
                    for i in range(0, len(brut), 4)]
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


def texture_32(chemin: Path, nom: str) -> tuple[int, int, bytes] | None:
    """La texture 32 bits `nom` du paquet (B V R A) ; None si absente ou autre."""
    p = paquet(chemin)
    if p is None:
        return None
    try:
        return p.texture_32(nom)
    except (ValueError, IndexError, struct.error):
        log.warning("Texture %s illisible dans %s", nom, chemin, exc_info=True)
        return None

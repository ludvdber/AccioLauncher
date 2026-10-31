"""Les modèles 3D de HP5 et HP6 : le format EA « FPM » (FPM4, FPM8).

Demande de Ludo (2026-10-31) : les Personnages de HP5 et HP6 en 3D, comme
ceux de HP1-HP3 (« c'était une update pour la Collection et finalement ce
sont les moins avancées »). Format relevé dans l'atelier (`notes/RENDERWARE.md`,
lecteur `fpm_obj2.py`, comptes justes sur 7 modèles des trois jeux) :

- Les modèles vivent dans les flux STRM des archives BIGF (`data2.big` de
  HP5, `data3.big` de HP6) : `events/body_models/body_<nom>.str.shd` pour le
  corps, `heads/head_models/head_<nom>.str.shd` pour la tête des élèves (le
  corps d'un élève n'en a pas). Le `.shd` porte la version haute (textures
  `_ps3_cm`), le `.ffs` la basse. Un asset de type 0x6B43 = le FPM ; les
  textures sont des blocs SHPI du même flux (`images_ea`).
- FPM : F+0x80 {n parties, offset} → parties de 0x30 → niveaux de détail de
  0x40 → fiches de 0x30 {boîtes, offset du sous-maillage, extra, palette,
  u8 matériau}. Sous-maillage `PH` : S+0x02 indices, S+0x04 triangles,
  S+0x14 offset des indices (depuis F + u32(F+0x0C)), S+0x24 pas du sommet,
  S+0x25 & 0x80 disposition haute, S+0x26 sommets, sommets à S+0x40. Indices :
  une bande de triangles (les dégénérés s'écartent).
- Matériaux (16 octets à F+u32(F+0x8C)) : u32 offset d'une fiche dont le u16
  de tête est l'indice de texture ; textures nommées à F+u32(F+0x94).
- Repère : Y en haut, le modèle regarde +Z. Converti vers celui des modèles
  Unreal de la visionneuse (X devant, Y à sa gauche, Z en haut).

Seule la pose de liaison se montre : les mouvements sont des banques CCT
(`.rcb` + `.bnk`) que personne n'a encore décodées. Le niveau de détail 0
(le plus fin) de chaque partie est gardé.
"""

import logging
import struct
from collections.abc import Iterable
from pathlib import Path

from src.core import archives_ea, images_ea
from src.core.maillages_ue1 import PF_DEUX_FACES, PF_MASQUE, Face, Maillage, Materiau, Point, UV

log = logging.getLogger(__name__)

_MAGIES = (b"FPM4", b"FPM8")
_TYPE_FPM = 0x6B43
_COTE_TEXTURE = 512
_PLAFOND = 16 << 20
# Le haut du col des corps pour lesquels les têtes sont modelées (corps moldus
# de HP5 : 1,406 à 1,411).
_COL = 1.408
# Les textures communes à tous les personnages de HP6 (mains, cils, bouche,
# baguette), rangées une fois pour le chapitre et non dans chaque modèle
# (relevé du 2026-10-31). Une entrée absente de l'archive (HP5) est passée.
_COMMUNS = ("events/body_models/body_generic_female.str.shd", "chapters/hogwarts.str.shd",
            "chapters/hogwarts.str.ffs")
Textures = dict[str, tuple[int, int, bytes]]


def _u32(d: bytes, p: int) -> int:
    v: int = struct.unpack_from("<I", d, p)[0]
    return v


def _u16(d: bytes, p: int) -> int:
    v: int = struct.unpack_from("<H", d, p)[0]
    return v


def _chaine(d: bytes, p: int) -> str:
    return d[p:d.index(b"\0", p)].decode("latin-1")


def assets_strm(flux: bytes) -> list[tuple[int, str, bytes]]:
    """(type, nom, données) de chaque asset d'un flux STRM (magies écrites à
    l'envers : « MRTS »)."""
    def magie(p: int) -> tuple[bytes, int]:
        return flux[p:p + 4][::-1], _u32(flux, p + 4)
    m, taille = magie(0)
    if m != b"STRM" or taille != len(flux):
        raise ValueError("pas un flux STRM complet")
    sortie = []
    p = 8
    while p + 8 <= len(flux):
        m, t = magie(p)
        if m != b"AGRP" or t < 8:
            break
        q = p + 8
        while q + 8 <= p + t:
            m3, t3 = magie(q)
            if m3 == b"ASET":
                _id, type_, _a, _b, _c, debut, longueur, nom, _d = struct.unpack_from("<IHHIIIIII", flux, q + 8)
                if debut + longueur > len(flux):
                    raise ValueError("asset hors du flux")
                sortie.append((type_, _chaine(flux, nom), flux[debut:debut + longueur]))
            if t3 < 8:
                raise ValueError("bloc vide")
            q += t3
        p += t
    return sortie


def _bande(indices: tuple[int, ...]) -> list[tuple[int, int, int]]:
    tris = []
    for i in range(2, len(indices)):
        a, b, c = indices[i - 2], indices[i - 1], indices[i]
        if a == b or b == c or a == c:
            continue
        tris.append((a, b, c) if i % 2 == 0 else (a, c, b))
    return tris


def lire(d: bytes) -> tuple[list[Point], list[tuple[tuple[int, int, int], tuple[UV, UV, UV], str]]]:
    """Les points (repère de la visionneuse) et les triangles (sommets, UV,
    nom de texture) du niveau de détail 0 d'un FPM4 ou FPM8."""
    if d[:4] not in _MAGIES:
        raise ValueError("pas un FPM4 / FPM8")
    base_idx = _u32(d, 0x0C)
    nb_mat, off_mat = _u32(d, 0x88), _u32(d, 0x8C)
    nb_tex, off_tex = _u32(d, 0x90), _u32(d, 0x94)
    textures = [_chaine(d, _u32(d, off_tex + 4 * i)) for i in range(nb_tex)]
    mat_tex = [_u16(d, _u32(d, off_mat + 16 * i)) for i in range(nb_mat)]
    points: list[Point] = []
    faces: list[tuple[tuple[int, int, int], tuple[UV, UV, UV], str]] = []
    for a in range(_u32(d, 0x80)):
        partie = _u32(d, 0x84) + 0x30 * a
        if _u32(d, partie + 0x20) == 0:
            continue
        niveau = _u32(d, partie + 0x24)            # le niveau 0 : le plus fin
        for c in range(_u32(d, niveau + 0x20)):
            fiche = _u32(d, niveau + 0x28) + 0x30 * c
            s = _u32(d, fiche + 0x20)
            if d[s:s + 2] != b"PH":
                raise ValueError("sous-maillage introuvable")
            nb_idx, nb_som = _u16(d, s + 2), _u16(d, s + 0x26)
            pas, haute = d[s + 0x24], bool(d[s + 0x25] & 0x80)
            o_uv = pas - 8 if haute else 24
            i0 = base_idx + _u32(d, s + 0x14)
            if pas < 32 or s + 0x40 + nb_som * pas > i0 or i0 + 2 * nb_idx > len(d):
                raise ValueError("sous-maillage hors du fichier")
            m = d[fiche + 0x2C]
            texture = textures[mat_tex[m]] if m < len(mat_tex) and mat_tex[m] < len(textures) else ""
            premier = len(points)
            uvs: list[UV] = []
            p = s + 0x40
            for _ in range(nb_som):
                x, y, z = struct.unpack_from("<3f", d, p)
                points.append((z, x, y))
                u, v = struct.unpack_from("<2f", d, p + o_uv)
                uvs.append((u, v))
                p += pas
            indices: tuple[int, ...] = struct.unpack_from(f"<{nb_idx}H", d, i0)
            for t in _bande(indices):
                if max(t) >= nb_som:
                    raise ValueError("indice hors du sous-maillage")
                faces.append(((premier + t[0], premier + t[1], premier + t[2]),
                              (uvs[t[0]], uvs[t[1]], uvs[t[2]]), texture))
    return points, faces


def _fpms(flux: bytes) -> list[bytes]:
    """Les FPM d'un flux : un seul d'ordinaire, deux quand la tête d'un adulte
    est à part de son corps dans le même flux (Dumbledore de HP5)."""
    trouves = [d for type_, _nom, d in assets_strm(flux) if type_ == _TYPE_FPM and d[:4] in _MAGIES]
    if not trouves:
        raise ValueError("pas de FPM dans le flux")
    return trouves


def _textures(flux: bytes, voulues: set[str]) -> Textures:
    positions = images_ea.images_nommees(flux)
    sortie: Textures = {}
    for nom in voulues:
        q = positions.get(nom)
        image = images_ea.image(flux, q, _COTE_TEXTURE) if q is not None else None
        if image is not None:
            sortie[nom] = image
    return sortie


def _a_de_la_transparence(image: tuple[int, int, bytes]) -> bool:
    return any(a < 128 for a in image[2][3::4])


def _hausse_de_la_tete(points: list[Point],
                       faces: list[tuple[tuple[int, int, int], tuple[UV, UV, UV], str]]) -> float:
    """De combien monter la tête d'un élève pour la poser sur le col de SON
    corps. Les têtes sont faites pour un col à `_COL` (les corps moldus de
    Harry, Ron, Hermione) ; le corps d'uniforme « tall » monte à 1,575 et la
    tête de Luna y disparaissait dans les épaules (relevé du 2026-10-31). La
    baguette, tenue en l'air, ne compte pas."""
    hauts = [points[i][2] for s, _uv, t in faces if "wand" not in t.lower() for i in s]
    return max(hauts) - _COL if hauts else 0.0


def assembler(flux: list[bytes], annexes: Iterable[bytes] = ()) -> tuple[Maillage, Textures]:
    """Un modèle fait de plusieurs flux (le corps, puis la tête d'un élève),
    dans le même repère de liaison. Les textures absentes de ses flux se
    cherchent ensuite dans les `annexes`, lues une à une tant qu'il en manque."""
    points: list[Point] = []
    faces_brutes: list[tuple[tuple[int, int, int], tuple[UV, UV, UV], str]] = []
    textures: Textures = {}
    hausse = 0.0
    for rang, un in enumerate(flux):
        if rang == 1:
            hausse = _hausse_de_la_tete(points, faces_brutes)
        for fpm in _fpms(un):
            pts, fcs = lire(fpm)
            # Le halo d'un fantôme (`ct_moa_body_bloom` de HP5, `ct_gen_hbp_ghost_bloom_ps3_bm` de HP6, blanc uni) : une enveloppe
            # que le jeu ajoute en lumière par-dessus ; opaque, elle cachait Mimi.
            fcs = [f for f in fcs if "_bloom" not in f[2].lower()]
            decalage = len(points)
            points.extend((x, y, z + hausse) for x, y, z in pts)
            faces_brutes.extend(((a + decalage, b + decalage, c + decalage), uv, t) for (a, b, c), uv, t in fcs)
            textures.update(_textures(un, {t for _s, _uv, t in fcs if t} - set(textures)))
    noms = sorted({t for _s, _uv, t in faces_brutes})
    for annexe in annexes:
        manquantes = {n for n in noms if n} - set(textures)
        if not manquantes:
            break
        textures.update(_textures(annexe, manquantes))
    # Deux faces partout : l'ordre des bandes ne dit pas l'endroit d'une face.
    # Une texture à trous (cheveux, cils) se découpe au lieu de se mélanger.
    materiaux = tuple(Materiau(n, PF_DEUX_FACES | (PF_MASQUE if n in textures and _a_de_la_transparence(textures[n])
                                                   else 0)) for n in noms)
    indice = {n: i for i, n in enumerate(noms)}
    faces = tuple(Face(s, uv, indice[t]) for s, uv, t in faces_brutes)
    return Maillage(tuple(points), faces, materiaux), textures


def _base(nom: str) -> str:
    """Le flux de base d'un modèle (`body_x.str` pour `body_x.str.shd`) : il
    porte les petites textures partagées, la baguette, les verres de Harry."""
    for fin in (".shd", ".ffs"):
        if nom.lower().endswith(fin):
            return nom[:-len(fin)]
    return nom


def _lire(archive: Path, nom: str) -> bytes | None:
    entree = archives_ea.trouver(archive, nom)
    return archives_ea.lire(archive, entree, plafond=_PLAFOND) if entree is not None else None


def de_la_fiche(archive: Path, entrees: tuple[str, ...]) -> tuple[Maillage, Textures, None] | None:
    """Le modèle d'une fiche de HP5 ou HP6 lu dans l'archive du jeu installé ;
    None si une entrée manque ou ne se lit pas comme relevé."""
    flux = []
    for nom in entrees:
        donnees = _lire(archive, nom)
        if donnees is None:
            log.warning("Modèle %s absent de %s", nom, archive)
            return None
        flux.append(donnees)
    bases = [_base(n) for n in entrees if _base(n) != n]
    annexes = (d for n in (*bases, *_COMMUNS) if (d := _lire(archive, n)) is not None)
    try:
        maillage, textures = assembler(flux, annexes)
    except (ValueError, IndexError, struct.error):
        log.warning("Modèle %s illisible dans %s", entrees, archive, exc_info=True)
        return None
    return maillage, textures, None

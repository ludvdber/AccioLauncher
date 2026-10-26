"""Lire un modèle 3D (`SkeletalMesh`) dans un paquet Unreal 1 du jeu INSTALLÉ.

Premier usage : la visionneuse des Personnages et du Bestiaire, qui fait
tourner les vrais modèles des jeux. Relevé le 2026-10-26 sur le HP1 de Ludo :
les personnages vivent dans `System/HarryPotter.u` (`skharryMesh`,
`skhermioneMesh`…), les créatures et objets dans `HPModels.u` et `HProps.u`.
La lecture de `skharryMesh` tombe pile sur la fin de l'objet (41 218 octets) :
509 points, 774 coins texturés, 988 faces, 4 matériaux, 92 os.

Seule la pose de référence est rendue (les `Points`, déjà placés) : pas
d'animation, donc pas de pondération par les os.

Format (`USkeletalMesh` d'Unreal 1, version 76) : propriétés, puis les données
de `UMesh` (boîtes, tableaux « paresseux » vides précédés de leur position de
fin, liste des textures, échelle et origine), celles de `ULodMesh` (faces,
coins avec UV sur un octet, matériaux) et enfin celles du squelette.

Lecture SEULE et bornée, comme `textures_ue1` : un compte absurde, un indice
hors tableau ou une lecture qui ne finit pas sur la fin de l'objet rend None.
"""

import logging
import math
import struct
from dataclasses import dataclass, replace
from pathlib import Path

from src.core import encyclopedie, textures_ue1
from src.core.textures_ue1 import Paquet, _Lecteur

log = logging.getLogger(__name__)

_COMPTE_MAX = 65536
_BRAS_BAISSE = 60.0   # degrés sous l'horizontale au-delà desquels un bras est laissé tel quel
# Drapeaux de polygone d'un matériau (`EPolyFlags` d'Unreal 1).
PF_DEUX_FACES, PF_TRANSLUCIDE, PF_MASQUE = 0x100, 0x4, 0x2

Point = tuple[float, float, float]
UV = tuple[float, float]
Quat = tuple[float, float, float, float]   # x, y, z, w


@dataclass(frozen=True)
class Face:
    sommets: tuple[int, int, int]   # indices dans `Maillage.points`
    uv: tuple[UV, UV, UV]           # de 0 à 1 sur la texture
    materiau: int                   # indice dans `Maillage.materiaux`


@dataclass(frozen=True)
class Materiau:
    texture: str      # nom de l'objet texture, vide s'il n'y en a pas
    drapeaux: int     # `PF_*`


@dataclass(frozen=True)
class Os:
    nom: str
    rotation: Quat         # par rapport au parent, telle qu'écrite (voir `poser`)
    position: Point        # dans le repère du parent
    parent: int            # lui-même pour la racine


@dataclass(frozen=True)
class Influence:
    point: int
    os: int
    poids: float           # de 0 à 1 ; la somme par point vaut 1
    local: Point           # le point dans le repère de l'os


@dataclass(frozen=True)
class Maillage:
    points: tuple[Point, ...]       # repère du modèle, Z vers le haut, origine retirée
    faces: tuple[Face, ...]
    materiaux: tuple[Materiau, ...]
    squelette: tuple[Os, ...] = ()
    influences: tuple[Influence, ...] = ()
    origine: Point = (0.0, 0.0, 0.0)
    echelle: Point = (1.0, 1.0, 1.0)


def _compte(lec: _Lecteur, taille: int, fin: int) -> int:
    n = lec.index()
    if not 0 <= n <= _COMPTE_MAX or lec.p + n * taille > fin:
        raise ValueError("tableau hors de l'objet")
    return n


def _sauter(lec: _Lecteur, taille: int, fin: int) -> None:
    n = _compte(lec, taille, fin)   # pas `lec.p += _compte(…)` : lec.p serait lu AVANT l'appel
    lec.p += n * taille


def _paresseux(lec: _Lecteur, taille: int, fin: int) -> None:
    """Un tableau « paresseux » : sa position de fin, puis le tableau."""
    apres = lec.i32()
    _sauter(lec, taille, fin)
    if apres != lec.p:
        raise ValueError("tableau paresseux mal borné")


def _reels(lec: _Lecteur, n: int) -> tuple[float, ...]:
    v: tuple[float, ...] = struct.unpack_from(f"<{n}f", lec.d, lec.p)
    lec.p += 4 * n
    return v


def _uv(coin: tuple[int, ...]) -> UV:
    """Les UV d'un coin, rangés sur un octet chacun."""
    return coin[1] / 255, coin[2] / 255


def lire(p: Paquet, nom: str) -> Maillage | None:
    """Le `SkeletalMesh` `nom` du paquet, en pose de référence."""
    objet = p.objet(nom, "SkeletalMesh")
    if objet is None:
        return None
    lec, fin = objet
    # UPrimitive puis UMesh.
    lec.p += 25 + 16                       # boîte (2 vecteurs + validité), sphère
    _paresseux(lec, 4, fin)                # Verts
    _paresseux(lec, 20, fin)               # Tris
    if _compte(lec, 0, fin):               # AnimSeqs : vide sur un SkeletalMesh
        raise ValueError("séquences d'animation inattendues")
    _paresseux(lec, 8, fin)                # Connects
    lec.p += 25 + 16
    _paresseux(lec, 4, fin)                # VertLinks
    textures = [p.nom_objet(lec.index()) for _ in range(_compte(lec, 1, fin))]
    _sauter(lec, 25, fin)                  # BoundingBoxes
    _sauter(lec, 16, fin)                  # BoundingSpheres
    lec.p += 4 * 4                         # FrameVerts, AnimFrames, AndFlags, OrFlags
    echelle, origine = _reels(lec, 3), _reels(lec, 3)
    lec.p += 12 + 8                        # RotOrigin, CurPoly, CurVertex
    _sauter(lec, 4, fin)                   # TextureLOD
    # ULodMesh.
    _sauter(lec, 2, fin)                   # CollapsePointThus
    _sauter(lec, 2, fin)                   # FaceLevel
    brutes = [struct.unpack_from("<4H", lec.d, lec.p + 8 * i) for i in range(_compte(lec, 8, fin))]
    lec.p += 8 * len(brutes)
    _sauter(lec, 2, fin)                   # CollapseWedgeThus
    coins = [struct.unpack_from("<H2B", lec.d, lec.p + 4 * i) for i in range(_compte(lec, 4, fin))]
    lec.p += 4 * len(coins)
    materiaux = []
    for _ in range(_compte(lec, 8, fin)):
        drapeaux, rang = struct.unpack_from("<Ii", lec.d, lec.p)
        lec.p += 8
        texture = textures[rang] if 0 <= rang < len(textures) else ""
        materiaux.append(Materiau("" if texture == "None" else texture, drapeaux))
    _sauter(lec, 8, fin)                   # SpecialFaces
    lec.p += 4 * 8                         # ModelVerts… LODZDisplace
    _sauter(lec, 2, fin)                   # ReMapAnimVerts
    lec.p += 4                             # OldFrameVerts
    # USkeletalMesh.
    _sauter(lec, 12, fin)                  # ExtWedges
    n = _compte(lec, 12, fin)
    brut = struct.unpack_from(f"<{3 * n}f", lec.d, lec.p)
    lec.p += 12 * n
    points = tuple(((brut[3 * i] - origine[0]) * echelle[0],
                    (brut[3 * i + 1] - origine[1]) * echelle[1],
                    (brut[3 * i + 2] - origine[2]) * echelle[2]) for i in range(n))
    squelette = []
    for _ in range(_compte(lec, 1, fin)):  # RefSkeleton
        nom_os = p.noms[lec.index()]
        rotation = struct.unpack_from("<4f", lec.d, lec.p + 4)
        position = struct.unpack_from("<3f", lec.d, lec.p + 20)
        parent = struct.unpack_from("<i", lec.d, lec.p + 52)[0]
        lec.p += 4 + 44 + 8
        squelette.append(Os(nom_os, rotation, position, parent))
    if any(not 0 <= o.parent < len(squelette) for o in squelette):
        raise ValueError("os sans parent")
    paquets = [struct.unpack_from("<2H", lec.d, lec.p + 8 * i)
               for i in range(_compte(lec, 8, fin))]                         # BoneWeightIdx
    lec.p += 8 * len(paquets)
    poids = [struct.unpack_from("<2H", lec.d, lec.p + 4 * i) for i in range(_compte(lec, 4, fin))]
    lec.p += 4 * len(poids)
    nl = _compte(lec, 12, fin)                                               # LocalPoints
    locaux = struct.unpack_from(f"<{3 * nl}f", lec.d, lec.p)
    lec.p += 12 * nl + 4
    lec.index()                            # DefaultAnimation
    lec.p += 4 + 48                        # WeaponBoneIndex, WeaponAdjust
    if lec.p != fin:
        raise ValueError("fin de modèle inattendue")
    faces = []
    for a, b, c, m in brutes:
        if max(a, b, c) >= len(coins) or m >= len(materiaux):
            raise ValueError("face hors des tableaux")
        sommets = (coins[a][0], coins[b][0], coins[c][0])
        if max(sommets) >= n:
            raise ValueError("coin hors des points")
        faces.append(Face(sommets, (_uv(coins[a]), _uv(coins[b]), _uv(coins[c])), m))
    influences = []
    if len(paquets) == len(squelette) and nl == len(poids):
        for rang_os, (debut, nombre) in enumerate(paquets):
            for k in range(debut, debut + nombre):
                if k >= nl or poids[k][0] >= n:
                    raise ValueError("poids hors des tableaux")
                influences.append(Influence(poids[k][0], rang_os, poids[k][1] / 65535,
                                            (locaux[3 * k], locaux[3 * k + 1], locaux[3 * k + 2])))
    return Maillage(points, tuple(faces), tuple(materiaux), tuple(squelette), tuple(influences),
                    (origine[0], origine[1], origine[2]), (echelle[0], echelle[1], echelle[2]))


def _qmul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _qrot(q: Quat, v: Point) -> Point:
    x, y, z, w = q
    r = _qmul(_qmul(q, (v[0], v[1], v[2], 0.0)), (-x, -y, -z, w))
    return r[0], r[1], r[2]


def rotation_entre(de: Point, vers: Point) -> Quat:
    """La rotation la plus courte qui tourne la direction `de` vers `vers`."""
    def unite(v: Point) -> Point:
        n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
        return v[0] / n, v[1] / n, v[2] / n
    a, b = unite(de), unite(vers)
    c = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    w = 1.0 + a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    if w < 1e-6:
        return 0.0, 0.0, 1.0, 0.0   # demi-tour autour de Z
    n = math.sqrt(c[0] ** 2 + c[1] ** 2 + c[2] ** 2 + w * w)
    return c[0] / n, c[1] / n, c[2] / n, w / n


def os_monde(modele: Maillage, retouches: dict[int, Quat] | None = None) -> list[tuple[Quat, Point]]:
    """(rotation, position) de chaque os dans le repère du modèle. Une retouche
    tourne l'os sur place, ses enfants avec lui.

    Toutes les rotations se prennent conjuguées, racine comprise : ainsi
    recalculés, les points des 79 modèles des fiches de HP1 et HP2 retombent
    sur leur pose de référence à 0,05 unité près (relevé le 2026-10-26 ; la
    racine de Harry vaut l'identité et ne tranchait pas, celle de McGonagall
    si)."""
    retouches = retouches or {}
    monde: list[tuple[Quat, Point]] = []
    for rang, o in enumerate(modele.squelette):
        x, y, z, w = o.rotation
        if rang == 0:
            q, v = (-x, -y, -z, w), o.position
        else:
            pq, pv = monde[o.parent]
            t = _qrot(pq, o.position)
            q, v = _qmul(pq, (-x, -y, -z, w)), (pv[0] + t[0], pv[1] + t[1], pv[2] + t[2])
        if rang in retouches:
            q = _qmul(retouches[rang], q)
        monde.append((q, v))
    return monde


def poser(modele: Maillage, retouches: dict[int, Quat] | None = None) -> tuple[Point, ...]:
    """Les points recalculés par les os retouchés, dans le repère de `points`."""
    if not modele.influences:
        return modele.points
    monde = os_monde(modele, retouches)
    somme = [[0.0, 0.0, 0.0] for _ in modele.points]
    for inf in modele.influences:
        q, v = monde[inf.os]
        r = _qrot(q, inf.local)
        s = somme[inf.point]
        s[0] += (r[0] + v[0]) * inf.poids
        s[1] += (r[1] + v[1]) * inf.poids
        s[2] += (r[2] + v[2]) * inf.poids
    (ox, oy, oz), (ex, ey, ez) = modele.origine, modele.echelle
    return tuple(((x - ox) * ex, (y - oy) * ey, (z - oz) * ez) for x, y, z in somme)


def tourner_point(q: Quat, v: Point) -> Point:
    return _qrot(q, v)


def _os_lateraux(modele: Maillage, suffixe: str) -> tuple[int, int] | None:
    noms = [o.nom.lower() for o in modele.squelette]
    gauche = next((k for k, n in enumerate(noms) if n.endswith("l " + suffixe)), None)
    droite = next((k for k, n in enumerate(noms) if n.endswith("r " + suffixe)), None)
    return (gauche, droite) if gauche is not None and droite is not None else None


def face(modele: Maillage) -> Quat | None:
    """La rotation autour de Z qui tourne le modèle face à la caméra : sa
    gauche vers +Y, comme Harry. Une dizaine de personnages de HP1 (Rogue,
    Malefoy, Vernon…) ont leur squelette tourné d'un quart de tour. None sans
    cuisses ni bras nommés `L …` / `R …`, ou déjà de face."""
    paire = _os_lateraux(modele, "thigh") or _os_lateraux(modele, "upperarm")
    if paire is None:
        return None
    monde = os_monde(modele)
    (gx, gy, _), (dx, dy, _) = monde[paire[0]][1], monde[paire[1]][1]
    lateral = (gx - dx, gy - dy, 0.0)
    if math.hypot(lateral[0], lateral[1]) < 1e-6 or abs(math.atan2(-lateral[0], lateral[1])) < 0.05:
        return None
    return rotation_entre(lateral, (0.0, 1.0, 0.0))


def bras_baisses(modele: Maillage, angle: float = 72.0) -> dict[int, Quat]:
    """Les retouches qui baissent les bras d'un modèle posé en croix,
    `angle` degrés sous l'horizontale ; rien pour un bras déjà baissé de plus
    de 60° (les bras de Dumbledore, Quirrell et Voldemort dans HP1 partent à
    50°, écartés par leurs manches : ils sont baissés eux aussi)."""
    monde = os_monde(modele)
    retouches: dict[int, Quat] = {}
    noms = [o.nom.lower() for o in modele.squelette]
    for rang, nom in enumerate(noms):
        if not nom.endswith(("l upperarm", "r upperarm")):
            continue
        enfant = next((k for k, o in enumerate(modele.squelette)
                       if o.parent == rang and k != rang and "forearm" in noms[k]), None)
        if enfant is None:
            continue
        d = tuple(monde[enfant][1][i] - monde[rang][1][i] for i in range(3))
        horizontale = math.hypot(d[0], d[1])
        if horizontale < 1e-6 or math.degrees(math.atan2(-d[2], horizontale)) > _BRAS_BAISSE:
            continue
        a = math.radians(angle)
        cible = (d[0] / horizontale * math.cos(a), d[1] / horizontale * math.cos(a), -math.sin(a))
        retouches[rang] = rotation_entre((d[0], d[1], d[2]), cible)
    return retouches


def textures(chemin: Path, modele: Maillage) -> dict[str, tuple[int, int, bytes]]:
    """Les textures de ses matériaux rangées dans le même paquet, en
    (largeur, hauteur, pixels B V R A) ; un matériau « masqué » rend son
    indice 0 transparent (les lunettes, les cheveux de Harry)."""
    images: dict[str, tuple[int, int, bytes]] = {}
    for m in modele.materiaux:
        if not m.texture or m.texture in images:
            continue
        tex = textures_ue1.texture(chemin, m.texture)
        if tex is not None:
            masquee = tex.masquee or bool(m.drapeaux & PF_MASQUE)
            images[m.texture] = encyclopedie.bgra_de_palette(replace(tex, masquee=masquee))
    return images


def de_la_fiche(dossier_exe: Path, fiche: encyclopedie.Fiche
                ) -> tuple[Maillage, dict[str, tuple[int, int, bytes]]] | None:
    """Le modèle d'une fiche des Personnages ou du Bestiaire et ses textures,
    lus dans le jeu installé ; None sans modèle ou sans le jeu."""
    if fiche.modele is None:
        return None
    chemin = encyclopedie.chemin_image(dossier_exe, fiche.modele)
    if chemin is None:
        return None
    modele = maillage(chemin, fiche.modele.nom)
    return (modele, textures(chemin, modele)) if modele is not None else None


def maillage(chemin: Path, nom: str) -> Maillage | None:
    """Le modèle `nom` du paquet du jeu ; None s'il est absent ou pas comme relevé."""
    p = textures_ue1.paquet(chemin)
    if p is None:
        return None
    try:
        return lire(p, nom)
    except (ValueError, IndexError, struct.error):
        log.warning("Modèle %s illisible dans %s", nom, chemin, exc_info=True)
        return None

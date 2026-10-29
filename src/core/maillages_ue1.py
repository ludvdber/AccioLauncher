"""Lire un modèle 3D (`SkeletalMesh`) dans un paquet Unreal 1 du jeu INSTALLÉ.

Premier usage : la visionneuse des Personnages et du Bestiaire, qui fait
tourner les vrais modèles des jeux. Relevé le 2026-10-26 sur le HP1 de Ludo :
les personnages vivent dans `System/HarryPotter.u` (`skharryMesh`,
`skhermioneMesh`…), les créatures et objets dans `HPModels.u` et `HProps.u`.
La lecture de `skharryMesh` tombe pile sur la fin de l'objet (41 218 octets) :
509 points, 774 coins texturés, 988 faces, 4 matériaux, 92 os.

La pose de référence (les `Points`, déjà placés) se rend telle quelle ; les
mouvements du jeu (`Animation`, l'objet nommé par `DefaultAnimation` du
maillage) se rejouent par les os : `pose(modele, mouvement, t)`.

Format (`USkeletalMesh` d'Unreal 1, version 76) : propriétés, puis les données
de `UMesh` (boîtes, tableaux « paresseux » vides précédés de leur position de
fin, liste des textures, échelle et origine), celles de `ULodMesh` (faces,
coins avec UV sur un octet, matériaux) et enfin celles du squelette.

Format d'un `Animation` (relevé le 2026-10-28 sur HP1 et HP2, 54 + 368
objets lus jusqu'au dernier octet) : os de référence (nom, drapeaux, parent),
mouvements (vitesse racine, durée, os de départ, drapeaux, indices d'os, puis
PAR PISTE seulement des en-têtes : drapeaux, nombre de rotations, de positions
et de temps, échelle des positions, pas de 1/30 s), séquences (nom, groupe,
première image, nombre d'images, notifications, cadence), puis TROIS tableaux
plats que les pistes consomment dans l'ordre : rotations en 3 × int16 (chaque
composante = sin(entier × π/2/32767), w = √(1 − x² − y² − z²) ≥ 0, c'est
`FAnimVec::Quat` d'Engine.dll), positions en 3 × int16 × échelle/32767, temps
en un octet = images depuis la clé d'avant. Les temps sont toujours aussi
nombreux que les rotations ; une piste a une position (fixe) ou autant que de
rotations.

Lecture SEULE et bornée, comme `textures_ue1` : un compte absurde, un indice
hors tableau ou une lecture qui ne finit pas sur la fin de l'objet rend None.
"""

import bisect
import logging
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import cached_property, partial
from pathlib import Path

from src.core import encyclopedie, textures_ue1
from src.core.textures_ue1 import Paquet, _Lecteur

log = logging.getLogger(__name__)

_COMPTE_MAX = 65536
_CLES_MAX = 1 << 24   # clés d'animation d'un objet (Harry en a 80 686)
_K_ANIM = math.pi / 2 / 32767   # `FAnimVec` : composante = sin(entier × _K_ANIM)
_IMAGES_PAR_S = 30.0
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
    animation: str = ""             # l'objet `Animation` par défaut du maillage, vide sans


@dataclass(frozen=True)
class Piste:
    """Les clés d'un os dans un mouvement, dans le repère du parent et la
    convention du squelette de référence (rotations prises conjuguées)."""
    rotations: tuple[Quat, ...]
    positions: tuple[Point, ...]    # une seule (fixe) ou autant que de rotations
    temps: tuple[float, ...]        # secondes depuis le début, croissants, une par rotation


@dataclass(frozen=True)
class Mouvement:
    nom: str                        # tel que le jeu le nomme (« walk », « breath »)
    groupe: str
    duree: float                    # secondes
    images: int
    os: tuple[str, ...]             # le nom de l'os de chaque piste, dans l'ordre de l'animation
    # Les pistes, ou de quoi les décoder au PREMIER usage : décoder les 59
    # mouvements de chacun des 27 modèles de HP2 prenait 3 s de GIL au fil de
    # l'onglet Personnages, et la fenêtre se figeait jusqu'à 1,5 s (2026-10-29).
    # On n'en joue qu'un à la fois.
    source: tuple[Piste, ...] | Callable[[], tuple[Piste, ...]] = field(default=(), repr=False, compare=False)

    @cached_property
    def pistes(self) -> tuple[Piste, ...]:
        return self.source() if callable(self.source) else self.source

    def piste(self, nom_os: str) -> Piste | None:
        """La première piste de l'os `nom_os` (noms sans casse, comme le moteur)."""
        voulu = nom_os.lower()
        return next((p for n, p in zip(self.os, self.pistes, strict=True) if n.lower() == voulu), None)


@dataclass(frozen=True)
class Animation:
    nom: str
    mouvements: tuple[Mouvement, ...]


def _compte(lec: _Lecteur, taille: int, fin: int, maxi: int = _COMPTE_MAX) -> int:
    n = lec.index()
    if not 0 <= n <= maxi or lec.p + n * taille > fin:
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
    ref_animation = lec.index()            # DefaultAnimation
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
    animation = p.nom_objet(ref_animation) if ref_animation else ""
    return Maillage(points, tuple(faces), tuple(materiaux), tuple(squelette), tuple(influences),
                    (origine[0], origine[1], origine[2]), (echelle[0], echelle[1], echelle[2]),
                    "" if animation == "None" else animation)


def _quat_de(a: int, b: int, c: int) -> Quat:
    """Un quaternion `FAnimVec` : trois sinus, w positif."""
    x, y, z = math.sin(a * _K_ANIM), math.sin(b * _K_ANIM), math.sin(c * _K_ANIM)
    return x, y, z, math.sqrt(max(0.0, 1.0 - x * x - y * y - z * z))


def lire_animation(p: Paquet, nom: str) -> Animation | None:
    """L'objet `Animation` `nom` du paquet, toutes clés décodées ; None s'il
    n'y est pas. Lecture bornée : tout écart au format relevé lève ValueError."""
    objet = p.objet(nom, "Animation")
    if objet is None:
        return None
    lec, fin = objet
    os_ = []
    for _ in range(_compte(lec, 9, fin)):   # RefBones : nom, drapeaux, parent
        os_.append(p.noms[lec.index()])
        lec.p += 8
    en_tetes = []                             # par mouvement : durée, os, pistes
    for _ in range(_compte(lec, 25, fin)):   # Moves
        lec.p += 12                           # RootSpeed3D
        duree = _reels(lec, 1)[0]
        lec.p += 8                            # StartBone, Flags
        indices = []
        for _ in range(_compte(lec, 4, fin)):
            indices.append(lec.i32())
        pistes = []
        for _ in range(_compte(lec, 15, fin)):
            lec.p += 4                        # drapeaux, toujours 0
            nq, npos, nt = lec.index(), lec.index(), lec.index()
            echelle, pas = _reels(lec, 2)
            if nt != nq or npos not in (1, nq) or min(nq, npos, nt) < 0:
                raise ValueError("piste hors du format relevé")
            pistes.append((nq, npos, echelle, pas))
        if not indices:                       # sans table : une piste par os, dans l'ordre
            indices = list(range(len(pistes)))
        if len(pistes) != len(indices) or any(not 0 <= i < len(os_) for i in indices):
            raise ValueError("pistes et os ne se répondent pas")
        en_tetes.append((duree, indices, pistes))
    sequences = []
    for _ in range(_compte(lec, 11, fin)):   # AnimSeqs
        nom_seq, groupe = p.noms[lec.index()], p.noms[lec.index()]
        lec.p += 4                            # StartFrame
        images = lec.i32()
        for _ in range(_compte(lec, 5, fin)):   # Notifys : temps, fonction
            lec.p += 4
            lec.index()
        lec.p += 4                            # Rate
        sequences.append((nom_seq, groupe, images))
    if len(sequences) != len(en_tetes):
        raise ValueError("séquences et mouvements ne se répondent pas")
    nq_total = _compte(lec, 6, fin, _CLES_MAX)
    quats = struct.unpack_from(f"<{3 * nq_total}h", lec.d, lec.p)
    lec.p += 6 * nq_total
    npos_total = _compte(lec, 6, fin, _CLES_MAX)
    positions = struct.unpack_from(f"<{3 * npos_total}h", lec.d, lec.p)
    lec.p += 6 * npos_total
    nt_total = _compte(lec, 1, fin, _CLES_MAX)
    temps = lec.d[lec.p:lec.p + nt_total]
    lec.p += nt_total
    if lec.p != fin:
        raise ValueError("fin d'animation inattendue")
    # Les bornes se vérifient ICI, pour tous : un format inattendu lève encore
    # à la lecture. Seul le calcul des clés attend qu'on joue le mouvement.
    iq = ip = it = 0
    mouvements = []
    for (duree, indices, pistes), (nom_seq, groupe, images) in zip(en_tetes, sequences, strict=True):
        noms_os: list[str] = []
        plan: list[tuple[int, int, int, int, int, float, float]] = []
        for rang_os, (nq, npos, echelle, pas) in zip(indices, pistes, strict=True):
            if iq + nq > nq_total or ip + npos > npos_total or it + nq > nt_total:
                raise ValueError("plus de clés annoncées que rangées")
            noms_os.append(os_[rang_os])
            plan.append((iq, ip, it, nq, npos, echelle, pas))
            iq, ip, it = iq + nq, ip + npos, it + nq
        mouvements.append(Mouvement(nom_seq, groupe, duree, images, tuple(noms_os),
                                    partial(_pistes, quats, positions, temps, tuple(plan))))
    if (iq, ip, it) != (nq_total, npos_total, nt_total):
        raise ValueError("clés rangées sans piste")
    return Animation(nom, tuple(mouvements))


def _pistes(quats: tuple[int, ...], positions: tuple[int, ...], temps: bytes,
            plan: tuple[tuple[int, int, int, int, int, float, float], ...]) -> tuple[Piste, ...]:
    """Les clés d'un mouvement, décodées à la demande (bornes déjà vérifiées)."""
    lues = []
    for iq, ip, it, nq, npos, echelle, pas in plan:
        rotations = tuple(_quat_de(quats[3 * k], quats[3 * k + 1], quats[3 * k + 2])
                          for k in range(iq, iq + nq))
        k_pos = echelle / 32767
        pos = tuple((positions[3 * k] * k_pos, positions[3 * k + 1] * k_pos, positions[3 * k + 2] * k_pos)
                    for k in range(ip, ip + npos))
        instants, t = [], 0.0
        for delta in temps[it:it + nq]:
            t += delta * pas
            instants.append(t)
        lues.append(Piste(rotations, pos, tuple(instants)))
    return tuple(lues)


def _lerp(a: Point, b: Point, k: float) -> Point:
    return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k


def _nlerp(a: Quat, b: Quat, k: float) -> Quat:
    """Entre deux rotations proches : le mélange normalisé, par le chemin court."""
    if a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3] < 0:
        b = (-b[0], -b[1], -b[2], -b[3])
    x, y, z, w = (a[i] + (b[i] - a[i]) * k for i in range(4))
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    return x / n, y / n, z / n, w / n


def _cle(piste: Piste, t: float) -> tuple[Quat, Point]:
    """La rotation et la position de la piste à l'instant `t` (interpolées)."""
    temps = piste.temps
    if t <= temps[0] or len(temps) == 1:
        rang, k = 0, 0.0
    elif t >= temps[-1]:
        rang, k = len(temps) - 1, 0.0
    else:
        rang = bisect.bisect_right(temps, t) - 1
        ecart = temps[rang + 1] - temps[rang]
        k = (t - temps[rang]) / ecart if ecart > 0 else 0.0
    suivant = min(rang + 1, len(temps) - 1)
    q = _nlerp(piste.rotations[rang], piste.rotations[suivant], k) if k else piste.rotations[rang]
    if len(piste.positions) == 1:
        v = piste.positions[0]
    else:
        v = _lerp(piste.positions[rang], piste.positions[suivant], k) if k else piste.positions[rang]
    return q, v


def pose(modele: Maillage, mouvement: Mouvement, t: float) -> tuple[Point, ...]:
    """Les points du modèle à l'instant `t` du mouvement, rejoué en boucle ;
    un os sans piste garde sa pose de référence."""
    if not modele.influences or not mouvement.pistes:
        return modele.points
    if mouvement.duree > 0:
        t %= mouvement.duree
    # Les os se nomment sans casse et un squelette peut porter deux fois le même
    # nom (le Rogue de HP2 : 121 os, 111 pistes) : chaque piste va au premier os
    # de son nom encore libre, dans l'ordre, comme le moteur apparie les siens.
    libres: dict[str, list[int]] = {}
    for rang, o in enumerate(modele.squelette):
        libres.setdefault(o.nom.lower(), []).append(rang)
    locaux: dict[int, tuple[Quat, Point]] = {}
    for nom_os, piste in zip(mouvement.os, mouvement.pistes, strict=True):
        rangs = libres.get(nom_os.lower())
        if rangs and piste.rotations:
            locaux[rangs.pop(0)] = _cle(piste, t)
    return _peau(modele, os_monde(modele, locaux=locaux))


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


def os_monde(modele: Maillage, retouches: dict[int, Quat] | None = None,
             locaux: dict[int, tuple[Quat, Point]] | None = None) -> list[tuple[Quat, Point]]:
    """(rotation, position) de chaque os dans le repère du modèle. Une retouche
    tourne l'os sur place, ses enfants avec lui ; `locaux` remplace la rotation
    et la position d'un os par rapport à son parent (les clés d'un mouvement).

    Toutes les rotations se prennent conjuguées, racine comprise : ainsi
    recalculés, les points des 79 modèles des fiches de HP1 et HP2 retombent
    sur leur pose de référence à 0,05 unité près (relevé le 2026-10-26 ; la
    racine de Harry vaut l'identité et ne tranchait pas, celle de McGonagall
    si)."""
    retouches = retouches or {}
    locaux = locaux or {}
    monde: list[tuple[Quat, Point]] = []
    for rang, o in enumerate(modele.squelette):
        (x, y, z, w), position = locaux.get(rang, (o.rotation, o.position))
        if rang == 0:
            q, v = (-x, -y, -z, w), position
        else:
            pq, pv = monde[o.parent]
            t = _qrot(pq, position)
            q, v = _qmul(pq, (-x, -y, -z, w)), (pv[0] + t[0], pv[1] + t[1], pv[2] + t[2])
        if rang in retouches:
            q = _qmul(retouches[rang], q)
        monde.append((q, v))
    return monde


def poser(modele: Maillage, retouches: dict[int, Quat] | None = None) -> tuple[Point, ...]:
    """Les points recalculés par les os retouchés, dans le repère de `points`."""
    if not modele.influences:
        return modele.points
    return _peau(modele, os_monde(modele, retouches))


def _peau(modele: Maillage, monde: list[tuple[Quat, Point]]) -> tuple[Point, ...]:
    """Les points pondérés par les os posés dans le repère du modèle."""
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
                ) -> tuple[Maillage, dict[str, tuple[int, int, bytes]], Animation | None] | None:
    """Le modèle d'une fiche des Personnages ou du Bestiaire, ses textures et
    ses mouvements, lus dans le jeu installé ; None sans modèle ou sans le jeu."""
    if fiche.modele is None:
        return None
    chemin = encyclopedie.chemin_image(dossier_exe, fiche.modele)
    if chemin is None:
        return None
    modele = maillage(chemin, fiche.modele.nom)
    if modele is None:
        return None
    return modele, textures(chemin, modele), animation(chemin, modele.animation)


def animation(chemin: Path, nom: str) -> Animation | None:
    """Les mouvements `nom` du paquet du jeu ; None sans nom, s'ils sont
    absents ou pas comme relevé."""
    if not nom:
        return None
    p = textures_ue1.paquet(chemin)
    if p is None:
        return None
    try:
        return lire_animation(p, nom)
    except (ValueError, IndexError, struct.error):
        log.warning("Animation %s illisible dans %s", nom, chemin, exc_info=True)
        return None


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

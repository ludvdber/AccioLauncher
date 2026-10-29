"""Lire un modèle 3D (`SkeletalMesh`) dans un paquet Unreal 2 du jeu INSTALLÉ (HP3).

La suite de `maillages_ue1` pour la visionneuse des Personnages et du
Bestiaire : mêmes `Maillage`, `Face`, `Os`, rendus et posés par le même code.
Relevé le 2026-10-29 sur le HP3 de Ludo (paquets version 129) : les élèves et
les professeurs vivent dans `Animations/HPCharacters_32.ukx` (`harry`, `Ron`,
`Mcgonagall`…), les créatures dans `HPCharacters.ukx` (`Buckbeak`, `Imp`…),
les objets animés dans `HProps.ukx`. Les 167 `SkeletalMesh` des cinq `.ukx`
se lisent jusqu'au dernier octet.

Format (`USkeletalMesh` d'Unreal 2, `Version` 4) : boîte et sphère, puis
`ULodMesh` (matériaux, échelle, origine, rotation d'origine, tableaux de
l'ancien format, tous vides, réglages de niveaux de détail et d'imposteur sur
86 octets), le squelette (nom, drapeaux, rotation, position, longueur, taille,
enfants, parent), l'animation par défaut, cinq tableaux d'attaches vides, puis
les niveaux de détail. Le PREMIER est le modèle entier : influences (poids,
point, os), coins (point et UV en réels), faces (trois coins, matériau,
auxiliaire) et points, chacun dans un tableau « paresseux ». Suivent les mêmes
tableaux dans l'ancien format, et 8 octets nuls.

Le fichier range le haut en −Y. La rotation d'origine du modèle
(`RotOrigin`, appliquée comme le moteur : vecteur ligne × matrice du
`FRotator`) le remet debout et face à la caméra, comme ceux de HP1 et HP2.
L'échelle et l'origine
sont appliquées d'avance : le `Maillage` rendu a l'origine nulle et
l'échelle 1.

Les matériaux sont des imports : `HPCharTextures.HP3Harry_CoakS` (paquet, puis
nom). Un `Shader` renvoie à son image par `Diffuse`, un `FinalBlend` par
`Material` ; `TwoSided` donne une face à deux côtés, `AlphaTest` ou
`OutputBlending` 1 (`OB_Masked`) une image découpée par sa transparence (les
mèches des cheveux, au seuil `AlphaRef` s'il est donné). Tout autre matériau
est opaque, même si son image a une transparence.

Format d'un `MeshAnimation` (relevé le 2026-10-29, les 140 des cinq `.ukx`
lus jusqu'au dernier octet ; même nom que son modèle) : version 4, os de
référence (nom, drapeaux, parent), mouvements (vitesse racine, durée en
images, os de départ, drapeaux, indices d'os, pistes, piste racine, un tableau
vide), puis séquences (4 octets, nom, groupes, première image, nombre
d'images, notifications : temps, fonction, objet ; cadence). Une piste :
drapeaux, rotations en `FQuat` réels, positions, temps en IMAGES. Les clés
sont en clair, contrairement à HP1 et HP2 ; elles suivent la convention du
squelette (conjuguées, voir `os_monde`), et la piste de l'os 0 reçoit le même
redressement que la racine du modèle.

Lecture SEULE et bornée, comme `maillages_ue1`.
"""

import logging
import math
import struct
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from src.core import encyclopedie, textures_ue1
from src.core.maillages_ue1 import (
    PF_DEUX_FACES,
    PF_MASQUE,
    Animation,
    Face,
    Influence,
    Maillage,
    Materiau,
    Mouvement,
    Os,
    Piste,
    Point,
    Quat,
    _compte,
    _paresseux,
    _qmul,
    _qrot,
    _reels,
    _sauter,
    os_monde,
)
from src.core.textures_ue1 import Paquet, _Lecteur

log = logging.getLogger(__name__)

_VERSION = 4
_ENTRE_LOD_ET_OS = 24 + 62   # réglages de niveaux de détail, puis d'imposteur
_FIN = 8                     # octets nuls qui ferment l'objet
_SAUTS_MATERIAU = 4          # Shader → FinalBlend → … avant l'image
_PI_UNREAL = 32768           # un `FRotator` compte un demi-tour en 32 768
_OB_MASQUE = 1               # `EOutputBlending` d'un `Shader`
_SEUIL = 128                 # transparence d'un matériau masqué sans `AlphaRef`


def _rotateur(pitch: int, yaw: int, roll: int) -> tuple[Point, Point, Point]:
    """Les trois lignes de la matrice d'un `FRotator` d'Unreal."""
    sp, cp = math.sin(pitch * math.pi / _PI_UNREAL), math.cos(pitch * math.pi / _PI_UNREAL)
    sy, cy = math.sin(yaw * math.pi / _PI_UNREAL), math.cos(yaw * math.pi / _PI_UNREAL)
    sr, cr = math.sin(roll * math.pi / _PI_UNREAL), math.cos(roll * math.pi / _PI_UNREAL)
    return ((cp * cy, cp * sy, sp),
            (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp),
            (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp))


def _quat_de_colonnes(a: tuple[Point, Point, Point]) -> Quat:
    """Le quaternion d'une matrice de rotation donnée par ses LIGNES `a[i][j]`
    (vecteur colonne : v' = a × v)."""
    trace = a[0][0] + a[1][1] + a[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        return ((a[2][1] - a[1][2]) / s, (a[0][2] - a[2][0]) / s, (a[1][0] - a[0][1]) / s, s / 4)
    if a[0][0] > a[1][1] and a[0][0] > a[2][2]:
        s = math.sqrt(1.0 + a[0][0] - a[1][1] - a[2][2]) * 2
        return (s / 4, (a[0][1] + a[1][0]) / s, (a[0][2] + a[2][0]) / s, (a[2][1] - a[1][2]) / s)
    if a[1][1] > a[2][2]:
        s = math.sqrt(1.0 + a[1][1] - a[0][0] - a[2][2]) * 2
        return ((a[0][1] + a[1][0]) / s, s / 4, (a[1][2] + a[2][1]) / s, (a[0][2] - a[2][0]) / s)
    s = math.sqrt(1.0 + a[2][2] - a[0][0] - a[1][1]) * 2
    return ((a[0][2] + a[2][0]) / s, (a[1][2] + a[2][1]) / s, s / 4, (a[1][0] - a[0][1]) / s)


def redressement(rot_origine: tuple[int, int, int]) -> Quat:
    """La rotation qui met le modèle debout et face à la caméra : celle de
    `RotOrigin`, appliquée comme le moteur (v' = v × M, donc a = Mᵀ)."""
    m = _rotateur(*rot_origine)
    return _quat_de_colonnes(((m[0][0], m[1][0], m[2][0]),
                              (m[0][1], m[1][1], m[2][1]),
                              (m[0][2], m[1][2], m[2][2])))


def _paresseux_lu(lec: _Lecteur, taille: int, fin: int) -> tuple[int, int]:
    """Un tableau paresseux dont on garde (nombre, position des données)."""
    apres = lec.i32()
    n = _compte(lec, taille, fin)
    debut = lec.p
    lec.p += n * taille
    if apres != lec.p:
        raise ValueError("tableau paresseux mal borné")
    return n, debut


def _niveau(lec: _Lecteur, fin: int) -> tuple[tuple[int, int], ...]:
    """Un niveau de détail ; rend (nombre, position) des influences, des coins,
    des faces et des points."""
    _sauter(lec, 4, fin)                   # SkinningData
    _sauter(lec, 16, fin)                  # SkinPoints
    lec.p += 4                             # NumDynWedges
    _sauter(lec, 18, fin)                  # SmoothSections
    _sauter(lec, 18, fin)                  # RigidSections
    for _ in range(2):                     # SmoothIndices, RigidIndices et leur révision
        _sauter(lec, 2, fin)
        lec.p += 4
    lec.p += 12
    _sauter(lec, 32, fin)                  # VertexStream
    lus = tuple(_paresseux_lu(lec, t, fin) for t in (8, 10, 8, 12))
    lec.p += 8 + 16                        # distance, hystérésis, quatre entiers
    return lus


@dataclass(frozen=True)
class Repere:
    """Ce qui passe du fichier au `Maillage` : redressement, échelle, origine."""
    rotation: Quat
    echelle: float
    origine: Point

    def placer(self, v: Point) -> Point:
        o, k = self.origine, self.echelle
        return _qrot(self.rotation, ((v[0] - o[0]) * k, (v[1] - o[1]) * k, (v[2] - o[2]) * k))

    def racine(self, rotation: Quat) -> Quat:
        """La rotation écrite d'un os racine, redressée (rotations conjuguées)."""
        q = self.rotation
        return _qmul(rotation, (-q[0], -q[1], -q[2], q[3]))


def lire(p: Paquet, nom: str) -> Maillage | None:
    """Le `SkeletalMesh` `nom` du paquet, debout, en pose de référence."""
    lu = _lire(p, nom)
    return lu[0] if lu is not None else None


def _lire(p: Paquet, nom: str) -> tuple[Maillage, Repere] | None:
    objet = p.objet(nom, "SkeletalMesh")
    if objet is None:
        return None
    lec, fin = objet
    d = lec.d
    lec.p += 41                            # boîte, sphère
    if lec.i32() != _VERSION:
        raise ValueError("version de modèle inattendue")
    lec.p += 4                             # VertexCount
    _sauter(lec, 4, fin)                   # Verts
    refs = [lec.index() for _ in range(_compte(lec, 1, fin))]
    noms_materiaux = [f"{p.paquet_de(r)}.{p.nom_objet(r)}" if r < 0 else "" for r in refs]
    echelle, origine = _reels(lec, 3), _reels(lec, 3)
    rot: tuple[int, int, int] = struct.unpack_from("<3i", d, lec.p)
    lec.p += 12
    for taille in (2, 8, 2, 10):           # FaceLevel, Faces, CollapseWedgeThus, Wedges
        _sauter(lec, taille, fin)
    materiaux = []
    for _ in range(_compte(lec, 8, fin)):
        drapeaux, rang = struct.unpack_from("<Ii", d, lec.p)
        lec.p += 8
        materiaux.append(Materiau(noms_materiaux[rang] if 0 <= rang < len(refs) else "", drapeaux))
    lec.p += _ENTRE_LOD_ET_OS
    bruts = []
    for _ in range(_compte(lec, 56, fin)):  # RefSkeleton
        nom_os = p.noms[lec.index()]
        rotation: Quat = struct.unpack_from("<4f", d, lec.p + 4)
        position: Point = struct.unpack_from("<3f", d, lec.p + 20)
        parent = struct.unpack_from("<i", d, lec.p + 52)[0]
        lec.p += 56
        bruts.append(Os(nom_os, rotation, position, parent))
    if not bruts or any(not 0 <= o.parent < len(bruts) for o in bruts):
        raise ValueError("os sans parent")
    ref_animation = lec.index()
    lec.p += 4                             # SkeletalDepth
    for _ in range(5):                     # attaches
        if _compte(lec, 0, fin):
            raise ValueError("attaches inattendues")
    niveaux = _compte(lec, 1, fin)
    if niveaux < 1:
        raise ValueError("aucun niveau de détail")
    (ni, di), (nc, dc), (nf, df), (npt, dp) = _niveau(lec, fin)
    for _ in range(niveaux - 1):
        _niveau(lec, fin)
    if _compte(lec, 0, fin):
        raise ValueError("tableau inattendu après les niveaux")
    for taille in (12, 10, 12, 8, 2, 2):   # l'ancien format : points, coins, faces…
        _paresseux(lec, taille, fin)
    if lec.p + _FIN != fin:
        raise ValueError("fin de modèle inattendue")

    repere = Repere(redressement(rot), sum(echelle) / 3, (origine[0], origine[1], origine[2]))
    placer, k = repere.placer, repere.echelle

    brut = struct.unpack_from(f"<{3 * npt}f", d, dp)
    points = tuple(placer((brut[3 * i], brut[3 * i + 1], brut[3 * i + 2])) for i in range(npt))
    coins = [struct.unpack_from("<H2f", d, dc + 10 * i) for i in range(nc)]
    faces = []
    for i in range(nf):
        a, b, c, m, _aux = struct.unpack_from("<3H2B", d, df + 8 * i)
        if max(a, b, c) >= nc or m >= len(materiaux):
            raise ValueError("face hors des tableaux")
        sommets = (coins[a][0], coins[b][0], coins[c][0])
        if max(sommets) >= npt:
            raise ValueError("coin hors des points")
        faces.append(Face(sommets, ((coins[a][1], coins[a][2]), (coins[b][1], coins[b][2]),
                                    (coins[c][1], coins[c][2])), m))
    # La racine reçoit le redressement (rotations prises conjuguées, voir
    # `os_monde`) ; les positions des enfants suivent l'échelle.
    squelette = [replace(bruts[0], rotation=repere.racine(bruts[0].rotation), position=placer(bruts[0].position))]
    squelette += [replace(o, position=(o.position[0] * k, o.position[1] * k, o.position[2] * k))
                  for o in bruts[1:]]
    modele = Maillage(points, tuple(faces), tuple(materiaux), tuple(squelette))
    monde = os_monde(modele)
    influences = []
    for i in range(ni):
        poids, point, rang_os = struct.unpack_from("<f2H", d, di + 8 * i)
        if point >= npt or rang_os >= len(squelette):
            raise ValueError("influence hors des tableaux")
        (bx, by, bz, bw), v = monde[rang_os]
        pt = points[point]
        local = _qrot((-bx, -by, -bz, bw), (pt[0] - v[0], pt[1] - v[1], pt[2] - v[2]))
        influences.append(Influence(point, rang_os, poids, local))
    animation = p.nom_objet(ref_animation) if ref_animation else ""
    modele = replace(modele, influences=tuple(influences), animation="" if animation == "None" else animation)
    return modele, repere


# Une piste : (position, nombre) des rotations, des positions et des temps.
_Piste = tuple[int, int, int, int, int, int]


def _piste(lec: _Lecteur, fin: int) -> _Piste:
    lec.p += 4                             # drapeaux
    lue: list[int] = []
    for taille in (16, 12, 4):
        n = _compte(lec, taille, fin)
        lue += [lec.p, n]
        lec.p += n * taille
    dq, nq, dp, npos, dt, nt = lue
    if nq and (nt != nq or npos not in (1, nq)):
        raise ValueError("piste hors du format relevé")
    return dq, nq, dp, npos, dt, nt


def lire_animation(p: Paquet, nom: str, repere: Repere) -> Animation | None:
    """Le `MeshAnimation` `nom` du paquet ; None s'il n'y est pas. Tout écart
    au format relevé lève ValueError ; les clés se décodent au premier usage."""
    objet = p.objet(nom, "MeshAnimation")
    if objet is None:
        return None
    lec, fin = objet
    if lec.i32() != _VERSION:
        raise ValueError("version d'animation inattendue")
    os_ = []
    for _ in range(_compte(lec, 9, fin)):  # RefBones : nom, drapeaux, parent
        os_.append(p.noms[lec.index()])
        lec.p += 8
    en_tetes = []
    for _ in range(_compte(lec, 28, fin)):  # Moves
        lec.p += 12 + 4 + 8                # vitesse racine, durée, os de départ, drapeaux
        indices = [lec.i32() for _ in range(_compte(lec, 4, fin))]
        pistes = [_piste(lec, fin) for _ in range(_compte(lec, 7, fin))]
        _piste(lec, fin)                   # RootTrack
        if not indices:                    # sans table : une piste par os, dans l'ordre
            indices = list(range(len(pistes)))
        if _compte(lec, 0, fin):
            raise ValueError("tableau inattendu après la piste racine")
        if len(pistes) != len(indices) or any(not 0 <= i < len(os_) for i in indices):
            raise ValueError("pistes et os ne se répondent pas")
        en_tetes.append((indices, pistes))
    sequences = []
    for _ in range(_compte(lec, 18, fin)):  # AnimSeqs
        lec.p += 4
        nom_seq = p.noms[lec.index()]
        groupes = [p.noms[lec.index()] for _ in range(_compte(lec, 1, fin))]
        lec.p += 4                         # StartFrame
        images = lec.i32()
        for _ in range(_compte(lec, 6, fin)):   # Notifys : temps, fonction, objet
            lec.p += 4
            lec.index()
            lec.index()
        cadence = _reels(lec, 1)[0]
        if cadence <= 0 or images < 0:
            raise ValueError("séquence hors du format relevé")
        sequences.append((nom_seq, groupes[0] if groupes else "None", images, cadence))
    if lec.p != fin:
        raise ValueError("fin d'animation inattendue")
    if len(sequences) != len(en_tetes):
        raise ValueError("séquences et mouvements ne se répondent pas")
    mouvements = []
    for (indices, pistes), (nom_seq, groupe, images, cadence) in zip(en_tetes, sequences, strict=True):
        mouvements.append(Mouvement(nom_seq, groupe, images / cadence, images, tuple(os_[i] for i in indices),
                                    partial(_pistes, lec.d, tuple(pistes), tuple(i == 0 for i in indices),
                                            cadence, repere)))
    return Animation(nom, tuple(mouvements))


def _pistes(d: bytes, pistes: tuple[_Piste, ...], racines: tuple[bool, ...], cadence: float,
            repere: Repere) -> tuple[Piste, ...]:
    """Les clés d'un mouvement, décodées à la demande (bornes déjà vérifiées)."""
    k = repere.echelle
    lues = []
    for (dq, nq, dp, npos, dt, nt), racine in zip(pistes, racines, strict=True):
        q = struct.unpack_from(f"<{4 * nq}f", d, dq)
        rotations = tuple((q[4 * i], q[4 * i + 1], q[4 * i + 2], q[4 * i + 3]) for i in range(nq))
        v = struct.unpack_from(f"<{3 * npos}f", d, dp)
        positions = tuple((v[3 * i], v[3 * i + 1], v[3 * i + 2]) for i in range(npos))
        if racine:
            rotations = tuple(repere.racine(r) for r in rotations)
            positions = tuple(repere.placer(x) for x in positions)
        else:
            positions = tuple((x[0] * k, x[1] * k, x[2] * k) for x in positions)
        temps = tuple(t / cadence for t in struct.unpack_from(f"<{nt}f", d, dt))
        lues.append(Piste(rotations, positions, temps))
    return tuple(lues)


def _image_du_materiau(q: Paquet, nom: str) -> tuple[str, int, int] | None:
    """(texture, drapeaux, seuil de transparence) d'un matériau du paquet de
    textures, en suivant `Diffuse` / `Material` ; None s'il ne mène à aucune
    image de ce paquet."""
    drapeaux, seuil = 0, _SEUIL
    for _ in range(_SAUTS_MATERIAU):
        lu = q.proprietes_de(nom)
        if lu is None:
            return None
        classe, props = lu
        if classe == "Texture":
            return nom, drapeaux, seuil
        if props.get("TwoSided") is True:
            drapeaux |= PF_DEUX_FACES
        blending, alpha_ref = props.get("OutputBlending"), props.get("AlphaRef")
        if props.get("AlphaTest") is True or (isinstance(blending, bytes) and blending[:1] == bytes([_OB_MASQUE])):
            drapeaux |= PF_MASQUE
        if isinstance(alpha_ref, bytes) and alpha_ref:
            seuil = alpha_ref[0]
        suivant = next((props[c] for c in ("Diffuse", "Material", "Material1", "FallbackMaterial")
                        if isinstance(props.get(c), bytes)), None)
        if not isinstance(suivant, bytes) or not suivant:
            return None
        ref = _Lecteur(suivant).index()
        if ref <= 0:
            return None
        nom = q.nom_objet(ref)
    return None


def _transparence(image: tuple[int, int, bytes], seuil: int) -> tuple[int, int, bytes]:
    """L'image avec un alpha tout ou rien : opaque sous `seuil` 0, sinon
    transparent sous le seuil (le test d'alpha du moteur)."""
    largeur, hauteur, pixels = image
    table = bytes(255 if a >= seuil else 0 for a in range(256))
    sortie = bytearray(pixels)
    sortie[3::4] = pixels[3::4].translate(table)
    return largeur, hauteur, bytes(sortie)


def textures(racine: Path, modele: Maillage) -> tuple[Maillage, dict[str, tuple[int, int, bytes]]]:
    """Les images des matériaux (B V R A), lues dans les paquets de textures
    du jeu (`textures/<paquet>.utx`), et le modèle avec les drapeaux de ses
    matériaux (deux côtés, masque)."""
    images: dict[str, tuple[int, int, bytes]] = {}
    materiaux = list(modele.materiaux)
    for k, m in enumerate(materiaux):
        paquet, _, nom = m.texture.partition(".")
        chemin = encyclopedie.trouver(racine, f"textures/{paquet}.utx") if paquet and nom else None
        q = textures_ue1.paquet(chemin) if chemin is not None else None
        if q is None:
            continue
        try:
            trouve = _image_du_materiau(q, nom)
            if trouve is None:
                continue
            texture, drapeaux, seuil = trouve
            materiaux[k] = replace(m, drapeaux=m.drapeaux | drapeaux)
            if m.texture in images:
                continue
            tex = q.texture(texture)
            if tex is not None:
                masquee = tex.masquee or bool(materiaux[k].drapeaux & PF_MASQUE)
                images[m.texture] = encyclopedie.bgra_de_palette(replace(tex, masquee=masquee))
                continue
            image = q.texture_32(texture)
            if image is not None:
                images[m.texture] = _transparence(image, seuil if drapeaux & PF_MASQUE else 0)
        except (ValueError, IndexError, struct.error):
            log.warning("Matériau %s illisible", m.texture, exc_info=True)
    return replace(modele, materiaux=tuple(materiaux)), images


def de_la_fiche(chemin: Path, nom: str
                ) -> tuple[Maillage, dict[str, tuple[int, int, bytes]], Animation | None] | None:
    """Le modèle `nom` du `.ukx` `chemin` et ses images ; le dossier du jeu
    est le parent de `Animations`. None s'il n'est pas comme relevé."""
    p = textures_ue1.paquet(chemin)
    if p is None:
        return None
    try:
        lu = _lire(p, nom)
    except (ValueError, IndexError, struct.error):
        log.warning("Modèle %s illisible dans %s", nom, chemin, exc_info=True)
        return None
    if lu is None:
        return None
    modele, repere = lu
    animation = None
    if modele.animation:
        try:
            animation = lire_animation(p, modele.animation, repere)
        except (ValueError, IndexError, struct.error):
            log.warning("Animation %s illisible dans %s", modele.animation, chemin, exc_info=True)
    modele, images = textures(chemin.parent.parent, modele)
    return modele, images, animation

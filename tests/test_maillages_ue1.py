"""Modèles 3D d'Unreal 1 (HP1, HP2) : lecture d'un `SkeletalMesh`, pose par les os."""

import math
import struct

import pytest

from src.core import maillages_ue1 as mu
from src.core.textures_ue1 import _Lecteur


def _tab(n: int, octets: bytes = b"") -> bytes:
    """Un tableau de moins de 64 éléments : son compte tient sur un octet."""
    assert n < 64
    return bytes([n]) + octets


def _paresseux(debut: int) -> bytes:
    """Un tableau paresseux vide : sa position de fin, puis le compte 0."""
    return struct.pack("<i", debut + 5) + _tab(0)


def _os(nom: int, rotation, position, parent: int) -> bytes:
    return (bytes([nom]) + struct.pack("<I4f3f4f", 0, *rotation, *position, 1, 1, 1, 1)
            + struct.pack("<ii", 0, parent))


def modele_brut(fin_coupee: bool = False) -> bytes:
    """Un triangle porté par deux os : la racine, et un enfant décalé de 10 en X
    qui porte le troisième point. Tout le reste est vide."""
    d = bytearray(b"\0" * 41)                          # boîte et sphère
    for _ in range(2):                                 # Verts, Tris
        d += _paresseux(len(d))
    d += _tab(0)                                       # AnimSeqs
    d += _paresseux(len(d))                            # Connects
    d += b"\0" * 41
    d += _paresseux(len(d))                            # VertLinks
    d += _tab(1, bytes([7]))                           # Textures : l'objet 7
    d += _tab(0) + _tab(0)                             # BoundingBoxes, BoundingSpheres
    d += b"\0" * 16
    d += struct.pack("<3f3f", 1, 1, 1, 0, 0, 5)        # échelle, origine
    d += b"\0" * 20 + _tab(0)                          # RotOrigin, CurPoly, CurVertex, TextureLOD
    d += _tab(0) + _tab(0)                             # CollapsePointThus, FaceLevel
    d += _tab(1, struct.pack("<4H", 0, 1, 2, 0))       # Faces
    d += _tab(0)                                       # CollapseWedgeThus
    d += _tab(3, struct.pack("<H2B", 0, 0, 0) + struct.pack("<H2B", 1, 255, 0)
              + struct.pack("<H2B", 2, 0, 255))        # Wedges
    d += _tab(1, struct.pack("<Ii", mu.PF_MASQUE, 0))  # Materials
    d += _tab(0) + b"\0" * 32 + _tab(0) + b"\0" * 4    # SpecialFaces… OldFrameVerts
    d += _tab(0)                                       # ExtWedges
    d += _tab(3, struct.pack("<9f", 0, 0, 5, 0, 1, 5, 10, 0, 5))   # Points
    identite = (0.0, 0.0, 0.0, 1.0)
    d += _tab(2, _os(1, identite, (0, 0, 5), 0) + _os(2, identite, (10, 0, 0), 0))
    d += _tab(2, struct.pack("<4H", 0, 2, 0, 0) + struct.pack("<4H", 2, 1, 0, 0))  # BoneWeightIdx
    d += _tab(3, struct.pack("<6H", 0, 65535, 1, 65535, 2, 65535))                   # BoneWeights
    d += _tab(3, struct.pack("<9f", 0, 0, 0, 0, 1, 0, 0, 0, 0))                      # LocalPoints
    d += b"\0" * 4 + _tab(0) + b"\0" * 52
    return bytes(d[:-1] if fin_coupee else d)


def animation_brute(fin_coupee: bool = False) -> bytes:
    """Un mouvement « walk » de 4 images pour les deux os du triangle : la racine
    fait un quart de tour autour de Z entre l'image 0 et l'image 3 (position fixe),
    le bras ne bouge pas. Format relevé dans `maillages_ue1`."""
    d = bytearray()
    d += _tab(2, bytes([1]) + b"\0" * 8 + bytes([2]) + b"\0" * 8)   # RefBones : nom, drapeaux, parent
    d += _tab(1)                                                    # Moves
    d += struct.pack("<3ff2i", 0, 0, 0, 4 / 30, 0, 0)                # RootSpeed3D, TrackTime, StartBone, Flags
    d += _tab(2, struct.pack("<2i", 0, 1))                          # BoneIndices

    def piste(nq: int, npos: int, echelle: float) -> bytes:
        return struct.pack("<I", 0) + bytes([nq, npos, nq]) + struct.pack("<2f", echelle, 1 / 30)

    d += _tab(2, piste(2, 1, 5.0) + piste(1, 1, 10.0))
    d += _tab(1, bytes([3, 0]) + struct.pack("<2i", 0, 4) + _tab(0) + struct.pack("<f", 30))   # AnimSeqs
    d += _tab(3, struct.pack("<9h", 0, 0, 0, 0, 0, 16384, 0, 0, 0))   # rotations : identité, 90° Z, identité
    d += _tab(2, struct.pack("<6h", 0, 0, 32767, 32767, 0, 0))        # positions : (0, 0, 5), (10, 0, 0)
    d += _tab(3, bytes([0, 3, 0]))                                   # temps : images 0 et 3, image 0
    return bytes(d[:-1] if fin_coupee else d)


class _Paquet:
    noms = ["None", "Racine", "Bras", "walk"]

    def __init__(self, data: bytes, animation: bytes = b"") -> None:
        self.data = data
        self.animation = animation

    def objet(self, nom: str, classe: str):
        if classe == "SkeletalMesh":
            return _Lecteur(self.data), len(self.data)
        if classe == "Animation" and self.animation:
            return _Lecteur(self.animation), len(self.animation)
        return None

    def nom_objet(self, ref: int) -> str:
        return {7: "Peau"}.get(ref, "None")


class TestLecture:
    def test_un_triangle_et_son_squelette(self):
        m = mu.lire(_Paquet(modele_brut()), "x")
        assert m is not None
        assert m.points == ((0, 0, 0), (0, 1, 0), (10, 0, 0))        # origine (0, 0, 5) retirée
        assert m.faces == (mu.Face((0, 1, 2), ((0, 0), (1, 0), (0, 1)), 0),)
        assert m.materiaux == (mu.Materiau("Peau", mu.PF_MASQUE),)
        assert [o.nom for o in m.squelette] == ["Racine", "Bras"]
        assert len(m.influences) == 3
        assert m.animation == ""                                      # DefaultAnimation = None

    def test_une_fin_inattendue_se_refuse(self):
        with pytest.raises(ValueError):
            mu.lire(_Paquet(modele_brut(fin_coupee=True)), "x")

    def test_absent(self):
        class Vide(_Paquet):
            def objet(self, nom, classe):
                return None
        assert mu.lire(Vide(b""), "x") is None

    def test_un_fichier_absent_rend_none(self, tmp_path):
        assert mu.maillage(tmp_path / "absent.u", "skharryMesh") is None


class TestPose:
    def test_les_os_redonnent_la_pose_de_reference(self):
        m = mu.lire(_Paquet(modele_brut()), "x")
        for pose, ref in zip(mu.poser(m), m.points, strict=True):
            assert pose == pytest.approx(ref)

    def test_une_retouche_tourne_l_os_et_ses_points(self):
        m = mu.lire(_Paquet(modele_brut()), "x")
        quart = (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))   # 90° autour de Z
        pose = mu.poser(m, {1: quart})
        assert pose[2] == pytest.approx((10, 0, 0))     # le point est à l'origine de l'os
        pose = mu.poser(m, {0: quart})
        assert pose[2] == pytest.approx((0, 10, 0))     # la racine emporte l'enfant

    def test_rotation_entre(self):
        q = mu.rotation_entre((1, 0, 0), (0, 1, 0))
        assert mu.tourner_point(q, (1, 0, 0)) == pytest.approx((0, 1, 0))
        q = mu.rotation_entre((1, 0, 0), (-1, 0, 0))
        assert mu.tourner_point(q, (1, 0, 0)) == pytest.approx((-1, 0, 0))

    def _bonhomme(self, gauche_y: float, bras_z: float) -> mu.Maillage:
        """Un squelette : bassin, cuisses, bras et avant-bras, sans points."""
        identite = (0.0, 0.0, 0.0, 1.0)
        os_ = (
            mu.Os("Bip01 Pelvis", identite, (0, 0, 40), 0),
            mu.Os("Bip01 L Thigh", identite, (0, gauche_y * 4, 0), 0),
            mu.Os("Bip01 R Thigh", identite, (0, -gauche_y * 4, 0), 0),
            mu.Os("Bip01 L UpperArm", identite, (0, gauche_y * 7, 20), 0),
            mu.Os("Bip01 L Forearm", identite, (0, gauche_y * 12, bras_z), 3),
        )
        return mu.Maillage((), (), (), os_)

    def test_bras_en_croix_baisses(self):
        m = self._bonhomme(1, 0)
        retouches = mu.bras_baisses(m, 72)
        assert set(retouches) == {3}
        monde = mu.os_monde(m, retouches)
        d = [monde[4][1][i] - monde[3][1][i] for i in range(3)]
        assert math.degrees(math.atan2(-d[2], math.hypot(d[0], d[1]))) == pytest.approx(72)

    def test_bras_deja_baisses_laisses(self):
        assert mu.bras_baisses(self._bonhomme(1, -30)) == {}

    def test_face(self):
        assert mu.face(self._bonhomme(1, 0)) is None            # gauche vers +Y : déjà de face
        q = mu.face(self._bonhomme(-1, 0))                      # de dos : demi-tour
        assert q is not None
        assert mu.tourner_point(q, (0, -1, 0)) == pytest.approx((0, 1, 0))
        assert mu.face(mu.Maillage((), (), ())) is None          # sans os


class TestAnimation:
    """Les mouvements du jeu : lecture de l'objet `Animation`, pose à un instant."""

    def test_les_composantes_sont_des_sinus(self):
        x, y, z, w = mu._quat_de(16384, 0, 0)                   # asin(√2/2) = π/4 = 16 384 pas
        assert (x, y, z) == pytest.approx((math.sqrt(0.5), 0, 0), abs=1e-4)
        assert w == pytest.approx(math.sqrt(0.5), abs=1e-4)
        assert mu._quat_de(32767, 0, 0)[3] == 0                 # demi-tour : w nul, jamais négatif

    def test_lecture(self):
        a = mu.lire_animation(_Paquet(modele_brut(), animation_brute()), "x")
        assert a is not None and a.nom == "x"
        (walk,) = a.mouvements
        assert (walk.nom, walk.groupe, walk.images) == ("walk", "None", 4)
        assert walk.duree == pytest.approx(4 / 30)
        assert walk.os == ("Racine", "Bras")
        racine, bras = walk.piste("racine"), walk.piste("Bras")   # noms sans casse
        assert walk.piste("Jambe") is None
        assert racine.temps == pytest.approx((0, 0.1))          # 3 images après la première clé
        assert racine.positions == ((0, 0, 5),)
        assert racine.rotations[1] == pytest.approx((0, 0, math.sqrt(0.5), math.sqrt(0.5)), abs=1e-4)
        assert len(bras.positions) == 1 and bras.positions[0] == pytest.approx((10, 0, 0))

    def test_une_fin_inattendue_se_refuse(self):
        with pytest.raises(ValueError):
            mu.lire_animation(_Paquet(modele_brut(), animation_brute(fin_coupee=True)), "x")
        assert mu.lire_animation(_Paquet(modele_brut()), "x") is None

    def test_la_pose_suit_le_mouvement_et_boucle(self):
        p = _Paquet(modele_brut(), animation_brute())
        m, (walk,) = mu.lire(p, "x"), mu.lire_animation(p, "x").mouvements

        def memes(a, b) -> bool:
            return all(pa == pytest.approx(pb, abs=1e-6) for pa, pb in zip(a, b, strict=True))

        assert memes(mu.pose(m, walk, 0), m.points)
        # Image 3 : la racine a tourné d'un quart de tour (rotation prise conjuguée,
        # comme celles du squelette) et emporte le bras.
        fin = mu.pose(m, walk, 0.1)
        assert fin[1] == pytest.approx((1, 0, 0), abs=1e-3)
        assert fin[2] == pytest.approx((0, -10, 0), abs=1e-3)
        milieu = mu.pose(m, walk, 0.05)                          # à mi-chemin : 45°
        assert milieu[2] == pytest.approx((10 * math.sqrt(0.5), -10 * math.sqrt(0.5), 0), abs=1e-3)
        assert memes(mu.pose(m, walk, walk.duree + 0.05), milieu)   # en boucle

    def test_sans_fichier_ni_nom(self, tmp_path):
        assert mu.animation(tmp_path / "absent.u", "skharryAnims") is None
        assert mu.animation(tmp_path / "absent.u", "") is None

"""Modèles 3D d'Unreal 2 (HP3) : un `SkeletalMesh` FABRIQUÉ ici sur le modèle
relevé le 2026-10-29 dans les `.ukx` du jeu (aucune donnée du jeu)."""

import struct

import pytest

from src.core import maillages_ue1 as mu
from src.core import maillages_ue2 as m2
from src.core.textures_ue1 import Paquet, _Lecteur
from tests.test_textures_ue1 import _compact


def _tab(n: int, octets: bytes = b"") -> bytes:
    assert n < 64
    return bytes([n]) + octets


def _paresseux(debut: int, n: int = 0, octets: bytes = b"") -> bytes:
    """Un tableau paresseux posé à `debut` : sa position de fin, puis le tableau."""
    corps = _tab(n, octets)
    return struct.pack("<i", debut + 4 + len(corps)) + corps


def _os(nom: int, position, parent: int) -> bytes:
    return bytes([nom]) + struct.pack("<i4f3ff3fii", 0, 0, 0, 0, 1, *position, 0, 1, 1, 1, 0, parent)


def modele_brut(rot=(0, 0, 0), fin_coupee: bool = False) -> bytes:
    """Un triangle porté par deux os : la racine, et un enfant décalé de 10 en
    X qui porte le troisième point."""
    d = bytearray(b"\0" * 41)                                 # boîte et sphère
    d += struct.pack("<ii", m2._VERSION, 3)
    d += _tab(0)                                              # Verts
    d += _tab(1, _compact(-2))                                # matériaux : l'import 1
    d += struct.pack("<3f3f3i", 2, 2, 2, 0, 0, 5, *rot)       # échelle, origine, rotation
    d += _tab(0) * 4                                          # FaceLevel, Faces, CollapseWedgeThus, Wedges
    d += _tab(1, struct.pack("<Ii", 0, 0))                    # Materials
    d += b"\0" * m2._ENTRE_LOD_ET_OS
    d += _tab(2, _os(1, (0, 0, 5), 0) + _os(2, (10, 0, 0), 0))
    d += _compact(0) + struct.pack("<i", 1)                   # animation, SkeletalDepth
    d += _tab(0) * 5                                          # attaches
    d += _tab(1)                                              # un niveau de détail
    d += _tab(0) + _tab(0) + b"\0" * 4 + _tab(0) + _tab(0)
    d += (_tab(0) + b"\0" * 4) * 2 + b"\0" * 12 + _tab(0)
    d += _paresseux(len(d), 3, struct.pack("<fHH", 1, 0, 0) + struct.pack("<fHH", 1, 1, 0)
                    + struct.pack("<fHH", 1, 2, 1))           # influences
    d += _paresseux(len(d), 3, struct.pack("<H2f", 0, 0, 0) + struct.pack("<H2f", 1, 1, 0)
                    + struct.pack("<H2f", 2, 0, 1))           # coins
    d += _paresseux(len(d), 1, struct.pack("<3H2B", 0, 1, 2, 0, 0))   # faces
    d += _paresseux(len(d), 3, struct.pack("<9f", 0, 0, 5, 0, 1, 5, 10, 0, 5))   # points
    d += b"\0" * 24
    d += _tab(0)
    for _ in range(6):                                        # l'ancien format, vide
        d += _paresseux(len(d))
    d += b"\0" * m2._FIN
    return bytes(d[:-1] if fin_coupee else d)


class _Paquet:
    noms = ["None", "Racine", "Bras"]

    def __init__(self, data: bytes) -> None:
        self.data = data

    def objet(self, nom: str, classe: str):
        return (_Lecteur(self.data), len(self.data)) if classe == "SkeletalMesh" else None

    def nom_objet(self, ref: int) -> str:
        return {-2: "PeauS"}.get(ref, "None")

    def paquet_de(self, ref: int) -> str:
        return "Tissus" if ref == -2 else ""


class TestLecture:
    def test_un_triangle_et_son_squelette(self):
        m = m2.lire(_Paquet(modele_brut()), "x")
        assert m is not None
        # Origine (0, 0, 5) retirée, échelle 2 appliquée d'avance.
        assert [c for p in m.points for c in p] == pytest.approx([0, 0, 0, 0, 2, 0, 20, 0, 0])
        assert m.origine == (0, 0, 0) and m.echelle == (1, 1, 1)
        assert m.faces == (mu.Face((0, 1, 2), ((0, 0), (1, 0), (0, 1)), 0),)
        assert m.materiaux == (mu.Materiau("Tissus.PeauS", 0),)
        assert [o.nom for o in m.squelette] == ["Racine", "Bras"]
        assert len(m.influences) == 3 and m.animation == ""

    def test_les_os_redonnent_la_pose_de_reference(self):
        for rot in ((0, 0, 0), (0, -16384, 16384)):
            m = m2.lire(_Paquet(modele_brut(rot)), "x")
            for pose, ref in zip(mu.poser(m), m.points, strict=True):
                assert pose == pytest.approx(ref, abs=1e-6)

    def test_une_fin_inattendue_se_refuse(self):
        with pytest.raises(ValueError):
            m2.lire(_Paquet(modele_brut(fin_coupee=True)), "x")

    def test_un_fichier_absent_rend_none(self, tmp_path):
        assert m2.de_la_fiche(tmp_path / "Animations" / "absent.ukx", "harry") is None


def _piste_brute(quats, positions, temps) -> bytes:
    return (struct.pack("<i", 0) + _tab(len(quats), b"".join(struct.pack("<4f", *q) for q in quats))
            + _tab(len(positions), b"".join(struct.pack("<3f", *v) for v in positions))
            + _tab(len(temps), struct.pack(f"<{len(temps)}f", *temps)))


def animation_brute(fin_coupee: bool = False) -> bytes:
    """Un mouvement « walk » de 2 images à 1 image/s : la racine tourne d'un
    quart de tour autour de Z à l'image 1 ; l'enfant reste en place. Sans
    table d'os : une piste par os. Une notification dans la séquence."""
    quart = (0.0, 0.0, 2 ** -0.5, 2 ** -0.5)
    d = bytearray(struct.pack("<i", m2._VERSION))
    d += _tab(2, bytes([1]) + struct.pack("<ii", 0, 0) + bytes([2]) + struct.pack("<ii", 0, 0))
    d += _tab(1, struct.pack("<3ffii", 0, 0, 0, 2, 0, 0) + _tab(0)
              + _tab(2, _piste_brute([(0, 0, 0, 1), quart], [(0, 0, 5)], [0, 1])
                     + _piste_brute([(0, 0, 0, 1)], [(10, 0, 0)], [0]))
              + _piste_brute([], [], []) + _tab(0))
    d += _tab(1, b"\0" * 4 + bytes([3]) + _tab(0) + struct.pack("<ii", 0, 2)
              + _tab(1, struct.pack("<f", 0.5) + bytes([0, 0])) + struct.pack("<f", 1.0))
    return bytes(d[:-1] if fin_coupee else d)


class _PaquetAnime(_Paquet):
    noms = ["None", "Racine", "Bras", "walk"]

    def __init__(self, data: bytes, animation: bytes) -> None:
        super().__init__(data)
        self.animation = animation

    def objet(self, nom: str, classe: str):
        if classe == "MeshAnimation":
            return _Lecteur(self.animation), len(self.animation)
        return super().objet(nom, classe)


class TestMouvements:
    def test_lecture_et_pose(self):
        p = _PaquetAnime(modele_brut(), animation_brute())
        m, repere = m2._lire(p, "x")
        a = m2.lire_animation(p, "x", repere)
        assert a is not None and [mv.nom for mv in a.mouvements] == ["walk"]
        walk = a.mouvements[0]
        assert walk.duree == 2.0 and walk.images == 2 and walk.os == ("Racine", "Bras")
        # À l'image 0, la pose de référence ; à l'image 1, tout a tourné
        # d'un quart de tour autour de Z (rotations prises conjuguées).
        for pose, ref in zip(mu.pose(m, walk, 0.0), m.points, strict=True):
            assert pose == pytest.approx(ref, abs=1e-6)
        assert mu.pose(m, walk, 1.0)[1] == pytest.approx((2, 0, 0), abs=1e-6)
        assert mu.pose(m, walk, 1.0)[2] == pytest.approx((0, -20, 0), abs=1e-6)

    def test_une_fin_inattendue_se_refuse(self):
        p = _PaquetAnime(modele_brut(), animation_brute(fin_coupee=True))
        with pytest.raises((ValueError, struct.error)):    # deux erreurs qu'attrape `de_la_fiche`
            m2.lire_animation(p, "x", m2._lire(p, "x")[1])


class TestRedressement:
    def test_le_haut_du_fichier_est_moins_y(self):
        """La rotation d'origine des personnages de HP3 : −Y monte en +Z, le
        devant (+Z) va vers la caméra (+X)."""
        q = m2.redressement((0, -16384, 16384))
        assert mu.tourner_point(q, (0, -1, 0)) == pytest.approx((0, 0, 1), abs=1e-9)
        assert mu.tourner_point(q, (0, 0, 1)) == pytest.approx((1, 0, 0), abs=1e-9)

    def test_sans_rotation(self):
        assert m2.redressement((0, 0, 0)) == pytest.approx((0, 0, 0, 1))


class TestMateriaux:
    class _Textures:
        def __init__(self, objets):
            self.objets = objets

        def proprietes_de(self, nom):
            return self.objets.get(nom)

        def nom_objet(self, ref):
            return {1: "CheveuxA", 2: "CheveuxS"}[ref]

    def test_un_shader_masque_mene_a_son_image(self):
        q = self._Textures({"CheveuxFB": ("FinalBlend", {"Material": _compact(2), "AlphaTest": True,
                                                         "AlphaRef": bytes([75])}),
                            "CheveuxS": ("Shader", {"Diffuse": _compact(1), "TwoSided": True}),
                            "CheveuxA": ("Texture", {})})
        assert m2._image_du_materiau(q, "CheveuxFB") == ("CheveuxA", mu.PF_MASQUE | mu.PF_DEUX_FACES, 75)

    def test_output_blending_masque(self):
        q = self._Textures({"S": ("Shader", {"Diffuse": _compact(1), "OutputBlending": bytes([1])}),
                            "CheveuxA": ("Texture", {})})
        assert m2._image_du_materiau(q, "S") == ("CheveuxA", mu.PF_MASQUE, m2._SEUIL)

    def test_un_materiau_sans_image(self):
        q = self._Textures({"S": ("Shader", {})})
        assert m2._image_du_materiau(q, "S") is None
        assert m2._image_du_materiau(q, "absent") is None

    def test_transparence_tout_ou_rien(self):
        image = (2, 1, bytes([1, 2, 3, 40, 4, 5, 6, 200]))
        assert m2._transparence(image, 75)[2] == bytes([1, 2, 3, 0, 4, 5, 6, 255])
        assert m2._transparence(image, 0)[2] == bytes([1, 2, 3, 255, 4, 5, 6, 255])


def _paquet_ukx() -> bytes:
    """Deux exports nommés `Imp` (mouvements puis modèle, comme dans HP3) et un
    import rangé dans un groupe d'un paquet de textures."""
    noms = ["None", "Core", "Engine", "Class", "Package", "MeshAnimation", "SkeletalMesh",
            "Texture", "Imp", "HPCharTextures", "Creatures", "Peau"]
    n = {nom: i for i, nom in enumerate(noms)}
    corps = bytearray(b"\x00" * 36)
    pos_objets = len(corps)
    corps += _compact(n["None"]) + b"A" + _compact(n["None"]) + b"B"
    pos_noms = len(corps)
    for nom in noms:
        corps += _compact(len(nom) + 1) + nom.encode() + b"\x00" + struct.pack("<I", 0)
    pos_imports = len(corps)
    # -1, -2 : classes ; -3 : paquet ; -4 : groupe dans -3 ; -5 : texture dans -4.
    for paquet, classe, dans, nom in (("Core", "Class", 0, "MeshAnimation"), ("Core", "Class", 0, "SkeletalMesh"),
                                      ("Core", "Package", 0, "HPCharTextures"),
                                      ("Core", "Package", -3, "Creatures"), ("Engine", "Texture", -4, "Peau")):
        corps += _compact(n[paquet]) + _compact(n[classe]) + struct.pack("<i", dans) + _compact(n[nom])
    pos_exports = len(corps)
    for classe, pos in ((-1, pos_objets), (-2, pos_objets + 2)):
        corps += (_compact(classe) + _compact(0) + struct.pack("<i", 0) + _compact(n["Imp"])
                  + struct.pack("<I", 0) + _compact(2) + _compact(pos))
    corps[0:36] = struct.pack("<IIIIIIIII", 0x9E2A83C1, 129, 1, len(noms), pos_noms,
                              2, pos_exports, 5, pos_imports)
    return bytes(corps)


class TestPaquet:
    def test_le_modele_et_ses_mouvements_portent_le_meme_nom(self):
        p = Paquet(_paquet_ukx())
        modele = p.objet("Imp", "SkeletalMesh")
        assert modele is not None and modele[0].d[modele[0].p] == ord("B")
        assert p.objet("Imp", "MeshAnimation") is not None
        assert p.objet("Imp", "Texture") is None

    def test_le_paquet_d_un_import(self):
        p = Paquet(_paquet_ukx())
        assert p.paquet_de(-5) == "HPCharTextures"
        assert p.paquet_de(-3) == "HPCharTextures"
        assert p.paquet_de(1) == "" and p.paquet_de(-99) == ""

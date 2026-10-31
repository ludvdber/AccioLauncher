"""Les modèles de HP5 et HP6 (FPM d'EA), sur des fichiers fabriqués (règle 78)."""

import struct

import pytest

from src.core import maillages_fpm as mf
from src.core.maillages_ue1 import PF_DEUX_FACES


def _fpm(hauteur: float = 1.0, texture: str = "ct_test", magie: bytes = b"FPM4") -> bytes:
    """Un FPM minimal : une partie, un niveau, un sous-maillage de 4 sommets en
    bande (deux triangles), un matériau, une texture."""
    nom = texture.encode() + b"\0"
    d = bytearray(0x2D8 + len(nom))
    d[0:4] = magie
    struct.pack_into("<III", d, 0x04, len(d), 0x20, 0x2D0)       # taille, 0x20, base des indices
    struct.pack_into("<II", d, 0x80, 1, 0x140)                     # parties
    struct.pack_into("<II", d, 0x88, 1, 0x120)                     # matériaux
    struct.pack_into("<II", d, 0x90, 1, 0x100)                     # textures
    struct.pack_into("<I", d, 0x100, 0x2D8)                        # nom de la texture, en fin de fichier
    d[0x2D8:] = nom
    struct.pack_into("<I", d, 0x120, 0x130)                        # matériau → fiche de paramètres
    struct.pack_into("<H", d, 0x130, 0)                            # → texture 0
    struct.pack_into("<II", d, 0x140 + 0x20, 1, 0x180)             # partie : un niveau
    struct.pack_into("<I", d, 0x180 + 0x20, 1)                     # niveau : une fiche
    struct.pack_into("<I", d, 0x180 + 0x28, 0x1C0)
    struct.pack_into("<I", d, 0x1C0 + 0x20, 0x200)                 # fiche → sous-maillage
    d[0x1C0 + 0x2C] = 0                                            # matériau 0
    d[0x200:0x202] = b"PH"
    struct.pack_into("<HH", d, 0x202, 4, 2)                        # indices, triangles
    struct.pack_into("<I", d, 0x214, 0)                            # indices à la base
    d[0x224], d[0x225] = 36, 0x05                                  # pas, disposition basse
    struct.pack_into("<H", d, 0x226, 4)                            # sommets
    coins = ((0, 0, 0), (1, 0, 0), (0, hauteur, 0), (1, hauteur, 0))
    for i, (x, y, z) in enumerate(coins):
        struct.pack_into("<8f", d, 0x240 + 36 * i, x, y, z, 0, 0, 1, x, y)
        d[0x240 + 36 * i + 32:0x240 + 36 * i + 36] = b"\0\xde\xad\xc0"
    struct.pack_into("<4H", d, 0x2D0, 0, 1, 2, 3)
    return bytes(d)


def _strm(*fpms: bytes) -> bytes:
    """Un flux STRM qui range ces FPM en assets de type 0x6B43."""
    def bloc(nom: bytes, corps: bytes) -> bytes:
        return nom[::-1] + struct.pack("<I", len(corps) + 8) + corps
    noms = [b"EA3\0"] + [f"m{i}.fpm\0".encode().ljust(8, b"\0") for i in range(len(fpms))]
    tete = 8 + 8 + 0x14 + 0x28 * len(fpms)
    debut_strs = tete
    positions, p = [], debut_strs + 8
    for n in noms:
        positions.append(p)
        p += len(n)
    debut_data = p + 8
    donnees, offsets = b"", []
    for f in fpms:
        offsets.append(debut_data + len(donnees))
        donnees += f
    corps = bloc(b"GHDR", struct.pack("<3I", 16, positions[0], 16))
    for i, f in enumerate(fpms):
        corps += bloc(b"ASET", struct.pack("<IHHIIIIII", i, 0x6B43, 0, 0, 0, offsets[i], len(f), positions[i + 1], 0))
    interieur = bloc(b"AGRP", corps) + bloc(b"STRS", b"".join(noms)) + bloc(b"DATA", donnees)
    return bloc(b"STRM", interieur)


def test_un_fpm_se_lit_en_triangles_dans_le_repere_de_la_visionneuse():
    points, faces = mf.lire(_fpm())
    # Y en haut, face vers +Z → X devant, Y à gauche, Z en haut.
    assert points[2] == (0.0, 0.0, 1.0) and points[1] == (0.0, 1.0, 0.0)
    assert [s for s, _uv, _t in faces] == [(0, 1, 2), (1, 3, 2)], "bande : un triangle sur deux retourné"
    assert {t for *_x, t in faces} == {"ct_test"}
    assert faces[0][1][1] == (1.0, 0.0)


def test_fpm8_et_refus():
    assert len(mf.lire(_fpm(magie=b"FPM8"))[1]) == 2
    with pytest.raises(ValueError):
        mf.lire(b"FPM20k" + bytes(0x300))
    with pytest.raises(ValueError):
        mf.assets_strm(b"pas un flux")


def test_les_assets_d_un_flux():
    assets = mf.assets_strm(_strm(_fpm(), _fpm()))
    assert [(t, n) for t, n, _d in assets] == [(0x6B43, "m0.fpm"), (0x6B43, "m1.fpm")]
    assert assets[0][2] == _fpm()


def test_la_tete_d_un_eleve_monte_sur_le_col_de_son_corps():
    """Les têtes sont faites pour un col à 1,408 ; un corps plus grand les
    relève d'autant (Luna sur le corps « tall » de HP5, 2026-10-31)."""
    maillage, textures = mf.assembler([_strm(_fpm(hauteur=1.6)), _strm(_fpm(hauteur=1.0))])
    assert textures == {}
    tete = maillage.points[4:]
    assert [p[2] for p in tete] == pytest.approx([0.192, 0.192, 1.192, 1.192])
    assert len(maillage.faces) == 4
    assert all(m.drapeaux & PF_DEUX_FACES for m in maillage.materiaux)


def test_le_halo_d_un_fantome_ne_cache_pas_le_modele():
    maillage, _ = mf.assembler([_strm(_fpm(), _fpm(texture="ct_moa_body_bloom"))])
    assert [m.texture for m in maillage.materiaux] == ["ct_test"]
    assert len(maillage.faces) == 2


def test_le_flux_de_base_porte_les_petites_textures():
    assert mf._base("events/body_models/body_x.str.shd") == "events/body_models/body_x.str"
    assert mf._base("heads/head_models/head_y.str.FFS") == "heads/head_models/head_y.str"
    assert mf._base("x.str") == "x.str"

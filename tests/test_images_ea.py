"""Le décodeur d'images EA (BIGF, SHPI, DXT) sur des données FABRIQUÉES."""

import struct

from src.core import images_ea

ROUGE, BLEU = 0xF800, 0x001F     # RGB 565


def _dxt1(c0: int, c1: int, indices: int) -> bytes:
    return struct.pack("<HHI", c0, c1, indices)


def _shpi(images: list[tuple[str, int, int, int, bytes, int]]) -> bytes:
    """Un bloc SHPI : par image (nom complet, code, largeur, hauteur, pixels, mips),
    l'en-tête, les pixels, puis le bloc attaché 0x70 qui porte le nom."""
    tete = 16 + 8 * len(images)
    corps = b""
    entrees = b""
    for nom, code, w, h, pixels, mips in images:
        position = tete + len(corps)
        saut = 16 + len(pixels)
        en_tete = bytes([code]) + saut.to_bytes(3, "little") + struct.pack("<HHHH", w, h, 0, 0)
        en_tete += b"\0" * 3 + bytes([mips << 4])
        corps += en_tete + pixels + bytes([0x70, 0, 0, 0]) + nom.encode() + b"\0" * 12
        entrees += nom[:4].ljust(4, "_").encode() + struct.pack("<I", position)
    return b"SHPI" + struct.pack("<II", tete + len(corps), len(images)) + b"G354" + entrees + corps


class TestDXT:
    def test_quatre_teintes(self):
        """Indices 0, 1, 2, 3 sur la première rangée : rouge, bleu, puis les
        deux tiers ; pixels en B V R A."""
        px = images_ea.dxt1(_dxt1(ROUGE, BLEU, 0b11100100), 4, 4)
        assert px[0:4] == bytes((0, 0, 255, 255))
        assert px[4:8] == bytes((255, 0, 0, 255))
        assert px[8:12] == bytes((85, 0, 170, 255))
        assert px[12:16] == bytes((170, 0, 85, 255))
        assert px[16:20] == bytes((0, 0, 255, 255))     # rangée 2 : indice 0

    def test_trois_teintes_et_transparent(self):
        """c0 <= c1 : l'indice 3 est un pixel transparent."""
        px = images_ea.dxt1(_dxt1(BLEU, ROUGE, 0b11), 4, 4)
        assert px[0:4] == bytes(4)
        assert px[4:8] == bytes((255, 0, 0, 255))

    def test_les_blocs_vont_a_leur_place(self):
        """Le deuxième bloc d'une image 8 × 4 remplit les colonnes 4 à 7."""
        px = images_ea.dxt1(_dxt1(ROUGE, BLEU, 0) + _dxt1(BLEU, ROUGE, 0x55555555), 8, 4)
        assert px[0:4] == bytes((0, 0, 255, 255))
        assert px[16:20] == bytes((0, 0, 255, 255))     # indice 1 du second bloc : rouge
        assert px[32 * 3 + 28:32 * 3 + 32] == bytes((0, 0, 255, 255))

    def test_dxt5_porte_son_alpha(self):
        alpha = bytes((255, 0)) + (1).to_bytes(6, "little")   # pixel 0 : a1 = 0
        px = images_ea.dxt5(alpha + _dxt1(ROUGE, BLEU, 0), 4, 4)
        assert px[0:4] == bytes((0, 0, 255, 0))
        assert px[4:8] == bytes((0, 0, 255, 255))


class TestSHPI:
    def test_les_images_par_leur_nom(self):
        flux = b"bourrage" + _shpi([("PT_BDG_UN_CM", 0x60, 4, 4, _dxt1(ROUGE, BLEU, 0), 0),
                                    ("PT_BDG_DEUX_CM", 0x60, 4, 4, _dxt1(BLEU, ROUGE, 0), 0)])
        positions = images_ea.images_nommees(flux)
        assert set(positions) == {"PT_BDG_UN_CM", "PT_BDG_DEUX_CM"}
        largeur, hauteur, px = images_ea.image(flux, positions["PT_BDG_DEUX_CM"])
        assert (largeur, hauteur, px[:4]) == (4, 4, bytes((255, 0, 0, 255)))

    def test_le_niveau_de_mip_qui_tient(self):
        """8 × 8 avec un mip : à côté 4, c'est le 4 × 4 (bleu) qui est rendu."""
        pixels = _dxt1(ROUGE, BLEU, 0) * 4 + _dxt1(BLEU, ROUGE, 0)
        flux = _shpi([("IMG", 0x60, 8, 8, pixels, 1)])
        q = images_ea.images_nommees(flux)["IMG"]
        assert images_ea.image(flux, q, cote_max=8)[:2] == (8, 8)
        largeur, _, px = images_ea.image(flux, q, cote_max=4)
        assert (largeur, px[:4]) == (4, bytes((255, 0, 0, 255)))

    def test_rien_d_invente(self):
        """Code inconnu ou pixels tronqués : None, jamais une image fausse."""
        flux = _shpi([("PALETTE", 0x7B, 4, 4, bytes(16), 0)])
        assert images_ea.image(flux, images_ea.images_nommees(flux)["PALETTE"]) is None
        tronque = _shpi([("IMG", 0x60, 64, 64, _dxt1(ROUGE, BLEU, 0), 0)])
        assert images_ea.image(tronque, images_ea.images_nommees(tronque)["IMG"]) is None
        assert images_ea.images_nommees(b"rien ici") == {}


class TestBIG:
    def test_une_entree_par_son_nom(self, tmp_path):
        contenu = b"bonjour"
        nom = b"Chapters/FrontEnd.str\0"
        tete = 16 + 8 + len(nom)
        big = (b"BIGF" + struct.pack("<I", 0) + struct.pack(">II", 1, tete)
               + struct.pack(">II", tete, len(contenu)) + nom + contenu)
        chemin = tmp_path / "data.big"
        chemin.write_bytes(big)
        assert images_ea.entree_big(chemin, "chapters/frontend.str") == contenu
        assert images_ea.entree_big(chemin, "absent.str") == b""
        (tmp_path / "autre.big").write_bytes(b"PAS UNE ARCHIVE")
        assert images_ea.entree_big(tmp_path / "autre.big", "chapters/frontend.str") == b""

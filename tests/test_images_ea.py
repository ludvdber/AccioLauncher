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


def _reference(donnees: bytes, largeur: int, hauteur: int, dxt5: bool) -> bytes:
    """Le décodage de manuel, bloc par bloc et pixel par pixel : ce que le décodeur doit rendre."""
    def canaux(c: int) -> tuple[int, int, int]:
        b, v, r = c & 31, (c >> 5) & 63, c >> 11
        return (b << 3) | (b >> 2), (v << 2) | (v >> 4), (r << 3) | (r >> 2)
    sortie = bytearray(4 * largeur * hauteur)
    pas = 16 if dxt5 else 8
    for bloc in range((largeur // 4) * (hauteur // 4)):
        d = donnees[bloc * pas:(bloc + 1) * pas]
        c0, c1, indices = struct.unpack("<HHI", d[-8:])
        t0, t1 = canaux(c0), canaux(c1)
        if dxt5 or c0 > c1:
            teintes = [(*t0, 255), (*t1, 255), (*((2 * a + b) // 3 for a, b in zip(t0, t1, strict=True)), 255),
                       (*((a + 2 * b) // 3 for a, b in zip(t0, t1, strict=True)), 255)]
        else:
            teintes = [(*t0, 255), (*t1, 255), (*((a + b) // 2 for a, b in zip(t0, t1, strict=True)), 255),
                       (0, 0, 0, 0)]
        alphas, bits = [], 0
        if dxt5:
            a0, a1 = d[0], d[1]
            bits = int.from_bytes(d[2:8], "little")
            alphas = [a0, a1] + ([((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)] if a0 > a1 else
                                 [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255])
        x0, y0 = 4 * (bloc % (largeur // 4)), 4 * (bloc // (largeur // 4))
        for n in range(16):
            pixel = list(teintes[(indices >> (2 * n)) & 3])
            if dxt5:
                pixel[3] = alphas[(bits >> (3 * n)) & 7]
            o = 4 * ((y0 + n // 4) * largeur + x0 + n % 4)
            sortie[o:o + 4] = bytes(pixel)
    return bytes(sortie)


class TestDecodeurEnBloc:
    """2026-11-16 : le décodeur traite tous les blocs d'une image à la fois (tranches à pas,
    tables, entiers longs) ; il doit rendre les octets du décodage de manuel, à l'octet près."""

    def test_memes_octets_que_le_decodage_de_manuel(self):
        import random
        hasard = random.Random(20261116)
        for largeur, hauteur in ((4, 4), (8, 4), (4, 12), (12, 8), (32, 16)):
            blocs = (largeur // 4) * (hauteur // 4)
            for tour in range(30):
                for dxt5 in (False, True):
                    pas = 16 if dxt5 else 8
                    d = bytearray(hasard.randbytes(blocs * pas))
                    if tour % 3 == 0:       # les cas de bord : couleurs égales, alphas égaux ou extrêmes
                        for b in range(blocs):
                            o = b * pas + pas - 8
                            if hasard.random() < 0.4:
                                d[o + 2:o + 4] = d[o:o + 2]
                            if dxt5 and hasard.random() < 0.6:
                                d[b * 16:b * 16 + 2] = hasard.choice((b"\xff\xff", b"\0\0", b"\xff\0", b"\0\xff"))
                    decode = images_ea.dxt5 if dxt5 else images_ea.dxt1
                    assert decode(bytes(d), largeur, hauteur) == _reference(bytes(d), largeur, hauteur, dxt5), \
                        (largeur, hauteur, tour, dxt5)

    def test_une_image_tronquee_est_refusee(self):
        import pytest
        with pytest.raises(ValueError, match="tronquée"):
            images_ea.dxt1(_dxt1(ROUGE, BLEU, 0), 8, 8)
        with pytest.raises(ValueError, match="tronquée"):
            images_ea.dxt5(bytes(16), 8, 4)

    def test_512_pixels_en_moins_de_cent_millisecondes(self):
        """Une texture de personnage de HP5-HP6 : 174 ms en DXT5 bloc par bloc, 15 ms depuis."""
        import random
        import time
        d = random.Random(1).randbytes(128 * 128 * 16)
        debut = time.perf_counter()
        images_ea.dxt5(d, 512, 512)
        assert time.perf_counter() - debut < 0.1


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

    def test_un_cote_hors_des_blocs_dxt_ne_leve_pas(self):
        """Un côté de 6 levait StopIteration (DXT1) ou IndexError (DXT5)."""
        for code in (images_ea.DXT1, images_ea.DXT5):
            flux = _shpi([("IMG", code, 6, 8, bytes(64), 0)])
            assert images_ea.image(flux, images_ea.images_nommees(flux)["IMG"]) is None

    def test_le_mip_s_arrete_avant_un_cote_hors_des_blocs(self):
        """12 × 8 : sa moitié ferait 6 × 4, on rend le 12 × 8."""
        flux = _shpi([("IMG", 0x60, 12, 8, _dxt1(ROUGE, BLEU, 0) * 6 + bytes(16), 1)])
        assert images_ea.image(flux, images_ea.images_nommees(flux)["IMG"], cote_max=4)[:2] == (12, 8)


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

    def test_l_index_se_lit_une_fois(self, tmp_path, monkeypatch, vieillir):
        """Banc de rapidité, 2026-11-13 : chaque image du folio de HP4-HP5 relisait et réanalysait
        l'index de l'archive (data.big ×15 sur un parcours). Mesure : les octets lus."""
        import builtins
        contenu = b"bonjour"
        nom = b"Chapters/FrontEnd.str\0"
        tete = 16 + 8 + len(nom)
        chemin = tmp_path / "index.big"
        chemin.write_bytes(b"BIGF" + struct.pack("<I", 0) + struct.pack(">II", 1, tete)
                           + struct.pack(">II", tete, len(contenu)) + nom + contenu)
        vieillir(chemin)
        lectures = []
        vrai_open = builtins.open

        def compter(f, *a, **k):
            fichier = vrai_open(f, *a, **k)
            if str(f).endswith("index.big"):
                vraie_lecture = fichier.read
                fichier.read = lambda n=-1: (lambda o: (lectures.append(len(o)), o)[1])(vraie_lecture(n))
            return fichier
        monkeypatch.setattr(builtins, "open", compter)
        for _ in range(10):
            assert images_ea.entree_big(chemin, "chapters/frontend.str") == contenu
        assert sum(lectures) <= tete + 10 * len(contenu), lectures   # l'index une fois, puis l'entrée seule

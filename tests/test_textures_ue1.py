"""Lecture d'une texture dans un paquet Unreal 1 : un paquet FABRIQUÉ ici, sur
le modèle de `HPMenu.u` relevé le 2026-10-14 (aucune donnée du jeu)."""

import struct

import pytest

from src.core import folio, textures_ue1


def _compact(v: int) -> bytes:
    a = abs(v)
    octets = bytearray([(0x80 if v < 0 else 0) | (a & 0x3F)])
    a >>= 6
    if a:
        octets[0] |= 0x40
    while a:
        b = a & 0x7F
        a >>= 7
        octets.append(b | (0x80 if a else 0))
    return bytes(octets)


def paquet(nom_texture: str = "Tex0", format_: int | None = None, masquee: bool = True,
           signature: int = 0x9E2A83C1, pixels: bytes = bytes([0, 1, 2, 3]),
           cote: int = 2) -> bytes:
    """Un paquet à deux objets : une palette de 4 couleurs et une texture
    `cote` × `cote` (2 × 2 par défaut)."""
    noms = ["None", "Core", "Class", "Texture", "Palette", "bMasked", "Pal0", nom_texture, "Format"]
    n = {nom: i for i, nom in reversed(list(enumerate(noms)))}

    palette = (_compact(n["None"]) + _compact(4)
               + bytes([10, 20, 30, 0, 255, 0, 0, 0, 0, 255, 0, 0, 0, 0, 255, 0]))
    props = b""
    if masquee:
        props += _compact(n["bMasked"]) + bytes([0xD3, 0x00])       # booléen vrai, taille 0
    if format_ is not None:
        props += _compact(n["Format"]) + bytes([0x01, format_])     # octet
    props += _compact(n["Palette"]) + bytes([0x05]) + _compact(1)   # objet : export 1
    texture = (props + _compact(n["None"]) + bytes([1]) + struct.pack("<i", 0)
               + _compact(len(pixels)) + pixels + struct.pack("<ii", cote, cote) + bytes([1, 1]))

    corps = bytearray(b"\x00" * 36)
    pos_palette = len(corps)
    corps += palette
    pos_texture = len(corps)
    corps += texture
    pos_noms = len(corps)
    for nom in noms:
        corps += _compact(len(nom) + 1) + nom.encode() + b"\x00" + struct.pack("<I", 0)
    pos_imports = len(corps)
    for classe in ("Texture", "Palette"):
        corps += (_compact(n["Core"]) + _compact(n["Class"]) + struct.pack("<i", 0)
                  + _compact(n[classe]))
    pos_exports = len(corps)
    for classe, nom, taille, pos in ((-2, "Pal0", len(palette), pos_palette),
                                     (-1, nom_texture, len(texture), pos_texture)):
        corps += (_compact(classe) + _compact(0) + struct.pack("<i", 0) + _compact(n[nom])
                  + struct.pack("<I", 0) + _compact(taille) + _compact(pos))
    corps[0:36] = struct.pack("<IIIIIIIII", signature, 69, 1, len(noms), pos_noms,
                              2, pos_exports, 2, pos_imports)
    return bytes(corps)


class TestTexture:
    def test_une_texture_256_couleurs(self, tmp_path):
        chemin = tmp_path / "Menu.u"
        chemin.write_bytes(paquet())
        tex = textures_ue1.texture(chemin, "Tex0")
        assert (tex.largeur, tex.hauteur, tex.indices) == (2, 2, bytes([0, 1, 2, 3]))
        assert tex.palette[1] == (255, 0, 0, 0) and len(tex.palette) == 256
        assert tex.masquee

    def test_sans_masque(self, tmp_path):
        chemin = tmp_path / "Menu.u"
        chemin.write_bytes(paquet(masquee=False))
        assert textures_ue1.texture(chemin, "Tex0").masquee is False

    def test_un_autre_format_n_est_pas_devine(self, tmp_path):
        chemin = tmp_path / "Menu.u"
        chemin.write_bytes(paquet(format_=3))   # DXT1 : jamais relevé, jamais deviné
        assert textures_ue1.texture(chemin, "Tex0") is None

    def test_une_texture_32_bits(self, tmp_path):
        """Format 5 (les boucliers de défi de HP3) : 4 octets par pixel, B V R A."""
        pixels = bytes(range(16))
        chemin = tmp_path / "Menu.utx"
        chemin.write_bytes(paquet(format_=5, pixels=pixels))
        assert textures_ue1.texture_32(chemin, "Tex0") == (2, 2, pixels)
        assert textures_ue1.texture(chemin, "Tex0") is None, "pas une texture à palette"

    @pytest.mark.parametrize("format_, bloc", [
        (3, struct.pack("<HHI", 0xF800, 0, 0)),                             # DXT1
        (8, bytes([255, 0]) + bytes(6) + struct.pack("<HHI", 0xF800, 0, 0)),  # DXT5
    ])
    def test_le_dxt_des_friandises_de_hp3(self, tmp_path, format_, bloc):
        """Format 3 et 8 (les dragées, patacitrouilles et fondants de HP3) :
        un bloc 4 × 4 tout rouge, opaque, rendu en B V R A."""
        chemin = tmp_path / "Menu.utx"
        chemin.write_bytes(paquet(format_=format_, pixels=bloc, cote=4))
        assert textures_ue1.texture_32(chemin, "Tex0") == (4, 4, bytes([0, 0, 255, 255]) * 16)

    def test_un_dxt_tronque_ne_rend_rien(self, tmp_path):
        chemin = tmp_path / "Menu.utx"
        chemin.write_bytes(paquet(format_=8, pixels=bytes(8), cote=4))
        assert textures_ue1.texture_32(chemin, "Tex0") is None

    def test_32_bits_seulement_au_format_5(self, tmp_path):
        chemin = tmp_path / "Menu.utx"
        chemin.write_bytes(paquet())
        assert textures_ue1.texture_32(chemin, "Tex0") is None
        chemin.write_bytes(paquet(format_=5, pixels=bytes(12)))     # tronquée
        assert textures_ue1.texture_32(chemin, "Tex0") is None
        assert textures_ue1.texture_32(tmp_path / "absent.utx", "Tex0") is None

    def test_absente(self, tmp_path):
        chemin = tmp_path / "Menu.u"
        chemin.write_bytes(paquet())
        assert textures_ue1.texture(chemin, "Autre") is None
        assert textures_ue1.texture(chemin, "Pal0") is None, "une palette n'est pas une texture"

    def test_pas_un_paquet(self, tmp_path):
        chemin = tmp_path / "Menu.u"
        chemin.write_bytes(paquet(signature=0x12345678))
        assert textures_ue1.texture(chemin, "Tex0") is None
        chemin.write_bytes(b"\x00" * 10)
        assert textures_ue1.texture(chemin, "Tex0") is None
        assert textures_ue1.texture(tmp_path / "rien.u", "Tex0") is None

    def test_un_paquet_tronque_ne_plante_pas(self, tmp_path):
        complet = paquet()
        chemin = tmp_path / "Menu.u"
        for coupe in (40, 80, len(complet) - 20):
            chemin.write_bytes(complet[:coupe])
            assert textures_ue1.texture(chemin, "Tex0") is None

    def test_une_taille_negative_ne_fait_pas_reculer_la_lecture(self):
        """Un booléen dont la taille (sur 4 octets) vaut -6 ramenait la lecture
        au début de la propriété : boucle sans fin, page du folio figée."""
        p = textures_ue1.Paquet.__new__(textures_ue1.Paquet)
        p.noms = ["None", "bMasked"]
        # Nom 1, octet d'info : booléen (3), taille sur 4 octets (code 7).
        donnees = bytes([1, 0x73]) + struct.pack("<i", -6)
        lecteur = textures_ue1._Lecteur(donnees)
        with pytest.raises(ValueError):
            p._proprietes(lecteur, len(donnees))

    def test_des_tables_annoncees_plus_grandes_que_le_fichier(self, tmp_path):
        """Des compteurs absurdes sont refusés d'emblée, sans des millions de tours."""
        complet = bytearray(paquet())
        struct.pack_into("<i", complet, 12, 2**31 - 1)     # nombre de noms
        chemin = tmp_path / "Menu.u"
        chemin.write_bytes(bytes(complet))
        assert textures_ue1.texture(chemin, "Tex0") is None


class TestCartesDuFolio:
    def test_l_image_vient_du_paquet_du_jeu(self, tmp_path):
        system = tmp_path / "System"
        system.mkdir()
        (system / "HPMenu.u").write_bytes(paquet("WizCardMerlinBigTexture"))
        menu = folio.paquet_menu(system)
        assert menu is not None
        # Emplacement 2 du folio : Merlin (le 1 est Dumbledore, ordre du jeu).
        assert folio.image_carte_hp1(menu, 2).largeur == 2
        assert folio.image_carte_hp1(menu, 1) is None
        assert folio.image_carte_hp1(menu, 2, grande=False) is None
        assert folio.image_carte_hp1(menu, 99) is None
        assert folio.image_carte_hp1(None, 2) is None

    def test_jeu_absent(self, tmp_path):
        assert folio.paquet_menu(tmp_path / "rien") is None

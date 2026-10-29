"""Le son des cartes de HP4 : table `fe_cards.map`, banque « BNKl » et EA-XA v2, FABRIQUÉS au format relevé."""

import struct
from pathlib import Path

from src.core import sons_cartes_hp4 as s


def _table(sons: dict[str, tuple[int, ...]]) -> bytes:
    """Le morceau du flux du front-end : nom de la banque, fiches, puis nœuds dans l'ordre des rangs."""
    fiches = b"".join(struct.pack("<I", s.fnv1(nom)) + bytes.fromhex("01000000d00700005c837604")
                      + struct.pack("<II", rang, 0) for rang, nom in enumerate(sons))
    noeuds = b""
    for numeros in sons.values():
        noeuds += b"\x00\x00\xc8\x42" + bytes(28) + struct.pack("<H", len(numeros)) + bytes(6)
        noeuds += b"".join(struct.pack("<IHHII", n, 0xFFFF, 0, 0, 1) for n in numeros)
    return b"bruit\x00fe_general\x00" + b"\x00fe_cards\x00\x00\x00\x00\x00" + bytes(20) + fiches + noeuds


def _banque(echantillons: list[bytes], totaux: list[int]) -> bytes:
    """Une banque v5 : table de décalages à 0x14, en-têtes « PT », puis les données."""
    n = len(echantillons)
    tetes_debut = 0x14 + 4 * n
    taille_tete = 4 + 1 + 4 + 6 + 1
    donnees_debut = tetes_debut + n * taille_tete
    table, tetes, donnees = b"", b"", b""
    for i, (e, total) in enumerate(zip(echantillons, totaux, strict=True)):
        p = tetes_debut + i * taille_tete
        table += struct.pack("<I", p - (0x14 + 4 * i))
        tetes += (b"PT\x00\x00\xfd" + b"\x85\x02" + total.to_bytes(2, "big")
                  + b"\x88\x04" + (donnees_debut + len(donnees)).to_bytes(4, "big") + b"\xff")
        donnees += e
    return b"BNKl" + struct.pack("<HH", 5, n) + bytes(12) + table + tetes + donnees


class TestSonsDesCartes:
    def test_fnv1(self):
        assert s.fnv1("") == 0x811C9DC5
        assert s.fnv1("a") == ((0x811C9DC5 * 0x01000193) & 0xFFFFFFFF) ^ 0x61

    def test_sons_de_scene_dans_l_ordre_sans_doublon(self):
        flux = b"seed:audio\x00fe_cards\x00dgb_call\x00fe_cards\x00dgb_intro\x00x\x00fe_cards\x00dgb_call\x00"
        assert s.sons_de_scene(flux) == ["dgb_call", "dgb_intro"]
        assert s.ordre_des_sons(["dgb_call", "dgb_intro"]) == ["dgb_intro", "dgb_call"]

    def test_table_part_du_nom_de_la_banque(self):
        table = s.table_echantillons(_table({"sal_intro": (21,), "ron_sneeze": (89, 90, 91)}))
        assert table == {s.fnv1("sal_intro"): (21,), s.fnv1("ron_sneeze"): (89, 90, 91)}
        assert s.table_echantillons(b"rien") == {}

    def test_trame_pcm_puis_adpcm_nul(self):
        pcm = list(range(28))
        trame_pcm = b"\xee" + struct.pack(">hh", 27, 26) + struct.pack(">28h", *pcm)
        # Coefficients nuls (0x0_), quartets nuls : 28 zéros.
        trame_adpcm = b"\x0c" + bytes(14)
        assert s.decoder_ea_xa(trame_pcm + trame_adpcm, 0, 56) == pcm + [0] * 28

    def test_adpcm_un_quartet(self):
        # Coefficients nuls, décalage 0 + 8 : 0x7 en tête donne (7 << 28 >> 8) >> 8 = 7 << 12.
        trame = b"\x00\x70" + bytes(13)
        assert s.decoder_ea_xa(trame, 0, 2) == [7 << 12, 0]

    def test_donnees_tronquees_s_arretent(self):
        assert s.decoder_ea_xa(b"\x00\x11", 0, 28) == []

    def test_echantillon_et_wav(self):
        trame = b"\xee" + bytes(4) + struct.pack(">28h", *range(28))
        banque = _banque([trame, trame], [28, 10])
        frequence, pcm = s.echantillon(banque, 2)
        assert frequence == 22050 and pcm == list(range(10))
        assert s.echantillon(banque, 3) is None and s.echantillon(b"BNKx", 1) is None
        w = s.wav(frequence, pcm)
        assert w[:4] == b"RIFF" and w[8:12] == b"WAVE" and len(w) == 44 + 20

    def test_sans_le_jeu(self, tmp_path: Path):
        assert s.son_carte(tmp_path / "absent", "138851E3-044A-446E-8659-C23456EC245A") is None
        assert s.son_carte(tmp_path, "138851E3-044A-446E-8659-C23456EC245A") is None

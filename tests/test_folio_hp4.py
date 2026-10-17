"""Le folio de HP4 : sauvegarde `HPGOF` et textes du jeu FABRIQUÉS, au format relevé chez Ludo."""

import struct
from datetime import datetime

from src.core import folio_hp4


def _entite(nom: str, attributs: list[tuple[int, bytes]]) -> bytes:
    """Une entité 0x705 : GUID, nom sur 32 octets (bourrage SALE, comme chez Ludo), attributs."""
    corps = struct.pack("<II", 0x18, 0x40000000) + bytes(16)
    nom_brut = nom.encode() + b"\0" + b"\x10\0\0\0run\0\xf8e\x15\x05"
    corps += struct.pack("<II", 0x28, 0x80000000) + nom_brut[:32].ljust(32, b"\xbf")
    for indice, charge in attributs:
        corps += struct.pack("<II", 8 + len(charge), indice) + charge
    return struct.pack("<III", 0x705, len(corps), 0x1C02002D) + corps


def _f(x: float) -> bytes:
    return struct.pack("<f", x)


def _i(x: int) -> bytes:
    return struct.pack("<i", x)


def _mots_cartes(cartes: list[int]) -> list[tuple[int, bytes]]:
    """Les sept mots de `GlobalData` 0x22-0x28 : un bit par carte possédée."""
    mots = [0] * 7
    for c in cartes:
        mots[c // 32] |= 1 << (c % 32)
    return [(0x22 + k, struct.pack("<I", m)) for k, m in enumerate(mots)]


# L'emplacement 1 de Ludo (VU) : Harry 1, 8, 9 ; Hermione 120 ; seize cartes de créature.
_CARTES_LUDO = [1, 8, 9, 120, *range(151, 156), *range(157, 161), *range(163, 168), 169, 171]


def _hpgof(rang: int = 4, boucliers: int = 3, cartes: list[int] = _CARTES_LUDO) -> bytes:
    """Emplacement 1 occupé (Forêt des dragons, 28/09/2026), 2 et 3 vides."""
    d = bytearray(0x220 + 3 * 0x2800)
    d[0:4] = b"20CM"
    for k in range(3):
        fiche = 0x10 + k * 0xAC
        struct.pack_into("<ii", d, fiche + 0xAC, -1, -1)
    d[0x10 + 0x0C:0x10 + 0x0C + 19] = b"lvl_003_DragonWoods"
    d[0x10 + 0x6C:0x10 + 0x6C + 10] = b"28/09/2026"
    d[0x10 + 0x8C:0x10 + 0x8C + 8] = b"12:23:58"
    struct.pack_into("<ii", d, 0x10 + 0xAC, rang, boucliers)
    # Les jauges de Ludo (VU à l'écran) et quatre quêtes de la table.
    maitrise = [110, 62, 184, 0, 0, 0, 10.4, 7.2, 27.2, 10, 0, 10, 3, 4.2, 0, 0]
    quetes = [(8, 99, 5, 1, 3), (15, 104, 6, 0, 3), (2, 92, 5, 0, 1), (16, 105, 5, 2, 3),
              (4, 5, 10, 0, 0)]    # un défi de Maugrey : laissé de côté
    globales = []
    for k, champs in enumerate(quetes):
        globales += [(0x63 + 5 * k + j, _i(v)) for j, v in enumerate(champs)]
    globales.append((0x52, _i(501)))
    globales += _mots_cartes(cartes)
    corps = (struct.pack("<III", 0x722, 0x18, 0) + b"evaslvl_003_DragonWoods\0"
             + _entite("GlobalData", globales)
             + _entite("MagicMastery", [(i, _f(v)) for i, v in enumerate(maitrise)]))
    d[0x220:0x220 + len(corps)] = corps
    return bytes(d)


class TestSauvegarde:
    def test_l_emplacement_comme_la_pensine(self):
        parties = folio_hp4.lire(_hpgof())
        assert len(parties) == 1
        p = parties[0]
        assert (p.emplacement, p.niveau, p.rang, p.boucliers) == (1, "lvl_003_DragonWoods", 4, 3)
        assert p.ecrite == datetime(2026, 9, 28, 12, 23, 58)
        assert p.nom_rang == (110, "Compétent(e)")

    def test_les_dragees_du_compteur(self):
        """`GlobalData` 0x52 : les 501 du compteur des pages de cartes (VU)."""
        assert folio_hp4.lire(_hpgof())[0].dragees == 501

    def test_les_jauges_valeur_sur_maximum(self):
        """Wingardium 110/250, Bullitor 4,2/20 : les longueurs mesurées à l'écran."""
        p = folio_hp4.lire(_hpgof())[0]
        jauges = {nom: round(folio_hp4.part(p, i, m), 3)
                  for i, (_, nom), m in folio_hp4.SORTILEGES + folio_hp4.SORTS}
        assert jauges["Wingardium Leviosa"] == 0.44
        assert jauges["Carpe Retractum"] == 0.413
        assert jauges["Aqua Eructo"] == 0.46
        assert jauges["Herbivicus"] == 0
        assert jauges["Orchideus"] == 0.272
        assert jauges["Bullitor"] == 0.21

    def test_les_quetes_par_famille(self):
        """Statues de dragon de deux niveaux additionnées ; défi de Maugrey ignoré."""
        p = folio_hp4.lire(_hpgof())[0]
        quetes = {q.nom[1]: (q.trouves, q.total) for q in p.quetes}
        assert quetes == {"Détecteurs de magie noire": (1, 5), "Gargouilles": (0, 6),
                          "Statues de dragon": (2, 10)}

    def test_les_cartes_comme_le_folio_universitas(self):
        """Page « Jeu 1 » de la pensine (VU) : Harry a 1 carte Endurance et 2 cartes Sort."""
        cartes = folio_hp4.lire(_hpgof())[0].cartes
        assert cartes == frozenset(_CARTES_LUDO)
        harry, ron, hermione = folio_hp4.PERSONNAGES
        assert folio_hp4.compte(cartes, harry[1]) == 3
        assert folio_hp4.compte(cartes, harry[2]["endurance"]) == 1
        assert folio_hp4.compte(cartes, harry[2]["sort"]) == 2
        assert folio_hp4.compte(cartes, ron[1]) == 0
        assert folio_hp4.compte(cartes, hermione[2]["magicus"]) == 1
        assert folio_hp4.compte(cartes, folio_hp4.CREATURES) == 16

    def test_les_bits_hors_de_la_table_sont_ignores(self):
        """Bit 0 (NONE) et au-delà des 203 cartes de l'exe : pas des cartes."""
        assert folio_hp4.lire(_hpgof(cartes=[0, 5, 203, 223]))[0].cartes == frozenset({5})

    def test_les_familles_ne_se_chevauchent_pas(self):
        for _, (debut, fin), familles in folio_hp4.PERSONNAGES:
            plages = sorted(familles.values())
            assert all(debut <= a <= b <= fin for a, b in plages)
            assert all(b1 < a2 for (_, b1), (a2, _) in zip(plages, plages[1:]))
            assert set(familles) == set(folio_hp4.FAMILLES)

    def test_un_rang_jamais_vu_n_a_pas_de_nom(self):
        assert folio_hp4.lire(_hpgof(rang=7))[0].nom_rang is None

    def test_des_boucliers_absurdes_sont_bornes(self):
        assert folio_hp4.lire(_hpgof(boucliers=500))[0].boucliers == folio_hp4.BOUCLIERS

    def test_pas_une_sauvegarde_de_hp4(self):
        assert folio_hp4.lire(b"20CM" + bytes(100)) == []
        assert folio_hp4.lire(b"XXXX" + _hpgof()[4:]) == []

    def test_un_corps_abime_garde_l_en_tete(self):
        d = bytearray(_hpgof())
        struct.pack_into("<I", d, 0x220 + 4, 0x7FFFFFFF)    # morceau plus grand que le corps
        p = folio_hp4.lire(bytes(d))[0]
        assert p.rang == 4 and p.maitrise == () and p.quetes == ()


def _data_big(textes: list[str], dossier: str = "French",
              flux_nom: str = "{1025472C-AB8F-438C-87FB-E0AA3DFE4007}.str") -> bytes:
    """Une archive BIGF d'une entrée : un flux de textes (le front-end par défaut) avec sa table LOCH/LOCL."""
    chaines = [t.encode("utf-16-le") + b"\0\0" for t in textes]
    entete = 16 + 4 * len(chaines)
    offs, corps = [], b""
    for c in chaines:
        offs.append(entete + len(corps))
        corps += c
    locl = b"LOCL" + struct.pack("<III", entete + len(corps), 0, len(chaines))
    locl += struct.pack(f"<{len(offs)}I", *offs) + corps
    flux = b"\x1c\x07\0\0" + bytes(60) + b"LOCH" + struct.pack("<IIII", 0x14, 0, 1, 0x14) + locl
    nom = f"{dossier}/{flux_nom}".encode() + b"\0"
    taille_tete = 16 + 8 + len(nom)
    return (b"BIGF" + struct.pack("<I", 0) + struct.pack(">II", 1, taille_tete)
            + struct.pack(">II", taille_tete, len(flux)) + nom + flux)


class TestTextesDuJeu:
    def _table(self) -> list[str]:
        textes = [f"t{i}" for i in range(150)]
        textes[149], textes[140], textes[137] = "Wingardium Leviosa", "Ebublio", "Carpe Retractum "
        return textes

    def test_les_noms_dans_la_langue_du_joueur(self, tmp_path):
        (tmp_path / "data.big").write_bytes(_data_big(self._table(), "Spanish"))
        folio_hp4._textes.cache_clear()
        table = folio_hp4.textes(tmp_path, "es")
        assert folio_hp4.nom(table, (140, "Bullitor")) == "Ebublio"
        assert folio_hp4.nom(table, (137, "Carpe Retractum")) == "Carpe Retractum"
        assert folio_hp4.nom(table, (-1, "Feux d'artifice du Dr Flibuste")) is None

    def test_une_langue_absente_du_jeu_rend_rien(self, tmp_path):
        (tmp_path / "data.big").write_bytes(_data_big(self._table(), "French"))
        folio_hp4._textes.cache_clear()
        assert folio_hp4.textes(tmp_path, "en") == ()
        assert folio_hp4.textes(tmp_path, "es") == ()

    def test_une_autre_version_du_jeu_se_tait(self, tmp_path):
        """Le repère (149 = Wingardium Leviosa) manque : rien plutôt que des noms faux."""
        textes = self._table()
        textes[149] = "Autre chose"
        (tmp_path / "data.big").write_bytes(_data_big(textes))
        folio_hp4._textes.cache_clear()
        assert folio_hp4.textes(tmp_path, "fr") == ()

    def test_sans_le_jeu(self, tmp_path):
        folio_hp4._textes.cache_clear()
        assert folio_hp4.textes(tmp_path / "absent", "fr") == ()

    def test_la_table_de_la_pensine(self, tmp_path):
        """Un autre flux, un autre repère (49 = Magicus Extremos dans toutes les langues)."""
        textes = [f"t{i}" for i in range(700)]
        textes[49], textes[50], textes[618] = "Magicus Extremos", "Resistencia", "Folio Universitas"
        (tmp_path / "data.big").write_bytes(
            _data_big(textes, "Spanish", "{3932FD6C-38F4-4867-BC66-CE9355A07CF5}.str"))
        folio_hp4._textes.cache_clear()
        table = folio_hp4.textes_jeu(tmp_path, "es")
        assert folio_hp4.nom(table, folio_hp4.FAMILLES["endurance"]) == "Resistencia"
        assert folio_hp4.textes(tmp_path, "es") == (), "le flux du front-end n'est pas là"
        textes[49] = "Autre chose"
        (tmp_path / "data.big").write_bytes(
            _data_big(textes, "Spanish", "{3932FD6C-38F4-4867-BC66-CE9355A07CF5}.str"))
        folio_hp4._textes.cache_clear()
        assert folio_hp4.textes_jeu(tmp_path, "es") == ()


class TestImagesDuMenu:
    """Les blocs SHPI du flux de menu : image 0x7B et sa palette attachée 0x2A."""

    @staticmethod
    def _shpi(nom: bytes, indices: bytes, palette: list[bytes]) -> bytes:
        image = bytes([0x7B]) + (16 + len(indices)).to_bytes(3, "little") \
            + struct.pack("<HH", 2, 2) + bytes(8) + indices
        pal = bytes([0x2A, 0, 0, 0]) + struct.pack("<H", len(palette)) + bytes(10) + b"".join(palette)
        return b"SHPI" + bytes(4) + struct.pack("<I", 1) + b"G264" + nom + struct.pack("<I", 24) \
            + image + pal

    def test_une_dragee(self):
        rouge, bleu = b"\x00\x00\xff\xff", b"\xff\x00\x00\xff"
        flux = b"xx" + self._shpi(b"BEAN", bytes([0, 1, 1, 0]), [rouge, bleu]) \
            + self._shpi(b"PLAY", bytes([1, 1, 1, 1]), [rouge, bleu])
        assert folio_hp4.images_shpi(flux, b"BEAN") == [(2, 2, rouge + bleu + bleu + rouge)]

    def test_un_indice_hors_palette_est_refuse(self):
        flux = self._shpi(b"BEAN", bytes([0, 5, 0, 0]), [b"\x00\x00\x00\xff"])
        assert folio_hp4.images_shpi(flux, b"BEAN") == []

    def test_sans_le_jeu(self, tmp_path):
        assert folio_hp4.image_dragee(tmp_path / "absent") is None

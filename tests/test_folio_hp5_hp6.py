"""Folio de HP5 et HP6 : fichiers FABRIQUÉS sur le relevé du 2026-10-15
(sauvegardes de Ludo, valeurs VUES à l'écran du jeu), aucune donnée du jeu."""

import struct
from datetime import datetime

from src.core import folio_hp5, folio_hp6
from tests.test_sauvegardes import _hpootp


class TestHP5:
    @staticmethod
    def _fichier(*decouvertes: int | None) -> bytes:
        d = bytearray(_hpootp(*[("Hogwarts", datetime(2026, 10, 1, 16, 8, 24), 14)] * len(decouvertes)))
        d.extend(bytes(0x484 + 3 * 0x400 - len(d)))
        for k, points in enumerate(decouvertes):
            if points is None:
                continue
            corps = 0x484 + k * 0x400
            d[corps:corps + 8] = b"PTOO30.1"
            d[corps + 0x108:corps + 0x10C] = points.to_bytes(4, "little")
        return bytes(d)

    def test_les_points_de_decouverte_par_partie(self):
        parties = folio_hp5.lire(self._fichier(330, 75, 0))
        assert [(p.emplacement, p.pourcentage, p.decouverte) for p in parties] == [
            (1, 14, 330), (2, 14, 75), (3, 14, 0)]
        assert parties[0].ecrite == datetime(2026, 10, 1, 16, 8, 24)

    def test_un_corps_inconnu_ne_donne_pas_de_points(self):
        (partie,) = folio_hp5.lire(self._fichier(None))
        assert partie.pourcentage == 14 and partie.decouverte is None

    def test_au_dela_du_maximum_rien_d_invente(self):
        (partie,) = folio_hp5.lire(self._fichier(99999))
        assert partie.decouverte is None

    def test_pas_une_sauvegarde(self):
        assert folio_hp5.lire(b"PK\x03\x04" + bytes(0x1000)) == []


def _hphbp0(ecussons: int = 7, jauge: int = 372, quand=datetime(2026, 10, 1, 18, 42, 44)) -> bytes:
    """En-tête `20CM`, date à 0x20, corps `HPHB2.00WN32`, deux sections."""
    d = bytearray(0x600)   # 125 écussons de 8 octets à partir de 0x130
    d[0:4] = b"20CM"
    struct.pack_into("<7I", d, 0x20, quand.year, quand.month, 4, quand.day,
                     quand.hour, quand.minute, quand.second)
    d[0x54:0x60] = b"HPHB2.00WN32"
    struct.pack_into(">I", d, 0x60, 2)
    struct.pack_into(">III", d, 0x64, folio_hp6.hachage("CrestsCollected"), 0xD8, 125)
    struct.pack_into(">III", d, 0x70, folio_hp6.hachage("Minicrestometer"), 0xD0, 1)
    struct.pack_into(">I", d, 0x58 + 0xD0, jauge)
    for i in range(125):
        cle = 0x08CD_0000 + i if i < ecussons else 0
        struct.pack_into(">II", d, 0x58 + 0xD8 + 8 * i, cle, 124 - i)
    return bytes(d)


class TestHP6:
    def test_le_hachage_du_jeu(self):
        """Les deux clés relevées dans la sauvegarde de Ludo."""
        assert folio_hp6.hachage("CrestsCollected") == 0x0F805E54
        assert folio_hp6.hachage("Minicrestometer") == 0x0FB93262

    def test_ecussons_et_jauge_comme_le_menu_de_pause(self):
        partie = folio_hp6.lire(_hphbp0())
        assert (partie.ecussons, partie.mini_ecussons) == (7, 372)
        assert partie.ecrite == datetime(2026, 10, 1, 18, 42, 44)

    def test_une_date_illisible_garde_le_reste(self):
        partie = folio_hp6.lire(_hphbp0(quand=datetime(2026, 10, 1)).replace(
            (2026).to_bytes(4, "little"), (0).to_bytes(4, "little"), 1))
        assert partie.ecrite is None and partie.ecussons == 7

    def test_pas_une_sauvegarde_de_hp6(self):
        assert folio_hp6.lire(b"20CM" + bytes(0x200)) is None
        assert folio_hp6.lire(_hphbp0()[:0x80]) is None

    def test_un_repertoire_absurde_ne_plante_pas(self):
        d = bytearray(_hphbp0())
        struct.pack_into(">I", d, 0x60, 0xFFFF)
        assert folio_hp6.lire(bytes(d)) is None

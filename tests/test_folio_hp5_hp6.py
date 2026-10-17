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
            # Le répertoire des morceaux, comme chez Ludo (GLOB, DISC, SCRI).
            d[corps + 0x18:corps + 0x3C] = struct.pack(
                "<4sII4sII4sII", b"BOLG", 0xCC, 0x3C, b"CSID", 0x34, 0x108, b"IRCS", 0x3C, 0x13C)
        return bytes(d)

    @staticmethod
    def _poser(fichier: bytes, partie: int, *drapeaux: int) -> bytes:
        d = bytearray(fichier)
        glob = 0x484 + (partie - 1) * 0x400 + 0x3C
        for n in drapeaux:
            d[glob + (n >> 3)] |= 1 << (n & 7)
        return bytes(d)

    def test_le_chapitre_de_chaque_partie(self):
        """L'entier à +0x6C de la fiche choisit la vignette de « Continuer
        aventure » : 4 / 3 / 2 chez Ludo, VU deux silhouettes, Dumbledore,
        Sirius. Hors de la table du jeu : pas de chapitre."""
        d = bytearray(self._fichier(330, 75, 0))
        for k, chapitre in enumerate((4, 3, 99)):
            fiche = 0x20 + k * 0x178 + 0x6C
            d[fiche:fiche + 4] = chapitre.to_bytes(4, "little")
        parties = folio_hp5.lire(bytes(d))
        assert [p.chapitre for p in parties] == [4, 3, None]
        assert folio_hp5.CHAPITRES[4] == "Room_of_Requirement"
        assert folio_hp5.CHAPITRES[3] == "Hogwarts"

    def test_sans_le_jeu_pas_de_vignette(self, tmp_path):
        assert folio_hp5.image_chapitre(tmp_path, 3) is None
        assert folio_hp5.image_chapitre(tmp_path, None) is None

    def test_l_ecran_informations_sur_le_jeu(self):
        """Les drapeaux de la partie 1 de Ludo pour les lignes non nulles de son écran."""
        personnages = (38, 39, 54, *range(62, 72), 73, 74, 75, 78, 84, 85)
        fichier = self._poser(self._fichier(330, 0), 1, 16, 26, 235, 106, *personnages, 376,
                              128, 243, *range(464, 469), 449, 450,
                              103, 302, 583)   # voisins hors des lignes : ignorés
        un, deux = folio_hp5.lire(fichier)
        valeurs = dict(zip((c.libelle for c in folio_hp5.COMPTEURS), un.compteurs, strict=True))
        assert valeurs == {
            "Mots de passe de portraits": 2, "Fantômes": 1, "Créatures volantes": 1,
            "Personnages rencontrés": 19, "Joueurs d'échecs battus": 1,
            "Joueurs de bataille explosive battus": 0, "Joueurs de Bavboules battus": 0,
            "Affaires de Luna": 0, "Paquets de Fred et George": 0,
            "Statues de pièces d'échiquier": 1, "Plaques de sorcier": 0, "Traces d'animaux": 0,
            "Insignes de Poudlard": 1, "Poudlard rangé": 5,
            "Sorts défensifs en une rencontre": 2, "Quêtes de professeurs": 0,
            "Meilleure note dans chaque matière": 0}
        assert deux.compteurs == (0,) * len(folio_hp5.COMPTEURS)

    def test_les_bornes_tombent_dans_le_morceau(self):
        assert max(c.premier + c.total for c in folio_hp5.COMPTEURS) <= 0xCC * 8

    def test_sans_le_morceau_des_drapeaux_pas_de_compteurs(self):
        d = bytearray(self._fichier(330))
        d[0x484 + 0x18:0x484 + 0x1C] = b"XXXX"
        (partie,) = folio_hp5.lire(bytes(d))
        assert partie.decouverte == 330 and partie.compteurs is None

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


# Les identifiants des 7 écussons de la partie de Ludo, dans l'ordre du fichier.
_ECUSSONS_LUDO = (0x08CCF721, 0x08CCF722, 0x06CABEC1, 0x010033B4, 0x0B7B53AE, 0x0EFB3422,
                  0x08CCF723)


def _hphbp0(ecussons: int = 7, jauge: int = 372, quand=datetime(2026, 10, 1, 18, 42, 44)) -> bytes:
    """En-tête `20CM`, date à 0x20, corps `HPHB2.00WN32` à 0x54 ; sections en
    paires (clé, valeur), décalages depuis le corps, comme chez Ludo."""
    h = folio_hp6.hachage
    sections = [
        ("Minicrestometer", [(h("MiniCrestsCollected"), jauge)]),
        ("CrestsCollected", [(k, _ECUSSONS_LUDO[k] if k < ecussons else 0)
                             for k in range(125)]),
        ("CurrentChapterId", [(0x6F4, 2)]),
        ("MissionId", [(h("SpellUnlock_Stupefy"), 5), (h("SpellUnlock_Lumos"), 5),
                       (h("SpellUnlock_Accio"), 0), (h("Chapter_BurrowIntro"), 15)]),
        ("Badges", [(h("COM_BEGINNERSLUCK"), 1), (h("COM_PACIFIST"), 0),
                    (h("NOT_ACQUIRED"), 0)]),
    ]
    d = bytearray(0x100)
    d[0:4] = b"20CM"
    struct.pack_into("<7I", d, 0x20, quand.year, quand.month, 4, quand.day,
                     quand.hour, quand.minute, quand.second)
    d[0x54:0x60] = b"HPHB2.00WN32"
    struct.pack_into(">I", d, 0x60, len(sections))
    for k, (nom, paires) in enumerate(sections):
        struct.pack_into(">III", d, 0x64 + 12 * k, h(nom), len(d) - 0x54, len(paires))
        for cle, valeur in paires:
            d += struct.pack(">II", cle, valeur)
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
        # « 3 / 25 (372) » à l'écran ; la barre va de 300 à 450.
        assert folio_hp6.palier(372) == (3, 0.48)

    def test_paliers_aux_bords(self):
        assert folio_hp6.palier(0) == (0, 0.0)
        assert folio_hp6.palier(50) == (0, 0.5)
        assert folio_hp6.palier(100) == (1, 0.0)
        assert folio_hp6.palier(25000) == (25, 1.0)
        assert folio_hp6.palier(99999) == (25, 1.0)

    def test_chapitre_sorts_et_badges(self):
        """Un sort à 0 n'est pas appris ; ordre de `SORTS`, pas du fichier.
        `NOT_ACQUIRED` n'est pas un badge : 30 à l'écran du jeu, pas 31."""
        partie = folio_hp6.lire(_hphbp0())
        assert partie.chapitre == 2
        assert partie.sorts == ("Stupefy", "Lumos")
        assert (partie.badges, partie.badges_total) == (1, 2)

    def test_les_decalages_partent_du_corps(self):
        """Lue depuis 0x58, la jauge serait la clé suivante : rien ne doit
        sortir d'un fichier décalé de 4 octets."""
        d = bytearray(_hphbp0())
        struct.pack_into(">I", d, 0x64 + 4, struct.unpack_from(">I", d, 0x64 + 4)[0] - 4)
        assert folio_hp6.lire(bytes(d)).mini_ecussons == 0

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


class TestEcussonsParLieu:
    def test_125_ecussons_sans_doublon(self):
        """Le « / 125 » du menu de pause, et deux noms ne tombent jamais sur le
        même identifiant."""
        noms = [n for _, groupe in folio_hp6.LIEUX for n in groupe.split()]
        assert len(noms) == folio_hp6.ECUSSONS
        assert len({folio_hp6.hachage(n) for n in noms}) == folio_hp6.ECUSSONS

    def test_les_identifiants_releves_dans_les_niveaux(self):
        """Hachage du nom d'entité = identifiant de la sauvegarde (vu dans
        les archives du jeu pour « Forest_Path_Crest_01 » et un « .CrestMain »)."""
        assert folio_hp6.hachage("Forest_Path_Crest_01") == 0x08CCF721
        assert folio_hp6.hachage("Viaduct_Entrance_Crest_03.CrestMain") == 0x0B7B53AE

    def test_la_partie_de_ludo_lieu_par_lieu(self):
        partie = folio_hp6.lire(_hphbp0())
        lieux = {x.libelle: (x.trouves, x.total) for x in folio_hp6.par_lieu(partie.trouves)}
        assert lieux["Chemin de la forêt"] == (3, 3)
        assert lieux["Grand escalier"] == (1, 4)
        assert lieux["Dortoir des garçons"] == (1, 1)
        assert lieux["Entrée du viaduc"] == (1, 3)
        assert lieux["Pont couvert"] == (1, 1)
        assert sum(t for t, _ in lieux.values()) == 7
        assert sum(n for _, n in lieux.values()) == 125

    def test_un_identifiant_inconnu_n_est_compte_nulle_part(self):
        lieux = folio_hp6.par_lieu(frozenset({0x12345678}))
        assert sum(x.trouves for x in lieux) == 0


class TestBadges:
    def test_trente_badges_en_trois_series(self):
        cles = [cle for cle, _, _ in folio_hp6.BADGES]
        assert len(cles) == len(set(cles)) == 30
        for prefixe, _ in folio_hp6.SERIES:
            assert sum(c.startswith(prefixe) for c in cles) == 10

    def test_les_badges_remportes(self):
        partie = folio_hp6.lire(_hphbp0())
        assert partie.acquis == frozenset({"COM_BEGINNERSLUCK"})

    def test_la_cle_des_textes_du_jeu(self):
        """« Badge star du club de potions » est rangé sous 0x03ababec."""
        assert folio_hp6.fnv1("GUI_POTIONS_BADGES_CLUB_STAR") == 0x03ABABEC

    def test_la_table_de_textes(self):
        def entree(cle: int, texte: str) -> bytes:
            brut = (texte + "\0").encode("utf-16-le")
            brut += b"*" * (-len(brut) % 4)
            return struct.pack("<II", cle, len(brut)) + brut + struct.pack("<II", 0, 0)

        flux = b"xx" + b"TX  " + struct.pack("<I", 1) + entree(7, "Badge") + entree(9, "Été")
        assert folio_hp6.table_textes(flux + b"\xff" * 8) == {7: "Badge", 9: "Été"}

    def test_sans_le_jeu_rien(self, tmp_path):
        assert folio_hp6.images_badges(tmp_path) == {}
        assert folio_hp6.textes_badges(tmp_path, "fr") == {}

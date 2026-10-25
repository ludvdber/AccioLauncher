"""Le folio de HP3 : un paquet Unreal 2 FABRIQUÉ sur le modèle des sauvegardes
de Ludo (relevé le 2026-10-15), aucune donnée du jeu."""

import os
from datetime import datetime
import struct

from src.core import folio_hp3, textures_ue1
from tests.test_textures_ue1 import _compact


class _Paquet:
    """Un paquet à quelques objets, chacun d'une classe importée, aux
    propriétés étiquetées imbriquées comme dans un paquet Unreal 2."""

    def __init__(self) -> None:
        self.noms = ["None", "Core", "Class", "HGame"]
        self.objets: list[tuple[str, bytes]] = []
        self._imports: list[str] = []

    def n(self, nom: str) -> bytes:
        if nom not in self.noms:
            self.noms.append(nom)
        return _compact(self.noms.index(nom))

    def entier(self, nom: str, v: int, indice: int = 0) -> bytes:
        return (self.n(nom) + bytes([0x22 | (0x80 if indice else 0)])
                + (bytes([indice]) if indice else b"") + struct.pack("<i", v))

    def octet(self, nom: str, v: int, indice: int = 0) -> bytes:
        return (self.n(nom) + bytes([0x01 | (0x80 if indice else 0)])
                + (bytes([indice]) if indice else b"") + bytes([v]))

    def nom(self, nom: str, valeur: str) -> bytes:
        corps = self.n(valeur)
        return self.n(nom) + bytes([0x06 | 0x50]) + bytes([len(corps)]) + corps

    def classe(self, nom: str, valeur: str) -> bytes:
        # Une référence de classe : un import, d'indice négatif.
        self.n(valeur)
        corps = _compact(-(self._import(valeur) + 1))
        return self.n(nom) + bytes([0x08 | 0x50]) + bytes([len(corps)]) + corps

    def structure(self, nom: str, struct_nom: str, champs: bytes, indice: int = 0) -> bytes:
        corps = champs + self.n("None")
        return (self.n(nom) + bytes([0x0A | 0x50 | (0x80 if indice else 0)]) + self.n(struct_nom)
                + bytes([len(corps)]) + (bytes([indice]) if indice else b"") + corps)

    def tableau(self, nom: str, elements: list[bytes]) -> bytes:
        corps = _compact(len(elements)) + b"".join(e + self.n("None") for e in elements)
        return self.n(nom) + bytes([0x09 | 0x70]) + struct.pack("<I", len(corps)) + corps

    def objet(self, classe: str, *props: bytes) -> None:
        self.n(classe)
        self.objets.append((classe, b"".join(props) + self.n("None")))

    def _import(self, nom: str) -> int:
        if nom not in self._imports:
            self._imports.append(nom)
        return self._imports.index(nom)

    def octets(self) -> bytes:
        for classe, _ in self.objets:
            self._import(classe)
        self.n("Objet")
        d = bytearray(b"\x00" * 36)
        positions = []
        for _, corps in self.objets:
            positions.append(len(d))
            d += corps
        pos_noms = len(d)
        for nom in self.noms:
            d += _compact(len(nom) + 1) + nom.encode() + b"\x00" + struct.pack("<I", 0)
        pos_imports = len(d)
        imports = self._imports
        for nom in imports:
            d += (_compact(self.noms.index("HGame")) + _compact(self.noms.index("Class"))
                  + struct.pack("<i", 0) + _compact(self.noms.index(nom)))
        pos_exports = len(d)
        for (classe, corps), pos in zip(self.objets, positions, strict=False):
            d += (_compact(-(imports.index(classe) + 1)) + _compact(0) + struct.pack("<i", 0)
                  + _compact(self.noms.index("Objet")) + struct.pack("<I", 0)
                  + _compact(len(corps)) + _compact(pos))
        d[0:36] = struct.pack("<IIIIIIIII", 0x9E2A83C1, 129, 1, len(self.noms), pos_noms,
                              len(self.objets), pos_exports, len(imports), pos_imports)
        return bytes(d)


def _partie() -> bytes:
    """La partie de Save0 de Ludo, en petit : 813 dragées, deux cartes
    possédées sur trois (dont une en `wc_` minuscule), un défi et un secret."""
    p = _Paquet()
    p.objet("JellybeanCollection", p.entier("iNumItems", 813))
    p.objet("PumpkinPastyCollection", p.entier("iNumItems", 23))
    p.objet("hgame", p.nom("CurrentGameState", "GState010"))
    carte = lambda classe, statut: p.classe("CardClass", classe) + p.octet("Status", statut)  # noqa: E731
    p.objet("WizardCardManager", p.tableau("Cards", [
        carte("WC_ZouYen", 5), carte("wc_ThaddeusThurkell", 5), carte("WC_Merlin", 1)]))
    trouves = p.octet("Found", 1) + p.octet("Found", 1, 1) + p.octet("Found", 1, 5)
    p.objet("ChallengeStarManager", p.structure(
        "FoundStatus", "LevelFoundStatus",
        p.nom("LevelID", "CR") + p.entier("NumInLevel", 4) + trouves))
    p.objet("SecretManager", p.structure(
        "FoundStatus", "LevelSecretStatus",
        p.nom("LevelID", "CRB") + p.entier("NumFound", 2) + p.entier("NumInLevel", 2), indice=1))
    return p.octets()


class TestLecture:
    def test_la_partie(self):
        partie = folio_hp3.lire(_partie())
        assert (partie.dragees, partie.pasties, partie.gateaux) == (813, 23, 0)
        assert partie.histoire == "GState010"
        assert partie.cartes == frozenset({"wc_zouyen", "wc_thaddeusthurkell"})
        assert partie.total_cartes == 3

    def test_les_etoiles_au_dela_du_niveau_ne_comptent_pas(self):
        """Found[5] est posé mais le niveau n'en a que 4."""
        (niveau,) = folio_hp3.lire(_partie()).etoiles
        assert (niveau.ident, niveau.trouves, niveau.total) == ("CR", 2, 4)

    def test_les_secrets(self):
        (niveau,) = folio_hp3.lire(_partie()).secrets
        assert (niveau.ident, niveau.trouves, niveau.total) == ("CRB", 2, 2)

    def test_au_tout_debut_rien_a_lire(self):
        p = _Paquet()
        p.objet("hgame", p.nom("CurrentGameState", "GSTATE000"))
        assert folio_hp3.lire(p.octets()) is None

    def test_pas_un_paquet(self):
        assert folio_hp3.lire(b"PK\x03\x04" + bytes(100)) is None

    def test_un_paquet_tronque_ne_plante_pas(self):
        assert folio_hp3.lire(_partie()[:-40]) is None


class TestReleve:
    def test_emplacements_et_sauvegarde_rapide(self, tmp_path):
        for n in (0, 9):
            (tmp_path / f"Save{n}.usa").write_bytes(_partie())
        releves = folio_hp3.emplacements({p.name: p for p in tmp_path.iterdir()})
        assert [(r.emplacement, r.rapide, r.lu) for r in releves] == [(1, False, True), (10, True, True)]

    def test_relu_quand_le_fichier_change(self, tmp_path):
        chemin = tmp_path / "Save0.usa"
        chemin.write_bytes(_partie())
        os.utime(chemin, (1_700_000_000, 1_700_000_000))
        assert folio_hp3.releve(chemin).dragees == 813
        p = _Paquet()
        p.objet("JellybeanCollection", p.entier("iNumItems", 36))
        chemin.write_bytes(p.octets())
        os.utime(chemin, (1_700_000_100, 1_700_000_100))
        assert folio_hp3.releve(chemin).dragees == 36


class TestNomsDesCartes:
    def _jeu(self, tmp_path, menu: str, ext: str = "Fre"):
        """`HGame.u` avec deux classes de cartes et leur `dialogId`, et le texte."""
        p = _Paquet()
        dialog = p.n("dialogId")
        carte = p.n("CardID")
        noms = p.noms + ["WC_ZouYen", "wc_ThaddeusThurkell"]
        p.noms = noms
        # Comme dans HGame.u : `dialogId` (entier), puis `CardID` (chaîne « BE14 »).
        corps = {"WC_ZouYen": b"\x06\x00\xff" + dialog + b"\x22" + struct.pack("<i", 142)
                 + carte + b"\x5d\x06\x05BE14\x00" + b"\x00",
                 "wc_ThaddeusThurkell": dialog + b"\x22" + struct.pack("<i", 150)
                 + carte + b"\x5d\x06\x05WZ09\x00"}
        d = bytearray(b"\x00" * 36)
        positions = []
        for c in corps.values():
            positions.append(len(d))
            d += c
        pos_noms = len(d)
        for nom in noms:
            d += _compact(len(nom) + 1) + nom.encode() + b"\x00" + struct.pack("<I", 0)
        pos_exports = len(d)
        for (classe, c), pos in zip(corps.items(), positions, strict=False):
            d += (_compact(0) + _compact(0) + struct.pack("<i", 0) + _compact(noms.index(classe))
                  + struct.pack("<I", 0) + _compact(len(c)) + _compact(pos))
        d[0:36] = struct.pack("<IIIIIIIII", 0x9E2A83C1, 129, 1, len(noms), pos_noms,
                              2, pos_exports, 0, len(d))
        system = tmp_path / "system"
        system.mkdir()
        (system / "HGame.u").write_bytes(bytes(d))
        (system / f"HpMenu.{ext}").write_bytes(menu.encode("utf-16"))
        return system

    def test_par_le_numero_du_jeu_pas_par_le_nom_de_classe(self, tmp_path):
        system = self._jeu(tmp_path, "[All]\r\nWizardName_142=Dzou Yen\r\n"
                                     "wizardname_150=Thadée Thurkell\r\n")
        assert folio_hp3.noms_cartes(system, "fr") == {
            "wc_zouyen": "Dzou Yen", "wc_thaddeusthurkell": "Thadée Thurkell"}

    def test_sans_la_langue_l_anglais(self, tmp_path):
        system = self._jeu(tmp_path, "[All]\r\nWizardName_142=Zou Yen\r\n", ext="int")
        assert folio_hp3.noms_cartes(system, "fr") == {"wc_zouyen": "Zou Yen"}

    def test_jeu_absent(self, tmp_path):
        assert folio_hp3.noms_cartes(tmp_path / "rien", "fr") == {}
        assert folio_hp3.catalogue(tmp_path / "rien", "fr") == folio_hp3.Catalogue()

    def test_series_dans_l_ordre_du_jeu_et_descriptions(self, tmp_path):
        system = self._jeu(tmp_path, (
            "[All]\r\nWizardName_142=Dzou Yen\r\nWizardName_150=Thadée Thurkell\r\n"
            "wizarddesc_142=Dzou Yen (an 300 environ) - Sorcier chinois.\r\n"
            "WizardDesc_150=Sans dates, rien à couper\r\n"
            "wizardmenu_104=Cartes des sorciers célèbres\r\nwizardmenu_112=Cartes des monstres\r\n"
            "achievemntsmenu_2=Défi du Carpe Retractum\r\n"))
        cat = folio_hp3.catalogue(system, "fr")
        assert [(s.code, s.titre, [c.code for c in s.cartes]) for s in cat.series] == [
            ("WZ", "Cartes des sorciers célèbres", ["WZ09"]),
            ("BE", "Cartes des monstres", ["BE14"])]
        dzou = cat.cartes[1]
        assert (dzou.classe, dzou.dates, dzou.texte) == ("wc_zouyen", "an 300 environ", "Sorcier chinois.")
        assert cat.cartes[0].dates == "" and cat.cartes[0].texte == "Sans dates, rien à couper"
        assert cat.defis == {"cr": "Défi du Carpe Retractum"}

    def test_l_image_sans_le_jeu(self, tmp_path):
        assert folio_hp3.image_carte(tmp_path / "system", "VP05") is None
        assert folio_hp3.image_carte(tmp_path / "system", "../x") is None


class TestDefis:
    def test_les_deux_cartes_d_un_defi_reunies(self, tmp_path):
        r = folio_hp3.Releve(
            1, tmp_path / "Save0.usa", datetime(2026, 9, 20), True,
            etoiles=(folio_hp3.Niveau("CR", 6, 6), folio_hp3.Niveau("crb", 4, 4)),
            secrets=(folio_hp3.Niveau("CR", 3, 3), folio_hp3.Niveau("adv1", 0, 0)))
        (defi,) = folio_hp3.defis(r, {"cr": "Défi du Carpe Retractum", "gl": "Défi du Glacius"})
        assert defi == folio_hp3.Defi("Défi du Carpe Retractum", 10, 10, 3, 3, "cr")

    def test_resume_la_derniere_lisible(self, tmp_path):
        (tmp_path / "Save0.usa").write_bytes(_partie())
        vide = _Paquet()
        vide.objet("hgame", vide.nom("CurrentGameState", "GSTATE000"))
        (tmp_path / "Save1.usa").write_bytes(vide.octets())
        os.utime(tmp_path / "Save0.usa", (1_700_000_000, 1_700_000_000))
        resume = folio_hp3.resume({p.name: p for p in tmp_path.iterdir()}, tmp_path, "fr")
        assert resume.releve.emplacement == 1, "un début de jeu plus récent ne compte pas"
        assert (resume.trouvees, resume.total) == (2, 3)

    def test_le_lecteur_de_paquet_rend_les_structures(self):
        paquet = textures_ue1.Paquet(_partie())
        cartes = dict((n, v) for n, _, v in paquet.lues("WizardCardManager"))["Cards"]
        assert cartes[0] == [("CardClass", 0, "WC_ZouYen"), ("Status", 0, 5)]


def test_bouclier_sans_le_jeu_ou_sans_defi(tmp_path):
    """Pas de jeu installé, ou un défi sans bouclier relevé : rien d'inventé."""
    assert folio_hp3.image_bouclier(tmp_path / "system", "cr") is None
    assert folio_hp3.image_bouclier(tmp_path / "system", "adv1") is None


class TestIconesDuMenu:
    """Les icônes des tuiles et des séries, lues dans `textures/HP3_Menu.utx`."""

    def _menu(self, tmp_path, contenu: bytes):
        (tmp_path / "textures").mkdir()
        (tmp_path / "textures" / "HP3_Menu.utx").write_bytes(contenu)
        return tmp_path / "system"

    def test_une_friandise_en_32_bits(self, tmp_path):
        from tests.test_textures_ue1 import paquet
        pixels = bytes(range(16))
        system = self._menu(tmp_path, paquet("Beans", format_=5, pixels=pixels))
        assert folio_hp3.image_menu(system, "Beans") == (2, 2, pixels)

    def test_un_pentagone_de_serie_en_256_couleurs(self, tmp_path):
        """`CardWZ` et les autres sont à palette : rendus en B V R A, l'indice 0
        transparent quand la texture est masquée."""
        from tests.test_textures_ue1 import paquet
        system = self._menu(tmp_path, paquet("CardWZ"))
        largeur, hauteur, pixels = folio_hp3.image_menu(system, "CardWZ")
        assert (largeur, hauteur) == (2, 2)
        assert pixels == bytes([30, 20, 10, 0, 0, 0, 255, 255, 0, 255, 0, 255, 255, 0, 0, 255])

    def test_sans_le_jeu(self, tmp_path):
        assert folio_hp3.image_menu(tmp_path / "system", "Beans") is None

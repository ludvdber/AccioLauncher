"""Le folio de HP3 : un paquet Unreal 2 FABRIQUÉ sur le modèle des sauvegardes
de Ludo (relevé le 2026-10-15), aucune donnée du jeu."""

import os
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
        for (classe, corps), pos in zip(self.objets, positions):
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
        noms = p.noms + ["WC_ZouYen", "wc_ThaddeusThurkell"]
        p.noms = noms
        corps = {"WC_ZouYen": b"\x06\x00\xff" + dialog + b"\x22" + struct.pack("<i", 142) + b"\x00",
                 "wc_ThaddeusThurkell": dialog + b"\x22" + struct.pack("<i", 150)}
        d = bytearray(b"\x00" * 36)
        positions = []
        for c in corps.values():
            positions.append(len(d))
            d += c
        pos_noms = len(d)
        for nom in noms:
            d += _compact(len(nom) + 1) + nom.encode() + b"\x00" + struct.pack("<I", 0)
        pos_exports = len(d)
        for (classe, c), pos in zip(corps.items(), positions):
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

    def test_le_lecteur_de_paquet_rend_les_structures(self):
        paquet = textures_ue1.Paquet(_partie())
        cartes = dict((n, v) for n, _, v in paquet.lues("WizardCardManager"))["Cards"]
        assert cartes[0] == [("CardClass", 0, "WC_ZouYen"), ("Status", 0, 5)]

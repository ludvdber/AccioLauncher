"""Le folio de HP2 sur des paquets FABRIQUÉS ici, sur le modèle relevé le
2026-10-16 dans `Slot1/Save0.usa` et `system/hgame.u` (aucune donnée du jeu)."""
import os
import struct
from datetime import datetime

import pytest

from src.core import folio, folio_hp2
from src.core.i18n import set_language
from tests.test_textures_ue1 import _compact


class _Paquet:
    """Un paquet Unreal 1 minimal : des noms, des imports, des exports."""

    def __init__(self) -> None:
        self.noms: list[str] = ["None", "Core", "Class"]
        self.imports: list[str] = []
        self.exports: list[tuple[int, int, str, bytes]] = []   # classe, parent, nom, corps

    def nom(self, nom: str) -> int:
        if nom not in self.noms:
            self.noms.append(nom)
        return self.noms.index(nom)

    def importer(self, nom: str) -> int:
        self.nom(nom)
        if nom not in self.imports:
            self.imports.append(nom)
        return -(self.imports.index(nom) + 1)

    def exporter(self, classe: int, nom: str, corps: bytes, parent: int = 0) -> int:
        self.nom(nom)
        self.exports.append((classe, parent, nom, corps))
        return len(self.exports)

    def prop(self, nom: str, genre: int, valeur: bytes, indice: int = 0,
             structure: str | None = None) -> bytes:
        code = {1: 0, 2: 1, 4: 2, 12: 3, 16: 4}.get(len(valeur))
        info = genre | ((code if code is not None else 5) << 4) | (0x80 if indice else 0)
        sortie = _compact(self.nom(nom)) + bytes([info])
        if structure is not None:
            sortie += _compact(self.nom(structure))
        if code is None:
            sortie += bytes([len(valeur)])
        if indice:
            sortie += bytes([indice])
        return sortie + valeur

    def fin(self) -> bytes:
        return _compact(self.nom("None"))

    def octets(self) -> bytes:
        corps = bytearray(b"\x00" * 36)
        positions = []
        for _, _, _, contenu in self.exports:
            positions.append(len(corps))
            corps += contenu
        pos_noms = len(corps)
        for nom in self.noms:
            corps += _compact(len(nom) + 1) + nom.encode() + b"\x00" + struct.pack("<I", 0)
        pos_imports = len(corps)
        for nom in self.imports:
            corps += (_compact(self.nom("Core")) + _compact(self.nom("Class"))
                      + struct.pack("<i", 0) + _compact(self.nom(nom)))
        pos_exports = len(corps)
        for (classe, parent, nom, contenu), pos in zip(self.exports, positions):
            corps += (_compact(classe) + _compact(parent) + struct.pack("<i", 0)
                      + _compact(self.nom(nom)) + struct.pack("<I", 0)
                      + _compact(len(contenu)) + _compact(pos))
        corps[0:36] = struct.pack("<IIIIIIIII", 0x9E2A83C1, 69, 1, len(self.noms), pos_noms,
                                  len(self.exports), pos_exports, len(self.imports), pos_imports)
        return bytes(corps)


def _chaine(texte: str) -> bytes:
    return _compact(len(texte) + 1) + texte.encode("latin-1") + b"\x00"


def sauvegarde(cartes=(), marchands=(), dragees=0, points=None, etoiles=None,
               titre="Whomping Willow") -> bytes:
    """`harry` et `LevelInfo0`, comme une sauvegarde du jeu."""
    p = _Paquet()
    statuts = [("StatusGroupJellybeans", "StatusItemJellybeans", dragees)]
    for item, valeur in (points or {}).items():
        statuts.append(("StatusGroupHousePoints", item, valeur))
    if etoiles is not None:
        statuts.append(("StatusGroupStars", "StatusItemStars", etoiles))
    props = b""
    for i, (groupe, item, valeur) in enumerate(statuts):
        brut = (_compact(p.importer(groupe)) + _compact(p.importer(item))
                + struct.pack("<iii", valeur, valeur, 600))
        props += p.prop("StatusSave", 10, brut.ljust(16, b"\x00")[:16], i, "StatusSaveData")
    liste = [(n, folio_hp2.HARRY) for n in cartes] + [(n, 2) for n in marchands]
    for i, (n, proprietaire) in enumerate(liste):
        props += p.prop("BronzeCardSave", 10, struct.pack("<ii", n, proprietaire), i,
                        "WCardSaveData")
    props += p.prop("CurrentGameState", 13, _chaine("GSTATE040"))
    p.exporter(p.importer("harry"), "harry0", props + p.fin())
    p.exporter(p.importer("LevelInfo"), "LevelInfo0",
               p.prop("Title", 13, _chaine(titre)) + p.fin())
    return p.octets()


def hgame(cartes: dict[int, tuple[str, str]]) -> bytes:
    """Les classes `WC…` : numéro → (classe, catégorie parente)."""
    p = _Paquet()
    parents = {nom: p.exporter(0, nom, p.fin()) for nom in ("BronzeCards", "SilverCards",
                                                            "Goldcards")}
    for numero, (classe, parent) in cartes.items():
        defauts = (p.prop("Id", 2, struct.pack("<i", numero))
                   + p.prop("strDescriptionId", 13, _chaine(f"WizCard_{numero - 1:04d}"))
                   + p.fin())
        # Le corps d'une classe : du code d'abord, ses valeurs par défaut à la fin.
        p.exporter(0, classe, b"\x07\x07\x07" + defauts, parents[parent])
    return p.octets()


MENU = (
    "[All]\r\n"
    "WizCard_0006=Hesper Starkey (1881 - 1973). Etudia l'influence des phases de la lune.\r\n"
    "WizCard_0099=Harry Potter. Le Survivant.\r\n"
    "Maps_0013=Saule cogneur\r\n"
)
MENU_INT = (
    "[All]\r\n"
    "WizCard_0006=Hesper Starkey 1881-1973 Witch who studied the phases of the moon.\r\n"
    "WizCard_0099=Harry Potter The boy who lived.\r\n"
    "Maps_0013=Whomping Willow\r\n"
)


@pytest.fixture
def hp2(tmp_path, monkeypatch):
    """Un HP2 installé et ses emplacements, dans tmp_path."""
    from src.core import sauvegardes
    from src.core.game_data import GameData
    set_language("fr")
    folio_hp2._catalogue.cache_clear()
    monkeypatch.setattr(sauvegardes, "racines", lambda: {"documents": tmp_path / "Docs"})
    jeu = GameData.from_dict({
        "id": "hp2", "name": "Harry Potter et la Chambre des Secrets", "year": 2002,
        "description": "d", "developer": "d", "executable": "HP2/system/Game.exe",
        "cover_image": "c.jpg",
        "saves": {"root": "documents", "folders": ["Harry Potter II/Save"],
                  "files": "Slot*/Save0.usa", "first": 1}})
    system = tmp_path / "Jeux" / "HP2" / "system"
    system.mkdir(parents=True)
    (system / "HpMenu.fre").write_bytes(MENU.encode("cp1252"))
    (system / "HPMenu.int").write_bytes(MENU_INT.encode("cp1252"))
    (system / "hgame.u").write_bytes(hgame({7: ("WCStarkey", "BronzeCards"),
                                            100: ("WCPotter", "Goldcards")}))
    return jeu, tmp_path / "Jeux", system, tmp_path / "Docs" / "Harry Potter II" / "Save"


def _ecrire(saves, slot: int, contenu: bytes, quand: datetime):
    chemin = saves / f"Slot{slot}" / "Save0.usa"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    os.utime(chemin, (quand.timestamp(), quand.timestamp()))
    return chemin


class TestLire:
    def test_les_compteurs_et_les_cartes(self):
        v = folio_hp2.lire(sauvegarde(
            cartes=(7, 100), marchands=(9,), dragees=126,
            points={"StatusItemGryffindorPts": 155, "StatusItemSlytherinPts": 173}, etoiles=12))
        assert v.cartes == {7, 100} and v.marchands == {9}
        assert v.dragees == 126 and v.etoiles == 12
        assert v.points[folio.GRYFFONDOR] == 155 and v.points[folio.SERPENTARD] == 173
        assert v.points[folio.SERDAIGLE] == 0
        assert (v.histoire, v.titre) == ("GSTATE040", "Whomping Willow")

    def test_une_carte_chez_un_marchand_n_est_pas_a_harry(self):
        """ECardOwner : 1 Harry, 2 un marchand. La sauvegarde de Ludo, au tout
        début, n'avait qu'une carte, chez Fred et George."""
        v = folio_hp2.lire(sauvegarde(marchands=(7,)))
        assert v.cartes == frozenset() and v.marchands == {7}

    def test_sans_etoiles_le_folio_ne_les_invente_pas(self):
        assert folio_hp2.lire(sauvegarde()).etoiles is None

    def test_pas_un_paquet(self):
        assert folio_hp2.lire(b"\x00" * 64) is None


class TestCatalogue:
    def test_categorie_par_classe_parente(self, hp2):
        _, _, system, _ = hp2
        cat = folio_hp2.catalogue(system, "fr")
        assert cat[7].categorie == folio_hp2.BRONZE and cat[100].categorie == folio_hp2.OR
        assert (cat[7].nom, cat[7].dates) == ("Hesper Starkey", "1881 - 1973")
        assert cat[100].nom == "Harry Potter" and cat[100].texte == "Le Survivant."

    def test_en_anglais(self, hp2):
        _, _, system, _ = hp2
        cat = folio_hp2.catalogue(system, "en")
        assert (cat[7].nom, cat[7].dates) == ("Hesper Starkey", "1881-1973")
        assert (cat[100].nom, cat[100].texte) == ("Harry Potter", "The boy who lived.")

    def test_sans_le_jeu(self, tmp_path):
        assert folio_hp2.catalogue(tmp_path, "fr") == {}

    @pytest.mark.parametrize(("brut", "attendu"), [
        ("Queen Maeve Legendary witch.", ("Queen Maeve", "", "Legendary witch.")),
        ("Mirabella Plunkett 1839-unknown Fell in love.", ("Mirabella Plunkett", "1839-unknown",
                                                            "Fell in love.")),
        ("Merlin Medieval, dates unknown Most famous.", ("Merlin", "Medieval, dates unknown",
                                                          "Most famous.")),
    ])
    def test_decouper(self, brut, attendu):
        classe = "WCMaeve" if "Maeve" in brut else "WCX"
        assert folio_hp2.decouper(brut, classe) == attendu

    def test_le_niveau_dans_la_langue_du_launcher(self, hp2):
        _, _, system, _ = hp2
        assert folio_hp2.lieu(system, "fr", "Whomping Willow") == "Saule cogneur"
        assert folio_hp2.lieu(system, "fr", "Inconnu") == "Inconnu"


class TestEmplacements:
    def test_le_numero_vient_du_dossier(self, hp2):
        jeu, _, _, saves = hp2
        _ecrire(saves, 1, sauvegarde(dragees=3), datetime(2026, 3, 8))
        _ecrire(saves, 3, sauvegarde(cartes=(7,)), datetime(2026, 4, 1))
        releves = folio_hp2.emplacements(jeu.sauvegardes)
        assert [r.emplacement for r in releves] == [1, 3]
        assert releves[1].cartes == {7} and releves[0].dragees == 3

    def test_le_resume_de_la_fiche(self, hp2):
        jeu, _, system, saves = hp2
        _ecrire(saves, 1, sauvegarde(cartes=(7, 100)), datetime(2026, 3, 8))
        resume = folio_hp2.resume(jeu.sauvegardes, system, "fr")
        assert (resume.trouvees, resume.total, resume.lieu) == (2, 101, "Saule cogneur")

    def test_rien_n_est_ecrit(self, hp2):
        jeu, _, _, saves = hp2
        chemin = _ecrire(saves, 1, sauvegarde(cartes=(7,)), datetime(2026, 3, 8))
        avant = (chemin.read_bytes(), chemin.stat().st_mtime)
        folio_hp2.emplacements(jeu.sauvegardes)
        assert (chemin.read_bytes(), chemin.stat().st_mtime) == avant


class TestPage:
    def test_trois_categories_et_la_coupe(self, qtbot, hp2):
        from src.ui.folio_jeux import FolioPageHP2, page_folio
        jeu, install, _, saves = hp2
        _ecrire(saves, 1, sauvegarde(cartes=(7,), dragees=40,
                                     points={"StatusItemSlytherinPts": 30}), datetime(2026, 3, 8))
        page = page_folio(jeu, install)
        qtbot.addWidget(page)
        assert isinstance(page, FolioPageHP2)
        assert page.phrase_coupe.text() == "Serpentard mène de 30 points"
        assert page.carte_montree == 7 and page._fiche_nom.text() == "Hesper Starkey"

    def test_une_carte_en_vente_le_dit(self, qtbot, hp2):
        from src.ui.folio_jeux import page_folio
        jeu, install, _, saves = hp2
        _ecrire(saves, 1, sauvegarde(cartes=(100,), marchands=(7,)), datetime(2026, 3, 8))
        page = page_folio(jeu, install)
        qtbot.addWidget(page)
        page._montrer_carte(7)
        assert page._fiche_nom.text() == "Pas encore trouvée"
        assert "marchand la propose" in page._fiche_texte.text()


class TestIcones:
    def test_le_cadre_visible_d_une_icone(self):
        """Une icône au centre de sa texture : on n'en garde que la partie
        visible, sinon un blason de HP2 s'affiche à 40 % de sa taille."""
        from src.core.textures_ue1 import TexturePaletee
        from src.ui.folio_page import cadre_visible
        indices = bytearray(8 * 8)
        for y in range(2, 5):
            for x in range(3, 7):
                indices[y * 8 + x] = 5
        tex = TexturePaletee(8, 8, bytes(indices), ((0, 0, 0, 0),) * 256, True)
        assert cadre_visible(tex) == (3, 2, 4, 3)
        assert cadre_visible(TexturePaletee(8, 8, bytes(64), ((0, 0, 0, 0),) * 256, True)) is None

    def test_sans_le_jeu_pas_d_icone(self, tmp_path):
        assert folio_hp2.image_menu(tmp_path / "system", "HP2CardFolio") is None

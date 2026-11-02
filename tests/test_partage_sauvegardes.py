"""Export d'une sauvegarde en .zip, import d'un .zip ou d'un fichier seul.

Documents et `_Launcher` sont ceux du conftest : aucune vraie sauvegarde n'est
lue ni écrite.
"""
import json
import os
import zipfile
from datetime import datetime

import pytest

from src.core import copies_sauvegardes as cs
from src.core import partage_sauvegardes as ps
from src.core import sauvegardes
from src.core.game_data import Sauvegardes

HP1 = Sauvegardes(racine="documents", dossiers=("Harry Potter/Save",), fichiers="Save*.usa",
                  compagnons=("GameSaveInfo{n}",))
HP2 = Sauvegardes(racine="documents", dossiers=("Harry Potter II/Save",), fichiers="Slot*/Save0.usa",
                  premier=1, compagnons=("*_pa.usa", "Save0.bmp"))
HP6 = Sauvegardes(racine="localappdata", dossiers=("Electronic Arts/HPHBP0",), fichiers="HPHBP0")
T0 = datetime(2026, 10, 21, 12, 17, 38)


def _ecrire(chemin, contenu: bytes, quand: datetime = T0):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    os.utime(chemin, (quand.timestamp(), quand.timestamp()))


@pytest.fixture
def hp2():
    return sauvegardes.racines()["documents"] / "Harry Potter II" / "Save"


class TestExporter:
    def test_la_sauvegarde_ses_compagnons_et_le_manifeste(self, hp2, tmp_path):
        _ecrire(hp2 / "Slot1" / "Save0.usa", b"partie")
        _ecrire(hp2 / "Slot1" / "Grounds_Night_pa.usa", b"zone")
        _ecrire(hp2 / "Slot1" / "Save0.bmp", b"image")
        zip_ = tmp_path / "sortie" / "HP2.zip"
        assert ps.exporter("hp2", HP2, "Slot1/Save0.usa", zip_, "1.2.4")
        with zipfile.ZipFile(zip_) as z:
            assert sorted(z.namelist()) == ["Grounds_Night_pa.usa", "Save0.bmp", "Save0.usa", "accio.json"]
            manifeste = json.loads(z.read("accio.json"))
            assert z.getinfo("Save0.usa").date_time == (2026, 10, 21, 12, 17, 38)
        assert manifeste["jeu"] == "hp2" and manifeste["emplacement"] == "Slot1/Save0.usa"

    def test_une_version_gardee(self, hp2, tmp_path):
        _ecrire(hp2 / "Slot2" / "Save0.usa", b"ancienne")
        cs.avant_partie("hp2", HP2)
        version = cs.versions("hp2")["Slot2/Save0.usa"][0]
        _ecrire(hp2 / "Slot2" / "Save0.usa", b"nouvelle", datetime(2026, 10, 26))
        assert ps.exporter_version("hp2", version, tmp_path / "v.zip")
        with zipfile.ZipFile(tmp_path / "v.zip") as z:
            assert z.read("Save0.usa") == b"ancienne"

    def test_sauvegarde_absente(self, tmp_path):
        assert not ps.exporter("hp6", HP6, "HPHBP0", tmp_path / "x.zip")
        assert not (tmp_path / "x.zip").exists()


class TestLire:
    def test_aller_retour(self, hp2, tmp_path):
        _ecrire(hp2 / "Slot1" / "Save0.usa", b"partie")
        _ecrire(hp2 / "Slot1" / "Adv1Willow_pa.usa", b"zone")
        ps.exporter("hp2", HP2, "Slot1/Save0.usa", tmp_path / "p.zip")
        paquet = ps.lire(tmp_path / "p.zip", HP2)
        assert isinstance(paquet, ps.Paquet)
        assert paquet.jeu == "hp2" and paquet.complet
        assert paquet.principal.donnees == b"partie"
        assert [f.nom for f in paquet.compagnons] == ["Adv1Willow_pa.usa"]

    def test_un_zip_d_ailleurs_dans_un_sous_dossier(self, tmp_path):
        with zipfile.ZipFile(tmp_path / "forum.zip", "w") as z:
            z.writestr("ma partie/Save3.usa", b"x")
            z.writestr("ma partie/GameSaveInfo3", b"i")
            z.writestr("LISEZMOI.txt", b"bonne chance")
        paquet = ps.lire(tmp_path / "forum.zip", HP1)
        assert isinstance(paquet, ps.Paquet)
        assert paquet.jeu is None and not paquet.complet
        assert paquet.principal.nom == "Save3.usa"
        assert [f.nom for f in paquet.compagnons] == ["GameSaveInfo3"]

    def test_refus(self, tmp_path):
        with zipfile.ZipFile(tmp_path / "deux.zip", "w") as z:
            z.writestr("Save0.usa", b"a")
            z.writestr("Save1.usa", b"b")
        assert ps.lire(tmp_path / "deux.zip", HP1) == ps.PLUSIEURS
        with zipfile.ZipFile(tmp_path / "rien.zip", "w") as z:
            z.writestr("photo.png", b"a")
        assert ps.lire(tmp_path / "rien.zip", HP1) == ps.SANS_SAUVEGARDE
        (tmp_path / "notes.txt").write_bytes(b"x")
        assert ps.lire(tmp_path / "notes.txt", HP1) == ps.SANS_SAUVEGARDE
        assert ps.lire(tmp_path / "absent.zip", HP1) == ps.ILLISIBLE
        (tmp_path / "casse.zip").write_bytes(b"PK\x03\x04 pas un zip")
        assert ps.lire(tmp_path / "casse.zip", HP1) in (ps.ILLISIBLE, ps.SANS_SAUVEGARDE)

    def test_un_fichier_seul_renomme_par_le_navigateur(self, tmp_path):
        _ecrire(tmp_path / "HPHBP0 (1)", b"hp6")
        paquet = ps.lire(tmp_path / "HPHBP0 (1)", HP6)
        assert isinstance(paquet, ps.Paquet)
        assert paquet.principal.nom == "HPHBP0" and paquet.principal.donnees == b"hp6"


class TestEmplacements:
    def test_six_au_menu_sans_la_rapide(self, hp2):
        _ecrire(hp2 / "Slot2" / "Save0.usa", b"x")
        rangee = ps.emplacements("hp2", HP2)
        assert [r for r, _ in rangee] == [f"Slot{n}/Save0.usa" for n in range(1, 7)]
        assert [pris for _, pris in rangee] == [False, True, False, False, False, False]
        assert all(r != "Save9.usa" for r, _ in ps.emplacements("hp1", HP1))

    def test_un_seul_pour_hp6(self):
        assert ps.emplacements("hp6", HP6) == [("HPHBP0", False)]


class TestImporter:
    def test_remplace_et_garde_l_ancienne_dans_les_versions(self, hp2, tmp_path):
        _ecrire(hp2 / "Slot1" / "Save0.usa", b"ancienne")
        _ecrire(hp2 / "Slot1" / "Vieille_zone_pa.usa", b"vieille zone")
        with zipfile.ZipFile(tmp_path / "p.zip", "w") as z:
            z.writestr(ps.MANIFESTE, json.dumps({"jeu": "hp2", "sauvegarde": "Save0.usa"}))
            z.writestr("Save0.usa", b"nouvelle")
            z.writestr("Entryhall_hub_pa.usa", b"zone")
        paquet = ps.lire(tmp_path / "p.zip", HP2)
        assert ps.importer("hp2", HP2, paquet, "Slot1/Save0.usa")
        assert (hp2 / "Slot1" / "Save0.usa").read_bytes() == b"nouvelle"
        assert (hp2 / "Slot1" / "Entryhall_hub_pa.usa").read_bytes() == b"zone"
        assert not (hp2 / "Slot1" / "Vieille_zone_pa.usa").exists()   # une autre partie
        gardee = cs.versions("hp2")["Slot1/Save0.usa"]
        assert len(gardee) == 1 and gardee[0].quand == T0

    def test_dans_un_emplacement_libre(self, hp2, tmp_path):
        _ecrire(tmp_path / "Save0.usa", b"partie")
        paquet = ps.lire(tmp_path / "Save0.usa", HP2)
        assert ps.importer("hp2", HP2, paquet, "Slot4/Save0.usa")
        assert (hp2 / "Slot4" / "Save0.usa").read_bytes() == b"partie"
        assert os.path.getmtime(hp2 / "Slot4" / "Save0.usa") == pytest.approx(T0.timestamp())

    def test_fichier_seul_garde_le_resume_d_emplacement(self, tmp_path):
        base = sauvegardes.racines()["documents"] / "Harry Potter" / "Save"
        _ecrire(base / "Save1.usa", b"ancienne")
        _ecrire(base / "GameSaveInfo1", b"resume")
        _ecrire(tmp_path / "Save5.usa", b"nouvelle")
        assert ps.importer("hp1", HP1, ps.lire(tmp_path / "Save5.usa", HP1), "Save1.usa")
        assert (base / "Save1.usa").read_bytes() == b"nouvelle"
        assert (base / "GameSaveInfo1").read_bytes() == b"resume"

    def test_hp1_d_un_autre_emplacement_prend_le_numero_vise(self, tmp_path):
        """Grand audit du 2026-11-02 : un .zip de l'emplacement 3 posé dans le 5
        écrivait `GameSaveInfo3` (le résumé d'une AUTRE partie, écrasé sans copie)
        et effaçait `GameSaveInfo5`, sans le remplacer."""
        base = sauvegardes.racines()["documents"] / "Harry Potter" / "Save"
        _ecrire(base / "Save3.usa", b"partie 3")
        _ecrire(base / "GameSaveInfo3", b"resume 3")
        _ecrire(base / "Save5.usa", b"ancienne 5")
        _ecrire(base / "GameSaveInfo5", b"ancien resume 5")
        with zipfile.ZipFile(tmp_path / "forum.zip", "w") as z:
            z.writestr("Save3.usa", b"importee")
            z.writestr("GameSaveInfo3", b"resume importe")
        assert ps.importer("hp1", HP1, ps.lire(tmp_path / "forum.zip", HP1), "Save5.usa")
        assert (base / "Save5.usa").read_bytes() == b"importee"
        assert (base / "GameSaveInfo5").read_bytes() == b"resume importe"
        assert (base / "GameSaveInfo3").read_bytes() == b"resume 3"

    def test_compagnon_d_une_autre_sauvegarde_pas_pose(self, tmp_path):
        base = sauvegardes.racines()["documents"] / "Harry Potter" / "Save"
        _ecrire(base / "GameSaveInfo7", b"resume 7")
        with zipfile.ZipFile(tmp_path / "melange.zip", "w") as z:
            z.writestr("Save2.usa", b"partie 2")
            z.writestr("GameSaveInfo7", b"intrus")
        assert ps.importer("hp1", HP1, ps.lire(tmp_path / "melange.zip", HP1), "Save4.usa")
        assert (base / "GameSaveInfo7").read_bytes() == b"resume 7"
        assert not (base / "GameSaveInfo4").exists()

    def test_jeu_jamais_lance_cree_son_dossier(self, tmp_path):
        _ecrire(tmp_path / "HPHBP0", b"hp6")
        assert ps.importer("hp6", HP6, ps.lire(tmp_path / "HPHBP0", HP6), "HPHBP0")
        assert (sauvegardes.racines()["localappdata"] / "Electronic Arts" / "HPHBP0" / "HPHBP0").read_bytes() == b"hp6"

    def test_chemin_douteux_refuse(self, tmp_path):
        _ecrire(tmp_path / "HPHBP0", b"hp6")
        paquet = ps.lire(tmp_path / "HPHBP0", HP6)
        assert not ps.importer("hp6", HP6, paquet, "../HPHBP0")
        assert not ps.importer("hp6", HP6, paquet, "C:/HPHBP0")


class TestHP6TroisEmplacements:
    """Catalogue 0.52 : `HPHBP?/HPHBP?`. Sans le « ? » compté comme joker, HP6
    passait pour un jeu à fichier unique et l'import visait un dossier nommé
    « HPHBP? », interdit sous Windows (Firox, Discord, 2026-11-02)."""

    SPEC = Sauvegardes(racine="localappdata", dossiers=("Electronic Arts/HP6",),
                       fichiers="HPHBP?/HPHBP?")

    def test_trois_emplacements_au_menu(self):
        jeu = sauvegardes.racines()["localappdata"] / "Electronic Arts" / "HP6"
        _ecrire(jeu / "HPHBP1" / "HPHBP1", b"x")
        assert ps.a_plusieurs_emplacements(self.SPEC)
        assert ps.emplacements("hp6", self.SPEC) == [
            ("HPHBP0/HPHBP0", False), ("HPHBP1/HPHBP1", True), ("HPHBP2/HPHBP2", False)]

    def test_un_fichier_renomme_va_dans_l_emplacement_choisi(self, tmp_path):
        _ecrire(tmp_path / "HPHBP0 (1)", b"partie de Firox")
        paquet = ps.lire(tmp_path / "HPHBP0 (1)", self.SPEC)
        assert isinstance(paquet, ps.Paquet)
        jeu = sauvegardes.racines()["localappdata"] / "Electronic Arts" / "HP6"
        jeu.mkdir(parents=True)
        assert ps.importer("hp6", self.SPEC, paquet, "HPHBP2/HPHBP2")
        assert (jeu / "HPHBP2" / "HPHBP2").read_bytes() == b"partie de Firox"

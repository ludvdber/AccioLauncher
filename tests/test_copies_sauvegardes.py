"""Copies des sauvegardes avant chaque partie, éclaircissement, retour à une version.

Documents et `_Launcher` sont ceux du conftest : aucune vraie sauvegarde n'est
lue ni écrite.
"""
import gzip
import os
from datetime import datetime, timedelta

import pytest

from src.core import copies_sauvegardes as cs
from src.core import sauvegardes
from src.core.game_data import Sauvegardes

HP2 = Sauvegardes(racine="documents", dossiers=("Harry Potter II/Save",),
                  fichiers="Slot*/Save0.usa", premier=1)
HP5 = Sauvegardes(racine="localappdata", dossiers=("Electronic Arts/HPOOTP",),
                  fichiers="HPOOTP")


def _ecrire(chemin, contenu: bytes, quand: datetime):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    os.utime(chemin, (quand.timestamp(), quand.timestamp()))


@pytest.fixture
def save_dir():
    return sauvegardes.racines()["documents"] / "Harry Potter II" / "Save"


T0 = datetime(2026, 10, 1, 20, 15, 0)


class TestCopier:
    def test_une_copie_par_version_pas_une_par_lancement(self, save_dir):
        _ecrire(save_dir / "Slot1" / "Save0.usa", b"partie A" * 1000, T0)
        assert cs.avant_partie("hp2", HP2) == 1
        assert cs.avant_partie("hp2", HP2) == 0          # rien n'a changé
        versions = cs.versions("hp2")["Slot1/Save0.usa"]
        assert [v.quand for v in versions] == [T0]
        with gzip.open(versions[0].chemin, "rb") as gz:
            assert gz.read() == b"partie A" * 1000
        assert versions[0].taille < 8000                 # compressée

    def test_une_nouvelle_version_ajoute_une_copie(self, save_dir):
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"A", T0)
        cs.avant_partie("hp2", HP2)
        _ecrire(save, b"B", T0 + timedelta(hours=2))
        assert cs.avant_partie("hp2", HP2) == 1
        assert len(cs.versions("hp2")["Slot1/Save0.usa"]) == 2

    def test_plusieurs_emplacements(self, save_dir):
        _ecrire(save_dir / "Slot1" / "Save0.usa", b"un", T0)
        _ecrire(save_dir / "Slot3" / "Save0.usa", b"trois", T0)
        cs.avant_partie("hp2", HP2)
        assert set(cs.versions("hp2")) == {"Slot1/Save0.usa", "Slot3/Save0.usa"}

    def test_une_sauvegarde_reecrite_pendant_la_copie_n_est_pas_gardee(self, save_dir, monkeypatch):
        """Le jeu peut écrire pendant qu'on lit : une copie à moitié vaut moins que rien."""
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"avant", T0)
        vraie = cs.shutil.copyfileobj

        def ecrit_pendant(src, dst, n):
            vraie(src, dst, n)
            _ecrire(save, b"pendant", T0 + timedelta(seconds=30))
        monkeypatch.setattr(cs.shutil, "copyfileobj", ecrit_pendant)
        assert cs.avant_partie("hp2", HP2) == 0
        assert cs.versions("hp2") == {}
        assert not list(cs.racine().rglob("*.tmp"))     # le temporaire est parti

    def test_jeu_sans_sauvegardes_declarees(self):
        assert cs.avant_partie("hp8", None) == 0


class TestCalendrier:
    MAINTENANT = datetime(2026, 10, 3, 12, 0, 0)

    def test_les_cinq_dernieres_toujours(self):
        dates = [self.MAINTENANT - timedelta(minutes=10 * i) for i in range(8)]
        garde = cs.a_garder(dates, self.MAINTENANT)
        assert set(dates[:5]) <= garde

    def test_une_par_jour_sur_deux_semaines_puis_une_par_mois_puis_une_par_an(self):
        dates = [self.MAINTENANT - timedelta(hours=6 * i) for i in range(4 * 800)]
        garde = cs.a_garder(dates, self.MAINTENANT)
        jours = {d.date() for d in garde if (self.MAINTENANT - d).days < cs.JOURS}
        assert len(jours) >= cs.JOURS                    # chaque jour récent a la sienne
        anciennes = [d for d in garde if (self.MAINTENANT - d).days > 400]
        assert len({d.year for d in anciennes}) == len(anciennes)   # une par an au-delà
        assert len(garde) < 60                           # borné, pas 3 200

    def test_la_plus_recente_de_chaque_jour_est_celle_gardee(self):
        matin = datetime(2026, 9, 10, 9, 0)
        soir = datetime(2026, 9, 10, 22, 0)
        recentes = [self.MAINTENANT - timedelta(minutes=i) for i in range(5)]
        garde = cs.a_garder([matin, soir, *recentes], self.MAINTENANT)
        assert soir in garde and matin not in garde

    def test_eclaircir_n_efface_que_nos_copies(self, tmp_path):
        dossier = tmp_path / "copies"
        dossier.mkdir()
        for i in range(30):
            (dossier / (datetime(2024, 1, 1) + timedelta(hours=i)).strftime("%Y-%m-%d_%H%M%S.gz")).write_bytes(b"x")
        (dossier / "note.txt").write_bytes(b"a moi")
        (dossier / "2024-01-01_000000.gz.bak").write_bytes(b"a moi aussi")
        effacees = cs.eclaircir(dossier, self.MAINTENANT, original_present=True)
        assert effacees == 30 - 5
        assert (dossier / "note.txt").exists() and (dossier / "2024-01-01_000000.gz.bak").exists()

    def test_sans_original_rien_n_est_efface(self, tmp_path):
        """Une sauvegarde effacée dans le jeu : ses copies sont tout ce qui reste d'elle."""
        dossier = tmp_path / "copies"
        dossier.mkdir()
        for i in range(30):
            (dossier / (datetime(2024, 1, 1) + timedelta(hours=i)).strftime("%Y-%m-%d_%H%M%S.gz")).write_bytes(b"x")
        assert cs.eclaircir(dossier, self.MAINTENANT, original_present=False) == 0
        assert len(list(dossier.iterdir())) == 30

    def test_une_sauvegarde_disparue_garde_ses_copies_au_lancement(self, save_dir):
        save = save_dir / "Slot2" / "Save0.usa"
        for i in range(8):
            _ecrire(save, bytes([i]), T0 - timedelta(days=400 + i))
            cs.avant_partie("hp2", HP2)
        avant = len(cs.versions("hp2")["Slot2/Save0.usa"])
        save.unlink()
        _ecrire(save_dir / "Slot1" / "Save0.usa", b"autre", T0)
        cs.avant_partie("hp2", HP2)
        assert len(cs.versions("hp2")["Slot2/Save0.usa"]) == avant


class TestRevenir:
    def test_revenir_garde_d_abord_le_present(self, save_dir):
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"hier", T0)
        cs.avant_partie("hp2", HP2)
        _ecrire(save, b"aujourd'hui, abimee", T0 + timedelta(days=1))   # jamais copiée
        hier = cs.versions("hp2")["Slot1/Save0.usa"][-1]
        assert cs.revenir("hp2", HP2, hier)
        assert save.read_bytes() == b"hier"
        assert datetime.fromtimestamp(save.stat().st_mtime) == T0       # sa vraie date
        # Le présent a été copié avant : on peut y revenir.
        present = cs.versions("hp2")["Slot1/Save0.usa"][0]
        assert present.quand == T0 + timedelta(days=1)
        assert cs.revenir("hp2", HP2, present)
        assert save.read_bytes() == b"aujourd'hui, abimee"

    def test_sans_copie_du_present_rien_n_est_remplace(self, save_dir, monkeypatch):
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"hier", T0)
        cs.avant_partie("hp2", HP2)
        _ecrire(save, b"present", T0 + timedelta(days=1))
        hier = cs.versions("hp2")["Slot1/Save0.usa"][0]
        monkeypatch.setattr(cs, "_copier", lambda *_a: (None, False))
        assert not cs.revenir("hp2", HP2, hier)
        assert save.read_bytes() == b"present"

    def test_une_sauvegarde_effacee_peut_revenir(self, save_dir):
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"seule trace", T0)
        cs.avant_partie("hp2", HP2)
        save.unlink()
        assert cs.revenir("hp2", HP2, cs.versions("hp2")["Slot1/Save0.usa"][0])
        assert save.read_bytes() == b"seule trace"

    @pytest.mark.skipif(os.name != "posix", reason="droits POSIX")
    def test_la_sauvegarde_remise_garde_des_droits_ordinaires(self, save_dir):
        """rw------- après une restauration (Bazzite, 2026-10-20) : le
        fichier temporaire de mkstemp donnait ses droits à la sauvegarde."""
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"hier", T0)
        os.chmod(save, 0o664)
        cs.avant_partie("hp2", HP2)
        assert cs.revenir("hp2", HP2, cs.versions("hp2")["Slot1/Save0.usa"][0])
        assert save.stat().st_mode & 0o777 == 0o664
        save.unlink()
        assert cs.revenir("hp2", HP2, cs.versions("hp2")["Slot1/Save0.usa"][0])
        assert save.stat().st_mode & 0o777 == 0o644

    def test_la_sauvegarde_remise_reste_modifiable(self, save_dir):
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"hier", T0)
        cs.avant_partie("hp2", HP2)
        save.unlink()
        assert cs.revenir("hp2", HP2, cs.versions("hp2")["Slot1/Save0.usa"][0])
        assert os.access(save, os.W_OK)


HP2_AVEC = Sauvegardes(racine="documents", dossiers=("Harry Potter II/Save",),
                       fichiers="Slot*/Save0.usa", premier=1,
                       compagnons=("*_pa.usa", "Save0.bmp"))
HP1_AVEC = Sauvegardes(racine="documents", dossiers=("Harry Potter/Save",),
                       fichiers="Save*.usa", compagnons=("GameSaveInfo{n}",))


class TestCompagnons:
    """Les états de zone de HP2 et le `GameSaveInfoN` de HP1 vont avec leur sauvegarde."""

    def test_copies_et_remis_avec_la_sauvegarde(self, save_dir):
        slot = save_dir / "Slot1"
        _ecrire(slot / "Save0.usa", b"partie A", T0)
        _ecrire(slot / "Grounds_pa.usa", b"zone A", T0 - timedelta(minutes=5))
        assert cs.avant_partie("hp2", HP2_AVEC) == 1
        # La partie continue : la zone change, une autre zone apparaît.
        _ecrire(slot / "Save0.usa", b"partie B", T0 + timedelta(hours=1))
        _ecrire(slot / "Grounds_pa.usa", b"zone B", T0 + timedelta(hours=1))
        _ecrire(slot / "Willow_pa.usa", b"zone neuve", T0 + timedelta(hours=1))
        avant = cs.versions("hp2")["Slot1/Save0.usa"][-1]
        assert cs.revenir("hp2", HP2_AVEC, avant)
        assert (slot / "Save0.usa").read_bytes() == b"partie A"
        assert (slot / "Grounds_pa.usa").read_bytes() == b"zone A"
        assert not (slot / "Willow_pa.usa").exists()     # visitée après cette version
        # Le présent est revenu en entier.
        present = cs.versions("hp2")["Slot1/Save0.usa"][0]
        assert cs.revenir("hp2", HP2_AVEC, present)
        assert (slot / "Grounds_pa.usa").read_bytes() == b"zone B"
        assert (slot / "Willow_pa.usa").read_bytes() == b"zone neuve"

    def test_la_version_prend_la_date_du_plus_recent(self, save_dir):
        slot = save_dir / "Slot1"
        _ecrire(slot / "Save0.usa", b"A", T0)
        _ecrire(slot / "Grounds_pa.usa", b"z", T0 + timedelta(seconds=40))
        cs.avant_partie("hp2", HP2_AVEC)
        assert [v.quand for v in cs.versions("hp2")["Slot1/Save0.usa"]] == \
            [T0 + timedelta(seconds=40)]

    def test_une_version_d_avant_les_compagnons_les_recoit(self, save_dir):
        slot = save_dir / "Slot1"
        _ecrire(slot / "Save0.usa", b"A", T0)
        _ecrire(slot / "Grounds_pa.usa", b"z", T0)
        cs.avant_partie("hp2", HP2)                      # launcher d'avant
        assert cs.avant_partie("hp2", HP2_AVEC) == 1     # complétée, pas doublée
        versions = cs.versions("hp2")["Slot1/Save0.usa"]
        assert len(versions) == 1
        assert (versions[0].chemin.parent / "2026-10-01_201500" / "Grounds_pa.usa.gz").is_file()

    def test_une_version_d_avant_ne_retire_rien(self, save_dir):
        slot = save_dir / "Slot1"
        _ecrire(slot / "Save0.usa", b"A", T0)
        cs.avant_partie("hp2", HP2)
        _ecrire(slot / "Save0.usa", b"B", T0 + timedelta(hours=1))
        _ecrire(slot / "Grounds_pa.usa", b"z", T0 + timedelta(hours=1))
        assert cs.revenir("hp2", HP2_AVEC, cs.versions("hp2")["Slot1/Save0.usa"][-1])
        assert (slot / "Save0.usa").read_bytes() == b"A"
        assert (slot / "Grounds_pa.usa").read_bytes() == b"z"

    def test_le_numero_choisit_le_compagnon(self, tmp_path):
        save = tmp_path / "Save2.usa"
        for nom in ("Save2.usa", "GameSaveInfo2", "GameSaveInfo0", "Save0.usa"):
            (tmp_path / nom).write_bytes(b"x")
        assert [p.name for p in cs.compagnons(save, HP1_AVEC)] == ["GameSaveInfo2"]

    def test_eclaircir_emporte_les_compagnons(self, tmp_path):
        maintenant = datetime(2026, 10, 3, 12, 0, 0)
        for i in range(8):
            stamp = (maintenant - timedelta(minutes=i)).strftime(cs._FORMAT)
            (tmp_path / f"{stamp}.gz").write_bytes(b"x")
            (tmp_path / stamp).mkdir()
            (tmp_path / stamp / "Grounds_pa.usa.gz").write_bytes(b"x")
        assert cs.eclaircir(tmp_path, maintenant, original_present=True) == 3
        assert len(list(tmp_path.glob("*.gz"))) == len([p for p in tmp_path.iterdir() if p.is_dir()])

    def test_taille_compte_les_compagnons(self, save_dir):
        slot = save_dir / "Slot1"
        _ecrire(slot / "Save0.usa", b"A", T0)
        cs.avant_partie("hp2", HP2)
        seule = cs.versions("hp2")["Slot1/Save0.usa"][0].taille
        _ecrire(slot / "Grounds_pa.usa", os.urandom(4000), T0)
        cs.avant_partie("hp2", HP2_AVEC)
        assert cs.versions("hp2")["Slot1/Save0.usa"][0].taille > seule + 3000


class TestLancement:
    def test_launch_game_lance_la_copie_avant_le_jeu(self):
        """Câblage : la copie part AVANT le processus du jeu, et suit le réglage."""
        import inspect
        from src.core import game_manager as gm
        source = inspect.getsource(gm.GameManager.launch_game)
        assert "copies_sauvegardes.avant_partie" in source
        assert source.index("copies_sauvegardes.avant_partie") < source.index("subprocess.Popen(")
        assert "self.config.copies_sauvegardes" in source


class TestFenetre:
    def test_lister_et_remettre(self, qtbot, save_dir, monkeypatch):
        from src.ui import copies_dialog as cd
        from src.core.game_data import GameData
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"hier", T0)
        cs.avant_partie("hp2", HP2)
        _ecrire(save, b"aujourd'hui", T0 + timedelta(days=1))
        cs.avant_partie("hp2", HP2)
        game = GameData(id="hp2", name="Harry Potter II", year=2002, description="",
                        developer="", executable="HP2/system/Game.exe", cover_image="",
                        latest_version="1.0", recommended_version="1.0", sauvegardes=HP2)
        dlg = cd.CopiesDialog(game)
        qtbot.addWidget(dlg)
        # En tête, la sauvegarde telle qu'elle est : elle s'exporte, ne se « remet » pas.
        assert dlg._liste.count() == 3
        assert dlg._liste.item(0).text().startswith("Telle qu'elle est maintenant")
        assert not dlg._bouton.isEnabled() and dlg._exporter_bouton.isEnabled()
        assert dlg._liste.item(1).text().endswith("(la plus récente)")
        questions = []
        monkeypatch.setattr(dlg, "_boite", lambda *a, **k: questions.append(a[1:3]) or 0)
        dlg._liste.setCurrentRow(2)
        dlg._remettre()
        assert save.read_bytes() == b"hier"
        titre, texte = questions[0]
        assert titre == "Remettre cette version"
        # L'emplacement est nommé, et la version datée à la minute.
        assert texte.startswith("« Emplacement 1 » va revenir à sa version du ")
        assert "20:15" in texte

    def test_refuse_pendant_une_partie(self, qtbot, save_dir, monkeypatch):
        from src.ui import copies_dialog as cd
        from src.core.game_data import GameData
        save = save_dir / "Slot1" / "Save0.usa"
        _ecrire(save, b"hier", T0)
        cs.avant_partie("hp2", HP2)
        _ecrire(save, b"en cours", T0 + timedelta(days=1))
        game = GameData(id="hp2", name="Harry Potter II", year=2002, description="",
                        developer="", executable="HP2/system/Game.exe", cover_image="",
                        latest_version="1.0", recommended_version="1.0", sauvegardes=HP2)
        dlg = cd.CopiesDialog(game, partie_en_cours=lambda: "Harry Potter II")
        qtbot.addWidget(dlg)
        titres = []
        monkeypatch.setattr(dlg, "_boite", lambda *a, **k: titres.append(a[1]) or 0)
        dlg._liste.setCurrentRow(1)
        dlg._remettre()
        dlg._importer()
        assert titres == ["Partie en cours", "Partie en cours"]
        assert save.read_bytes() == b"en cours"

    def _jeu(self):
        from src.core.game_data import GameData
        return GameData(id="hp2", name="Harry Potter II", year=2002, description="",
                        developer="", executable="HP2/system/Game.exe", cover_image="",
                        latest_version="1.0", recommended_version="1.0", sauvegardes=HP2)

    def test_exporter_puis_importer_dans_un_emplacement_libre(self, qtbot, save_dir, monkeypatch, tmp_path):
        from src.ui import copies_dialog as cd
        _ecrire(save_dir / "Slot1" / "Save0.usa", b"partie", T0)
        dlg = cd.CopiesDialog(self._jeu())
        qtbot.addWidget(dlg)
        titres = []
        monkeypatch.setattr(dlg, "_boite", lambda *a, **k: titres.append(a[1]) or 1)
        zip_ = tmp_path / "partage.zip"
        monkeypatch.setattr(cd.QFileDialog, "getSaveFileName", lambda *a: (str(zip_), ""))
        dlg._exporter()
        assert zip_.is_file() and titres == ["Sauvegarde exportée"]
        # Import : un emplacement libre est proposé d'abord, sans question.
        monkeypatch.setattr(cd.QFileDialog, "getOpenFileName", lambda *a: (str(zip_), ""))
        monkeypatch.setattr(cd._ChoixEmplacement, "exec", lambda self: cd.QDialog.DialogCode.Accepted)
        dlg._importer()
        assert (save_dir / "Slot2" / "Save0.usa").read_bytes() == b"partie"
        assert titres[-1] == "Sauvegarde importée"

    def test_importer_le_fichier_d_un_autre_jeu(self, qtbot, save_dir, monkeypatch, tmp_path):
        import json
        import zipfile
        from src.ui import copies_dialog as cd
        with zipfile.ZipFile(tmp_path / "hp1.zip", "w") as z:
            z.writestr("accio.json", json.dumps({"jeu": "hp1", "sauvegarde": "Save0.usa"}))
            z.writestr("Save0.usa", b"hp1")
        dlg = cd.CopiesDialog(self._jeu())
        qtbot.addWidget(dlg)
        textes = []
        monkeypatch.setattr(dlg, "_boite", lambda *a, **k: textes.append(a[2]) or 1)
        monkeypatch.setattr(cd.QFileDialog, "getOpenFileName", lambda *a: (str(tmp_path / "hp1.zip"), ""))
        dlg._importer()
        assert textes == ["Cette sauvegarde vient d'un autre jeu."]
        assert not (save_dir / "Slot1").exists()

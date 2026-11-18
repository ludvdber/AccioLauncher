"""Le folio de HP7 et HP8 sur des `auto.sav` FABRIQUÉS ici, sur le modèle relevé
le 2026-10-16 dans les deux sauvegardes de Ludo (aucune donnée du jeu)."""
import struct
from datetime import datetime

from src.core import folio_hp7
from src.core.i18n import set_language

NOMS = ["LastSaveCheckpoint", "Completed_ns01", "Completed_ns02", "Completed_ns04",
        "PlayerLevel", "KillCount", "HeadShotCount", "PlayerMaxHealth"]


def auto_sav(valeurs: dict[str, float], noms=NOMS) -> bytes:
    """En-tête, table de noms, puis les valeurs typées (et une chaîne vide)."""
    entete = b"\x71\xb1\x44\x39" + b"\x00" * 24 + b"bu_theburrow\x00".ljust(64, b"\x00")
    table = struct.pack("<ii", len(noms), 0)
    for k, nom in enumerate(noms):
        table += nom.encode() + b"\x00"
        if k < len(noms) - 1:
            table += struct.pack("<i", k + 1)
    corps = b"STRING_\x00" + struct.pack("<i", 0) + b"\x00"
    for nom, v in valeurs.items():
        if isinstance(v, float):
            corps += b"F32____\x00" + struct.pack("<if", NOMS.index(nom), v)
        else:
            corps += b"S32____\x00" + struct.pack("<ii", NOMS.index(nom), v)
    return entete + table + corps + b"\x00" * 32


class TestLire:
    def test_les_valeurs_par_nom(self):
        valeurs, missions = folio_hp7.lire(auto_sav(
            {"Completed_ns02": 1, "PlayerLevel": 3, "KillCount": 40, "PlayerMaxHealth": 450.0}))
        assert valeurs["KillCount"] == 40 and valeurs["PlayerLevel"] == 3
        assert valeurs["PlayerMaxHealth"] == 450.0
        assert missions == ("Completed_ns01", "Completed_ns02", "Completed_ns04")

    def test_sans_table_de_noms(self):
        assert folio_hp7.lire(b"\x00" * 200) is None

    def test_une_table_absurde(self):
        brut = bytearray(auto_sav({}))
        debut = brut.find(b"LastSaveCheckpoint")
        struct.pack_into("<i", brut, debut - 8, 10**6)
        assert folio_hp7.lire(bytes(brut)) is None


class TestPartie:
    def test_missions_et_combats(self, tmp_path):
        chemin = tmp_path / "auto.sav"
        chemin.write_bytes(auto_sav({"Completed_ns01": 1, "Completed_ns04": 1, "KillCount": 12}))
        p = folio_hp7.releve(chemin)
        assert p.lu and p.missions_terminees == 2 and len(p.missions) == 3
        assert p.entier("KillCount") == 12 and p.entier("HeadShotCount") == 0
        assert p.entier("DemKillCount") is None, "HP8 n'a pas ce compteur : pas de zéro inventé"

    def test_un_reel_nan_ou_infini_ne_fait_pas_tomber_la_page(self, tmp_path):
        """Audit du 2026-11-16 : `int(nan)` et `int(inf)` levaient."""
        p = folio_hp7.Partie(tmp_path / "auto.sav", None,
                             valeurs={"KillCount": float("nan"), "HeadShotCount": float("inf")})
        assert p.entier("KillCount") == 0 and p.entier("HeadShotCount") == 0

    def test_rien_n_est_ecrit(self, tmp_path):
        chemin = tmp_path / "auto.sav"
        chemin.write_bytes(auto_sav({"KillCount": 1}))
        avant = (chemin.read_bytes(), chemin.stat().st_mtime)
        folio_hp7.releve(chemin)
        assert (chemin.read_bytes(), chemin.stat().st_mtime) == avant


class TestPage:
    def test_la_page_des_reliques(self, qtbot, tmp_path, monkeypatch):
        from PyQt6.QtWidgets import QLabel
        from src.core import sauvegardes
        from src.core.game_data import GameData
        from src.ui.folio_jeux import FolioPageHP7, page_folio
        set_language("fr")
        monkeypatch.setattr(sauvegardes, "racines", lambda: {"localappdata": tmp_path / "App"})
        dossier = tmp_path / "App" / "Electronic Arts" / "Harry Potter Premiere Partie"
        dossier.mkdir(parents=True)
        (dossier / "auto.sav").write_bytes(auto_sav({"Completed_ns01": 1, "PlayerLevel": 2,
                                                     "KillCount": 40}))
        jeu = GameData.from_dict({
            "id": "hp7a", "name": "HP7", "year": 2010, "description": "d", "developer": "d",
            "executable": "HP7/pc/hp7.exe", "cover_image": "c.jpg",
            "saves": {"root": "localappdata", "folders": ["Electronic Arts/Harry Potter*Partie"],
                      "files": "auto.sav"}})
        page = page_folio(jeu, tmp_path / "Jeux")
        qtbot.addWidget(page)
        assert isinstance(page, FolioPageHP7)
        textes = [lbl.text() for lbl in page.findChildren(QLabel)]
        assert "1 / 3" in textes and "Missions annexes terminées" in textes
        assert "Ennemis vaincus" in textes and "40" in textes
        assert page.releve.ecrite <= datetime.now()


class TestEncadreDeLaFiche:
    """Ludo, 2026-11-15 : HP7 et HP8 ont « leur encadré de folio et pas juste un bouton
    folio souligné »."""

    def test_missions_annexes_et_niveau(self, tmp_path):
        from src.core import folio
        from src.ui.resume_partie import lieu_resume, phrase_resume
        set_language("fr")
        chemin = tmp_path / "auto.sav"
        chemin.write_bytes(auto_sav({"Completed_ns01": 1, "PlayerLevel": 4}))
        resume = folio_hp7.resume({"auto.sav": chemin})
        assert "hp7a" in folio.FICHES and "hp7b" in folio.FICHES
        assert (resume.trouvees, resume.total, resume.unite) == (1, 3, "missions")
        assert phrase_resume(resume) == "1 mission annexe sur 3"
        assert lieu_resume(resume) == "Niveau 4"

    def test_sans_partie_lisible_la_description_reste(self, tmp_path):
        chemin = tmp_path / "auto.sav"
        chemin.write_bytes(b"\x00" * 200)
        assert folio_hp7.resume({"auto.sav": chemin}) is None
        assert folio_hp7.resume({}) is None

"""Succès lus dans les sauvegardes : définitions, datation au retour de partie, fichier, page et toast."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import folio, succes

JEUX = ("hp1", "hp2", "hp3", "hp4", "hp5", "hp6")
FIN = datetime(2026, 10, 24, 21, 30)


@pytest.fixture
def fichier(tmp_path) -> Path:
    return tmp_path / "succes.json"


@pytest.fixture
def porte(monkeypatch):
    """Ce que « porte » la sauvegarde, sans fichier de jeu : evaluer est remplacé."""
    etat: dict[str, set[str] | None] = {}
    monkeypatch.setattr(succes, "evaluer", lambda jeu, spec, rel: etat.get(rel))
    return etat


class TestDefinitions:
    def test_chaque_jeu_lu_par_le_folio_a_ses_succes_aux_identifiants_uniques(self):
        for jeu in JEUX:
            idents = [s.ident for s in succes.du_jeu(jeu)]
            assert idents and len(idents) == len(set(idents)), jeu

    def test_un_jeu_sans_lecteur_n_en_a_aucun(self):
        """Jamais de succès sans ce qu'une sauvegarde prouve (HP7 : pas confronté au jeu)."""
        assert succes.du_jeu("hp7a") == () and succes.du_jeu("inconnu") == ()

    def test_chaque_texte_est_traduit(self):
        textes = {"{} sur {}", "Succès dans {} : {}", "{} succès dans {} :", "et {} autres"}
        for jeu in JEUX:
            textes |= {t for s in succes.du_jeu(jeu) for t in (s.titre, s.description)}
        for code in ("en", "es"):
            cles = json.loads(Path(f"src/data/i18n/{code}.json").read_text(encoding="utf-8"))["strings"]
            assert not sorted(t for t in textes if t not in cles), code

    def test_hp1_cartes_et_maisons(self):
        defs = {s.ident: s for s in succes.du_jeu("hp1")}
        r = SimpleNamespace(cartes=frozenset(range(1, 14)),
                            points={folio.GRYFFONDOR: 185, folio.SERPENTARD: 222,
                                    folio.SERDAIGLE: 164, folio.POUFSOUFFLE: 104})
        obtenus = {i for i, s in defs.items() if s.obtenu(r)}
        # Relevé de Ludo, 2026-10-24 : Serpentard devant, Gryffondor au-delà de 100.
        assert obtenus == {"carte", "cartes_13", "points_100"}

    def test_hp6_badges_sans_total_ne_comptent_pas_comme_tous(self):
        tous = next(s for s in succes.du_jeu("hp6") if s.ident == "badges")
        assert not tous.obtenu(SimpleNamespace(badges=0, badges_total=0))
        assert tous.obtenu(SimpleNamespace(badges=30, badges_total=30))

    def test_hp5_une_ligne_pleine_par_compteur(self):
        from src.core import folio_hp5
        lignes = [s for s in succes.du_jeu("hp5") if s.ident.startswith("complet_")]
        assert len(lignes) == len(folio_hp5.COMPTEURS)
        fantomes = next(s for s, c in zip(lignes, folio_hp5.COMPTEURS, strict=False) if c.libelle == "Fantômes")
        compteurs = [0] * len(folio_hp5.COMPTEURS)
        compteurs[[c.libelle for c in folio_hp5.COMPTEURS].index("Fantômes")] = 4
        assert fantomes.obtenu(SimpleNamespace(compteurs=tuple(compteurs)))
        assert not fantomes.obtenu(SimpleNamespace(compteurs=None))

    def test_une_condition_qui_casse_ne_fait_pas_tomber_les_autres(self, monkeypatch, tmp_path):
        """Un champ absent (lecteur changé) : ce succès n'est pas accordé, les autres si."""
        monkeypatch.setattr("src.core.progression.cible", lambda spec, rel: (tmp_path / "x", 1))
        monkeypatch.setattr(succes, "_partie", lambda jeu, chemin, n: SimpleNamespace(cartes=frozenset({1})))
        assert succes.evaluer("hp1", None, "Save0.usa") == {"carte"}


class TestConstater:
    def test_premier_regard_sur_une_vieille_sauvegarde_sans_date_et_sans_annonce(self, porte, fichier):
        porte["Save0.usa"] = {"carte", "points_100"}
        assert succes.constater("hp1", None, "Save0.usa", FIN, nee=False, chemin=fichier) == []
        assert succes.charger(fichier) == {("hp1", "Save0.usa"): {"carte": None, "points_100": None}}

    def test_ensuite_ce_qui_tombe_est_date_et_annonce(self, porte, fichier):
        porte["Save0.usa"] = {"carte"}
        succes.constater("hp1", None, "Save0.usa", FIN, nee=False, chemin=fichier)
        porte["Save0.usa"] = {"carte", "cartes_13"}
        nouveaux = succes.constater("hp1", None, "Save0.usa", FIN, nee=False, chemin=fichier)
        assert [s.ident for s in nouveaux] == ["cartes_13"]
        assert succes.charger(fichier)[("hp1", "Save0.usa")] == {"carte": None, "cartes_13": FIN}
        assert succes.constater("hp1", None, "Save0.usa", FIN, nee=False, chemin=fichier) == []

    def test_une_sauvegarde_nee_pendant_la_partie_date_ce_qu_elle_porte(self, porte, fichier):
        porte["Save1.usa"] = {"carte"}
        nouveaux = succes.constater("hp1", None, "Save1.usa", FIN, nee=True, chemin=fichier)
        assert [s.ident for s in nouveaux] == ["carte"]
        assert succes.charger(fichier)[("hp1", "Save1.usa")] == {"carte": FIN}

    def test_regardee_vide_puis_premier_succes_date(self, porte, fichier):
        """Sans la liste des regardées, ce premier succès serait noté « sans date »."""
        porte["Save0.usa"] = set()
        succes.constater("hp1", None, "Save0.usa", FIN, nee=False, chemin=fichier)
        assert succes.charger(fichier) == {("hp1", "Save0.usa"): {}}
        porte["Save0.usa"] = {"carte"}
        assert [s.ident for s in succes.constater("hp1", None, "Save0.usa", FIN, nee=False,
                                                  chemin=fichier)] == ["carte"]

    def test_illisible_rien_n_est_conclu(self, porte, fichier):
        porte["Save0.usa"] = None
        assert succes.constater("hp1", None, "Save0.usa", FIN, nee=True, chemin=fichier) == []
        assert not fichier.exists()

    def test_un_fichier_illisible_est_mis_de_cote(self, fichier):
        fichier.write_text("{pas du json", encoding="utf-8")
        assert succes.charger(fichier) == {}
        assert fichier.with_suffix(".corrompu").exists()

    def test_aller_retour_du_fichier(self, porte, fichier):
        porte["HPGOF#2"] = {"carte"}
        succes.constater("hp4", None, "HPGOF#2", FIN, nee=True, chemin=fichier)
        brut = json.loads(fichier.read_text(encoding="utf-8"))
        assert brut["obtenus"] == [{"jeu": "hp4", "sauvegarde": "HPGOF#2", "succes": "carte",
                                    "date": "2026-10-24T21:30:00"}]


class TestObtenus:
    def test_la_premiere_fois_datee_passe_devant(self, porte):
        stock = {("hp1", "Save0.usa"): {"carte": datetime(2026, 10, 20)},
                 ("hp1", "Save1.usa"): {"carte": datetime(2026, 10, 10)},
                 ("hp1", "Save2.usa"): {"carte": None},
                 ("hp2", "Slot1/Save0.usa"): {"carte": FIN}}
        vus = succes.obtenus("hp1", [], None, stock)
        assert vus["carte"].date == datetime(2026, 10, 10) and vus["carte"].sauvegarde == "Save1.usa"

    def test_ce_que_portent_les_sauvegardes_compte_meme_jamais_note(self, porte):
        porte["Save0.usa"] = {"points_100"}
        vus = succes.obtenus("hp1", ["Save0.usa"], None, {})
        assert set(vus) == {"points_100"} and vus["points_100"].date is None

    def test_un_succes_retire_d_une_version_est_ignore(self, porte):
        assert succes.obtenus("hp1", [], None, {("hp1", "Save0.usa"): {"disparu": FIN}}) == {}


class TestRecommencer:
    """« Recommencer les défis » (Ludo, 2026-10-27) : un jeu repart de zéro."""

    def test_oublie_ce_jeu_seulement_et_garde_la_date(self, porte, fichier):
        porte["Save0.usa"] = {"carte"}
        succes.constater("hp1", None, "Save0.usa", FIN, nee=True, chemin=fichier)
        porte["Slot1/Save0.usa"] = {"carte"}
        succes.constater("hp2", None, "Slot1/Save0.usa", FIN, nee=True, chemin=fichier)
        succes.recommencer("hp1", datetime(2026, 10, 27, 12), chemin=fichier)
        assert set(succes.charger(fichier)) == {("hp2", "Slot1/Save0.usa")}
        assert succes.remises(fichier) == {"hp1": datetime(2026, 10, 27, 12)}
        # Une écriture suivante garde la remise.
        porte["Slot2/Save0.usa"] = {"carte"}
        succes.constater("hp2", None, "Slot2/Save0.usa", FIN, nee=True, chemin=fichier)
        assert "hp1" in succes.remises(fichier)

    def test_une_partie_d_avant_la_remise_ne_redonne_rien(self, porte, monkeypatch, tmp_path):
        import os
        vieille, neuve = tmp_path / "Save0.usa", tmp_path / "Save1.usa"
        for f in (vieille, neuve):
            f.write_bytes(b"x")
        os.utime(vieille, (datetime(2026, 10, 1).timestamp(),) * 2)
        os.utime(neuve, (datetime(2026, 10, 28).timestamp(),) * 2)
        from src.core import progression
        monkeypatch.setattr(progression, "cible", lambda spec, rel: (tmp_path / rel, 1))
        monkeypatch.setattr(succes, "remises", lambda chemin=None: {"hp1": datetime(2026, 10, 27)})
        porte["Save0.usa"] = {"carte"}
        porte["Save1.usa"] = {"points_100"}
        vus = succes.obtenus("hp1", ["Save0.usa", "Save1.usa"], None, {})
        assert set(vus) == {"points_100"}


class TestToast:
    def test_un_succes_au_retour_passe_devant_le_merci(self, make_window, monkeypatch):
        fenetre = make_window()
        merci = []
        monkeypatch.setattr(fenetre, "_maybe_thank_milestone", lambda: merci.append(1))
        fenetre._session.succes_obtenus = [s for s in succes.du_jeu("hp6") if s.ident == "ecusson"]
        fenetre._on_game_exited("Harry Potter 6", partie=True)
        assert "Premier écusson" in fenetre._toast.text() and merci == []

    def test_plusieurs_succes_trois_titres_au_plus(self, make_window):
        fenetre = make_window()
        fenetre._session.succes_obtenus = list(succes.du_jeu("hp6")[:5])
        fenetre._on_game_exited("Harry Potter 6", partie=True)
        texte = fenetre._toast.text()
        assert texte.startswith("5 succès dans Harry Potter 6 :") and "et 2 autres" in texte

    def test_rien_quand_le_jeu_n_a_pas_demarre(self, make_window):
        fenetre = make_window()
        fenetre._session.succes_obtenus = list(succes.du_jeu("hp6")[:1])
        fenetre._on_game_exited("Harry Potter 6", partie=False)
        assert "succès" not in fenetre._toast.text().lower()


class TestSession:
    def test_les_succes_sont_poses_avant_la_fin_de_partie(self, tmp_path, monkeypatch, qtbot):
        """Règle 134 : la fenêtre lit `succes_obtenus` en recevant `terminee`."""
        from unittest.mock import patch

        from src.core import sauvegardes
        from src.core.config import Config
        from src.core.game_data import Catalog, GameData
        from src.core.game_manager import GameManager
        from src.ui.game_session import GameSession

        jeu = GameData.from_dict({
            "id": "hp6", "name": "HP6", "year": 2009, "description": "d", "developer": "d",
            "executable": "HP6/hp6.exe", "cover_image": "c.jpg",
            "saves": {"root": "localappdata", "folders": ["Accio_test_inexistant/HPHBP0"], "files": "HPHBP0"}})
        catalog = Catalog(catalog_version="1.0", catalog_url="", games=(jeu,))
        with patch("src.core.game_manager.load_catalog", return_value=catalog):
            manager = GameManager(Config(install_path=tmp_path, cache_path=tmp_path / ".cache"))
        session = GameSession(manager)
        session._monitor.start = lambda proc, nom, *, relance: None
        session.demarrer(SimpleNamespace(pid=1), jeu.name, "hp6")
        appels = []
        monkeypatch.setattr(sauvegardes, "attribuer", lambda *a, **k: "HPHBP0")
        monkeypatch.setattr(succes, "constater",
                            lambda jeu, spec, rel, fin, nee: appels.append((rel, nee)) or ["ecusson"])
        vus = []
        session.terminee.connect(lambda *a: vus.append(list(session.succes_obtenus)))
        session._on_game_exited(jeu.name, 0, 600.0)
        assert appels == [("HPHBP0", True)] and vus == [["ecusson"]]


class TestToastOuvreLeFolio:
    def test_le_clic_ouvre_le_folio_ou_vivent_les_succes(self, make_window, monkeypatch, qtbot):
        """Les succès ont rejoint le Folio (2026-10-24) : le toast menait
        encore au Relevé, où il n'y en a plus."""
        fenetre = make_window()
        ouverts = []
        monkeypatch.setattr(fenetre, "_on_stats", lambda rubrique="releve": ouverts.append(rubrique))
        fenetre._session.succes_obtenus = [s for s in succes.du_jeu("hp6") if s.ident == "ecusson"]
        fenetre._on_game_exited("Harry Potter 6", partie=True)
        from PyQt6.QtCore import Qt
        qtbot.mouseClick(fenetre._toast, Qt.MouseButton.LeftButton)
        assert ouverts == ["folio"]

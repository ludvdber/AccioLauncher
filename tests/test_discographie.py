"""La discographie (`src/core/discographie.py`) : seuils, 75 %, morceaux nouveaux."""

import json

from src.core import discographie
from src.core.discographie import Morceau, debloque, nouveaux, pourcentage


def _fichier(tmp_path, jeux):
    chemin = tmp_path / "discographie.json"
    chemin.write_text(json.dumps({"jeux": jeux}), encoding="utf-8")
    return chemin


class TestCharger:
    def test_lit_les_morceaux_et_borne_les_seuils(self, tmp_path):
        chemin = _fichier(tmp_path, {"hp2": [{"f": "a", "t": "A", "s": 140}, {"f": "b", "t": "B", "s": -3}]})
        assert discographie.charger(chemin) == {"hp2": (Morceau("a", "A", 100), Morceau("b", "B", 0))}

    def test_une_entree_mal_formee_est_ecartee(self, tmp_path):
        chemin = _fichier(tmp_path, {"hp1": [{"f": "a", "t": "A", "s": "10"}, {"f": "b", "t": "B", "s": 5}]})
        assert [m.fichier for m in discographie.charger(chemin)["hp1"]] == ["b"]

    def test_un_fichier_illisible(self, tmp_path):
        assert discographie.charger(tmp_path / "absent.json") == {}

    def test_le_fichier_embarque_se_lit(self):
        assert set(discographie.charger()) >= {"hp1", "hp2", "hp3"}


class TestPourcentage:
    def test_etapes_de_hp2_de_0_a_100(self):
        assert pourcentage("hp2", "GSTATE000") == 0
        assert pourcentage("hp2", "gstate180") == 100

    def test_niveau_de_hp1(self):
        assert pourcentage("hp1", "Lev_Tut1") == 0
        assert pourcentage("hp1", "LEV5_FINAL") == 100

    def test_inconnu(self):
        assert pourcentage("hp3", "GSTATE999") is None
        assert pourcentage("hp6", "x") is None
        assert pourcentage("hp1", "") is None


class TestDebloque:
    def test_seuil_zero_ouvert_sans_partie(self):
        assert debloque(Morceau("a", "A", 0), None)
        assert not debloque(Morceau("a", "A", 10), None)

    def test_au_seuil(self):
        assert debloque(Morceau("a", "A", 30), 30)
        assert not debloque(Morceau("a", "A", 30), 29)

    def test_tout_s_ouvre_a_75(self):
        assert debloque(Morceau("generique", "Fin", 100), 75)
        assert not debloque(Morceau("generique", "Fin", 100), 74)


class TestVus:
    def test_nouveaux_puis_marques(self, tmp_path):
        chemin = tmp_path / "vus.json"
        assert nouveaux("hp1", {"a", "b"}, discographie.charger_vus(chemin)) == {"a", "b"}
        discographie.marquer_vus("hp1", {"a"}, chemin)
        assert nouveaux("hp1", {"a", "b"}, discographie.charger_vus(chemin)) == {"b"}
        assert not list(tmp_path.glob("*.accio-tmp"))

    def test_rien_de_neuf_n_ecrit_rien(self, tmp_path):
        chemin = tmp_path / "vus.json"
        discographie.marquer_vus("hp1", set(), chemin)
        assert not chemin.exists()

    def test_un_fichier_abime_vaut_rien_de_vu(self, tmp_path):
        chemin = tmp_path / "vus.json"
        chemin.write_text("[", encoding="utf-8")
        assert discographie.charger_vus(chemin) == {}

    def test_le_chemin_suit_la_config(self, tmp_path):
        assert discographie.chemin_vus().name == "musiques_vues.json"

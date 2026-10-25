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


class TestAvancement:
    """La partie la plus avancée décide de ce qui s'ouvre : chaque jeu lit la sienne."""

    SPEC = object()

    def test_sans_dossier_de_sauvegardes_rien(self):
        assert discographie.avancement("hp2", None) is None

    def test_hp1_prend_le_niveau_le_plus_loin(self, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import folio, sauvegardes
        monkeypatch.setattr(sauvegardes, "fichiers", lambda spec: {})
        monkeypatch.setattr(folio, "emplacements_hp1", lambda f: [
            N(niveau="Lev_Tut1"), N(niveau="LEV5_FINAL"), N(niveau="inconnu")])
        assert discographie.avancement("hp1", self.SPEC) == 100

    def test_hp2_et_hp3_lisent_l_etape(self, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import folio_hp2, folio_hp3, sauvegardes
        monkeypatch.setattr(folio_hp2, "emplacements", lambda spec: [N(histoire="GSTATE000")])
        assert discographie.avancement("hp2", self.SPEC) == 0
        monkeypatch.setattr(sauvegardes, "fichiers", lambda spec: {})
        monkeypatch.setattr(folio_hp3, "emplacements", lambda f: [])
        assert discographie.avancement("hp3", self.SPEC) is None, "aucune partie : rien d'ouvert"

    def test_hp5_prend_le_pourcentage_ecrit_par_le_jeu(self, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import sauvegardes
        monkeypatch.setattr(sauvegardes, "releve", lambda spec: {
            "a": N(avancement=14), "b": N(avancement=None), "c": N(avancement=62)})
        assert discographie.avancement("hp5", self.SPEC) == 62
        monkeypatch.setattr(sauvegardes, "releve", lambda spec: {"a": N(avancement=None)})
        assert discographie.avancement("hp5", self.SPEC) is None

    def test_une_sauvegarde_illisible_ne_fait_pas_tomber_la_page(self, monkeypatch):
        from src.core import folio_hp2

        def casse(spec):
            raise OSError("verrouillé")
        monkeypatch.setattr(folio_hp2, "emplacements", casse)
        assert discographie.avancement("hp2", self.SPEC) is None


class TestCredits:
    def test_lit_les_credits_bien_formes(self, tmp_path):
        chemin = tmp_path / "d.json"
        chemin.write_text(json.dumps({"credits": {
            "hp1": {"compositeur": "Jeremy Soule", "annee": 2001, "editeur": "EA"},
            "hp2": {"compositeur": "X"}}}), encoding="utf-8")
        assert discographie.charger_credits(chemin) == {
            "hp1": discographie.Credit("Jeremy Soule", 2001, "EA")}

    def test_illisible_ou_absent(self, tmp_path):
        assert discographie.charger_credits(tmp_path / "absent.json") == {}
        (tmp_path / "liste.json").write_text("[]", encoding="utf-8")
        assert discographie.charger_credits(tmp_path / "liste.json") == {}

    def test_le_fichier_embarque_credite_chaque_jeu_qui_a_des_morceaux(self):
        credits = discographie.charger_credits()
        sans = [j for j, m in discographie.charger().items() if m and j not in credits]
        assert not sans, f"morceaux sans crédit : {sans}"

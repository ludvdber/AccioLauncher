"""Une nouvelle aventure dans un même emplacement : `progression` mesure,
`sauvegardes` sépare, la carte de la page Stats le dit.

Les sauvegardes sont FABRIQUÉES ; les mesures des attributions sont données
par un faux `mesurer`, sauf là où c'est la lecture elle-même qu'on vérifie.
"""

import json
import os
from datetime import date, datetime

import pytest

from src.core import progression, sauvegardes
from tests.test_folio import _paquet_harry
from tests.test_folio_hp4 import _hpgof
from tests.test_sauvegardes import HP1, HP4, RANGEE, _poser


class TestRecommencee:
    def test_un_compteur_qui_baisse(self):
        assert progression.recommencee((12, 3), (2, 3))
        assert progression.recommencee((12, 3), (14, 1)), "un seul suffit"

    def test_rien_qui_baisse(self):
        assert not progression.recommencee((12, 3), (12, 3))
        assert not progression.recommencee((12, 3), (13, 5))

    def test_sans_mesure_rien_n_est_conclu(self):
        assert not progression.recommencee(None, (0,))
        assert not progression.recommencee((5,), None)
        assert not progression.recommencee((5, 1), (0,)), "lecteur changé : pas comparable"


class TestMesure:
    def test_hp1_les_cartes_de_l_acteur(self, docs):
        _poser(docs, "Harry Potter/Save/Save0.usa", datetime(2026, 10, 1),
               _paquet_harry({"numBeans": 12}, {0: True, 3: True, 5: False}))
        assert progression.mesure("hp1", HP1, "Save0.usa") == (2,)

    def test_hp1_le_tout_debut_vaut_zero(self, docs):
        """L'acteur est là, sans aucune valeur : c'est une mesure, pas un échec."""
        _poser(docs, "Harry Potter/Save/Save1.usa", datetime(2026, 10, 1), _paquet_harry({}))
        assert progression.mesure("hp1", HP1, "Save1.usa") == (0,)

    def test_hp4_l_emplacement_dans_le_fichier(self, appdata):
        _poser(appdata, RANGEE, datetime(2026, 10, 1), _hpgof(boucliers=3, cartes=[1, 8, 151]))
        assert progression.mesure("hp4", HP4, "HPGOF#1") == (3, 3)
        assert progression.mesure("hp4", HP4, "HPGOF#2") is None, "emplacement vide"

    def test_illisible_ou_inconnu(self, docs):
        _poser(docs, "Harry Potter/Save/Save0.usa", datetime(2026, 10, 1), b"rien")
        assert progression.mesure("hp1", HP1, "Save0.usa") is None
        assert progression.mesure("hp1", HP1, "Save4.usa") is None, "absente"
        assert progression.mesure("hp7", HP1, "Save0.usa") is None, "pas de lecteur"
        assert progression.mesure("hp1", None, "Save0.usa") is None



class TestLecteursParJeu:
    """Ce que chaque jeu compte, sur des relevés FABRIQUÉS : l'ordre des
    compteurs ne doit jamais changer pour un même jeu (sinon deux mesures ne
    se comparent plus)."""

    @pytest.fixture
    def ici(self, monkeypatch, tmp_path):
        from src.core import sauvegardes as s
        monkeypatch.setattr(s, "dossier", lambda spec: tmp_path)
        return tmp_path

    def test_hp2_etape_puis_cartes(self, ici, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import folio_hp2
        vus = []

        def releve(chemin, n):
            vus.append((chemin.name, n))
            return N(lu=True, histoire="GSTATE070", cartes=[1, 2, 3])
        monkeypatch.setattr(folio_hp2, "releve", releve)
        assert progression.mesure("hp2", object(), "Slot.sav#2") == (70, 3)
        assert vus == [("Slot.sav", 2)]

    def test_hp2_illisible(self, ici, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import folio_hp2
        monkeypatch.setattr(folio_hp2, "releve", lambda c, n: N(lu=False, histoire="", cartes=[]))
        assert progression.mesure("hp2", object(), "Slot.sav#1") is None

    def test_hp3_etape_cartes_et_tout_debut(self, ici, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import folio_hp3
        monkeypatch.setattr(folio_hp3, "releve", lambda c: N(lu=True, histoire="GState120", cartes=[4]))
        assert progression.mesure("hp3", object(), "a.sav#1") == (120, 1)
        monkeypatch.setattr(folio_hp3, "releve", lambda c: None)
        assert progression.mesure("hp3", object(), "a.sav#1") is None

    def test_hp5_pourcentage_puis_decouverte(self, ici, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import folio_hp5
        monkeypatch.setattr(folio_hp5, "releve", lambda c: [
            N(emplacement=1, pourcentage=None, decouverte=None),
            N(emplacement=2, pourcentage=14, decouverte=None)])
        assert progression.mesure("hp5", object(), "HPOOTP#2") == (14, 0)
        assert progression.mesure("hp5", object(), "HPOOTP#1") is None, "emplacement vide"

    def test_hp6_chapitre_ecussons_sorts(self, ici, monkeypatch):
        from types import SimpleNamespace as N

        from src.core import folio_hp6
        monkeypatch.setattr(folio_hp6, "releve", lambda c: N(chapitre=4, ecussons=9, sorts=("a", "b")))
        assert progression.mesure("hp6", object(), "Save1#1") == (4, 9, 2)

    def test_une_lecture_qui_casse_ne_conclut_rien(self, ici, monkeypatch):
        from src.core import folio_hp6

        def casse(c):
            raise ValueError("tronqué")
        monkeypatch.setattr(folio_hp6, "releve", casse)
        assert progression.mesure("hp6", object(), "Save1#1") is None

    def test_etape_illisible_vaut_zero(self):
        assert progression._etape("GSTATE") == 0
        assert progression._etape("GState010") == 10


@pytest.fixture
def docs():
    return sauvegardes.racines()["documents"]


@pytest.fixture
def appdata():
    return sauvegardes.racines()["localappdata"]


def _jouer(docs, jour: int, duree: int, mesure: tuple[int, ...] | None,
           rel: str = "Save0.usa") -> None:
    """Une partie le `jour` octobre, qui réécrit `rel` ; la sauvegarde mesure `mesure`."""
    chemin = docs / "Harry Potter" / "Save" / rel
    if not chemin.exists():
        _poser(docs, f"Harry Potter/Save/{rel}", datetime(2026, 9, 1))
    avant = sauvegardes.releve(HP1)
    t = datetime(2026, 10, jour, 22, 0).timestamp()
    os.utime(chemin, (t, t))
    sauvegardes.attribuer("hp1", avant, sauvegardes.releve(HP1),
                          datetime(2026, 10, jour, 21, 0), duree,
                          mesurer=lambda _rel: mesure)


class TestNouvelleAventure:
    def test_la_chute_ouvre_une_nouvelle_aventure(self, docs):
        _jouer(docs, 1, 3600, (5,))
        _jouer(docs, 2, 1800, (8,))
        _jouer(docs, 5, 600, (0,))
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert (vue.parties, vue.temps) == (1, 600), "la carte suit l'aventure en cours"
        assert vue.nouvelle == vue.commencee == date(2026, 10, 5)
        assert (vue.precedentes, vue.temps_precedent) == (1, 5400)

    def test_rien_n_est_efface(self, docs):
        _jouer(docs, 1, 3600, (5,))
        _jouer(docs, 5, 600, (0,))
        (entree,) = sauvegardes.charger().values()
        assert [d for _, d in entree["parties"]] == [3600, 600]

    def test_sans_chute_la_meme_aventure(self, docs):
        _jouer(docs, 1, 3600, (5,))
        _jouer(docs, 2, 1800, (5,))
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert (vue.parties, vue.temps, vue.nouvelle, vue.precedentes) == (2, 5400, None, 0)

    def test_deux_chutes(self, docs):
        for jour, mesure in ((1, (9,)), (3, (1,)), (4, (6,)), (6, (0,))):
            _jouer(docs, jour, 1000, mesure)
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert (vue.parties, vue.precedentes, vue.temps_precedent) == (1, 2, 3000)
        assert vue.nouvelle == date(2026, 10, 6)

    def test_une_lecture_ratee_garde_la_mesure_d_avant(self, docs):
        _jouer(docs, 1, 1000, (9,))
        _jouer(docs, 2, 1000, None)
        _jouer(docs, 3, 1000, (2,))
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert vue.precedentes == 1 and vue.parties == 1

    def test_la_premiere_partie_vue_n_ouvre_rien(self, docs):
        """Sans partie déjà comptée, il n'y a pas d'aventure d'avant à séparer."""
        _jouer(docs, 1, 1000, (0,))
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert vue.precedentes == 0 and vue.nouvelle is None

    def test_la_sauvegarde_rapide_n_en_ouvre_jamais(self, docs):
        _jouer(docs, 1, 1000, (9,), "Save9.usa")
        _jouer(docs, 2, 1000, (0,), "Save9.usa")
        (vue,) = sauvegardes.vues("hp1", HP1)
        assert vue.rapide and vue.precedentes == 0 and vue.parties == 2

    def test_sans_mesurer_le_fichier_ne_change_pas_de_forme(self, docs):
        _poser(docs, "Harry Potter/Save/Save0.usa", datetime(2026, 9, 1))
        avant = sauvegardes.releve(HP1)
        t = datetime(2026, 10, 1, 22, 0).timestamp()
        os.utime(docs / "Harry Potter" / "Save" / "Save0.usa", (t, t))
        sauvegardes.attribuer("hp1", avant, sauvegardes.releve(HP1),
                              datetime(2026, 10, 1, 21, 0), 600)
        (e,) = json.loads(sauvegardes.chemin_fichier().read_text(encoding="utf-8"))["sauvegardes"]
        assert set(e) == {"jeu", "fichier", "commencee", "parties"}

    def test_des_champs_douteux_sont_ignores(self, docs):
        chemin = sauvegardes.chemin_fichier()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps({"version": 1, "sauvegardes": [
            {"jeu": "hp1", "fichier": "Save0.usa", "commencee": None,
             "parties": [{"debut": "2026-10-01T21:00:00", "duree": 60}],
             "mesure": [1, True], "nouvelles": ["hier", "2026-10-01T21:00:00"]}]}),
            encoding="utf-8")
        (entree,) = sauvegardes.charger().values()
        assert entree["mesure"] is None
        assert entree["nouvelles"] == [datetime(2026, 10, 1, 21, 0)]


class TestCarte:
    def _textes(self, qtbot, vue) -> list[str]:
        pytest.importorskip("pytestqt")
        from PyQt6.QtWidgets import QLabel
        from src.core.i18n import set_language
        from src.ui.stats_widgets import _CarteSauvegarde
        set_language("fr")
        carte = _CarteSauvegarde(vue, 0)
        qtbot.addWidget(carte)
        return [lbl.text() for lbl in carte.findChildren(QLabel)]

    def test_la_carte_dit_la_nouvelle_aventure(self, qtbot):
        vue = sauvegardes.Vue("Save0.usa", 1, date(2026, 10, 5), date(2026, 10, 9), 2, 1200,
                              nouvelle=date(2026, 10, 5), precedentes=1,
                              temps_precedent=14 * 3600)
        textes = self._textes(qtbot, vue)
        assert "Nouvelle aventure" in textes and "Commencée" not in textes
        assert "Aventure précédente" in textes, textes

    def test_plusieurs_aventures_d_avant(self, qtbot):
        vue = sauvegardes.Vue("Save0.usa", 1, date(2026, 10, 5), date(2026, 10, 5), 1, 600,
                              nouvelle=date(2026, 10, 5), precedentes=2, temps_precedent=7200)
        textes = self._textes(qtbot, vue)
        assert "Nouvelle aventure" in textes and "Jouée le" not in textes
        assert "Aventures précédentes" in textes
        assert any(t.startswith("2 · ") for t in textes), textes

    def test_sans_nouvelle_aventure_rien_ne_change(self, qtbot):
        vue = sauvegardes.Vue("Save0.usa", 1, date(2026, 10, 1), date(2026, 10, 9), 3, 5400)
        textes = self._textes(qtbot, vue)
        assert "Commencée" in textes
        assert not {"Nouvelle aventure", "Aventure précédente"} & set(textes)

"""« Se joue à la manette : oui / en partie / non », par jeu (ACT-061).

Le niveau vient du CATALOGUE et reste vide tant que le jeu n'a pas été essayé manette en main :
une pastille fausse discrédite la fiche. Les jeux sont FABRIQUÉS ici — jamais lus dans `games.json`
(règle 78), dont le contenu se met à jour à distance.
"""
from unittest.mock import MagicMock

import pytest

from src.core.game_data import NIVEAUX_MANETTE, GameData
from src.core.i18n import set_language

BASE = {"id": "x", "name": "X", "year": 2001, "description": "d", "developer": "d",
        "executable": "x/x.exe", "cover_image": "c.jpg"}


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


class TestChamp:
    @pytest.mark.parametrize("niveau", NIVEAUX_MANETTE)
    def test_les_trois_niveaux_sont_lus(self, niveau):
        assert GameData.from_dict(dict(BASE, controller=niveau)).controller == niveau

    def test_absent_veut_dire_non_renseigne(self):
        assert GameData.from_dict(BASE).controller == ""

    @pytest.mark.parametrize("valeur", ["oui", "YES", "maybe", True, 1, ["yes"], {"a": 1}])
    def test_une_valeur_hors_vocabulaire_ne_dit_rien(self, valeur):
        """Le catalogue est distant : ni `True`, ni `"oui"` ne doivent se lire « oui »."""
        assert GameData.from_dict(dict(BASE, controller=valeur)).controller == ""

    def test_la_note_suit_la_langue(self):
        jeu = dict(BASE, controller="partial", controller_note="Souris au démarrage",
                   i18n={"en": {"controller_note": "Mouse at start"}})
        assert GameData.from_dict(jeu).controller_note == "Souris au démarrage"
        set_language("en")
        assert GameData.from_dict(jeu).controller_note == "Mouse at start"


class TestPastille:
    @pytest.fixture
    def panneau(self, qtbot):
        from src.ui.info_panel import InfoPanel
        p = InfoPanel(MagicMock())
        qtbot.addWidget(p)
        return p

    @staticmethod
    def _pastilles(panneau):
        lay = panneau._tags_layout
        return [lay.itemAt(i).widget().text() for i in range(lay.count())]

    def _montrer(self, panneau, **champs):
        panneau._refresh_tags(GameData.from_dict(dict(BASE, tags=["Aventure"], **champs)))
        return self._pastilles(panneau)

    def test_rien_tant_que_le_jeu_n_est_pas_essaye(self, panneau):
        assert self._montrer(panneau) == ["AVENTURE"]

    @pytest.mark.parametrize("niveau, texte", [
        ("yes", "MANETTE"), ("partial", "MANETTE EN PARTIE"), ("no", "SANS MANETTE")])
    def test_chaque_niveau_a_son_libelle(self, panneau, niveau, texte):
        assert self._montrer(panneau, controller=niveau) == ["AVENTURE", texte]

    def test_la_note_est_en_infobulle(self, panneau):
        self._montrer(panneau, controller="partial", controller_note="Souris au démarrage")
        lay = panneau._tags_layout
        assert lay.itemAt(lay.count() - 1).widget().toolTip() == "Souris au démarrage"

    def test_changer_de_jeu_efface_la_pastille(self, panneau):
        self._montrer(panneau, controller="yes")
        assert self._montrer(panneau) == ["AVENTURE"]

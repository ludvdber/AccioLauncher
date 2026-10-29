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



def _bulle(panneau) -> str:
    """Le texte LU de l'infobulle (riche et échappée depuis le 2026-10-29)."""
    import html
    import re
    brut = panneau._meta.toolTip()
    return html.unescape(re.sub(r"<br>", "\n", re.sub(r"</?qt>", "", brut)))

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
        manager = MagicMock()
        manager.download_count.return_value = 0
        manager.is_installed.return_value = False
        p = InfoPanel(manager)
        qtbot.addWidget(p)
        return p

    # Depuis la piste A (2026-10-09), la manette n'est plus une pastille parmi
    # les genres ; depuis la maquette « Plan du launcher v2 » (2026-10-26), elle
    # est un fait du jeu dans la ligne méta, à côté de l'année et du poids.

    def _montrer(self, panneau, **champs):
        jeu = GameData.from_dict(dict(BASE, **champs))
        panneau.apply_game(jeu)
        return panneau._meta.text()

    def test_rien_tant_que_le_jeu_n_est_pas_essaye(self, panneau):
        assert "manette" not in self._montrer(panneau).lower()

    @pytest.mark.parametrize("niveau, texte", [
        ("yes", "Jouable à la manette"), ("partial", "Manette en partie"),
        ("no", "Sans manette")])
    def test_chaque_niveau_a_son_libelle(self, panneau, niveau, texte):
        ligne = self._montrer(panneau, controller=niveau)
        # Un pictogramme depuis la maquette « Plan du launcher v2 » : le libellé
        # est en infobulle ; « sans manette » reste écrit.
        assert _bulle(panneau).startswith(texte)
        assert ("<img" in ligne) == (niveau != "no")

    def test_la_note_est_en_infobulle(self, panneau):
        self._montrer(panneau, controller="partial", controller_note="Souris au démarrage")
        assert _bulle(panneau) == "Manette en partie : Souris au démarrage"

    def test_changer_de_jeu_efface_la_manette(self, panneau):
        self._montrer(panneau, controller="yes")
        assert "manette" not in self._montrer(panneau).lower()


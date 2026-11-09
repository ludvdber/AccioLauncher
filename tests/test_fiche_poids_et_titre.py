"""La fiche : un seul poids à la fois, le titre des deux HP7, l'encre des icônes."""

import dataclasses

import pytest

pytest.importorskip("pytestqt")

from src.core.config import Config  # noqa: E402
from src.core.formatting import format_size  # noqa: E402
from src.core.game_manager import GameManager, GameState  # noqa: E402
from src.core.i18n import set_language  # noqa: E402

_NOM_HP7 = "Harry Potter et les Reliques de la Mort — Partie 1"


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
    set_language("fr")
    return GameManager(Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache", langue="fr"))


@pytest.fixture
def jeu(manager):
    return next(e.game for e in manager.get_games()
                if e.game.current_download and e.game.current_download.is_available)


@pytest.fixture
def info(manager, qtbot):
    from src.ui.info_panel import InfoPanel
    panel = InfoPanel(manager)
    qtbot.addWidget(panel)
    panel.resize(650, 500)
    return panel


@pytest.fixture
def actions(manager, qtbot):
    from src.ui.action_panel import ActionPanel
    panel = ActionPanel(manager)
    qtbot.addWidget(panel)
    return panel


def _poids(jeu):
    from src.ui.info_panel import _insecable
    return _insecable(format_size(jeu.current_download.size_mb))


class TestUnSeulPoids:
    """« 7,0 GO » au-dessus de « Installer 3,4 Go », sans rien pour les distinguer."""

    def test_pas_de_poids_dans_la_meta_avant_l_installation(self, info, jeu):
        info.apply_game(jeu)
        assert _poids(jeu) not in info._meta.text()

    def test_la_place_occupee_une_fois_installe(self, info, jeu, manager):
        manager._states[jeu.id] = GameState.INSTALLED
        info.apply_game(jeu)
        assert _poids(jeu) in info._meta.text()

    def test_la_meta_suit_l_installation_sans_changer_de_jeu(self, info, jeu, manager, qtbot):
        """La fiche reste sur le jeu : seul `rafraichir_indices` passe."""
        info.apply_game(jeu)
        manager._states[jeu.id] = GameState.INSTALLED
        info.rafraichir_indices(jeu)
        qtbot.waitUntil(lambda: not info.lecture_en_cours(), timeout=5000)
        assert _poids(jeu) in info._meta.text()

    def test_l_infobulle_du_bouton_dit_la_place_occupee(self, actions, jeu):
        from src.ui.glow_button import GlowButton
        actions.set_game(jeu)
        actions.refresh()
        bouton = actions.findChild(GlowButton, "btnDownload")
        assert bouton.toolTip() == f"{format_size(jeu.current_download.size_mb)} une fois installé"

    def test_hors_ligne_l_infobulle_dit_pourquoi(self, actions, jeu):
        from src.ui.glow_button import GlowButton
        actions.set_game(jeu)
        actions.set_online(False)
        boutons = [b for b in actions.findChildren(GlowButton, "btnDownload") if not b.isHidden()]
        assert "Hors ligne" in boutons[0].toolTip()


class TestTitreDesDeuxHP7:
    def test_la_partie_quitte_le_titre(self, info, jeu):
        info.apply_game(dataclasses.replace(jeu, name=_NOM_HP7))
        assert info._title.text() == "Harry Potter et les Reliques de la Mort"
        assert info._partie.text() == "Partie 1"
        assert not info._partie.isHidden()

    def test_le_nom_entier_reste_accessible(self, info, jeu):
        info.apply_game(dataclasses.replace(jeu, name=_NOM_HP7))
        assert info._title.accessibleName() == _NOM_HP7

    def test_un_titre_sans_partie_ne_montre_rien_de_plus(self, info, jeu):
        info.apply_game(dataclasses.replace(jeu, name=_NOM_HP7))
        info.apply_game(jeu)
        assert info._title.text() == jeu.name
        assert info._partie.isHidden()

    def test_aucun_titre_du_catalogue_ne_garde_son_tiret(self, info, manager):
        for entree in manager.get_games():
            info.apply_game(entree.game)
            assert "—" not in info._title.text(), entree.game.id


class TestEncreDesIcones:
    def test_l_encre_se_lit_et_le_contour_ne_bouge_pas(self, actions, jeu, manager):
        from src.ui.icon_button import IconButton
        from src.ui.theme import accent_qcolor
        manager._states[jeu.id] = GameState.INSTALLED
        actions.set_game(jeu)
        actions.refresh()
        bouton = actions.findChild(IconButton, "btnGameSettings")
        assert bouton._encre(False).name() == "#b4b4d0"
        assert bouton._cadre.name() == "#8a8aaa"
        assert bouton._encre(True) == accent_qcolor(), "le survol reste à l'accent"

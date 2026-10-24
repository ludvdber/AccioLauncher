"""Le Carnet (Folio puis Relevé) et la rubrique Captures des Collections, sur une vraie fenêtre."""

import pytest
from PyQt6.QtCore import Qt

from src.core import folio


@pytest.fixture
def fenetre_carnet(make_window, monkeypatch, tmp_path):
    """Deux jeux du folio « installés » (les deux premiers du catalogue), sans fichiers ni parties."""
    from src.core.game_manager import GameManager
    win = make_window()
    jeux = [e.game.id for e in win.manager.get_games() if e.game.id in folio.JEUX][:2]
    if len(jeux) < 2:
        pytest.skip("le catalogue n'a pas deux jeux du folio")
    monkeypatch.setattr(GameManager, "is_installed", lambda self, j: j in jeux)
    monkeypatch.setattr(GameManager, "get_game_path", lambda self, j: tmp_path / j)
    return win, jeux


class TestCarnet:
    def test_l_onglet_ouvre_le_folio(self, fenetre_carnet):
        from src.ui.carnet_page import FOLIO, CarnetPage
        from src.ui.folio_page import FolioPage
        from src.ui.title_bar import CARNET
        win, jeux = fenetre_carnet
        win._on_onglet(CARNET)
        page = win._pages.page
        assert isinstance(page, CarnetPage) and page.rubrique_courante == FOLIO
        assert isinstance(page._pile.currentWidget(), FolioPage)
        assert page.jeu in jeux
        assert win._title_bar.onglet(CARNET).isChecked()

    def test_le_releve_puis_retour_au_folio_du_jeu(self, fenetre_carnet):
        from src.ui.carnet_page import FOLIO, RELEVE
        from src.ui.stats_dialog import StatsDialog
        from src.ui.title_bar import CARNET
        win, jeux = fenetre_carnet
        win._on_onglet(CARNET)
        page = win._pages.page
        page.rubrique(RELEVE)
        assert isinstance(page._pile.currentWidget(), StatsDialog)
        assert page._choix.isHidden(), "le choix du jeu ne sert qu'au folio"
        page._pile.currentWidget().ouvrir_folio(jeux[1])
        assert page.rubrique_courante == FOLIO and page.jeu == jeux[1]

    def test_changer_de_jeu_rebatit_le_folio(self, fenetre_carnet):
        from src.ui.title_bar import CARNET
        win, jeux = fenetre_carnet
        win._on_onglet(CARNET)
        page = win._pages.page
        page.montrer(jeux[0])
        avant = page._folio
        page.montrer(jeux[1])
        assert page._folio is not avant and page._folio.game.id == jeux[1]
        assert page._pile.indexOf(avant) == -1

    def test_le_lien_de_la_fiche_souligne_l_onglet(self, fenetre_carnet):
        from src.ui.carnet_page import CarnetPage
        from src.ui.title_bar import CARNET
        win, jeux = fenetre_carnet
        win._detail.game = next(e.game for e in win.manager.get_games() if e.game.id == jeux[1])
        win._detail.ouvrir_folio()
        page = win._pages.page
        assert isinstance(page, CarnetPage) and page.jeu == jeux[1]
        assert win._title_bar.onglet(CARNET).isChecked()

    def test_echap_dans_le_folio_ferme_le_carnet(self, fenetre_carnet, qtbot):
        from src.ui.title_bar import CARNET
        win, _jeux = fenetre_carnet
        win.show()
        qtbot.waitExposed(win)
        win._on_onglet(CARNET)
        page = win._pages.page
        qtbot.keyClick(page._folio, Qt.Key.Key_Escape)
        assert win._pages.page is None

    def test_sans_jeu_installe(self, make_window, monkeypatch):
        from src.core.game_manager import GameManager
        from src.ui.title_bar import CARNET
        monkeypatch.setattr(GameManager, "is_installed", lambda self, j: False)
        win = make_window()
        win._on_onglet(CARNET)
        page = win._pages.page
        assert page._pile.currentWidget() is page._vide and page._choix.isHidden()


class TestCaptures:
    def test_rubrique_captures(self, make_window):
        from src.ui.galerie_page import GaleriePage
        from src.ui.mediatheque import CAPTURES
        from src.ui.title_bar import COLLECTIONS
        win = make_window()
        win._on_onglet(COLLECTIONS)
        page = win._pages.page
        assert page.rubrique_courante == CAPTURES, "l'onglet ouvre sur les captures"
        assert isinstance(page._pile.currentWidget(), GaleriePage)
        assert page._jeux.isHidden(), "la Galerie a ses propres filtres par jeu"
        assert win._title_bar.onglet(COLLECTIONS).isChecked()
        page.accept()
        assert win._pages.page is None

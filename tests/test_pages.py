"""Mes années, Paramètres et les réglages d'un jeu en PAGES (refonte du 2026-10-09)."""

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent

pytest.importorskip("pytestqt")


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    """MainWindow sur une config temporaire — même recette que le smoke test."""
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check", lambda self: None)
    from src.core.config import Config
    Config(install_path=tmp_path / "games", cache_path=tmp_path / "games" / ".cache",
           langue="fr", autoplay_videos=False).save()
    from src.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    yield win
    from src.core.i18n import set_language
    from src.ui.theme import set_theme
    set_language("fr")
    set_theme("poudlard")


def _touche(cle):
    return QKeyEvent(QEvent.Type.KeyPress, cle, Qt.KeyboardModifier.NoModifier)


class TestUnePagePrendLaPlaceDeLaFiche:
    def test_la_fiche_et_le_carrousel_s_effacent(self, fenetre):
        fenetre._on_stats()
        assert fenetre._pages.page is not None
        assert not fenetre._detail.isVisible() and not fenetre._carousel.isVisible()
        assert not fenetre._particles.isVisible(), "des particules par-dessus un relevé"

    def test_le_retour_rend_la_bibliotheque(self, fenetre):
        fenetre._on_settings()
        fenetre._pages.fermer()
        assert fenetre._pages.page is None
        assert fenetre._detail.isVisible() and fenetre._particles.isVisible()
        assert fenetre._title_bar.onglet("bibliotheque").isChecked()

    def test_une_seule_page_a_la_fois(self, fenetre):
        fenetre._on_stats()
        fenetre._on_settings()
        assert fenetre._pages.count() == 2, "la page précédente doit être refermée"
        assert fenetre._pages.cle == "parametres"

    def test_echap_ferme_la_page(self, fenetre, qtbot):
        fenetre._on_stats()
        page = fenetre._pages.page
        page.setFocus()
        qtbot.keyClick(page, Qt.Key.Key_Escape)
        assert fenetre._pages.page is None

    def test_la_barre_de_telechargement_reste_hors_des_pages(self, fenetre):
        assert not fenetre._pages.isAncestorOf(fenetre._download_bar), (
            "un téléchargement se suit depuis n'importe quelle page")


class TestLesTouchesDeLaBibliothequeSeTaisent:
    def test_les_fleches_ne_changent_pas_de_jeu(self, fenetre):
        fenetre._on_settings()
        assert not fenetre._handle_global_key(_touche(Qt.Key.Key_Right))

    def test_entree_ne_lance_rien(self, fenetre, monkeypatch):
        lances = []
        monkeypatch.setattr(fenetre._detail, "trigger_primary_action", lambda: lances.append(1))
        fenetre._on_stats()
        fenetre.keyPressEvent(_touche(Qt.Key.Key_Return))
        assert lances == [], "Entrée sur une page lançait le jeu de la fiche cachée"


def test_fermer_le_launcher_ferme_la_page(fenetre):
    """Les Paramètres comptent l'espace disque dans un thread : il doit s'arrêter."""
    fenetre._on_settings()
    page = fenetre._pages.page
    fenetre._fermeture_confirmee = True
    fenetre.close()
    assert not page._scan_worker.isRunning()

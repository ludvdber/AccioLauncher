"""Audit plein écran (Ludo, 2026-11-16 : « le launcher est horrible en plein écran ») : la colonne centrée des
pages, les bandeaux qui s'alignent dessus, l'air entre pictogramme et nom, et la langue qui ne fait plus sauter
la carte."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtWidgets import QWidget  # noqa: E402

from src.ui import composants  # noqa: E402


class TestColonneCentree:
    def test_retrait(self):
        assert composants.retrait_de_colonne(1280) == 0
        assert composants.retrait_de_colonne(composants.LARGEUR_PAGE_MAX) == 0
        assert composants.retrait_de_colonne(2048) == (2048 - composants.LARGEUR_PAGE_MAX) // 2

    def test_les_marges_suivent_la_largeur(self, qtbot):
        w = QWidget()
        qtbot.addWidget(w)
        composants.colonne_centree(w)
        w.resize(2048, 600)
        w.show()
        qtbot.waitExposed(w)
        assert w.contentsMargins().left() == w.contentsMargins().right() == 304
        w.resize(1200, 600)
        qtbot.wait(10)
        assert w.contentsMargins().left() == 0


@pytest.fixture
def parametres(qtbot, tmp_path, monkeypatch):
    from src.core.config import Config
    from src.core.game_manager import GameManager
    from src.ui.settings_panel import SettingsDialog
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
    cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c", langue="fr")
    dlg = SettingsDialog(cfg, GameManager(cfg))
    qtbot.addWidget(dlg)
    yield dlg
    dlg._shutdown_scan()


class TestParametresEnPleinEcran:
    def test_la_page_et_les_pastilles_dans_la_colonne(self, parametres, qtbot):
        from src.ui.composants import MARGES_PAGE
        parametres.resize(2048, 1100)
        parametres.show()
        qtbot.waitExposed(parametres)
        qtbot.wait(30)   # les marges posées au redimensionnement se mettent en page au tour suivant
        retrait = composants.retrait_de_colonne(2048)
        page = parametres._pages.currentWidget().widget().layout().itemAt(0).widget()
        gauche = page.mapTo(parametres, page.rect().topLeft()).x()
        assert gauche == retrait + MARGES_PAGE[0]
        assert parametres._nav.mapTo(parametres, parametres._nav.rect().topLeft()).x() == gauche
        droite = page.mapTo(parametres, page.rect().topRight()).x()
        assert abs((2048 - droite) - gauche) <= 2, "centrée : autant de vide à droite qu'à gauche"

    def test_une_autre_langue_ne_fait_pas_sauter_la_carte(self, parametres, qtbot):
        """« Redémarrez » prend la place de la phrase d'aide au lieu de s'y ajouter (« un effet bizarre »)."""
        parametres.resize(1280, 800)
        parametres.show()
        qtbot.waitExposed(parametres)
        assert parametres._lang_hint.isHidden() and not parametres._lang_desc.isHidden()
        autre = next(i for i in range(parametres._choix_langue.count())
                     if parametres._choix_langue.itemData(i) != "fr")
        parametres._choix_langue.tuiles[autre].click()
        assert not parametres._lang_hint.isHidden() and parametres._lang_desc.isHidden()
        parametres._choix_langue.setCurrentIndex(parametres._choix_langue.findData("fr"))
        assert parametres._lang_hint.isHidden() and not parametres._lang_desc.isHidden()


class TestBandeau:
    def test_le_contenu_s_aligne_sur_la_colonne(self, qtbot):
        from PyQt6.QtWidgets import QLabel, QVBoxLayout
        from src.ui.bandeau_jeu import Bandeau, fond_du_jeu
        bandeau = Bandeau(fond_du_jeu("hp6"))
        qtbot.addWidget(bandeau)
        lay = QVBoxLayout(bandeau)
        lay.setContentsMargins(40, 18, 40, 14)
        lay.addWidget(QLabel("nom"))
        bandeau.resize(2048, 180)
        bandeau.show()
        qtbot.waitExposed(bandeau)
        assert lay.contentsMargins().left() == 40 + composants.retrait_de_colonne(2048)
        bandeau.resize(1280, 180)
        qtbot.wait(10)
        assert lay.contentsMargins().left() == 40

    def test_l_image_du_jeu_couvre_plus_que_le_coin(self, qtbot):
        """À 1,7 fois la hauteur, l'image ne prenait que le coin droit d'un écran de 2 048 px."""
        from PyQt6.QtCore import QSize
        from src.ui.bandeau_jeu import _LARGEUR_MINI_IMAGE, Bandeau, fond_du_jeu
        chemin = fond_du_jeu("hp6")
        if not chemin.is_file():
            pytest.skip("fonds absents")
        bandeau = Bandeau(chemin)
        qtbot.addWidget(bandeau)
        bandeau.resize(QSize(2048, 180))
        fond = bandeau._fond()
        assert fond is not None
        # La colonne de gauche reste le noir de la page ; l'image commence avant 1 - 0,55 de la largeur.
        image = fond.toImage()
        x = round(fond.width() * (1 - _LARGEUR_MINI_IMAGE)) + 4
        assert image.pixelColor(x, image.height() // 3).name() != "#060611"


class TestPictogrammes:
    def test_de_l_air_entre_le_pictogramme_et_le_nom(self, qtbot):
        from src.ui.bandeau_jeu import pastille_rubrique
        b = pastille_rubrique("À propos", "infos")
        qtbot.addWidget(b)
        assert b.iconSize().width() == 16 + composants.ECART_PICTO
        pm = b.icon().pixmap(b.iconSize())
        assert pm.width() >= (16 + composants.ECART_PICTO) * pm.devicePixelRatio() - 1


class TestDefis:
    def test_la_tuile_du_compte_reste_a_sa_taille(self, qtbot):
        """Extensible, la tuile « 2 / 5 » prenait la place libre : un cadre vide de 500 × 240 px."""
        from types import SimpleNamespace
        from src.ui.defis_page import _LARGEUR_TUILE, DefisPage
        page = DefisPage(SimpleNamespace(id="hp1", name="HP1", sauvegardes=None))
        qtbot.addWidget(page)
        page.resize(1440, 1000)
        page.show()
        qtbot.waitExposed(page)
        tuile = next(w for w in page.findChildren(QWidget, "tuile"))
        assert tuile.width() <= _LARGEUR_TUILE
        assert tuile.height() <= tuile.sizeHint().height() + 2

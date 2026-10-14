"""Quelles images appellent un artiste, et comment le launcher rend les autres."""

import pytest

from src.core.images_a_refaire import a_refaire, fond_a_refaire, jaquette_a_refaire


class TestLaRegle:
    def test_une_jaquette_au_format_passe(self):
        assert not jaquette_a_refaire(1080, 1500)
        assert not jaquette_a_refaire(600, 900), "2:3, à 7 % du 18:25 : recadrée sans perte"

    def test_une_jaquette_carree_est_a_refaire(self):
        assert jaquette_a_refaire(1024, 1024)

    def test_une_jaquette_trop_petite_est_a_refaire(self):
        assert jaquette_a_refaire(267, 400)

    def test_un_fond_plus_etroit_que_l_ecran_est_a_refaire(self):
        assert fond_a_refaire(849, 274)
        assert not fond_a_refaire(1920, 620)

    def test_dans_l_ordre_du_catalogue(self):
        tailles = {"a": ((1024, 1024), (1920, 1080)), "b": ((1080, 1500), (900, 400))}
        assert a_refaire(tailles) == [("a", "jaquette"), ("b", "fond")]


pytest.importorskip("pytestqt")


class TestLaJaquetteNEstPlusEtiree:
    def test_carree_elle_garde_ses_proportions(self, qapp):
        from PyQt6.QtGui import QColor, QImage

        from src.ui.images import jaquette
        carree = QImage(400, 400, QImage.Format.Format_RGB32)
        carree.fill(QColor("#ff0000"))
        rendue = jaquette(carree, 180, 250)
        assert (rendue.width(), rendue.height()) == (180, 250)
        # Le carré tient entier au milieu : rouge vif au centre, assombri au bord.
        centre, bord = QColor(rendue.pixel(90, 125)), QColor(rendue.pixel(90, 3))
        assert centre.red() > 240
        assert bord.red() < 200, "la bande autour doit être le fond flouté et assombri"

    def test_au_bon_format_elle_est_seulement_recadree(self, qapp):
        from PyQt6.QtGui import QColor, QImage

        from src.ui.images import jaquette
        portrait = QImage(600, 900, QImage.Format.Format_RGB32)
        portrait.fill(QColor("#00ff00"))
        rendue = jaquette(portrait, 180, 250)
        assert QColor(rendue.pixel(90, 2)).green() > 240, "aucune bande : recadrage simple"


class TestLAppel:
    def test_sans_besoin_pas_d_appel(self, qapp, monkeypatch):
        from src.ui import appel_artistes
        monkeypatch.setattr(appel_artistes, "besoins", lambda _jeux: [])
        assert appel_artistes.construire([]) is None

    def test_il_nomme_chaque_image(self, qapp, monkeypatch):
        from PyQt6.QtWidgets import QLabel

        from src.core.i18n import get_language, set_language
        from src.ui import appel_artistes
        avant = get_language()
        set_language("fr")
        try:
            monkeypatch.setattr(appel_artistes, "besoins",
                                lambda _jeux: [("Jeu A", "jaquette"), ("Jeu B", "fond")])
            cadre = appel_artistes.construire([])
            textes = [lbl.text() for lbl in cadre.findChildren(QLabel)]
            assert "Jeu A" in textes and "Jeu B" in textes
            assert "Jaquette" in textes and "Fond d'écran" in textes
        finally:
            set_language(avant)

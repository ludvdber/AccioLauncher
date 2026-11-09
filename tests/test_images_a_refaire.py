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

    def test_un_fond_agrandi_cherche_toujours_un_artiste(self):
        """HP3 et HP5, agrandis le 2026-11-02, restent à refaire : la pastille de
        la fiche et l'atelier se jugent sur l'image d'origine."""
        from PyQt6.QtGui import QImageReader

        from src.core.config import ASSETS_DIR
        from src.core.images_a_refaire import taille_a_juger
        for jeu in ("hp3", "hp5"):
            taille = QImageReader(str(ASSETS_DIR / "backgrounds" / f"{jeu}_bg.jpg")).size()
            assert fond_a_refaire(*taille_a_juger(jeu, (taille.width(), taille.height())))

    def test_un_fond_remplace_se_juge_sur_lui_meme(self):
        """Un vrai fond 3840 × 2160 livré par un artiste ne doit plus être jugé
        sur la taille d'origine de l'agrandi qu'il remplace."""
        from src.core.images_a_refaire import taille_a_juger
        assert taille_a_juger("hp5", (3840, 2160)) == (3840, 2160)
        assert not fond_a_refaire(*taille_a_juger("hp5", (3840, 2160)))
        assert taille_a_juger("hp5", (3396, 1096)) == (849, 274)

    def test_dans_l_ordre_du_catalogue(self):
        tailles = {"a": ((1024, 1024), (1920, 1080)), "b": ((1080, 1500), (900, 400))}
        assert a_refaire(tailles) == [("a", "jaquette"), ("b", "fond")]


pytest.importorskip("pytestqt")


def _bandes_horizontales(image, haut, bas):
    """La moitié haute de l'image dans une couleur, la moitié basse dans l'autre."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QPainter

    p = QPainter(image)
    p.fillRect(QRect(0, 0, image.width(), image.height() // 2), haut)
    p.fillRect(QRect(0, image.height() // 2, image.width(), image.height()), bas)
    p.end()
    return image


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
        assert bord.red() < 200, "la bande autour doit être l'aplat assombri"

    def test_les_bandes_prennent_la_couleur_de_leur_bord(self, qapp):
        """ACC15 : un aplat net par bord, plus de flou de la jaquette elle-même."""
        from PyQt6.QtGui import QColor, QImage

        from src.ui.images import jaquette
        carree = QImage(400, 400, QImage.Format.Format_RGB32)
        carree = _bandes_horizontales(carree, QColor("#c80000"), QColor("#0000c8"))
        rendue = jaquette(carree, 180, 250)
        for y in (0, 15, 29):
            haut = rendue.pixelColor(90, y)
            assert (haut.red(), haut.green(), haut.blue()) == (110, 0, 0), y
        for y in (221, 235, 249):
            bas = rendue.pixelColor(90, y)
            assert (bas.red(), bas.green(), bas.blue()) == (0, 0, 110), y

    def test_trop_etroite_les_aplats_sont_sur_les_cotes(self, qapp):
        from PyQt6.QtGui import QColor, QImage

        from src.ui.images import jaquette
        etroite = QImage(100, 400, QImage.Format.Format_RGB32)
        etroite.fill(QColor("#00c800"))
        rendue = jaquette(etroite, 180, 250)
        assert (rendue.width(), rendue.height()) == (180, 250)
        assert rendue.pixelColor(90, 125).green() > 190
        assert rendue.pixelColor(2, 125).green() == 110
        assert rendue.pixelColor(177, 125).green() == 110

    def test_au_bon_format_elle_est_seulement_recadree(self, qapp):
        from PyQt6.QtGui import QColor, QImage

        from src.ui.images import jaquette
        portrait = QImage(600, 900, QImage.Format.Format_RGB32)
        portrait.fill(QColor("#00ff00"))
        rendue = jaquette(portrait, 180, 250)
        assert QColor(rendue.pixel(90, 2)).green() > 240, "aucune bande : recadrage simple"


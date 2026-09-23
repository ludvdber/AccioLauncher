"""Le décor de l'Almanach — la silhouette dans le coin.

Demandé par Ludo le 2026-09-23 : « je m'attendais à plus, genre le Poudlard
Express dans un coin, des citrouilles Halloween ». Des particules habillent
l'air ; une silhouette raconte quelque chose.

Ce qu'aucun test ne peut faire, c'est dire si un dessin est BEAU : les deux
premières silhouettes ont été jetées après avoir été rendues et REGARDÉES (les
citrouilles se lisaient comme une masse ronde, la tour en ruine comme une
maison). Ces tests gardent ce qui se vérifie : que le décor existe pour chaque
ambiance, qu'il reste dans son coin, et qu'il ne coûte rien à répéter.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPoint, QRectF  # noqa: E402
from PyQt6.QtGui import QImage, QPainter, QRegion  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from src.core.season import SEASONS  # noqa: E402
from src.ui import decor  # noqa: E402


class TestChaqueAmbianceAUnDecor:
    def test_les_cinq_ambiances_datees_ont_leur_silhouette(self):
        attendues = {s for s in SEASONS if s not in ("auto", "aucune")}
        assert set(decor._TRACES) == attendues, (
            "une ambiance sans silhouette n'habille que l'air")

    def test_aucune_n_a_pas_de_decor(self):
        """L'ambiance ordinaire reste ordinaire : un décor permanent n'est
        plus un décor."""
        assert "aucune" not in decor._TRACES
        assert "auto" not in decor._TRACES

    @pytest.mark.parametrize("saison", sorted(decor._TRACES))
    def test_la_silhouette_n_est_pas_vide(self, saison, qtbot):
        chemin = decor._TRACES[saison](QRectF(0, 0, 200, 144))
        assert not chemin.isEmpty(), saison
        limites = chemin.boundingRect()
        # Elle occupe vraiment sa boîte : un tracé rabougri dans un coin est
        # un dessin raté qu'on ne verrait pas à l'opacité du décor.
        assert limites.width() > 200 * 0.5, (saison, limites)
        assert limites.height() > 144 * 0.4, (saison, limites)

    @pytest.mark.parametrize("saison", sorted(decor._TRACES))
    def test_la_silhouette_tient_dans_sa_boite(self, saison, qtbot):
        """Un tracé qui déborde salirait le carrousel ou le texte."""
        boite = QRectF(0, 0, 200, 144)
        limites = decor._TRACES[saison](boite).boundingRect()
        marge = 1.0            # l'antialiasing déborde d'un demi-pixel
        assert limites.left() >= -marge, (saison, limites)
        assert limites.top() >= -marge, (saison, limites)
        assert limites.right() <= boite.width() + marge, (saison, limites)
        assert limites.bottom() <= boite.height() + marge, (saison, limites)


class TestOuLeDecorSePose:
    def test_il_reste_a_droite_et_ne_touche_pas_le_texte(self):
        """La moitié gauche porte le titre, la description et les boutons."""
        for largeur, hauteur in ((1280, 800), (1920, 1080), (1100, 760)):
            rect = decor.zone(largeur, hauteur)
            assert rect.left() > largeur * 0.5, (largeur, rect)
            assert rect.right() <= largeur - 1

    def test_il_reste_au_dessus_du_carrousel(self):
        for largeur, hauteur in ((1280, 800), (1920, 1080), (1100, 760)):
            rect = decor.zone(largeur, hauteur)
            assert rect.bottom() <= hauteur - decor._BAS_RESERVE + 1, (largeur, rect)

    def test_il_grandit_avec_la_fenetre_mais_reste_borne(self):
        """Une taille fixe serait minuscule sur un 1440p et envahissante à
        980×660 — le défaut `THUMB_H` / `CAROUSEL_HEIGHT`, en ornement."""
        petite = decor.zone(1100, 760).width()
        grande = decor.zone(2560, 1440).width()
        assert petite < grande
        assert decor._LARGEUR_MIN <= petite <= decor._LARGEUR_MAX
        assert decor._LARGEUR_MIN <= grande <= decor._LARGEUR_MAX

    def test_a_la_taille_minimale_il_tient_encore(self):
        """980×660 est la taille minimale de la fenêtre, et le décor doit y
        tenir AU-DESSUS du carrousel — mesuré : 156×112 posé à (798, 352),
        donc un bas à 464, exactement la ligne réservée. Si ce test casse,
        c'est que le décor a grossi ou que le bas réservé a bougé : il faut
        alors le rétrécir, pas rogner la réserve."""
        rect = decor.zone(980, 660)
        assert rect.bottom() <= 660 - decor._BAS_RESERVE + 1, rect
        assert rect.top() >= decor._MARGE, rect
        assert rect.left() > 980 * 0.5, rect

    def test_une_fenetre_absurde_ne_peint_rien(self, qtbot):
        """Garde-fou : Qt redimensionne transitoirement les widgets pendant
        une passe de mise en page, et un décor posé dans une fenêtre de 200 px
        de haut tomberait n'importe où."""
        image = QImage(400, 200, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        p = QPainter(image)
        decor.peindre(p, "halloween", 400, 200)
        p.end()
        peint = any(image.pixelColor(x, y).alpha() > 0
                    for x in range(0, 400, 5) for y in range(0, 200, 5))
        assert not peint


class TestLeTraceEstMisEnCache:
    """`paintEvent` tourne à chaque image : y reconstruire quinze courbes de
    Bézier serait payer un décor STATIQUE au prix d'une animation."""

    def test_deux_appels_ne_construisent_qu_un_trace(self, qtbot):
        decor.vider_cache()
        image = QImage(1280, 800, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(image)
        for _ in range(30):
            decor.peindre(p, "rentree", 1280, 800)
        p.end()
        assert len(decor._cache) == 1

    def test_une_autre_taille_a_son_propre_trace(self, qtbot):
        decor.vider_cache()
        image = QImage(1920, 1080, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(image)
        decor.peindre(p, "rentree", 1280, 800)
        decor.peindre(p, "rentree", 1920, 1080)
        p.end()
        assert len(decor._cache) == 2


class TestDansLOverlay:
    def test_le_decor_est_peint_sous_les_particules(self, qtbot):
        """Les lettres et les flocons passent DEVANT la silhouette."""
        import inspect
        from src.ui.particles import ParticleOverlay

        src = inspect.getsource(ParticleOverlay.paintEvent)
        assert src.index("decor.peindre") < src.index("for pt in self._particles")

    @pytest.mark.parametrize("saison", sorted(decor._TRACES))
    def test_l_overlay_peint_le_decor_de_sa_saison(self, qtbot, saison):
        from src.ui.particles import ParticleOverlay

        overlay = ParticleOverlay()
        qtbot.addWidget(overlay)
        overlay.resize(1280, 800)
        overlay.apply_season(saison)
        overlay._ensure_particles()
        image = QImage(1280, 800, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        p = QPainter(image)
        overlay.render(p, QPoint(), QRegion(overlay.rect()),
                       QWidget.RenderFlag.DrawChildren)
        p.end()
        overlay.pause()
        zone = decor.zone(1280, 800)
        peint = sum(1 for x in range(zone.left(), zone.right(), 4)
                    for y in range(zone.top(), zone.bottom(), 4)
                    if image.pixelColor(x, y).alpha() > 0)
        assert peint > 40, (saison, peint)

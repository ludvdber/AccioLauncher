"""Au repos, rien ne repeint les jaquettes du carrousel.

Mesuré le 2026-10-14 : les huit jaquettes étaient repeintes environ 130 fois
par seconde, parce que les particules passaient devant et que le scintillement
des étoiles repeignait toute la bande. Ludo : « une anomalie ». Les particules
passent désormais DERRIÈRE, les étoiles ne repeignent que leurs points.
"""

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QWidget

from src.ui.particles import ParticleOverlay


class TestParticules:
    def test_la_zone_repeinte_evite_les_zones_masquees(self, qtbot, monkeypatch):
        hote = QWidget()
        hote.resize(400, 300)
        qtbot.addWidget(hote)
        overlay = ParticleOverlay(hote)
        overlay.setGeometry(0, 0, 400, 300)
        overlay.apply_season("halloween")
        jaquette = QRect(0, 150, 400, 150)       # toute la moitié basse
        overlay.masquer(lambda: [jaquette])
        hote.show()
        demandes = []
        monkeypatch.setattr(overlay, "update", lambda *a: demandes.append(a))
        for _ in range(30):
            overlay._advance()
        assert demandes
        for (region,) in demandes:
            assert region.intersected(jaquette).isEmpty()

    def test_sans_masque_rien_ne_change(self, qtbot):
        hote = QWidget()
        qtbot.addWidget(hote)
        overlay = ParticleOverlay(hote)
        assert overlay._masque().isEmpty()


class TestEtoiles:
    def test_les_etoiles_ne_repeignent_pas_les_jaquettes(self, qtbot):
        from tests.test_carousel import _FakeManager, _make_game
        from src.ui.carousel import Carousel
        c = Carousel([_make_game("a"), _make_game("b"), _make_game("c")], _FakeManager())
        c.resize(900, 192)
        qtbot.addWidget(c)
        c.show()
        qtbot.waitExposed(c)
        zone = c._zone_des_etoiles()
        assert not zone.isEmpty(), "plus aucune étoile hors des jaquettes"
        for item in c._items:
            assert zone.intersected(item.geometry()).isEmpty()

    def test_les_zones_des_jaquettes_suivent_la_fenetre(self, qtbot):
        from tests.test_carousel import _FakeManager, _make_game
        from src.ui.carousel import Carousel
        fenetre = QWidget()
        fenetre.resize(900, 400)
        qtbot.addWidget(fenetre)
        c = Carousel([_make_game("a"), _make_game("b")], _FakeManager(), fenetre)
        c.setGeometry(0, 200, 900, 192)
        fenetre.show()
        qtbot.waitExposed(fenetre)
        zones = c.zones_jaquettes()
        assert len(zones) == 2
        assert all(z.top() >= 200 for z in zones)
        c.hide()
        assert c.zones_jaquettes() == []

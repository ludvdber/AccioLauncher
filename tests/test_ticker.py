"""Horloge d'animation partagée — et surtout : sa mort.

À l'extinction de l'application, Qt détruit l'objet C++ de l'horloge AVANT que
les widgets ne reçoivent leur `hideEvent`. Le désabonnement tombait alors sur
un objet disparu, l'exception remontait jusqu'au hook de crash, et
l'utilisateur recevait un rapport de plantage au moment même où il fermait le
launcher — dernière chose qu'il voit de l'application.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6 import sip  # noqa: E402
from PyQt6.QtWidgets import QVBoxLayout, QWidget  # noqa: E402

from src.ui.ticker import Ticker  # noqa: E402


@pytest.fixture
def horloge_neuve():
    """Repart d'une horloge propre et en laisse une derrière soi.

    Les tests qui suivent détruisent le singleton : sans ce nettoyage, ils
    empoisonneraient tous les autres tests de widgets de la session.
    """
    ancienne = Ticker._instance
    Ticker._instance = None
    yield
    if Ticker._instance is not None and not sip.isdeleted(Ticker._instance):
        Ticker._instance.pause()
    Ticker._instance = ancienne if (ancienne is not None
                                    and not sip.isdeleted(ancienne)) else None


class TestExtinction:
    def test_detach_supporte_une_horloge_detruite(self, horloge_neuve):
        horloge = Ticker.instance()
        appels = []
        horloge.tick.connect(lambda: appels.append(1))
        sip.delete(horloge)              # ce que fait Qt à l'extinction
        assert sip.isdeleted(horloge)
        Ticker.detach(lambda: None)      # ne doit rien lever

    def test_detach_supporte_un_slot_jamais_abonne(self, horloge_neuve):
        Ticker.instance()
        Ticker.detach(lambda: None)      # TypeError sinon

    def test_instance_ne_rend_jamais_un_objet_mort(self, horloge_neuve):
        premiere = Ticker.instance()
        sip.delete(premiere)
        seconde = Ticker.instance()
        assert not sip.isdeleted(seconde)
        assert seconde is not premiere

    def test_cacher_un_bouton_apres_la_mort_de_l_horloge(self, qtbot, horloge_neuve):
        """Reproduction fidèle du plantage signalé à la fermeture."""
        from src.ui.glow_button import GlowButton

        hote = QWidget()
        qtbot.addWidget(hote)
        lay = QVBoxLayout(hote)
        bouton = GlowButton("JOUER", glow_color="#2ecc71")
        lay.addWidget(bouton)
        hote.show()
        qtbot.waitExposed(hote) if hote.isVisible() else None

        sip.delete(Ticker.instance())
        bouton.hide()        # levait RuntimeError avant correction

    def test_cacher_les_particules_apres_la_mort_de_l_horloge(self, qtbot,
                                                              horloge_neuve):
        from src.ui.particles import ParticleOverlay

        hote = QWidget()
        qtbot.addWidget(hote)
        overlay = ParticleOverlay(hote)
        hote.show()
        overlay.show()

        sip.delete(Ticker.instance())
        overlay.hide()

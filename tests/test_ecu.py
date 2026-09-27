"""Tests de src/ui/ecu.py — l'écu de la maison dans la barre de titre."""

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor, QImage, QRegion
from PyQt6.QtWidgets import QWidget

from src.core.i18n import tr
from src.ui.ecu import EMAUX, Ecu, emaux
from src.ui.theme import THEMES, set_theme
from src.ui.title_bar import TitleBar


@pytest.fixture(autouse=True)
def _reset_theme():
    set_theme("poudlard")
    yield
    set_theme("poudlard")


def _rendu(widget: QWidget) -> QImage:
    """Le widget seul, sur fond transparent : ce qu'il peint, sans le fond de personne."""
    image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    widget.render(image, QPoint(), QRegion(), QWidget.RenderFlag(0))
    return image


class TestEmaux:
    def test_chaque_maison_a_ses_deux_couleurs(self):
        maisons = set(THEMES) - {"poudlard"}
        assert set(EMAUX) == maisons
        for couleurs in EMAUX.values():
            assert len(couleurs) == 2 and couleurs[0] != couleurs[1]
            assert all(QColor(c).isValid() for c in couleurs)

    def test_poudlard_et_l_inconnu_n_ont_pas_d_ecu(self):
        assert emaux("poudlard") is None
        assert emaux("dortoir-des-blaireaux") is None


class TestPeinture:
    def test_parti_aux_deux_couleurs(self, qtbot):
        ecu = Ecu("serdaigle", hauteur=44)
        qtbot.addWidget(ecu)
        image = _rendu(ecu)
        w, h = image.width(), image.height()
        dextre, senestre = (QColor(c) for c in EMAUX["serdaigle"])
        assert image.pixelColor(w // 4, h // 3).rgb() == dextre.rgb()
        assert image.pixelColor(3 * w // 4, h // 3).rgb() == senestre.rgb()

    def test_la_pointe_laisse_les_coins_bas_vides(self, qtbot):
        # Un écu, pas un rectangle : sous les flancs, rien n'est peint.
        ecu = Ecu("gryffondor", hauteur=44)
        qtbot.addWidget(ecu)
        image = _rendu(ecu)
        assert image.pixelColor(2, image.height() - 3).alpha() == 0
        assert image.pixelColor(image.width() - 3, image.height() - 3).alpha() == 0

    def test_sans_maison_rien_n_est_peint(self, qtbot):
        ecu = Ecu("poudlard")
        qtbot.addWidget(ecu)
        image = _rendu(ecu)
        assert all(
            image.pixelColor(x, y).alpha() == 0
            for x in range(image.width())
            for y in range(image.height())
        )

    def test_ne_prend_pas_la_souris(self, qtbot):
        # La barre de titre se glisse pour déplacer la fenêtre : l'écu ne doit pas l'en empêcher.
        from PyQt6.QtCore import Qt

        ecu = Ecu("serpentard")
        qtbot.addWidget(ecu)
        assert ecu.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class TestBarreDeTitre:
    def _barre(self, qtbot) -> TitleBar:
        hote = QWidget()
        qtbot.addWidget(hote)
        return TitleBar(hote)

    def test_poudlard_sans_ecu_ni_maison(self, qtbot):
        barre = self._barre(qtbot)
        assert barre._ecu is None and barre._eleve is None

    @pytest.mark.parametrize("maison", sorted(EMAUX))
    def test_theme_de_maison_nomme_la_maison(self, qtbot, maison):
        set_theme(maison)
        barre = self._barre(qtbot)
        assert barre._ecu is not None
        assert tr(THEMES[maison].nom) in barre._eleve.text()

    def test_l_ecu_tient_dans_la_barre(self, qtbot):
        set_theme("poufsouffle")
        barre = self._barre(qtbot)
        assert barre._ecu.height() <= barre.height()

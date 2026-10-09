"""Tests de src/ui/ecu.py — l'écu de la maison dans la barre de titre."""

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor, QImage, QRegion
from PyQt6.QtWidgets import QWidget

from src.core.i18n import available_languages, set_language, tr
from src.ui.ecu import EMAUX, Ecu, emaux
from src.ui.theme import THEMES, set_theme
from src.ui.title_bar import TitleBar


@pytest.fixture(autouse=True)
def _reset_theme():
    set_theme("poudlard")
    yield
    set_theme("poudlard")


def _contraste(a: str, b: str) -> float:
    """Rapport de contraste WCAG entre deux couleurs hexadécimales."""
    def lum(h: str) -> float:
        c = QColor(h)
        canaux = [v / 255 for v in (c.red(), c.green(), c.blue())]
        lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in canaux]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


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

    def test_chaque_email_se_detache_du_fond_de_son_theme(self):
        # Planche 28 : le vrai noir de Poufsouffle (1,13 contre son fond) disparaissait.
        for maison, couleurs in EMAUX.items():
            for c in couleurs:
                assert _contraste(c, THEMES[maison].bg) >= 1.4, (maison, c)
        assert _contraste("#1b1a17", THEMES["poufsouffle"].bg) < 1.4       # contre-épreuve : l'ancien

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

    def test_poudlard_sans_ecu(self, qtbot):
        barre = self._barre(qtbot)
        assert barre._ecu is None

    @pytest.mark.parametrize("maison", sorted(EMAUX))
    def test_l_infobulle_de_l_ecu_nomme_la_maison(self, qtbot, maison):
        set_theme(maison)
        barre = self._barre(qtbot)
        assert barre._ecu is not None
        assert tr(THEMES[maison].nom) in barre._support_ecu.toolTip()

    def test_l_ecu_tient_dans_la_barre(self, qtbot):
        set_theme("poufsouffle")
        barre = self._barre(qtbot)
        assert barre._ecu.height() <= barre.height()

    @pytest.mark.parametrize("langue", [i.code for i in available_languages()])
    @pytest.mark.parametrize("maison", sorted(EMAUX))
    def test_rien_n_est_rogne_a_la_plus_petite_fenetre(self, qtbot, maison, langue):
        # 980 px = la largeur minimale de la fenêtre : nom, écu, trois onglets,
        # Discord et boutons de fenêtre doivent tous y tenir entiers.
        from src.ui.fonts import load_fonts
        from src.ui.title_bar import ANNEES, BIBLIOTHEQUE, PARAMETRES
        load_fonts()  # sous offscreen, sans elles, Qt substitue une police 22 % plus large
        set_language(langue)
        set_theme(maison)
        hote = QWidget()
        qtbot.addWidget(hote)
        barre = TitleBar(hote)
        hote.resize(980, 38)
        barre.setGeometry(0, 0, 980, 38)
        hote.show()
        barre.layout().activate()
        for w in (barre.onglet(BIBLIOTHEQUE), barre.onglet(ANNEES),
                  barre.onglet(PARAMETRES), barre.discord, barre._title):
            assert w.width() >= w.sizeHint().width(), w.text()

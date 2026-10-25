"""Le disque de la Médiathèque (`src/ui/disque.py`) : l'image peinte une fois,
le disque qui ne tourne que visible et en lecture (règle 18 : le Ticker partagé)."""

import pytest
from PyQt6.QtGui import QColor, QImage

from src.ui import disque
from src.ui.disque import Disque, pixmap_disque


@pytest.fixture(autouse=True)
def _cache_vide():
    disque._cache.clear()
    yield
    disque._cache.clear()


def _jaquette(tmp_path, couleur="red", taille=(60, 90)):
    chemin = tmp_path / "jaquette.png"
    image = QImage(*taille, QImage.Format.Format_RGB32)
    image.fill(QColor(couleur))
    assert image.save(str(chemin))
    return chemin


class TestImage:
    def test_troue_au_centre_et_rond(self, qtbot, tmp_path):
        image = pixmap_disque("hp1", _jaquette(tmp_path), 200).toImage()
        assert image.pixelColor(100, 100).alpha() == 0, "le trou au centre"
        assert image.pixelColor(2, 2).alpha() == 0, "un disque : les coins restent vides"
        assert image.pixelColor(100, 160).red() > 200, "l'étiquette est la jaquette"

    def test_sans_jaquette_un_disque_argente(self, qtbot, tmp_path):
        image = pixmap_disque("hp9", tmp_path / "absente.png", 100).toImage()
        teinte = image.pixelColor(50, 85)
        assert teinte.alpha() == 255 and min(teinte.red(), teinte.green(), teinte.blue()) > 150

    def test_peinte_une_fois_par_jeu_et_par_taille(self, qtbot, tmp_path):
        j = _jaquette(tmp_path)
        assert pixmap_disque("hp1", j, 120) is pixmap_disque("hp1", j, 120)
        assert pixmap_disque("hp1", j, 120) is not pixmap_disque("hp1", j, 121)

    def test_le_cadrage_reste_dans_l_image(self):
        for jeu in (*disque.CADRAGES, "inconnu"):
            for w, h in ((60, 90), (90, 60), (100, 100)):
                r = disque._source(QImage(w, h, QImage.Format.Format_RGB32), jeu)
                assert r.left() >= 0 and r.top() >= 0 and r.right() <= w and r.bottom() <= h, (jeu, w, h)
                assert r.width() == r.height(), "un carré"


class TestRotation:
    def test_ne_tourne_que_visible_et_en_lecture(self, qtbot):
        d = Disque(64)
        qtbot.addWidget(d)
        d.set_tourne(True)
        assert not d._abonne, "caché : rien ne bat"
        d.show()
        qtbot.waitExposed(d)
        assert d._abonne
        d.hide()
        assert not d._abonne, "caché en lecture : désabonné"
        d.show()
        assert d._abonne, "réaffiché en lecture : réabonné"
        d.set_tourne(False)
        assert not d._abonne

    def test_un_battement_avance_l_angle_sans_sauter(self, qtbot):
        d = Disque(64)
        qtbot.addWidget(d)
        d.show()
        qtbot.waitExposed(d)
        d.set_tourne(True)
        d._horloge.start()
        qtbot.wait(40)
        d._battement()
        assert 0 < d._angle < 360 * 0.25 / disque._TOUR_S + 1e-6, "un retard ne fait jamais sauter le disque"

    def test_poser_le_meme_disque_ne_repeint_pas(self, qtbot, tmp_path):
        d = Disque(64)
        qtbot.addWidget(d)
        j = _jaquette(tmp_path)
        d.poser("hp1", j)
        repeints = []
        d.update = lambda *a: repeints.append(1)
        d.poser("hp1", j)
        assert not repeints
        d.poser("hp2", j)
        assert repeints

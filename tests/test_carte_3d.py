"""La carte qui s'incline sous la souris (folio de HP4), hors écran."""

import pytest

pytest.importorskip("pytestqt")


def _carte(qtbot):
    from PyQt6.QtGui import QImage

    from src.ui.carte_3d import Carte3D
    carte = Carte3D()
    qtbot.addWidget(carte)
    carte.resize(420, 230)
    image = QImage(512, 256, QImage.Format.Format_ARGB32)
    image.fill(0xFF806040)
    carte.poser(image)
    return carte


def test_la_carte_garde_sa_proportion(qtbot):
    r = _carte(qtbot).rect_carte()
    assert r.width() == pytest.approx(2 * r.height())


def test_elle_penche_vers_la_souris_puis_revient_a_plat(qtbot):
    from PyQt6.QtCore import QPointF

    from src.ui.carte_3d import INCLINAISON
    carte = _carte(qtbot)
    carte.viser(QPointF(carte.width(), 0))            # coin haut droit
    for _ in range(100):
        carte._avancer()
    assert carte.angle == (INCLINAISON, INCLINAISON)
    assert not carte._minuteur.isActive(), "au repos, plus rien ne tourne"
    carte.leaveEvent(None)
    for _ in range(100):
        carte._avancer()
    assert carte.angle == (0.0, 0.0)


def test_le_dessin_incline_ne_plante_pas(qtbot):
    from PyQt6.QtCore import QPointF
    carte = _carte(qtbot)
    carte.viser(QPointF(0, carte.height()))
    for _ in range(5):
        carte._avancer()
    assert not carte.grab().isNull()

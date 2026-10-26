"""La visionneuse de modèles 3D des Personnages et du Bestiaire."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPointF, QSize  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402

from src.core import maillages_ue1 as mu  # noqa: E402
from src.ui.modele_3d import LACET_DEPART, TANGAGE_MAX, Modele3D, transformation_affine  # noqa: E402


def _carre() -> mu.Maillage:
    """Les deux faces avant d'un carré debout, face à la caméra (+X), à deux côtés."""
    points = ((0.0, -10.0, 0.0), (0.0, 10.0, 0.0), (0.0, 10.0, 20.0), (0.0, -10.0, 20.0))
    uv = ((0.0, 1.0), (1.0, 1.0), (1.0, 0.0))
    faces = (mu.Face((0, 1, 2), uv, 0), mu.Face((0, 2, 3), ((0.0, 1.0), (1.0, 0.0), (0.0, 0.0)), 0))
    return mu.Maillage(points, faces, (mu.Materiau("rouge", mu.PF_DEUX_FACES),))


def _rouge() -> QImage:
    img = QImage(4, 4, QImage.Format.Format_ARGB32)
    img.fill(QColor(200, 0, 0))
    return img


def test_transformation_affine():
    source = (QPointF(0, 0), QPointF(1, 0), QPointF(0, 1))
    cible = (QPointF(10, 10), QPointF(30, 10), QPointF(10, 50))
    t = transformation_affine(source, cible)
    assert t is not None
    for s, c in zip(source, cible, strict=True):
        assert t.map(s) == c
    assert transformation_affine((QPointF(0, 0),) * 3, cible) is None


def test_le_modele_se_dessine_texture(qtbot):
    v = Modele3D()
    qtbot.addWidget(v)
    v.poser(_carre(), {"rouge": _rouge()})
    image = v.rendu(QSize(120, 160), 1.0)
    couleurs = {image.pixelColor(x, y).name() for x in range(0, 120, 4) for y in range(0, 160, 4)}
    assert any(c[1:3] > "60" and c[3:] < "202020" for c in couleurs), couleurs   # du rouge, ombré
    assert image.pixelColor(0, 0).alpha() == 0                                  # fond transparent


def test_sans_modele_rien_ne_tourne(qtbot):
    v = Modele3D()
    qtbot.addWidget(v)
    v.show()
    v.poser(None)
    assert not v._minuteur.isActive()
    v.poser(_carre())
    assert v._minuteur.isActive()
    v.hide()
    assert not v._minuteur.isActive()


def test_tourner_borne_le_tangage_et_double_clic_revient(qtbot):
    v = Modele3D()
    qtbot.addWidget(v)
    v.poser(_carre())
    v.tourner(400, 90)
    assert v.lacet == pytest.approx((LACET_DEPART + 400) % 360)
    assert v.tangage == TANGAGE_MAX
    v.mouseDoubleClickEvent(None)
    assert (v.tangage, v.zoom) == (8.0, 1.0)

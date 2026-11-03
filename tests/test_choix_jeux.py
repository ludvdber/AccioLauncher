"""Les pastilles des jeux (`choix_jeux`), communes aux pages."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtGui import QColor, QPixmap  # noqa: E402

from src.ui.choix_jeux import espacee  # noqa: E402


def test_une_jaquette_carree_garde_ses_proportions(qapp):
    """Étirée dans la case 18 × 24, elle perdait un quart de sa largeur (audit du 2026-11-02) :
    centrée, un carré de 18 laisse 3 px vides au-dessus et au-dessous."""
    carree = QPixmap(100, 100)
    carree.fill(QColor(255, 0, 0))
    icone, taille = espacee(carree, QSize(18, 24), ecart=0)
    image = icone.pixmap(taille, 2.0).toImage()
    ratio = image.devicePixelRatio()
    assert image.pixelColor(int(9 * ratio), int(1 * ratio)).alpha() == 0
    assert image.pixelColor(int(9 * ratio), int(12 * ratio)).red() == 255
    assert image.pixelColor(int(1 * ratio), int(12 * ratio)).alpha() == 255

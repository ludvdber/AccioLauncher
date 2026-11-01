"""Le fond ÉTENDU : un bandeau n'est plus agrandi pour couvrir la fenêtre.

Les fonds du dépôt sont des bandeaux 1920 × 620 (HP3 920 × 430) que le cadrage
« cover » agrandissait jusqu'à ×2,4 à 125 % : la pixelisation de l'accueil
(2026-11-01). Posé net sur la largeur, prolongé flouté en dessous ; une
illustration 16:9 en haute définition garde le cadrage d'origine.
"""

from PyQt6.QtGui import QColor, QImage, QPainter

from src.ui.background_widget import BackgroundWidget


def _image(dossier, nom, w, h):
    """Moitié haute rouge, moitié basse bleue."""
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 255))
    p = QPainter(image)
    p.fillRect(0, 0, w, h // 2, QColor(255, 0, 0))
    p.end()
    chemin = dossier / nom
    image.save(str(chemin))
    return chemin


def _fond(qtbot, chemin):
    fond = BackgroundWidget()
    qtbot.addWidget(fond)
    fond.resize(1400, 860)
    fond.set_image(chemin)
    fond._ensure_prepared()
    return fond


def test_un_bandeau_trop_petit_est_etendu(qtbot, tmp_path):
    fond = _fond(qtbot, _image(tmp_path, "hp2_bg.png", 1920, 620))
    assert fond._etendu
    assert fond._flou is not None
    assert fond._prepared.devicePixelRatio() == fond.devicePixelRatioF()
    # Net sur la largeur (marge de parallaxe comprise), à la résolution physique.
    assert fond._prepared.width() / fond._prepared.devicePixelRatio() >= 1400


def test_une_illustration_16_9_garde_le_cadrage_d_origine(qtbot, tmp_path):
    fond = _fond(qtbot, _image(tmp_path, "hp9_bg.png", 2560, 1440))
    assert not fond._etendu
    assert fond._flou is None


def test_un_bandeau_assez_haut_n_est_pas_etendu(qtbot, tmp_path):
    """Plus large que la fenêtre mais assez haut pour la couvrir sans agrandir."""
    fond = _fond(qtbot, _image(tmp_path, "hp8_bg.png", 4800, 1600))
    assert not fond._etendu


def test_le_haut_reste_l_image_le_bas_devient_le_flou(qtbot, tmp_path):
    fond = _fond(qtbot, _image(tmp_path, "hp2_bg.png", 1920, 620))
    rendu = fond.grab().toImage()
    echelle = rendu.width() / 1400
    haut = rendu.pixelColor(int(700 * echelle), int(60 * echelle))
    assert haut.red() > haut.blue(), "le haut de la fenêtre montre le haut de l'image"
    bas = rendu.pixelColor(int(700 * echelle), int(840 * echelle))
    assert bas.blue() >= bas.red(), "sous l'image nette, le flou prolonge son bas bleu"

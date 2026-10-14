"""Les fonds décodés gardés en mémoire : les trois derniers, pas les huit.

Les huit coûtaient 30 Mo de plus après un tour des fiches (57 → 87 Mo,
mesuré le 2026-10-14) pour 12 ms par retour sur un jeu déjà vu.
"""

from PyQt6.QtGui import QColor, QImage

from src.ui import background_widget
from src.ui.background_widget import BackgroundWidget


def _fonds(dossier, n):
    chemins = []
    for i in range(n):
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.fill(QColor(i * 40, 0, 0))
        chemin = dossier / f"hp{i}_bg.png"
        image.save(str(chemin))
        chemins.append(chemin)
    return chemins


def test_seuls_les_trois_derniers_restent_decodes(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(background_widget, "_FONDS_DECODES", background_widget.OrderedDict())
    fond = BackgroundWidget()
    qtbot.addWidget(fond)
    chemins = _fonds(tmp_path, 5)
    for chemin in chemins:
        fond.set_image(chemin)
    assert list(background_widget._FONDS_DECODES) == [str(c) for c in chemins[-3:]]


def test_revenir_sur_un_voisin_ne_redecode_pas(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(background_widget, "_FONDS_DECODES", background_widget.OrderedDict())
    fond = BackgroundWidget()
    qtbot.addWidget(fond)
    a, b, c, d = _fonds(tmp_path, 4)
    fond.set_image(a)
    premier = background_widget._FONDS_DECODES[str(a)]
    for chemin in (b, a, c, d):    # revenir sur `a` le garde parmi les plus récents
        fond.set_image(chemin)
    assert background_widget._FONDS_DECODES.get(str(a)) is premier
    assert str(b) not in background_widget._FONDS_DECODES

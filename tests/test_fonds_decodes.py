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


def _octets(image):
    return bytes(image.constBits().asarray(image.sizeInBytes()))


def test_au_repos_le_fond_compose_rend_le_fond_peint(qtbot, tmp_path):
    """Au repos, le fond est composé une fois et posé tel quel (les particules le
    font repeindre 30 fois par seconde) : 10,8 → 8,0 % d'un cœur, 2026-10-29.
    Le rendu posé doit être celui qu'on peignait, et il doit suivre le jeu."""
    a, b = _fonds(tmp_path, 2)
    fond = BackgroundWidget()
    qtbot.addWidget(fond)
    fond.resize(301, 187)
    fond.set_image(a)
    peint = fond.grab().toImage()
    assert fond._compose is None, "une seule image : rien ne dit encore que le fond est fixe"
    fond.grab()
    pose = fond.grab().toImage()
    assert fond._compose is not None
    assert _octets(pose) == _octets(peint)

    fond.set_image(b)
    autre = fond.grab().toImage()
    assert _octets(autre) != _octets(pose), "un autre jeu : le fond composé n'est plus posé"
    fond.set_video_frame(QImage(16, 9, QImage.Format.Format_RGB32))
    fond.grab()
    assert fond._compose is None, "une vidéo change à chaque image : rien n'est gardé"

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


def test_les_voisins_se_decodent_d_avance(qtbot, tmp_path, monkeypatch):
    """Audit UI, 2026-11-13 : sous Linux, chaque changement de jeu figeait l'accueil 80 à
    150 ms, le temps de décoder le fond sur le fil de l'interface. Les voisins du fond
    montré se décodent d'avance sur un fil ; aller sur l'un ne décode rien sur place."""
    monkeypatch.setattr(background_widget, "_FONDS_DECODES", background_widget.OrderedDict())
    fond = BackgroundWidget()
    qtbot.addWidget(fond)
    a, b, c, d = _fonds(tmp_path, 4)
    fond.set_image(a)
    fond.precharger([a, b, c, d])
    assert set(fond._voisins) == {str(b), str(d)}, "celui d'après, et celui d'avant (en boucle)"
    decode = fond._voisins[str(b)]
    decode.result(timeout=3)
    fond.set_image(b)
    assert fond._courant == str(b), "déjà prêt : montré aussitôt"
    assert decode.done() and str(b) not in fond._voisins, "le décodage du fil a servi"
    assert set(fond._voisins) == {str(c)}, "a est déjà gardé décodé"
    fond.precharger([])
    assert fond._voisins == {}


class TestTailleDeDecodage:
    """f115, f127 : un fond se décode à la taille du plus grand écran, jamais au-delà de l'original."""

    def test_un_petit_ecran_decode_moins(self):
        from PyQt6.QtCore import QSize
        taille = background_widget.taille_de_decodage(QSize(3840, 1240), QSize(1366, 768))
        assert taille.height() >= 768 * BackgroundWidget.MAX_SCALE, "zoom et parallaxe couverts"
        assert taille.width() < 3840 and abs(taille.width() / taille.height() - 3840 / 1240) < 0.01

    def test_jamais_plus_grand_que_l_original(self):
        from PyQt6.QtCore import QSize
        assert background_widget.taille_de_decodage(QSize(3840, 1240), QSize(2560, 1440)) == QSize(3840, 1240)

    def test_le_rendu_processeur_decode_a_cette_taille(self, tmp_path):
        from PyQt6.QtCore import QSize
        image = QImage(3840, 1240, QImage.Format.Format_RGB32)
        image.fill(QColor(20, 0, 0))
        chemin = tmp_path / "hp1_bg.jpg"
        image.save(str(chemin))
        lue = background_widget._decoder(str(chemin), QSize(1366, 768))
        assert lue.size() == background_widget.taille_de_decodage(QSize(3840, 1240), QSize(1366, 768))

"""Pictogrammes PEINTS de la barre de bande-annonce.

Ils remplacent trois caractères posés dans des `QPushButton`. Le plus visible
des deux défauts : le haut-parleur était U+1F50A, un EMOJI — Windows le rend en
couleur, insensible au `setPen`, donc bleu au milieu d'une interface or et
blanche. Le second est plus sournois : un glyphe dépend de la police qui finit
par le servir, donc ni sa graisse, ni sa taille optique, ni son centrage ne
sont les nôtres, et rien ne garantit qu'ils soient les mêmes d'un pictogramme à
l'autre.
"""

import pathlib

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter, QRegion  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from src.ui import theme  # noqa: E402
from src.ui.icon_button import ICONES, IconButton  # noqa: E402

_RACINE = pathlib.Path(__file__).resolve().parent.parent


def _peindre(bouton: IconButton) -> QImage:
    """Rend le bouton SEUL, sans le fond de fenêtre que `render` ajoute sinon."""
    img = QImage(bouton.width(), bouton.height(), QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    bouton.render(p, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
    p.end()
    return img


def _pixels(img: QImage) -> list[tuple[int, int, int, int]]:
    return [QColor(img.pixel(x, y)).getRgb()
            for y in range(img.height()) for x in range(img.width())
            if QColor.fromRgba(img.pixel(x, y)).alpha() > 0]


class TestChaquePictogrammeSeDessine:
    """Un tracé qui ne peint rien ne se voit pas dans une suite offscreen."""

    @pytest.mark.parametrize("nom", ICONES)
    def test_il_y_a_de_l_encre(self, qtbot, nom):
        b = IconButton(nom)
        qtbot.addWidget(b)
        encre = _pixels(_peindre(b))
        assert len(encre) > 40, f"{nom} ne peint presque rien"

    @pytest.mark.parametrize("nom", ICONES)
    def test_l_encre_tient_dans_le_bouton(self, qtbot, nom):
        """Un tracé qui déborde serait rogné par le bouton voisin."""
        b = IconButton(nom)
        qtbot.addWidget(b)
        img = _peindre(b)
        bord = [(x, y) for y in (0, img.height() - 1) for x in range(img.width())]
        bord += [(x, y) for x in (0, img.width() - 1) for y in range(img.height())]
        debordements = [xy for xy in bord
                        if QColor.fromRgba(img.pixel(*xy)).alpha() > 40]
        assert not debordements, f"{nom} touche le bord du bouton"

    def test_deux_pictogrammes_different(self, qtbot):
        """Sinon `set_icone` pourrait ne rien changer sans qu'on le voie."""
        a, b = IconButton("play"), IconButton("pause")
        qtbot.addWidget(a)
        qtbot.addWidget(b)
        assert _peindre(a) != _peindre(b)

    def test_set_icone_repeint(self, qtbot):
        b = IconButton("volume")
        qtbot.addWidget(b)
        avant = _peindre(b)
        b.set_icone("muet")
        assert _peindre(b) != avant

    def test_une_icone_inconnue_est_refusee(self, qtbot):
        """Une faute de frappe doit tomber à la construction, pas au survol."""
        with pytest.raises(ValueError):
            IconButton("stop")


class TestLeSurvolPrendLaCouleurDeLaMaison:
    """Le pictogramme suit l'accent du thème — c'était impossible avec un emoji."""

    def test_le_trait_passe_a_l_accent(self, qtbot):
        b = IconButton("play")
        qtbot.addWidget(b)
        b._survol = True
        accent = theme.current().accent_rgb
        proches = [c for c in _pixels(_peindre(b))
                   if max(abs(c[i] - accent[i]) for i in range(3)) < 24]
        assert proches, "aucun pixel à la couleur d'accent au survol"


class TestPlusAucunEmojiDansLaBarre:
    """Garde-fou de la règle maison : pas de pictogramme à présentation emoji.

    Elle est écrite dans CLAUDE.md depuis longtemps, et la barre audio la
    violait quand même — parce que rien ne la VÉRIFIAIT.
    """

    @pytest.mark.parametrize("fichier", ["src/ui/audio_bar.py",
                                         "src/ui/icon_button.py"])
    def test_aucun_caractere_du_plan_emoji(self, fichier):
        texte = (_RACINE / fichier).read_text(encoding="utf-8")
        fautifs = sorted({c for c in texte if ord(c) >= 0x1F000})
        assert not fautifs, f"pictogramme emoji dans {fichier} : {fautifs}"

    @pytest.mark.parametrize("fichier", ["src/ui/audio_bar.py",
                                         "src/ui/icon_button.py"])
    def test_aucune_echappee_du_plan_emoji(self, fichier):
        """`"' + chr(92) + 'U0001f50a"` ne contient aucun caractère suspect : c'est du
        texte ASCII qui en produit un. C'est sous cette forme que le
        haut-parleur bleu vivait dans le fichier."""
        texte = (_RACINE / fichier).read_text(encoding="utf-8").lower()
        assert "' + chr(92) + 'u0001f" not in texte

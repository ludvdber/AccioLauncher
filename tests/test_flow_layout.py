"""FlowLayout : mémoïsation de `heightForWidth` et cohérence du cache.

Qt interroge `heightForWidth` EN BOUCLE pendant une négociation de mise en
page — mesuré sur la fiche de jeu : 107 appels pour un seul rafraîchissement,
chacun refaisant un passage complet sur les pastilles avec un `sizeHint()` par
item. Coût par appel : **16,55 µs sans cache, 0,22 µs avec** (mesuré hors
animations, 20 000 appels).

Le gain n'est PAS visible de bout en bout — un changement de jeu reste à ~47 ms,
dominé par le chargement de l'illustration — et il ne faut pas prétendre le
contraire. Ce qu'on achète est ailleurs : pendant un redimensionnement, où les
largeurs défilent et où le calcul revenait à chaque pixel parcouru.

Un cache ne vaut que par son invalidation, d'où ces tests : ils couvrent les
deux situations où la fiche fait bouger les pastilles sans en changer le nombre.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QRectF  # noqa: E402
from PyQt6.QtWidgets import QLabel, QWidget  # noqa: E402

from src.ui.flow_layout import FlowLayout  # noqa: E402

TAGS = ("Aventure", "Action", "Classique", "Monde ouvert", "Sorcier", "Solo")


@pytest.fixture
def flow(qtbot):
    hote = QWidget()
    qtbot.addWidget(hote)
    lay = FlowLayout(hote, spacing=8)
    labels = [QLabel(t, hote) for t in TAGS]
    for lbl in labels:
        lay.addWidget(lbl)
    hote.resize(300, 200)
    hote.show()
    qtbot.waitExposed(hote)
    return hote, lay, labels


def _direct(lay, largeur: int) -> int:
    """Hauteur recalculée sans passer par le cache."""
    return lay._do_layout(QRectF(0, 0, largeur, 0), test_only=True)


class TestCacheCoherent:
    def test_la_valeur_cachee_egale_le_calcul_direct(self, flow):
        _, lay, _ = flow
        for largeur in (200, 320, 400, 512, 640):
            assert lay.heightForWidth(largeur) == _direct(lay, largeur)

    def test_deux_appels_a_la_meme_largeur_rendent_la_meme_chose(self, flow):
        _, lay, _ = flow
        assert lay.heightForWidth(300) == lay.heightForWidth(300)


class TestInvalidation:
    def test_ajouter_une_pastille_change_la_hauteur(self, flow):
        hote, lay, _ = flow
        avant = lay.heightForWidth(200)
        for t in ("Un", "Deux", "Trois", "Quatre", "Cinq", "Six"):
            lay.addWidget(QLabel(t, hote))
        assert lay.heightForWidth(200) > avant, "cache non invalidé à l'ajout"

    def test_un_widget_cache_expres_ne_garde_pas_sa_place(self, flow, mise_en_page_stable):
        """Le filtre par jeu de la Galerie cache des vignettes : les restantes
        doivent se resserrer. Sans cela, des trous noirs restaient entre elles
        (Ludo, 2026-10-24)."""
        conteneur, lay, labels = flow
        for lbl in labels[1:-1]:
            lbl.hide()
        mise_en_page_stable(conteneur)
        assert labels[-1].x() == labels[0].x() + labels[0].width() + 8, (
            "la dernière pastille devait venir juste après la première")
        for lbl in labels:
            lbl.show()
        mise_en_page_stable(conteneur)
        assert lay.heightForWidth(300) == _direct(lay, 300), "cache périmé après le retour"

    def test_un_widget_jamais_affiche_compte(self, qtbot):
        """Avant le premier affichage du parent, `QWidgetItem.sizeHint()` vaut
        (0, 0) : la hauteur ne doit pas s'effondrer pour autant."""
        hote = QWidget()
        qtbot.addWidget(hote)
        lay = FlowLayout(hote, spacing=8)
        for t in TAGS:
            lay.addWidget(QLabel(t, hote))
        assert lay.heightForWidth(300) > 0

    def test_changer_le_texte_d_une_pastille_invalide(self, flow, qtbot, mise_en_page_stable):
        """Une fiche à l'autre, les tags changent de LIBELLÉ sans changer de
        nombre. `setText` déclenche `updateGeometry`, donc `invalidate()` —
        vérifié ici plutôt que supposé."""
        conteneur, lay, labels = flow
        # AMORCER le cache d'abord : sans cet appel il n'y a rien à périmer et
        # le test passerait même sans invalidation — il ne prouverait rien.
        amorce = lay.heightForWidth(300)
        # Un saut de ligne, et non un libellé plus LONG : la longueur ne crée
        # une rangée de plus qu'avec les métriques de la police substituée sous
        # Windows. Sous Linux (conteneur python:3.14-slim, avec ou sans DejaVu)
        # la pastille allongée partait seule sur la première rangée, les cinq
        # autres tenaient encore sur la seconde — 36 px avant, 36 px après, et
        # le garde-fou ci-dessous échouait. Une pastille sur deux lignes
        # relève la hauteur de SA rangée (`line_height` en prend le maximum),
        # quelle que soit la police.
        labels[0].setText("Un libellé devenu\nplus haut")
        mise_en_page_stable(conteneur)
        assert lay.heightForWidth(300) == _direct(lay, 300)
        assert lay.heightForWidth(300) != amorce, (
            "la hauteur devait changer : sinon ce test ne prouve rien")

    def test_retirer_un_item_invalide(self, flow):
        _, lay, _ = flow
        avant = lay.heightForWidth(150)
        while lay.count() > 2:
            lay.takeAt(lay.count() - 1)
        assert lay.heightForWidth(150) < avant, "cache non invalidé au retrait"

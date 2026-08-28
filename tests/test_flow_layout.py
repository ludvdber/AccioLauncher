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

    def test_le_cross_fade_ne_perime_pas_le_cache(self, flow, qtbot):
        """Les pastilles sont CACHÉES pendant le fondu du panneau d'info.

        `QWidgetItem.sizeHint()` vaut (0, 0) tant que son widget est caché —
        c'est le défaut que `_do_layout` compense en retombant sur
        `widget.sizeHint()`. Un cache rempli pendant le fondu et relu après
        aurait rouvert exactement ce trou, avec une hauteur figée à la valeur
        d'un panneau invisible.
        """
        _, lay, labels = flow
        visible = lay.heightForWidth(300)
        for lbl in labels:
            lbl.hide()
        qtbot.wait(1)
        pendant = lay.heightForWidth(300)
        for lbl in labels:
            lbl.show()
        qtbot.wait(1)
        assert pendant == visible, "la hauteur s'est effondrée pendant le fondu"
        assert lay.heightForWidth(300) == visible, "cache périmé après le fondu"

    def test_changer_le_texte_d_une_pastille_invalide(self, flow, qtbot):
        """Une fiche à l'autre, les tags changent de LIBELLÉ sans changer de
        nombre. `setText` déclenche `updateGeometry`, donc `invalidate()` —
        vérifié ici plutôt que supposé."""
        _, lay, labels = flow
        # AMORCER le cache d'abord : sans cet appel il n'y a rien à périmer et
        # le test passerait même sans invalidation — il ne prouverait rien.
        amorce = lay.heightForWidth(300)
        labels[0].setText(
            "Un libellé nettement plus long que celui d'origine, "
            "assez pour forcer un retour à la ligne supplémentaire")
        qtbot.wait(1)
        assert lay.heightForWidth(300) == _direct(lay, 300)
        assert lay.heightForWidth(300) != amorce, (
            "la hauteur devait changer : sinon ce test ne prouve rien")

    def test_retirer_un_item_invalide(self, flow):
        _, lay, _ = flow
        avant = lay.heightForWidth(150)
        while lay.count() > 2:
            lay.takeAt(lay.count() - 1)
        assert lay.heightForWidth(150) < avant, "cache non invalidé au retrait"

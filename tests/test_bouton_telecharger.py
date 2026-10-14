"""Le libellé du bouton principal doit tenir dans le bouton.

Signalé par Ludo sur capture d'écran le 2026-08-20 : « CHARGER — 463 Mo · ≈
~19s resta ». Deux défauts cumulés.

1. `drawText` centré ne coupe RIEN : un libellé plus large que le bouton
   déborde des DEUX côtés, hors du cadre dessiné — d'où le « TÉLÉ » disparu au
   début et le « ntes » au bout. Mesuré sur les 6 jeux téléchargeables × 3
   langues : débordement systématique, de +8 px (anglais) à +103 px (français).
2. La durée estimée réutilisait `format_eta`, faite pour un temps RESTANT
   pendant un téléchargement : « ≈ ~19s restantes » empile deux marqueurs
   d'approximation et parle d'un téléchargement que l'utilisateur n'a pas
   encore lancé.

**Pourquoi ni la suite ni l'audit ne l'ont vu** : `last_download_speed` vaut 0
tant qu'aucun téléchargement n'a abouti, donc l'estimation rendait une chaîne
vide et le libellé long n'existait jamais sous mesure. C'est un état qui
n'apparaît qu'APRÈS un premier téléchargement réussi.

La durée a depuis été RETIRÉE du bouton (Ludo, 2026-08-20) : elle promettait un
temps calculé sur la vitesse du dernier téléchargement, sans raison de valoir
encore. Ces tests restent le filet du reste — le libellé doit tenir dans son
bouton, quelle que soit la langue.

Depuis le 2026-10-14, « INSTALLER » et le poids en détail plus discret, sans
tiret cadratin : la mesure porte sur les deux.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtGui import QFontMetrics  # noqa: E402

import src.core.i18n as i18n  # noqa: E402
from src.core.formatting import format_size  # noqa: E402
from src.ui.action_panel import _BOUTON_MAX_W, _BOUTON_MIN_W, _MARGE_BOUTON  # noqa: E402
from src.ui.fonts import body_font, cinzel, load_fonts  # noqa: E402
from src.ui.glow_button import ECART_DETAIL, GlowButton  # noqa: E402

# Tailles réelles des six jeux téléchargeables du catalogue.
TAILLES = [431, 463, 775, 1680, 4600, 4414]


def _libelle(size_mb: int) -> tuple[str, str]:
    """Reconstitue exactement le libellé et le détail posés par `ActionPanel`."""
    return i18n.tr("INSTALLER"), format_size(size_mb)


def _besoin(libelle: str, detail: str) -> int:
    return (QFontMetrics(cinzel(13, bold=True)).horizontalAdvance(libelle)
            + ECART_DETAIL + QFontMetrics(body_font(14)).horizontalAdvance(detail))


class TestLargeur:
    @pytest.mark.parametrize("langue", ["fr", "en", "es"])
    @pytest.mark.parametrize("size_mb", TAILLES)
    def test_le_libelle_tient_dans_le_bouton_reellement_construit(
            self, qtbot, langue, size_mb):
        """L'invariant qui compte : le libellé entre dans le bouton tel qu'il
        sera dimensionné — pas dans une largeur fixe supposée.

        Mesurer contre les 300 px historiques serait un test fragile : sous
        `offscreen`, les métriques de Cinzel diffèrent de la plateforme native
        (mesuré : 302 px ici contre 298 là-bas pour le même libellé, piège
        n° 32). C'est justement pour ça que la largeur suit le contenu.
        """
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.action_panel import ActionPanel

        load_fonts()
        ancienne = i18n.get_language()
        try:
            i18n.set_language(langue)
            panneau = ActionPanel(GameManager(Config()))
            qtbot.addWidget(panneau)
            police = cinzel(13, bold=True)
            libelle, detail = _libelle(size_mb)
            besoin = _besoin(libelle, detail)

            largeur = panneau._largeur_bouton(libelle, police, detail, body_font(14))

            assert besoin <= largeur, (
                f"[{langue}] {libelle!r} réclame {besoin} px pour un bouton "
                f"de {largeur} px — le texte déborderait")
            assert largeur <= _BOUTON_MAX_W
        finally:
            i18n.set_language(ancienne)

    @pytest.mark.parametrize("langue", ["fr", "en", "es"])
    @pytest.mark.parametrize("size_mb", TAILLES)
    def test_aucun_libelle_reel_n_a_besoin_d_etre_elide(self, qtbot, langue, size_mb):
        """L'élision est un filet, pas le fonctionnement normal : sur le
        contenu réel du catalogue, elle ne doit jamais entrer en jeu."""
        load_fonts()
        ancienne = i18n.get_language()
        try:
            i18n.set_language(langue)
            besoin = _besoin(*_libelle(size_mb))
            assert besoin + _MARGE_BOUTON <= _BOUTON_MAX_W, (
                f"[{langue}] le libellé dépasse même le plafond du bouton")
        finally:
            i18n.set_language(ancienne)

    def test_la_largeur_suit_le_contenu_et_reste_bornee(self, qtbot):
        """Filet pour les traductions futures : le bouton s'élargit plutôt que
        de rogner, mais jamais au-delà du plafond."""
        pytest.importorskip("pytestqt")
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.action_panel import ActionPanel

        panneau = ActionPanel(GameManager(Config()))
        qtbot.addWidget(panneau)
        police = cinzel(13, bold=True)

        assert panneau._largeur_bouton("COURT", police) == _BOUTON_MIN_W
        assert panneau._largeur_bouton("X" * 400, police) == _BOUTON_MAX_W
        moyen = "TÉLÉCHARGER  —  4.6 Go  ·  ≈ 3 min  ·  et encore du texte"
        largeur = panneau._largeur_bouton(moyen, police)
        assert _BOUTON_MIN_W <= largeur <= _BOUTON_MAX_W
        besoin = QFontMetrics(police).horizontalAdvance(moyen)
        if _BOUTON_MIN_W < besoin + _MARGE_BOUTON < _BOUTON_MAX_W:
            assert largeur >= besoin, "le libellé doit tenir en entier"


class TestElision:
    """Filet systémique : plus aucun GlowButton ne peut déborder en silence."""

    def test_un_libelle_trop_long_est_elide_et_non_deborde(self, qtbot):
        load_fonts()
        bouton = GlowButton("UN LIBELLÉ BEAUCOUP TROP LONG POUR CE BOUTON",
                            style="outline")
        qtbot.addWidget(bouton)
        bouton.setFont(cinzel(13, bold=True))
        bouton.setFixedSize(120, 46)

        elide = bouton.fontMetrics().elidedText(
            bouton.text(), __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt
            .TextElideMode.ElideRight, 120 - 20)

        assert elide != bouton.text(), "le libellé aurait dû être élidé"
        assert bouton.fontMetrics().horizontalAdvance(elide) <= 120, (
            "même élidé, le texte doit tenir dans le bouton")
        # Et le rendu ne doit pas lever (paintEvent complet).
        bouton.grab()


class TestDetail:
    """Le poids à côté du libellé, et rien qui déborde du bouton (2026-10-14)."""

    def test_le_detail_cede_sa_place_avant_le_libelle(self, qtbot):
        load_fonts()
        bouton = GlowButton("INSTALLER", detail="4,6 Go", detail_font=body_font(14))
        qtbot.addWidget(bouton)
        bouton.setFont(cinzel(13, bold=True))
        bouton.setFixedSize(150, 46)
        bouton.grab()   # le rendu ne lève pas, le détail est simplement omis

    def test_rien_n_est_peint_dans_les_coins(self, qtbot):
        """Le halo débordait du rectangle arrondi : un voile carré dans les
        quatre coins du widget (« un bord aux 4 coins », Ludo)."""
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtGui import QImage, QPainter, QRegion
        from PyQt6.QtWidgets import QWidget

        bouton = GlowButton("INSTALLER", detail="4,6 Go")
        qtbot.addWidget(bouton)
        bouton.setFixedSize(300, 46)
        image = QImage(300, 46, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        # Sans le fond de fenêtre : seul compte ce que le bouton peint.
        bouton.render(p, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        p.end()
        for x, y in ((0, 0), (299, 0), (0, 45), (299, 45)):
            assert image.pixelColor(x, y).alpha() == 0, (x, y)

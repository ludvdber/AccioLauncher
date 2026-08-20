"""Écran de démarrage — il est peint à la main, donc rien ne le protège.

Un splash n'apparaît qu'une seconde et jamais pendant qu'on développe : c'est
exactement le genre de surface où un libellé débordant ou un logo manquant
passe inaperçu jusqu'à ce qu'un utilisateur le signale.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QFont, QFontMetrics  # noqa: E402

from src.core.config import APP_VERSION, ASSETS_DIR  # noqa: E402
from src.core.i18n import available_languages, set_language, tr  # noqa: E402
from src.ui.fonts import cinzel, load_fonts  # noqa: E402
import src.ui.splash as sp  # noqa: E402

# Les libellés réellement affichés par main.py pendant le démarrage.
ETATS = ["Initialisation", "Chargement des ressources",
         "Préparation de la bibliothèque", "Ouverture de la fenêtre", "Prêt"]


class TestAssetsDeMarque:
    def test_le_logo_horizontal_est_embarque(self):
        """Sans connexion, l'écran de démarrage doit quand même s'afficher."""
        logo = ASSETS_DIR / "accio_logo_horizontal.png"
        assert logo.exists(), f"{logo} absent — le splash s'afficherait sans logo"
        assert logo.stat().st_size > 1000

    def test_licone_multi_resolution_est_embarquee(self):
        icone = ASSETS_DIR / "accio_launcher.ico"
        assert icone.exists(), f"{icone} absent — PyInstaller ne peut pas construire l'exe"

    def test_le_png_de_marque_reste_leger(self):
        """Le PNG servait en 64×64 et pesait 1,35 Mo en 1024×1024.

        Il n'est plus qu'un repli d'icône : le garder énorme remettrait
        1,3 Mo dans l'exécutable pour rien.
        """
        png = ASSETS_DIR / "accio_launcher.png"
        assert png.exists()
        assert png.stat().st_size < 100_000, (
            f"{png.name} pèse {png.stat().st_size} octets — repasser sur une "
            "taille raisonnable (256×256 suffit)")


class TestSplash:
    def test_se_construit_et_peint(self, qtbot):
        load_fonts()
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        pix = s.pixmap()
        assert not pix.isNull()
        # Le pixmap est peint a la resolution PHYSIQUE : sur un ecran a 125 %
        # il fait 700x394 pour 560x315 logiques. Comparer les tailles brutes
        # ne passerait qu'en offscreen (DPR 1), pas sur la machine de Ludo.
        assert pix.deviceIndependentSize().width() == pytest.approx(560, abs=1)
        assert pix.deviceIndependentSize().height() == pytest.approx(315, abs=1)

    def test_le_statut_et_la_progression_changent_le_rendu(self, qtbot):
        """La règle du pack : le statut ne doit PAS être figé dans une image."""
        load_fonts()
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        s.set_statut(tr("Initialisation"), 0.1)
        debut = s.pixmap().toImage()
        s.set_statut(tr("Prêt"), 1.0)
        fin = s.pixmap().toImage()
        assert debut != fin, "le splash ne reflète pas le changement d'état"

    def test_la_progression_est_bornee(self, qtbot):
        load_fonts()
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        s.set_statut("x", -5.0)
        assert s._progres == 0.0
        s.set_statut("x", 42.0)
        assert s._progres == 1.0

    def test_la_version_affichee_suit_APP_VERSION(self, qtbot):
        """Le mockup portait « v1.1 » en dur : la vraie version doit être lue."""
        source = (sp.__file__ and open(sp.__file__, encoding="utf-8").read())
        assert "APP_VERSION" in source
        assert "v1.1" not in source
        assert APP_VERSION

    @pytest.mark.parametrize("largeur", [480, 560, 640])
    def test_aucun_libelle_ne_deborde_dans_aucune_langue(self, largeur):
        """Même contrôle que pour le reste de l'interface, appliqué au splash."""
        load_fonts()
        hauteur = int(largeur * 9 / 16)
        corps = max(8, int(hauteur * sp._STATUT_CORPS))
        police = cinzel(corps)
        police.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 132)
        fm = QFontMetrics(police)
        dispo = int(largeur * 0.92)
        try:
            for info in available_languages():
                set_language(info.code)
                for cle in ETATS:
                    texte = tr(cle).upper()
                    besoin = fm.horizontalAdvance(texte)
                    assert besoin <= dispo, (
                        f"{info.code} « {texte} » : {besoin} px pour {dispo} "
                        f"disponibles sur un splash de {largeur} px")
        finally:
            set_language("fr")

    def test_aucun_pictogramme_hors_police(self, qtbot):
        """Les libellés du splash doivent tenir dans Cinzel, sans repli."""
        load_fonts()
        fm = QFontMetrics(cinzel(12))
        try:
            for info in available_languages():
                set_language(info.code)
                for cle in ETATS:
                    for ch in tr(cle).upper():
                        assert fm.inFont(ch), (
                            f"{info.code} : {ch!r} (U+{ord(ch):04X}) absent de "
                            "Cinzel — repli de police sur l'écran de démarrage")
        finally:
            set_language("fr")

    def test_le_logo_est_centre_sur_son_encre(self, qtbot):
        """Le PNG a des marges asymétriques (52 px à gauche, 112 à droite).

        Le centrer tel quel décalait visiblement le logo vers la gauche.
        """
        assert sp._LOGO_DECALAGE > 0
        load_fonts()
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        img = s.pixmap().toImage()
        # L'image est en pixels PHYSIQUES : on raisonne sur sa propre largeur,
        # pas sur les dimensions logiques du splash.
        larg, haut = img.width(), img.height()
        y0 = int(haut * (sp._LOGO_CENTRE_Y - 0.10))
        y1 = int(haut * (sp._LOGO_CENTRE_Y + 0.10))
        xs = [x for x in range(larg) for y in range(y0, y1, 2)
              if img.pixelColor(x, y).red() > 140
              and img.pixelColor(x, y).blue() < 110]
        assert xs, "aucun pixel doré dans la bande du logo"
        centre = (min(xs) + max(xs)) / 2
        ecart = abs(centre - larg / 2) / larg
        assert ecart < 0.03, (
            f"logo décentré de {ecart:.1%} de la largeur (centre {centre:.0f} "
            f"pour {larg / 2:.0f})")


class TestIconeApplication:
    def test_licone_se_charge(self, qtbot):
        from src.ui.main_window import _load_app_icon
        icone = _load_app_icon()
        assert not icone.isNull()
        # Le .ico apporte plusieurs tailles : c'est tout l'intérêt face au PNG.
        tailles = {s.width() for s in icone.availableSizes()}
        assert len(tailles) >= 4, f"une seule taille disponible : {tailles}"
        assert 16 in tailles or min(tailles) <= 32

    def test_le_splash_utilise_lidentite_de_marque(self):
        """Ni couleur ni proportion inventée : tout vient du pack."""
        assert sp._OR == "#d6a72c", "l'or du pack de marque"
        assert sp._FOND == "#060611", "le bleu nuit du pack"
        assert Qt is not None

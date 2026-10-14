"""Écran de démarrage — il est peint à la main, donc rien ne le protège.

Un splash n'apparaît qu'une seconde et jamais pendant qu'on développe : c'est
exactement le genre de surface où un libellé débordant ou un logo manquant
passe inaperçu jusqu'à ce qu'un utilisateur le signale.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QFont, QFontMetrics  # noqa: E402

from src.core import almanach, demarrage  # noqa: E402
from src.core.config import APP_VERSION, ASSETS_DIR  # noqa: E402
from src.core.i18n import available_languages, set_language, tr  # noqa: E402
from src.ui.fonts import load_fonts  # noqa: E402
import src.ui.splash as sp  # noqa: E402


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
        # il fait 900x506 pour 720x405 logiques. Comparer les tailles brutes
        # ne passerait qu'en offscreen (DPR 1), pas sur la machine de Ludo.
        assert pix.deviceIndependentSize().width() == pytest.approx(720, abs=1)
        assert pix.deviceIndependentSize().height() == pytest.approx(405, abs=1)

    def test_chaque_etape_change_le_rendu(self, qtbot):
        """La règle du pack : le statut ne doit PAS être figé dans une image."""
        load_fonts()
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        rendus = [s.pixmap().toImage()]
        for etape in demarrage.ETAPES:
            s.etape(etape)
            rendus.append(s.pixmap().toImage())
        for avant, apres in zip(rendus, rendus[1:]):
            assert avant != apres, "le splash ne reflète pas le changement d'étape"

    def test_la_ligne_avance_avec_les_etapes(self, qtbot):
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        assert s.progres == 0.0
        vus = []
        for etape in demarrage.ETAPES:
            s.etape(etape)
            vus.append(s.progres)
        assert vus == sorted(vus) and 0 < vus[0] and vus[-1] < 1, (
            "la ligne ne se remplit jamais toute seule : la fenêtre le fait")

    def test_une_etape_inconnue_ne_change_rien(self, qtbot):
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        s.etape(demarrage.JEUX)
        s.etape("bandes-annonces")
        assert s.progres == pytest.approx(0.375)


class TestEtapesAnnoncees:
    """Les étapes viennent du code qui les fait, pas d'un minuteur."""

    def test_l_ecran_affiche_ecoute_et_l_ecran_ferme_n_ecoute_plus(self, qtbot):
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        s.show()
        demarrage.annoncer(demarrage.CATALOGUE)
        assert s.progres == pytest.approx(0.125)
        s.close()
        demarrage.annoncer(demarrage.FENETRE)
        assert s.progres == pytest.approx(0.125), (
            "un écran fermé écoute encore : il repeindrait un widget détruit")

    def test_le_gestionnaire_annonce_catalogue_puis_jeux(self):
        from src.core.config import Config
        from src.core.game_manager import GameManager
        vues = []
        demarrage.ecouter(vues.append)
        try:
            GameManager(Config())
        finally:
            demarrage.ecouter(None)
        assert vues == [demarrage.CATALOGUE, demarrage.JEUX]

    def test_sans_auditeur_l_annonce_ne_fait_rien(self):
        demarrage.ecouter(None)
        demarrage.annoncer(demarrage.CATALOGUE)

    def test_main_annonce_la_fenetre_et_ne_dit_plus_pret(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        assert "demarrage.annoncer(demarrage.FENETRE)" in source
        assert "set_statut" not in source


class TestFaitDuJour:
    def test_le_fait_est_peint(self, qtbot):
        load_fonts()
        sans = sp.AccioSplash()
        avec = sp.AccioSplash(fait="Nick Quasi-Sans-Tête fête l'anniversaire de sa mort.")
        qtbot.addWidget(sans)
        qtbot.addWidget(avec)
        assert sans.pixmap().toImage() != avec.pixmap().toImage()

    @pytest.mark.parametrize("largeur", [560, 720])
    def test_aucun_fait_ne_depasse_trois_lignes(self, qtbot, largeur):
        """Le cadre du fait coupe net au-delà : aucun fait ne doit l'être."""
        load_fonts()
        s = sp.AccioSplash(largeur)
        qtbot.addWidget(s)
        fm = QFontMetrics(s.police_du_fait())
        zone = s.zone_du_fait().toRect()
        try:
            for info in available_languages():
                set_language(info.code)
                for fait in almanach.tous_les_textes():
                    texte = tr(fait)
                    besoin = fm.boundingRect(zone, int(Qt.TextFlag.TextWordWrap), texte)
                    assert besoin.height() <= zone.height() + 1, (
                        f"{info.code} : « {texte} » prend {besoin.height()} px "
                        f"pour {zone.height()}")
        finally:
            set_language("fr")

class TestRendu:
    def test_la_version_affichee_suit_APP_VERSION(self, qtbot):
        """Le mockup portait « v1.1 » en dur : la vraie version doit être lue."""
        source = (sp.__file__ and open(sp.__file__, encoding="utf-8").read())
        assert "APP_VERSION" in source
        assert "v1.1" not in source
        assert APP_VERSION

    # 720 est la taille réelle ; sous offscreen la police de repli est 22 %
    # plus large que Gelasio, donc 560 n'y tient qu'à 9 px.
    @pytest.mark.parametrize("largeur", [720, 900])
    def test_les_etapes_tiennent_sous_la_ligne_dans_chaque_langue(self, qtbot, largeur):
        """Quatre noms côte à côte : ils doivent tenir sous la ligne, avec de l'air."""
        load_fonts()
        s = sp.AccioSplash(largeur)
        qtbot.addWidget(s)
        try:
            for info in available_languages():
                set_language(info.code)
                fm = QFontMetrics(s.police_etapes())
                besoin = sum(fm.horizontalAdvance(sp.libelle_etape(e))
                             for e in demarrage.ETAPES)
                assert besoin + 3 * fm.horizontalAdvance("  ") <= s._ligne().width() + 1, (
                    f"{info.code} : {besoin} px de noms pour {s._ligne().width():.0f}")
                assert s.police_etapes().pixelSize() >= 10, info.code
        finally:
            set_language("fr")

    @pytest.mark.parametrize("largeur", [560, 720])
    def test_aucune_phrase_ne_deborde(self, qtbot, largeur):
        load_fonts()
        s = sp.AccioSplash(largeur)
        qtbot.addWidget(s)
        police = sp._en_pixels(QFont(s.police_du_fait()), s._h * sp._CORPS_PHRASE)
        police.setItalic(False)
        fm = QFontMetrics(police)
        try:
            for info in available_languages():
                set_language(info.code)
                for etape in (None, *demarrage.ETAPES):
                    texte = sp.phrase_etape(etape)
                    assert fm.horizontalAdvance(texte) <= largeur * 0.9, (info.code, texte)
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
        from src.ui.utils import icone_application
        icone = icone_application()
        assert not icone.isNull()
        # Le .ico apporte plusieurs tailles : c'est tout l'intérêt face au PNG.
        tailles = {s.width() for s in icone.availableSizes()}
        assert len(tailles) >= 4, f"une seule taille disponible : {tailles}"
        assert 16 in tailles or min(tailles) <= 32

    def test_l_icone_est_posee_sur_toute_l_application(self):
        """L'assistant s'ouvre AVANT la fenêtre principale : sans icône
        d'application, il portait celle, générique, de Windows (exe, 2026-09-24)."""
        import ast
        from pathlib import Path
        racine = Path(__file__).resolve().parent.parent
        arbre = ast.parse((racine / "main.py").read_text(encoding="utf-8"))
        appels = [n for n in ast.walk(arbre) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "setWindowIcon"
                  and isinstance(n.func.value, ast.Name)
                  and n.func.value.id == "app"]
        assert appels, "main.py ne pose plus l'icône sur QApplication"

    def test_le_splash_utilise_lidentite_de_marque(self):
        """Ni couleur ni proportion inventée : tout vient du pack."""
        assert sp._OR == "#d6a72c", "l'or du pack de marque"
        assert sp._FOND == "#060611", "le bleu nuit du pack"
        assert Qt is not None


class TestLeSplashNeCoutePasUneSeconde:
    """`QSplashScreen.show()` coûte ≈ 1 s sur Windows 11. Mesuré, pas supposé.

    7 relevés entre 1 005 et 1 032 ms, plateforme déjà chaude et fenêtre
    réellement exposée ; une `QWidget` portant EXACTEMENT les mêmes drapeaux
    s'affiche en 2 à 19 ms. Ce n'était ni les polices (6 ms), ni le logo, ni
    l'icône : la classe elle-même. Et c'est la seconde la plus chère du
    launcher, puisqu'elle précède le PREMIER PIXEL — l'écran de marque existe
    pour couvrir le chargement, il arrivait après.

    Le contrôle est structurel et non chronométré : un test de durée serait
    instable sous la charge de la suite, et `build.bat` s'arrête au premier
    échec — un test qui rate une fois sur dix est pire que pas de test.
    """

    def test_le_splash_n_est_pas_un_QSplashScreen(self, qtbot):
        from PyQt6.QtWidgets import QSplashScreen
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        assert not isinstance(s, QSplashScreen), (
            "retour à QSplashScreen : ≈ 1 s rendue au démarrage, avant le "
            "premier pixel (cf. docstring de la classe)")

    def test_les_drapeaux_de_fenetre_sont_conserves(self, qtbot):
        """QSplashScreen les posait pour nous ; sans eux le splash prend une
        barre de titre et passe derrière la fenêtre principale."""
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        drapeaux = s.windowFlags()
        assert drapeaux & Qt.WindowType.FramelessWindowHint, "barre de titre"
        assert drapeaux & Qt.WindowType.WindowStaysOnTopHint, "passe derrière"

    def test_finish_referme_le_splash(self, qtbot):
        """`main.py` appelle `finish(window)` : sans lui, le splash reste
        au-dessus de la fenêtre, pour toujours."""
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        s.show()
        assert s.isVisible()
        s.finish(None)
        assert not s.isVisible()

    def test_le_splash_est_centre(self, qtbot):
        """QSplashScreen se centrait tout seul. Une QWidget s'ouvre en haut à
        gauche — une régression qu'aucun test de RENDU ne verrait, puisque le
        dessin, lui, resterait juste."""
        s = sp.AccioSplash()
        qtbot.addWidget(s)
        s.show()
        qtbot.waitExposed(s)
        ecran = s.screen().availableGeometry()
        assert abs(s.geometry().center().x() - ecran.center().x()) <= 2
        assert abs(s.geometry().center().y() - ecran.center().y()) <= 2

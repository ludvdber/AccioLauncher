"""Les finitions de la fenêtre de réglages d'un jeu (audit de l'interface, 2026-11-09) :
la remise à l'origine confirmée puis annoncée, un pied qui ne dit que ce qui sert, un
seul « Bêta » par page, le rail qui défile, les libellés qui disent un réglage."""

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QLabel, QPushButton

from src.core import difficulte_presets as dp
from src.core import reglages_correctif as rc
from src.core.game_data import GameData
from src.core.i18n import set_language, tr
from src.core.reglages_table import REGLAGES
from tests.modales import quand_ouverte
from src.ui.fonts import cinzel_decorative
from tests.rubriques import toutes

INI = "\r\n".join([
    "[Accio.Window]", "KeepRunningInBackground=1", "FPSLimit=100",
    "[Accio.Keys]", ";MoveUp=Z",
    "[Accio.Graphics]", "FXAA=1",
    "[Accio.Game]", "Width=1920", "Height=1080", "Language=auto", "SimulationStep=0",
    "[Accio.Hardcore]", "DamageTaken=1",
    "[Accio.Overlay]", "ShowFPS=0", "",
])
IDENTS = ["resolution", "arriere_plan", "langue_menu", "lissage", "ciel", "ombres_douces",
          "degats_recus", "camera_fluide"]


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


def _jeu(*idents, **champs):
    return GameData.from_dict({"id": "hp6", "name": "Harry Potter et le Prince de Sang-Mêlé", "year": 2009,
                               "description": "d", "developer": "d", "executable": "HP6/hp6.exe",
                               "cover_image": "c.jpg", "fix_settings": list(idents), **champs})


def _fenetre(qtbot, tmp_path, *idents, ini=INI, actions=()):
    from src.ui.game_settings_dialog import GameSettingsDialog
    chemin = tmp_path / "HP6" / "d3d9.ini"
    chemin.parent.mkdir(exist_ok=True)
    if ini:
        chemin.write_bytes(ini.encode("ascii"))
    manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                              config=SimpleNamespace(install_path=tmp_path, reprise={}))
    dlg = GameSettingsDialog(_jeu(*(idents or IDENTS)), manager, lambda c: True, actions=actions)
    qtbot.addWidget(dlg)
    return dlg, chemin


def _textes(dlg):
    return [lb.text() for lb in dlg.findChildren(QLabel)]


class TestRemiseALOrigine:
    def _avec_retouche(self, qtbot, tmp_path):
        """FXAA éteint APRÈS l'ouverture : la retouche crée l'ini d'origine."""
        dlg, ini = _fenetre(qtbot, tmp_path)
        rc.ecrire(ini, REGLAGES["lissage"], False)
        dlg._bouton_reset.setEnabled(True)
        return dlg, ini

    def test_annuler_est_le_defaut_et_ne_remet_rien(self, qtbot, tmp_path):
        dlg, ini = self._avec_retouche(qtbot, tmp_path)
        avant, vus = ini.read_bytes(), {}

        def regarder(boite):
            retablir, annuler = boite.buttons()
            vus.update(titre=boite.windowTitle(), corps=boite.text(), objet=retablir.objectName(),
                       defaut=annuler.isDefault(), retrait=boite._bouton_d_echap() is annuler)
            annuler.click()
        quand_ouverte(regarder)
        dlg._bouton_reset.click()
        assert vus["titre"] == tr("Remettre ce jeu comme à l'installation ?")
        assert vus["objet"] == "danger" and vus["defaut"] and vus["retrait"]
        for page in ("Image", "Jeu", "Difficulté"):
            assert page in vus["corps"], "la question nomme ce qui sera remis"
        assert "Performances" not in vus["corps"], "la page n'existe plus (audit UI reg21)"
        assert ini.read_bytes() == avant
        assert not dlg._pied_notes.text().startswith("Réglages d'origine")

    def test_confirmer_remet_puis_le_pied_le_dit_quatre_secondes(self, qtbot, tmp_path):
        dlg, ini = self._avec_retouche(qtbot, tmp_path)
        avant = dlg._pied_notes.text()
        quand_ouverte(lambda b: b.buttons()[0].click())
        dlg._bouton_reset.click()
        assert "FXAA=1" in ini.read_bytes().decode().split("\r\n")
        assert dlg._pied_notes.text() == tr("Réglages de l'installation remis.")
        assert dlg._minuteur_pied.isActive() and dlg._minuteur_pied.interval() == 4000
        dlg._minuteur_pied.start(1)
        qtbot.waitUntil(lambda: dlg._pied_notes.text() == avant, timeout=2000)

    def test_l_infobulle_nomme_les_pages_vraiment_remises(self, qtbot, tmp_path):
        dlg, _ini = self._avec_retouche(qtbot, tmp_path)
        infobulle = dlg._infobulle_origine()
        assert "Difficulté" in infobulle and "Jeu" in infobulle
        assert "Commandes" not in infobulle, "aucun réglage de ce jeu n'y est"

    def test_le_pictogramme_ne_touche_pas_le_libelle(self, qtbot, tmp_path):
        """Règle 30 : le blanc est peint dans le pixmap."""
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert dlg._bouton_reset.iconSize().width() > dlg._bouton_reset.iconSize().height()


class TestPied:
    def test_le_pied_ne_parle_plus_d_echap(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        for onglet in dlg._onglets:
            dlg.ouvrir_onglet(onglet)
            assert "Échap" not in dlg._pied_notes.text()
        retour = next(b for b in dlg.findChildren(QPushButton) if b.objectName() == "retour")
        assert "Échap" in retour.toolTip()

    def test_le_ciel_de_hp6_est_nomme_sur_l_onglet_image(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.ouvrir_onglet("image")
        assert "sauf le ciel" in dlg._pied_notes.text()
        dlg.ouvrir_onglet("jeu")
        assert "ciel" not in dlg._pied_notes.text()

    def test_rien_a_dire_et_pas_de_bouton_pas_de_pied(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path, "arriere_plan", ini="")
        assert dlg._bouton_reset is None
        assert dlg._cadre_pied.isHidden() and dlg._pied_info.isHidden()

    def test_le_haut_de_difficulte_ne_redit_pas_le_quand(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert not any("sauvegardes ne changent pas" in t for t in _textes(dlg)),             "un comportement normal ne se précise pas (Ludo, 2026-11-13)"
        assert not any("Change à tout moment" in t and "sauvegardes" in t for t in _textes(dlg))


class TestBandeau:
    """Maquette B « L'En-tête » (Ludo, 2026-11-13) : le bandeau du jeu remplace le rail de gauche."""

    def test_le_nom_du_jeu_tient_sur_sa_ligne_a_la_plus_petite_taille(self, qtbot, tmp_path):
        """Le nom descend de taille plutôt que de sortir du bandeau (titres les plus longs : HP7), et garde la
        PLUS GRANDE taille qui tient : la largeur où 24 points cessent de tenir dépend des polices du système
        (à la taille minimale, le titre tient en 24 sous Linux et pas sous Windows ; CI du 2026-11-15)."""
        from PyQt6.QtGui import QFontMetrics
        from src.ui.bandeau_jeu import NomDuJeu
        from src.ui.composants import TAILLE_MINIMALE_PAGE
        from src.ui.fonts import cinzel
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.resize(*TAILLE_MINIMALE_PAGE)
        dlg.show()
        qtbot.waitExposed(dlg)
        nom = dlg._titre
        for largeur in (nom.width(), nom.width() // 2):
            nom.setFixedWidth(largeur)
            # Posé APRÈS la mise en page : le texte seul doit suffire à réajuster la taille.
            nom.setText("Harry Potter et les Reliques de la Mort - 1re partie")
            taille = nom.font().pointSize()
            tient = [t for t in NomDuJeu._TAILLES
                     if QFontMetrics(cinzel(t, bold=True)).horizontalAdvance(nom.text()) <= largeur]
            assert taille == (tient[0] if tient else NomDuJeu._TAILLES[-1])
            assert nom.wordWrap() is not bool(tient)
        assert nom.font().pointSize() < 24, "à mi-largeur, 24 points ne tiennent sur aucun système"

    def test_les_rubriques_sont_les_pastilles_du_carnet(self, qtbot, tmp_path):
        """Le même menu que le Carnet et les Collections (`composants.filtre`, en grand)."""
        from src.ui.composants import HAUTEUR_FILTRE_GRAND
        dlg, _ini = _fenetre(qtbot, tmp_path)
        for b in dlg._onglets.values():
            assert b.objectName() == "filtre" and b.property("grand") is True
            assert b.height() == HAUTEUR_FILTRE_GRAND
        assert sum(b.isChecked() for b in dlg._onglets.values()) == 1

    def test_le_fond_decode_sur_un_fil_est_le_meme(self, qtbot):
        """Le JPEG du fond se décode pendant que la page se bâtit (100 à 170 ms de moins sur le fil de
        l'interface, banc du 2026-11-19) : les mêmes pixels que lus sur place."""
        from PyQt6.QtGui import QPixmap
        from src.ui.bandeau_jeu import Bandeau, fond_du_jeu
        chemin = fond_du_jeu("hp1")
        bandeau = Bandeau(chemin)
        qtbot.addWidget(bandeau)
        assert bandeau._image().toImage() == QPixmap(str(chemin)).toImage()

    def test_plus_de_rail_a_gauche(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QFrame
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert dlg.findChild(QFrame, "rail") is None
        assert dlg._zone_rail.objectName() == "bandeauJeu"


class TestBeta:
    def test_une_seule_mention_par_page(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg._page_img.ligne("camera_fluide")   # la Caméra vit dans « Fluidité » (audit UI reg21)
        assert _textes(dlg).count(tr("Bêta").upper()) == 2, "une en tête de la Difficulté, une sur la Caméra, seule en bêta sur sa page"
        assert "Discord" in dlg._beta["difficulte"].toolTip()

    def test_beta_a_cote_du_titre_de_la_difficulte(self, qtbot, tmp_path):
        """f44, f68 : seule à gauche du cadran, la gélule laissait 660 × 330 px vides. Maquette B : DANS la
        pastille « Difficulté » du bandeau ; posée à côté, entre deux pastilles, on ne savait pas si elle parlait
        de Difficulté ou de Fichiers (Ludo, 2026-11-15)."""
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.ouvrir_onglet("difficulte")
        dlg.resize(1280, 800)
        dlg.show()
        qtbot.waitExposed(dlg)
        beta = dlg._beta["difficulte"]
        pastille = dlg._onglets["difficulte"]
        assert beta.parentWidget() is pastille, "dans la pastille de sa rubrique"
        assert pastille.rect().contains(beta.geometry()), "entière, sans déborder"
        texte = pastille.fontMetrics().horizontalAdvance(pastille.text())
        assert beta.geometry().left() > pastille.iconSize().width() + texte, "à droite du nom, sans le couvrir"
        assert abs(beta.geometry().center().y() - pastille.rect().center().y()) <= 2
        assert pastille.toolTip() == beta.toolTip(), "le badge laisse passer la souris : la pastille l'explique"
        from PyQt6.QtWidgets import QWidget
        assert dlg._panneau.findChild(QWidget, "enteteDifficulte") is None, "plus de colonne vide"
        qtbot.wait(50)
        panneau, cadran = dlg._panneau, dlg._panneau.cadran
        assert abs(cadran.geometry().center().x() - panneau.rect().center().x()) <= 2, "le cadran se centre"

    def test_une_seule_etiquette_pour_toute_la_fenetre(self, qtbot, tmp_path):
        """f64 : « Bêta » en Gelasio sur une ligne, « BÊTA » en Cinzel dans la Difficulté."""
        from PyQt6.QtWidgets import QLabel
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg._page_img.ligne("camera_fluide")
        etiquettes = [lbl for lbl in dlg.findChildren(QLabel) if lbl.text() == tr("Bêta").upper()]
        assert len(etiquettes) == 2
        (a, b) = etiquettes
        assert a.font().family() == b.font().family() and a.font().pointSizeF() == b.font().pointSizeF()
        assert a.styleSheet() == b.styleSheet()
        # À l'image (f20) : les deux gélules sont peintes au pixel près pareil.
        from tests.pixels import sur_noir
        assert a.sizeHint() == b.sizeHint()
        a.resize(a.sizeHint())
        b.resize(b.sizeHint())
        assert sur_noir(a) == sur_noir(b)

    def test_la_fiche_de_difficulte_ne_le_redit_pas(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        toutes(dlg)
        assert "Discord" not in dlg._aides["degats_recus"]
        page = dlg._page_img
        page._activer("camera_fluide")
        assert "Discord" in page.fiche.texte.text(), "la fiche de la Caméra, elle, le dit"


class TestLibelles:
    def test_les_manettes_se_lisent_comme_un_reglage(self):
        assert REGLAGES["manette_playstation"].libelle == "Accepter les manettes PlayStation"
        assert REGLAGES["manette_playstation_hp4"].libelle == "Accepter les manettes PlayStation et Xbox"
        assert "USB" in REGLAGES["vibrations"].libelle

    def test_la_camera_ne_se_repete_pas_dans_sa_valeur(self):
        assert REGLAGES["camera_fluide"].libelle == "Caméra"

    def test_une_seule_vie_ne_redit_pas_la_regle(self):
        for ident in ("realiste", "impardonnable"):
            assert "mort" not in dp.PAR_IDENT[ident].phrase

    def test_sur_mesure_sans_phrase_sous_son_titre(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert not any("un preset les règle" in t for t in _textes(dlg))

    def test_la_difficulte_du_jeu_passe_avant_le_quidditch(self):
        idents = frozenset({dp.NATIVE, "quidditch"})
        noms = [nom for nom, _valeur in dp.changements(dp.PAR_IDENT["hardcore"], idents)]
        assert noms[0] == "Difficulté du jeu" and len(noms) == 2

    def test_ce_qui_se_voit_est_dit_dans_la_fiche(self, qtbot, tmp_path):
        """Plus d'œil ni de légende sur chaque ligne (maquette « Curseurs gradués ») : la fiche le dit."""
        dlg, _ini = _fenetre(qtbot, tmp_path)
        page = dlg._page_img
        ident = next(r.ident for c in page.categories for r in c.reglages if r.se_voit)
        page.ligne(ident).survolee.emit(ident)
        assert tr("Se voit nettement à l’écran.") in page.fiche.texte.text()


class TestRangement:
    def test_aucun_effet_d_image_sans_famille(self):
        """Le filet « Autres » reste pour un réglage futur : aucun n'y tombe aujourd'hui."""
        from src.core import reglages_image
        for r in REGLAGES.values():
            if r.onglet in ("image", "affichage"):
                assert reglages_image.place(r) != reglages_image._AILLEURS, r.ident

    def test_la_langue_du_menu_est_dans_demarrage(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        toutes(dlg)
        textes = _textes(dlg)
        assert tr("Démarrage").upper() in textes and tr("En arrière-plan").upper() in textes
        assert tr("Dans le jeu").upper() not in textes
        assert "langue_menu" in dlg._controles


class TestMiseEnPage:
    def test_la_page_n_a_plus_de_grand_titre(self, qtbot, tmp_path):
        """Maquette B : le nom de la rubrique est dans sa pastille cochée ; « IMAGE » en grand, au-dessus,
        la redisait."""
        from PyQt6.QtWidgets import QLabel
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert not [lb for lb in dlg.findChildren(QLabel)
                    if (lb.accessibleName() or lb.text()) == tr("Image") and lb.font().pointSize() == 22]

    def test_un_titre_en_i_prend_le_i_sans_ornement(self, qtbot):
        """Le I de Cinzel Decorative porte un crochet : « IMAGE » avait l'air mal écrit (Ludo, 2026-11-15).
        Le seul I initial passe en Cinzel ; le reste garde la décorative, et le nom lu reste le mot."""
        from src.ui.composants import titre_page
        from src.ui.fonts import cinzel
        t = titre_page("Image")
        qtbot.addWidget(t)
        assert t.accessibleName() == "Image"
        assert cinzel(22).family() in t.text() and t.text().endswith("mage")
        assert t.font().family() == cinzel_decorative(22).family()
        autre = titre_page("Jeu")
        qtbot.addWidget(autre)
        assert autre.text() == "Jeu"

    def test_le_bandeau_garde_sa_hauteur_dans_une_petite_fenetre(self, qtbot, tmp_path):
        from src.ui.bandeau_jeu import HAUTEUR_BANDEAU
        from src.ui.reglages_rubriques import ActionFichier
        dlg, _ini = _fenetre(qtbot, tmp_path, actions=[ActionFichier("Ouvrir le dossier", lambda: None, "", "Ouvrir")])
        dlg.setMinimumSize(0, 0)
        dlg.resize(980, 420)
        dlg.show()
        qtbot.waitExposed(dlg)
        assert dlg._zone_rail.height() == HAUTEUR_BANDEAU
        assert all(b.isVisible() for b in dlg._onglets.values())



def test_en_plein_ecran_le_controle_reste_pres_de_son_nom(qtbot, tmp_path):
    """Audit UI v40 : à 1 920 px, 800 à 980 px séparaient un nom de son contrôle sur la page
    Image ; la liste s'arrête à `LARGEUR_LISTE`, la fiche la suit."""
    from src.ui.page_image import LARGEUR_LISTE, PageImage
    dlg, _ = _fenetre(qtbot, tmp_path)
    dlg.ouvrir_onglet("image")
    dlg.resize(1920, 1000)
    dlg.show()
    qtbot.waitExposed(dlg)
    page = dlg.findChild(PageImage)
    qtbot.waitUntil(lambda: page.pile.width() > 0)
    assert page.pile.width() <= LARGEUR_LISTE
    assert page._zone_fiche.x() - page.pile.geometry().right() <= 40, "la fiche suit la liste"


def test_revenir_a_l_installation_remet_aussi_la_resolution(qtbot):
    """Audit UI v49 : la confirmation annonçait l'Image remise, la résolution restait
    sur 1600 × 1024."""
    from types import SimpleNamespace
    from PyQt6.QtWidgets import QComboBox
    from src.ui.page_image import PageImage
    liste = QComboBox()
    qtbot.addWidget(liste)
    liste.addItem("Remplir l'écran", "")
    liste.addItem("1600 × 1024", "1600x1024")
    liste.setCurrentIndex(1)
    page = SimpleNamespace(reglages={}, _resolution=True, liste_resolution=liste, _maj=lambda: None,
                           _relire_tout=lambda _r: None)
    PageImage.rafraichir(page)
    assert liste.currentIndex() == 0


def test_echap_vide_la_recherche_sans_fermer_la_page(qtbot, tmp_path):
    """Audit UI v46 : Échap dans « Rechercher un réglage » fermait toute la page des réglages."""
    from PyQt6.QtCore import Qt
    from src.ui.page_image import PageImage
    dlg, _ = _fenetre(qtbot, tmp_path)
    dlg.ouvrir_onglet("image")
    page = dlg.findChild(PageImage)
    page.recherche.setText("ombres")
    fermee = []
    dlg.rejected.connect(lambda: fermee.append(1))
    qtbot.keyClick(page.recherche, Qt.Key.Key_Escape)
    assert page.recherche.text() == "" and not fermee


def test_l_aide_en_infobulle_tient_en_paragraphe():
    """Audit UI v51 : sans la fiche, l'aide passait en infobulle d'une seule ligne de 1 336 px."""
    from src.ui.page_image import _bulle
    assert _bulle("a < b").startswith("<qt><table width='420'>") and "a &lt; b" in _bulle("a < b")


class TestCadranAuClavier:
    def test_tab_y_entre_fleches_visent_entree_choisit(self, qtbot, tmp_path):
        """f121 : les noms du cadran se cliquaient, mais Tab passait à côté (clavier, manette)."""
        from PyQt6.QtCore import Qt
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.ouvrir_onglet("difficulte")
        dlg.show()
        qtbot.waitExposed(dlg)
        cadran = dlg._panneau.cadran
        assert cadran.focusPolicy() & Qt.FocusPolicy.TabFocus
        dlg.activateWindow()
        cadran.setFocus(Qt.FocusReason.TabFocusReason)
        qtbot.waitUntil(cadran.hasFocus)
        depart = cadran.actif
        ordre = cadran._ordre()
        assert len(ordre) >= 2 and cadran._survole == depart
        touche = Qt.Key.Key_Right if ordre.index(depart) < len(ordre) - 1 else Qt.Key.Key_Left
        qtbot.keyClick(cadran, touche)
        vise = cadran._survole
        assert vise != depart
        qtbot.keyClick(cadran, Qt.Key.Key_Return)
        assert cadran.actif == vise, "Entrée choisit le nom visé"


class TestPictogrammesDuRail:
    """tra15 (refonte B, 2026-11-13) : « Jeu » portait un drapeau. reg21 : plus de « Commandes »
    ni de « Performances », entrées dans Jeu et Image ; « Fichiers », une page, en dernier."""

    def _icones(self, qtbot, tmp_path, monkeypatch, *idents):
        from src.ui import game_settings_dialog
        vues = {}
        fabrique = game_settings_dialog.pastille_rubrique
        monkeypatch.setattr(game_settings_dialog, "pastille_rubrique",
                            lambda libelle, icone: vues.setdefault(libelle, icone) and fabrique(libelle, icone))
        _fenetre(qtbot, tmp_path, *idents, ini=INI + "[Accio.Controller]\r\nPlayStation=0\r\n")
        return vues

    def test_quatre_rubriques_et_leurs_pictogrammes(self, qtbot, tmp_path, monkeypatch):
        vues = self._icones(qtbot, tmp_path, monkeypatch, "arriere_plan", "manette_playstation", "lissage",
                            "limite_fps")
        assert vues == {tr("Image"): "ecran", tr("Jeu"): "curseurs"}, "la manette et la limite d'images " \
            "ne font plus leur propre page"

    def test_la_manette_et_les_touches_sont_dans_jeu(self, qtbot, tmp_path):
        from src.ui.toggle_switch import ToggleSwitch
        dlg, _ini = _fenetre(qtbot, tmp_path, "arriere_plan", "manette_playstation",
                             ini=INI + "[Accio.Controller]\r\nPlayStation=0\r\n")
        dlg.ouvrir_onglet("jeu")
        page = dlg._defile.currentWidget()
        assert dlg._controles["manette_playstation"] in page.findChildren(ToggleSwitch)


def test_en_plein_ecran_les_pages_de_lignes_s_arretent_a_la_liste(qtbot, tmp_path):
    """Audit UI reg11 : sur Jeu, Commandes et Performances, le nom partait à 1 500 px de son
    interrupteur à 1 920 px ; ces pages s'arrêtent à la largeur de la liste de l'Image."""
    from src.ui.page_image import LARGEUR_LISTE
    from src.ui.toggle_switch import ToggleSwitch
    dlg, _ = _fenetre(qtbot, tmp_path)
    dlg.ouvrir_onglet("jeu")
    dlg.resize(1920, 1000)
    dlg.show()
    qtbot.waitExposed(dlg)
    zone = dlg._defile.currentWidget().zone   # la colonne de lignes, à gauche de la fiche (reg20)
    qtbot.waitUntil(lambda: zone.viewport().width() > 1000)
    bascules = [b for b in zone.widget().findChildren(ToggleSwitch) if b.isVisible()]
    assert bascules
    for b in bascules:
        assert b.mapTo(zone.widget(), b.rect().topRight()).x() <= LARGEUR_LISTE + 40


class TestUneSeuleLigne:
    """Audit UI reg20 : trois façons de montrer un réglage dans la même fenêtre (lignes de la page
    Image, « ? » collé au bord droit ailleurs). Une seule ligne, sans « ? », et la même fiche à droite."""

    def test_aucun_point_d_aide_et_la_ligne_de_la_page_image_partout(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QPushButton
        from src.ui.page_image import _LigneImage
        dlg, _ini = _fenetre(qtbot, tmp_path)
        toutes(dlg)
        assert not [b for b in dlg.findChildren(QPushButton) if b.text() == "?"]
        assert dlg._blocs and all(isinstance(b, _LigneImage) for b in dlg._blocs.values())

    def test_la_fiche_suit_la_ligne_survolee_et_l_infobulle_la_remplace_a_l_etroit(self, qtbot, tmp_path):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication
        from src.ui.page_image import PageAvecFiche
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.ouvrir_onglet("jeu")
        page = dlg._defile.currentWidget()
        assert isinstance(page, PageAvecFiche)
        dlg.setMinimumSize(0, 0)
        dlg.resize(1920, 1000)
        dlg.show()
        qtbot.waitExposed(dlg)
        ligne = dlg._blocs["arriere_plan"]
        QApplication.sendEvent(ligne, QEvent(QEvent.Type.Enter))
        assert page.fiche.isVisible() and page.fiche.titre.text() == ligne.libelle.text()
        assert ligne.fiche_ouverte(), "fiche à droite : pas d'infobulle qui la répète"
        dlg.resize(1000, 700)
        qtbot.waitUntil(lambda: not page.fiche.isVisible(), timeout=2000)
        assert not ligne.fiche_ouverte() and ligne.toolTip(), "à l'étroit, l'infobulle dit ce que disait la fiche"

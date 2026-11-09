"""Les finitions de la fenêtre de réglages d'un jeu (audit de l'interface, 2026-11-09) :
la remise à l'origine confirmée puis annoncée, un pied qui ne dit que ce qui sert, un
seul « Bêta » par page, le rail qui défile, les libellés qui disent un réglage."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from src.core import difficulte_presets as dp
from src.core import reglages_correctif as rc
from src.core.game_data import GameData
from src.core.i18n import set_language, tr
from src.core.reglages_table import REGLAGES
from src.ui.aide_reglage import BoutonAide
from src.ui.fenetre_message import FenetreMessage
from src.ui.fonts import cinzel_decorative

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


def _fenetre(qtbot, tmp_path, *idents, ini=INI):
    from src.ui.game_settings_dialog import GameSettingsDialog
    chemin = tmp_path / "HP6" / "d3d9.ini"
    chemin.parent.mkdir(exist_ok=True)
    if ini:
        chemin.write_bytes(ini.encode("ascii"))
    manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                              config=SimpleNamespace(install_path=tmp_path, reprise={}))
    dlg = GameSettingsDialog(_jeu(*(idents or IDENTS)), manager, lambda c: True)
    qtbot.addWidget(dlg)
    return dlg, chemin


def _quand_ouverte(action):
    """Agit sur la fenêtre modale dès qu'elle s'affiche (exec() bloque)."""
    def essayer():
        boite = QApplication.activeModalWidget()
        if isinstance(boite, FenetreMessage):
            action(boite)
        else:
            QTimer.singleShot(10, essayer)
    QTimer.singleShot(0, essayer)


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
        _quand_ouverte(regarder)
        dlg._bouton_reset.click()
        assert vus["titre"] == tr("Remettre ce jeu comme à l'installation ?")
        assert vus["objet"] == "danger" and vus["defaut"] and vus["retrait"]
        for page in ("Image", "Jeu", "Difficulté", "Performances"):
            assert page in vus["corps"], "la question nomme ce qui sera remis"
        assert ini.read_bytes() == avant
        assert not dlg._pied_notes.text().startswith("Réglages d'origine")

    def test_confirmer_remet_puis_le_pied_le_dit_quatre_secondes(self, qtbot, tmp_path):
        dlg, ini = self._avec_retouche(qtbot, tmp_path)
        avant = dlg._pied_notes.text()
        _quand_ouverte(lambda b: b.buttons()[0].click())
        dlg._bouton_reset.click()
        assert "FXAA=1" in ini.read_bytes().decode().split("\r\n")
        assert dlg._pied_notes.text() == tr("Réglages d'origine remis.")
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
        dlg.ouvrir_onglet("perfs")
        assert "ciel" not in dlg._pied_notes.text()

    def test_rien_a_dire_et_pas_de_bouton_pas_de_pied(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path, "arriere_plan", ini="")
        assert dlg._bouton_reset is None
        assert dlg._cadre_pied.isHidden() and dlg._pied_info.isHidden()

    def test_le_haut_de_difficulte_ne_redit_pas_le_quand(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert tr("Vos sauvegardes ne changent pas.") in _textes(dlg)
        assert not any("Change à tout moment" in t and "sauvegardes" in t for t in _textes(dlg))


class TestBeta:
    def test_une_seule_mention_par_page(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert _textes(dlg).count(tr("Bêta")) == 1, "Caméra, seule en bêta sur sa page, la garde"
        assert "Discord" in dlg._panneau.pastille_beta.toolTip()

    def test_la_fiche_de_difficulte_ne_le_redit_pas(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert "Discord" not in dlg._aides["degats_recus"]._corps
        assert "Discord" in dlg._aides["camera_fluide"]._corps


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

    def test_la_legende_dit_le_plus_visible(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert tr("le plus visible") in _textes(dlg) and "se voit" not in _textes(dlg)


class TestRangement:
    def test_aucun_effet_d_image_sans_famille(self):
        """Le filet « Autres » reste pour un réglage futur : aucun n'y tombe aujourd'hui."""
        from src.ui.reglages_rubriques import _GROUPES_AMBIANCE, _GROUPES_EFFETS
        ranges = {i for _nom, idents in (*_GROUPES_EFFETS, *_GROUPES_AMBIANCE) for i in idents}
        assert {r.ident for r in REGLAGES.values() if r.onglet == "image"} <= ranges

    def test_la_langue_du_menu_est_dans_demarrage(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        textes = _textes(dlg)
        assert tr("Démarrage").upper() in textes and tr("En arrière-plan").upper() in textes
        assert tr("Dans le jeu").upper() not in textes
        assert "langue_menu" in dlg._controles


class TestMiseEnPage:
    def test_le_titre_de_page_n_est_plus_en_decorative(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        titre = next(lb for lb in dlg.findChildren(QLabel) if lb.text() == tr("Image"))
        assert titre.font().family() != cinzel_decorative(20).family() and titre.font().bold()

    def test_les_en_tetes_voisins_ont_la_meme_hauteur(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.ouvrir_onglet("image")
        dlg.show()
        qtbot.waitExposed(dlg)
        affichage = next(lb for lb in dlg.findChildren(QLabel) if lb.text() == tr("Affichage").upper())
        effets = next(lb for lb in dlg.findChildren(QLabel) if lb.text() == tr("Chaque effet").upper())
        assert affichage.height() == effets.parentWidget().height()

    def test_le_rail_defile_au_lieu_de_se_tasser(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.setMinimumSize(0, 0)
        dlg.resize(980, 300)   # quatre rubriques tiennent en 400 px : il faut moins
        dlg.show()
        qtbot.waitExposed(dlg)
        qtbot.waitUntil(lambda: dlg._zone_rail.verticalScrollBar().maximum() > 0, timeout=2000)
        assert all(b.height() == 44 for b in dlg._onglets.values())
        assert dlg._titre.height() >= dlg._titre.heightForWidth(dlg._titre.width())

    def test_le_rond_d_aide_a_une_vraie_surface_de_clic(self):
        aide = BoutonAide("Titre", "<p>x</p>")
        assert aide.width() == 28 and aide.height() == 28
        assert "margin: 5px" in aide.styleSheet(), "le rond visible reste de 18 px"

"""Une VRAIE MainWindow : l'engrenage de la fiche et la page des réglages du jeu.

Config temporaire (CONFIG_FILE_PATH patché), `_start_update_check` neutralisé,
autoplay=False. Fixtures `make_window*` dans `conftest.py`.
"""

import pytest

pytest.importorskip("pytestqt")


@pytest.mark.usefixtures("registre_atteignable")
class TestEngrenageReglagesDuJeu:
    """La langue n'était atteignable que par le segment doré de la ligne méta.

    Il se lit très bien mais ne s'annonce pas comme cliquable : un réglage qu'il
    faut deviner n'existe pas. L'engrenage, lui, le dit — et c'est le point
    d'entrée des réglages graphiques à venir, d'où un MENU et non un second
    sélecteur.
    """

    @staticmethod
    def _poser(win, jeu, etat):
        win.manager._states[jeu.id] = etat
        win._detail.set_game(jeu)
        win._detail._action_panel.refresh()
        return win._detail._action_panel

    def test_present_sur_un_jeu_multilingue_installe(self, make_window_multilingue):
        from src.core.game_manager import GameState
        win, jeu = make_window_multilingue()
        panneau = self._poser(win, jeu, GameState.INSTALLED)
        assert panneau._btn_reglages is not None
        # DESSINÉ, plus écrit : U+2699 partait en couleur sous Windows (65 % de
        # pixels colorés, mesuré le 2026-08-26, contre 0 % pour une lettre
        # témoin). Le bouton n'a donc plus de texte du tout.
        from src.ui.icon_button import IconButton
        assert isinstance(panneau._btn_reglages, IconButton)
        assert panneau._btn_reglages.icone() == "reglages"

    def test_present_sur_un_jeu_sans_langue(self, make_window_multilingue):
        """Il n'apparaissait qu'avec une langue à choisir, donc sur HP1 seul :
        les fichiers du jeu, les captures et les réglages du correctif de HP4-HP7b
        étaient inatteignables (Ludo, 2026-09-27). La fenêtre n'est jamais vide :
        « Fichiers du jeu » y est toujours, et la rubrique « Langue » s'efface."""
        from src.core.game_manager import GameState
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, _ = make_window_multilingue()
        autre = win.manager.get_games()[1].game
        assert win.manager.game_language(autre) is None
        assert self._poser(win, autre, GameState.INSTALLED)._btn_reglages is not None
        dlg = GameSettingsDialog(autre, win.manager, lambda code: True,
                                 actions=[("Ouvrir le dossier du jeu", lambda: None)], parent=win)
        assert not dlg._boutons
        from PyQt6.QtWidgets import QLabel
        textes = " ".join(lb.text() for lb in dlg.findChildren(QLabel))
        assert "Langue du jeu" not in textes and "une seule langue" not in textes

    def test_le_choix_retenu_se_voit(self, make_window_multilingue):
        """Le rond natif coché se remplissait de sombre : sur fond bleu nuit, la
        langue RETENUE était la seule invisible (Ludo, 2026-09-27). Rendu réel :
        la rangée cochée doit porter de l'or, les autres non."""
        from PyQt6.QtGui import QColor
        from src.core.game_manager import GameState
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        dlg = GameSettingsDialog(jeu, win.manager, lambda code: True, parent=win)
        dlg.show()

        def or_(radio):
            img = radio.grab().toImage()
            n = 0
            for x in range(0, img.width(), 2):
                for y in range(0, img.height(), 2):
                    c = QColor(img.pixel(x, y))
                    if c.red() > 150 and c.green() > 110 and c.blue() < 90:
                        n += 1
            return n

        courant = win.manager.game_language(jeu)
        coche = or_(dlg._boutons[courant])
        autres = [or_(b) for c, b in dlg._boutons.items() if c != courant]
        assert coche > 40, coche
        assert all(a < coche / 4 for a in autres), (coche, autres)

    def test_le_folio_dans_la_ligne_d_indices(self, make_window_multilingue, monkeypatch):
        """Depuis Mes années seulement, le folio était « horrible à trouver » ;
        en bouton près de l'engrenage, il faisait passer le temps de jeu sous
        la rangée (Ludo, 2026-10-14). Il est un lien à côté de la version."""
        from src.ui.icon_button import IconButton
        from src.core import folio
        from src.core.game_manager import GameState
        from src.ui.folio_page import FolioPage
        win, jeu = make_window_multilingue()
        autre = win.manager.get_games()[1].game
        monkeypatch.setattr(folio, "JEUX", (jeu.id,))
        self._poser(win, autre, GameState.INSTALLED)
        assert 'href="folio"' not in win._detail._info._indices.text(),             "seulement là où le folio sait lire"
        panneau = self._poser(win, jeu, GameState.INSTALLED)
        win._detail._info.rafraichir_indices(jeu)
        assert panneau.findChild(IconButton, "btnFolio") is None, "plus de bouton dans la rangée"
        assert 'href="folio"' in win._detail._info._indices.text()
        win._detail._info._on_meta_link("folio")
        assert isinstance(win._pages.page, FolioPage) and win._pages.page.game is jeu

    def test_pas_de_folio_sur_un_jeu_non_installe(self, make_window_multilingue, monkeypatch):
        from src.core import folio
        from src.core.game_manager import GameState
        win, jeu = make_window_multilingue()
        monkeypatch.setattr(folio, "JEUX", (jeu.id,))
        self._poser(win, jeu, GameState.NOT_INSTALLED)
        win._detail._info.rafraichir_indices(jeu)
        assert 'href="folio"' not in win._detail._info._indices.text()

    def test_absent_quand_le_jeu_n_est_pas_installe(self, make_window_multilingue):
        """Rien à régler sur un jeu qu'on n'a pas encore."""
        from src.core.game_manager import GameState
        win, jeu = make_window_multilingue()
        assert self._poser(win, jeu, GameState.NOT_INSTALLED)._btn_reglages is None

    def test_la_fenetre_porte_les_langues_disponibles(self, make_window_multilingue):
        """La fenêtre est construite SANS `exec()` : l'ouvrir pour de vrai
        bloquerait la suite de tests jusqu'à ce qu'un humain clique."""
        from src.core.game_manager import GameState
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        dlg = GameSettingsDialog(jeu, win.manager, lambda code: True, parent=win)
        proposables = [lg.code for lg in win.manager.langues_disponibles(jeu)]
        assert set(dlg._boutons) == set(proposables)
        courant = win.manager.game_language(jeu)
        assert dlg._boutons[courant].isChecked()

    def test_la_rubrique_affichage_est_verrouillee(self, make_window_multilingue):
        """« Bientôt » doit être ANNONCÉ, pas absent : quelqu'un qui cherche la
        résolution doit comprendre que ce n'est pas lui qui n'a pas trouvé."""
        from PyQt6.QtWidgets import QRadioButton
        from src.core.game_manager import GameState
        from src.core.i18n import tr
        from src.ui.game_settings_dialog import GameSettingsDialog, _A_VENIR

        from dataclasses import replace

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        # Un jeu dont le catalogue ne dit pas où écrire la résolution.
        sans = replace(jeu, resolution=None)
        dlg = GameSettingsDialog(sans, win.manager, lambda code: True, parent=win)
        desactives = [b.text() for b in dlg.findChildren(QRadioButton)
                      if not b.isEnabled()]
        for nom in _A_VENIR:
            assert tr(nom) in desactives, nom
        assert dlg._choix_resolution is None

    def test_la_resolution_se_regle_quand_le_catalogue_dit_ou(self, make_window_multilingue):
        """HP1/HP2 (bloc `resolution`) : la rubrique devient un vrai réglage, et
        plus aucun choix grisé sans « BIENTÔT » ne traîne dessous (règle 119)."""
        from dataclasses import replace
        from PyQt6.QtWidgets import QRadioButton
        from src.core.catalogue_blocs import Resolution
        from src.core.game_manager import GameState
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        avec = replace(jeu, resolution=Resolution(
            "%DOCUMENTS%\\Harry Potter\\HP.ini", "WinDrv.WindowsClient",
            "WindowedViewportX", "WindowedViewportY"))
        dlg = GameSettingsDialog(avec, win.manager, lambda code: True, parent=win)
        assert dlg._choix_resolution is not None and dlg._choix_resolution.count() >= 1
        assert not [b for b in dlg.findChildren(QRadioButton) if not b.isEnabled()]

    def test_la_rubrique_affichage_previent_du_piege_du_menu_du_jeu(
            self, make_window_multilingue):
        """HP1 a HP3 ne livrent qu'UNE carte de rendu (`d3d11drv.dll` ; ni
        SoftDrv, ni D3DDrv, ni OpenGLDrv - verifie le 2026-09-20 sur une vraie
        installation). Le menu video du moteur, lui, les propose toutes : en
        choisir une autre donne `RenDev` nul, donc « Assertion failed: RenDev
        [WinViewport.cpp:351] » a chaque demarrage suivant.

        Cette rubrique est justement ou va celui qui cherche la resolution.
        """
        import dataclasses

        from PyQt6.QtWidgets import QLabel
        from src.core.game_manager import GameState
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, jeu = make_window_multilingue()
        jeu = dataclasses.replace(jeu, display_locked=True)
        self._poser(win, jeu, GameState.INSTALLED)
        dlg = GameSettingsDialog(jeu, win.manager, lambda code: True, parent=win)
        textes = " ".join(lb.text() for lb in dlg.findChildren(QLabel))
        assert "options vid" in textes and "redémarrer" in textes

    def test_les_jeux_dont_les_reglages_marchent_ne_recoivent_aucune_note(
            self, make_window_multilingue):
        """A partir de HP5 le moteur change et son menu video fonctionne.
        Afficher la mise en garde partout serait afficher un etat NORMAL."""
        import dataclasses

        from PyQt6.QtWidgets import QLabel
        from src.core.game_manager import GameState
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, jeu = make_window_multilingue()
        jeu = dataclasses.replace(jeu, display_locked=False)
        self._poser(win, jeu, GameState.INSTALLED)
        dlg = GameSettingsDialog(jeu, win.manager, lambda code: True, parent=win)
        textes = " ".join(lb.text() for lb in dlg.findChildren(QLabel))
        assert "options vid" not in textes

    def test_un_choix_refuse_remet_le_bouton_droit(self, make_window_multilingue):
        """Laisser la sélection sur un choix que le registre n'a pas pris
        afficherait une langue que le jeu n'a pas."""
        from src.core.game_manager import GameState
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        courant = win.manager.game_language(jeu)
        dlg = GameSettingsDialog(jeu, win.manager, lambda code: False, parent=win)
        autre = next(c for c in dlg._boutons if c != courant)
        dlg._boutons[autre].setChecked(True)
        assert dlg._boutons[courant].isChecked()
        assert not dlg._boutons[autre].isChecked()

    def test_l_engrenage_ouvre_bien_la_fenetre(self, make_window_multilingue, monkeypatch):
        from src.core.game_manager import GameState
        from src.ui import game_detail_handlers as gdh
        from src.ui.game_settings_dialog import GameSettingsDialog

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        gdh.on_game_settings(win._detail)
        # Une page à la place de la fiche, plus une fenêtre (2026-10-09).
        assert isinstance(win._pages.page, GameSettingsDialog)
        win._pages.fermer()
        assert win._pages.page is None

    def test_les_versions_s_ouvrent_en_page(self, make_window_multilingue):
        """Plus une boîte de 550 × 500 posée sur la fiche (2026-10-14)."""
        from src.core.game_manager import GameState
        from src.ui import game_detail_handlers as gdh
        from src.ui.versions_dialog import VersionsDialog

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        gdh.on_versions_clicked(win._detail)
        page = win._pages.page
        assert isinstance(page, VersionsDialog)
        assert not page.isWindow()
        page.reject()   # Échap
        assert win._pages.page is None

    def test_contribuer_ouvre_l_atelier_en_page(self, make_window_multilingue):
        """L'appel aux artistes vivait au bout d'À propos ; il est dans la barre."""
        from src.ui.atelier_page import AtelierPage

        win, _jeu = make_window_multilingue()
        win._title_bar.contribuer.click()
        page = win._pages.page
        assert isinstance(page, AtelierPage)
        assert not page.isWindow()
        page.reject()
        assert win._pages.page is None

    def test_la_pastille_de_la_fiche_ouvre_les_jaquettes(self, make_window_multilingue, monkeypatch):
        from src.core import atelier
        from src.ui import atelier_page
        from src.ui.atelier_page import AtelierPage

        win, jeu = make_window_multilingue()
        pastille = win._detail._pastille_atelier
        pastille._mesures = [atelier.Besoin(atelier.court(jeu.id), "Fond d'écran", "",
                                            atelier.CHERCHE, atelier.FOND, True)]
        monkeypatch.setattr(atelier_page, "besoins_mesures", lambda _jeux: pastille._mesures)
        pastille.pour(jeu.id, [jeu])
        assert not pastille.isHidden()
        pastille.click()
        page = win._pages.page
        assert isinstance(page, AtelierPage) and page.metier_affiche == "jaquettes"
        page.reject()


    def test_la_rubrique_fichiers_expose_le_clic_droit(self, make_window_multilingue):
        """« Gérer les versions » et « Vérifier / réparer » n'étaient
        atteignables qu'au clic droit — le défaut corrigé pour la langue."""
        from src.core.game_manager import GameState
        from src.core.i18n import tr
        from src.ui import game_detail_handlers as gdh

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        libelles = [lib for lib, _ in gdh._actions_fichiers(win._detail, jeu)]
        assert tr("Gérer les versions") in libelles
        assert tr("Vérifier / réparer les fichiers") in libelles
        assert tr("Ouvrir le dossier du jeu") in libelles

    def test_desinstaller_vit_dans_la_rubrique_fichiers(self, make_window_multilingue, monkeypatch):
        """ACT-055 : plus de DÉSINSTALLER dans la rangée de la fiche, il passait
        avant l'engrenage. On le trouve sous « Fichiers du jeu », et il mène
        toujours à la confirmation."""
        from PyQt6.QtWidgets import QPushButton
        from src.core.game_manager import GameState
        from src.core.i18n import tr
        from src.ui import game_detail_handlers as gdh

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.INSTALLED)
        panneau = win._detail._action_panel
        assert panneau.findChild(QPushButton, "btnUninstall") is None
        actions = gdh._actions_fichiers(win._detail, jeu)
        libelle, rappel = actions[-1]
        assert libelle == tr("Désinstaller le jeu")
        appels = []
        monkeypatch.setattr(gdh, "on_uninstall", lambda view: appels.append(view))
        rappel()
        assert appels == [win._detail]

    def test_rien_a_reparer_sur_un_jeu_absent(self, make_window_multilingue):
        """Réparer un jeu non installé n'a pas de sens, et ouvrir son dossier
        serait une erreur de plus à expliquer."""
        from src.core.game_manager import GameState
        from src.core.i18n import tr
        from src.ui import game_detail_handlers as gdh

        win, jeu = make_window_multilingue()
        self._poser(win, jeu, GameState.NOT_INSTALLED)
        libelles = [lib for lib, _ in gdh._actions_fichiers(win._detail, jeu)]
        assert libelles == [tr("Gérer les versions")]

    def test_le_dossier_ouvert_est_celui_de_l_executable(self, make_window_multilingue,
                                                        monkeypatch, tmp_path):
        """Depuis que HP7 range ses fichiers dans `pc`, la racine
        d'installation et le dossier du jeu ont divergé."""
        import dataclasses
        from src.ui import game_detail_handlers as gdh

        win, jeu = make_window_multilingue()
        jeu = dataclasses.replace(jeu, executable="HP7/pc/hp7.exe")
        cible = win.manager.config.install_path / "HP7" / "pc"
        cible.mkdir(parents=True, exist_ok=True)
        ouverts = []
        from src.ui import fichiers_manquants
        monkeypatch.setattr(fichiers_manquants, "open_local_path", lambda p: ouverts.append(p))
        gdh._ouvrir_dossier_du_jeu(win._detail, jeu)
        assert ouverts == [str(cible)]

    def test_le_pictogramme_est_a_presentation_texte(self):
        """U+2699 tombe en repli MONOCHROME et suit le setPen. Les emoji
        couleur (⚡ ✨ 🎃) y sont insensibles et sont écartés partout ailleurs
        dans le projet — celui-ci ne doit pas rouvrir la porte."""
        import unicodedata
        assert unicodedata.name("⚙") == "GEAR"
        assert ord("⚙") < 0x1F000

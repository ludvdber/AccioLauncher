"""Tests d'intégration offscreen — une VRAIE MainWindow pilotée par simulation :
le démarrage, le clavier, les pages et la fermeture.

Config temporaire (CONFIG_FILE_PATH patché), `_start_update_check` neutralisé,
autoplay=False. Fixtures `make_window*` dans `conftest.py`.
"""

import contextlib
import re
import sys

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QEvent, QObject, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402

from src.core.config import APP_VERSION  # noqa: E402
from tests.fenetre_commune import (  # noqa: E402
    _CATALOG, _IDS,
)


class TestHeroDynamique:
    def test_opens_on_last_played_game(self, make_window):
        target = _IDS[2]
        win = make_window(last_played={target: "2026-06-10"},
                          playtime_seconds={target: 3600})
        assert win._detail.game.id == target
        assert win._carousel.current_index == 2

    def test_defaults_to_first_game_without_history(self, make_window):
        win = make_window()
        assert win._detail.game.id == _IDS[0]
        assert win._carousel.current_index == 0

    def test_le_carrousel_suit_la_fiche_apres_maj_du_catalogue(self, make_window):
        """Scénario de la capture : premier lancement APRÈS une mise à jour.

        La fiche s'ouvre sur le dernier jeu joué, puis le catalogue distant
        arrive et la bande est reconstruite. Les deux doivent encore désigner
        le MÊME jeu — on voyait HP1 surligné sous HP6 affiché.
        """
        target = _IDS[5]
        win = make_window(last_played={target: "2026-06-10"},
                          playtime_seconds={target: 3600})
        assert win._detail.game.id == target

        win._on_catalog_updated(_CATALOG)

        assert win._detail.game.id == target
        assert win._carousel.current_game_id() == target
        assert win._carousel.current_index == 5
        surlignes = [i for i, item in enumerate(win._carousel._items) if item.selected]
        assert surlignes == [5]

    def test_la_bande_reste_navigable_apres_maj_du_catalogue(self, make_window):
        """Et le clic sur une autre vignette bascule toujours la fiche."""
        target = _IDS[5]
        win = make_window(last_played={target: "2026-06-10"},
                          playtime_seconds={target: 3600})
        win._on_catalog_updated(_CATALOG)
        win._carousel.select(0)
        assert win._detail.game.id == _IDS[0]
        assert win._carousel.current_index == 0


class TestKeyboardNav:
    def test_arrows_navigate_even_with_button_focus(self, make_window, qtbot):
        win = make_window()
        win.show()
        win.activateWindow()
        qtbot.waitUntil(win.isActiveWindow, timeout=2000)
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        assert win.eventFilter(win, ev) is True  # consommé par _handle_global_key
        assert win._carousel.current_index == 1
        ev_left = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
        assert win.eventFilter(win, ev_left) is True
        assert win._carousel.current_index == 0

    def test_other_keys_not_consumed(self, make_window, qtbot):
        win = make_window()
        win.show()
        win.activateWindow()
        qtbot.waitUntil(win.isActiveWindow, timeout=2000)
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
        assert win._handle_global_key(ev) is False


class TestNouveautesAuDemarrage:
    """La page des nouveautés, une fois, au premier lancement d'une version plus récente."""

    def test_s_ouvre_apres_une_mise_a_jour(self, make_window):
        from src.ui.nouveautes_page import NouveautesPage
        win = make_window(version_lancee="1.1.5")
        assert isinstance(win._pages.page, NouveautesPage)
        win._pages.fermer()
        assert win._pages.page is None

    def test_pas_au_premier_lancement(self, make_window):
        win = make_window()   # config neuve : elle porte déjà la version courante
        assert win._pages.page is None

    def test_pas_deux_fois(self, make_window):
        win = make_window(version_lancee="1.1.5")
        win._pages.fermer()
        win._maybe_thank_milestone()   # note la version lancée, comme au démarrage
        assert win.config.version_lancee == APP_VERSION
        from src.core import nouveautes
        assert not nouveautes.a_montrer(win.config.version_lancee)

    def test_a_propos_la_rouvre(self, make_window):
        from src.ui.nouveautes_page import NouveautesPage
        win = make_window()
        win._on_settings()
        win._pages.page.nouveautes_demandees.emit()
        assert isinstance(win._pages.page, NouveautesPage)


class TestKofiMilestone:
    """Le merci unique vient à la première mise à jour du launcher installée
    (ACT-072, 2026-10-09), plus au cap des 2 h de jeu : on remercie pour le
    travail du projet, pas pour les heures passées dans les jeux."""

    def test_toast_une_seule_fois_apres_une_mise_a_jour(self, make_window):
        win = make_window(version_lancee="1.1.5")
        win.show()
        assert win.config.kofi_milestone_thanked is False

        win._maybe_thank_milestone()
        assert win.config.kofi_milestone_thanked is True
        assert win.config.version_lancee == APP_VERSION
        assert win._toast.isVisible()
        assert APP_VERSION in win._toast.text()
        assert "caf" in win._toast.text()          # message « célébration », pas de nag
        assert win._toast._on_click is not None     # cliquable -> ouvre Ko-fi

        win._toast.hide()
        win.config.version_lancee = "1.1.5"   # même une autre mise à jour plus tard
        win._maybe_thank_milestone()  # une seule fois dans la vie du launcher
        assert not win._toast.isVisible()

    def test_config_d_avant_la_1_1_6_compte_comme_une_mise_a_jour(self, make_window):
        win = make_window(version_lancee="")
        win.show()
        win._maybe_thank_milestone()
        assert win.config.kofi_milestone_thanked is True

    def test_les_heures_de_jeu_ne_declenchent_plus_rien(self, make_window):
        """Premier lancement (config neuve) et beaucoup de jeu : pas de merci."""
        win = make_window(playtime_seconds={_IDS[0]: 50 * 3600})
        win.show()
        win._maybe_thank_milestone()
        assert win.config.kofi_milestone_thanked is False
        assert not win._toast.isVisible()

    def test_deja_remercie_au_cap_des_2_h(self, make_window):
        win = make_window(version_lancee="1.1.5", kofi_milestone_thanked=True)
        win.show()
        win._maybe_thank_milestone()
        assert not win._toast.isVisible()
        assert win.config.version_lancee == APP_VERSION

    def test_retour_en_arriere_pas_de_merci(self, make_window):
        win = make_window(version_lancee="9.0.0")
        win.show()
        win._maybe_thank_milestone()
        assert win.config.kofi_milestone_thanked is False

    def test_le_merci_cede_la_place_a_une_mise_a_jour_de_jeu(self, make_window, monkeypatch):
        win = make_window(version_lancee="1.1.5")
        win.show()
        monkeypatch.setattr(win, "_notify_game_updates", lambda: True)
        win._toasts_du_demarrage()
        assert win.config.kofi_milestone_thanked is False   # il attend son tour
        assert win.config.version_lancee == "1.1.5"


class TestSeasonLive:
    def test_les_particules_ne_passent_pas_sur_la_barre_du_haut(
            self, make_window, mise_en_page_stable):
        """Elles passaient devant les onglets et les boutons de la fenêtre."""
        win = make_window()
        win.show()
        win.resize(1200, 800)
        mise_en_page_stable(win)
        barre = win._title_bar
        bas_barre = barre.mapTo(win, barre.rect().bottomLeft()).y()
        assert win._particles.geometry().top() > bas_barre
        assert win._particles.geometry().bottom() == win.centralWidget().geometry().bottom()

    def test_apply_season_reseeds_particles(self, make_window):
        win = make_window()
        win._particles.resize(800, 600)
        # L'ambiance de DÉPART est posée explicitement. Elle était implicite,
        # et le test supposait alors que la fenêtre s'ouvre toujours sur des
        # particules qui montent — vrai tant que l'Almanach ne connaissait que
        # deux dates, faux dès qu'un mois entier porte une ambiance qui TOMBE
        # (la rentrée). Un test qui dépend de la date du jour échoue un mois
        # sur cinq, sans que rien n'ait changé dans le code.
        win._particles.apply_season("aucune")
        win._particles._ensure_particles()
        assert all(p.speed_y < 0 for p in win._particles._particles)  # ça monte

        win._particles.apply_season("noel")
        assert win._particles._particles == []  # re-semées au tick suivant
        win._particles._ensure_particles()
        assert all(p.speed_y > 0 for p in win._particles._particles)  # ça tombe

        win._particles.apply_season("aucune")
        win._particles._ensure_particles()
        assert all(p.speed_y < 0 for p in win._particles._particles)


class TestMuteLive:
    def test_settings_mute_applies_to_running_video(self, make_window):
        """Régression : « Couper le son » ne touchait que la PROCHAINE vidéo."""
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        dlg.config_changed.connect(win._on_config_changed)
        dlg.construire_rubrique(1)   # Affichage, bâtie à sa première visite

        dlg._tgl_mute.setChecked(True)
        dlg._on_setting_changed()  # ToggleSwitch n'émet que sur clic souris

        assert win.config.mute_videos is True
        assert win._detail._video.muted is True  # appliqué EN DIRECT
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()


class TestSettingsRestart:
    def test_restart_button_appears_on_theme_change(self, make_window, qtbot):
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        dlg.show()
        dlg._nav.setCurrentRow(1)  # page Affichage (où vit le combo thème)
        assert not dlg._theme_restart.isVisible()
        dlg._theme_combo.setCurrentIndex(1)  # Gryffondor
        assert dlg._theme_restart.isVisible()
        assert win.config.theme == "gryffondor"

        with qtbot.waitSignal(dlg.restart_requested, timeout=1000):
            dlg._theme_restart.click()
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()

    def test_changer_de_theme_ne_rogne_aucune_ligne(self, make_window, qtbot, mise_en_page_stable):
        """« Redémarrer maintenant » et l'aide apparaissent : la page Affichage ne tenait plus à la
        taille minimale, Qt accordait aux lignes MOINS que leur hauteur et rognait les textes par le
        bas (« Supprimer », les listes déroulantes — capture de Ludo, 2026-09-27). La page défile."""
        from PyQt6.QtWidgets import QComboBox, QPushButton
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        dlg.resize(dlg.minimumSize())
        dlg.show()
        dlg._nav.setCurrentRow(1)
        dlg._theme_combo.setCurrentIndex(1)
        qtbot.waitUntil(lambda: dlg._theme_restart.isVisible(), timeout=1000)
        mise_en_page_stable(dlg)
        page = dlg._pages.currentWidget()
        ecrases = [(w.text() if hasattr(w, "text") else w.currentText(), w.height(), w.sizeHint().height())
                   for w in page.widget().findChildren((QPushButton, QComboBox))
                   if w.isVisible() and w.height() < w.sizeHint().height()]
        assert not ecrases, ecrases
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()

    def test_revenir_a_la_langue_de_depart_cache_redemarrer(self, make_window, qtbot):
        """Aller-retour de langue : rien à appliquer, plus de « Redémarrer »
        (Ludo, 2026-10-14). Pareil pour le thème."""
        from src.core.i18n import get_language
        from src.ui.settings_panel import SettingsDialog
        from src.ui.theme import current as theme_courant
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        dlg.show()
        combo = dlg._lang_combo
        autre = next(i for i in range(combo.count()) if combo.itemData(i) != get_language())
        combo.setCurrentIndex(autre)
        assert dlg._lang_restart.isVisible()
        combo.setCurrentIndex(combo.findData(get_language()))
        assert not dlg._lang_restart.isVisible()

        dlg._nav.setCurrentRow(1)
        themes = dlg._theme_combo
        themes.setCurrentIndex(themes.findData("gryffondor"))
        assert dlg._theme_restart.isVisible()
        themes.setCurrentIndex(themes.findData(theme_courant().id))
        assert not dlg._theme_restart.isVisible()
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()

    def test_rouverte_apres_un_changement_elle_le_redit(self, make_window, qtbot):
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        win.config.theme = "serpentard"
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        dlg.show()
        dlg._nav.setCurrentRow(1)
        assert dlg._theme_restart.isVisible()
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()

    def test_season_change_emits_resolved_season(self, make_window, qtbot):
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        dlg.construire_rubrique(1)
        with qtbot.waitSignal(dlg.season_changed, timeout=1000) as blocker:
            dlg._season_combo.setCurrentIndex(3)  # Noël
        assert blocker.args == ["noel"]
        assert win.config.season == "noel"
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()


class TestParametresAuPremierClic:
    """Seule la rubrique Général se bâtit à l'ouverture (Ludo, 2026-10-14 :
    « charger la page paramètre est toujours lente ») ; 0,82 s → 0,22 s à froid."""

    def test_les_autres_rubriques_attendent_leur_visite(self, make_window, qtbot):
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        assert dlg._construites == {0}
        assert dlg._theme_hint is None
        dlg._nav.setCurrentRow(2)
        assert dlg._construites == {0, 2}
        assert dlg._pages.currentIndex() == 2
        assert dlg._versions_label is not None
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()

    def test_un_interrupteur_n_ecrase_pas_ceux_des_rubriques_pas_construites(self, make_window, qtbot):
        """L'enregistrement relisait TOUS les interrupteurs : il ne relit que
        ceux qui existent, et laisse les autres champs tels quels."""
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        win.config.mute_videos = True
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        dlg._tgl_copies.setChecked(not win.config.copies_sauvegardes)
        attendu = dlg._tgl_copies.isChecked()
        dlg._on_setting_changed()
        assert win.config.copies_sauvegardes is attendu
        assert win.config.mute_videos is True
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()

    def test_un_message_de_mise_a_jour_batit_sa_rubrique(self, make_window, qtbot):
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        dlg.show_update_status("Launcher à jour")
        assert dlg._update_status.text() == "Launcher à jour"
        assert dlg._pages.currentIndex() == 0, "la rubrique visible ne change pas"
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()


class TestAucuneFenetreParasite:
    """Ouvrir une page ne fait naître AUCUNE fenêtre à côté.

    `LigneReglage` rendait sa description visible avant de l'avoir rattachée :
    un widget sans parent rendu visible devient une fenêtre. Huit petites
    fenêtres clignotaient à l'ouverture des Paramètres, et l'ouverture
    traînait (Ludo, 2026-10-14).
    """

    def test_parametres_annees_et_reglages_des_jeux(self, make_window, qtbot):
        from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow
        from src.ui import game_detail_handlers

        class _Espion(QObject):
            vues: list = []

            def eventFilter(self, obj, ev):
                if (ev.type() == QEvent.Type.Show and obj.isWidgetType() and obj.isWindow()
                        and not isinstance(obj, (QDialog, QMainWindow))):
                    self.vues.append(f"{type(obj).__name__} {getattr(obj, 'text', str)()!r}")
                return False

        win = make_window()
        win.show()
        qtbot.waitExposed(win)
        espion = _Espion()
        QApplication.instance().installEventFilter(espion)
        try:
            win._on_settings()
            for rang in range(win._pages.page._nav.count()):
                win._pages.page._nav.setCurrentRow(rang)
            win._pages.fermer()
            win._on_stats()
            win._pages.fermer()
            game_detail_handlers.on_game_settings(win._detail)
            win._pages.fermer()
            # Même défaut, même cause, dans la fenêtre « Désinstaller ».
            from src.ui.desinstallation_dialog import DesinstallationDialog
            dlg = DesinstallationDialog(win.config.install_path, 0, True, win)
            dlg.show()
            QApplication.processEvents()
            dlg.close()
        finally:
            QApplication.instance().removeEventFilter(espion)
        assert espion.vues == []


class TestOngletsDuHaut:
    """Rapportés par la vérification du 2026-10-14."""

    def test_bibliotheque_sans_page_reste_soulignee(self, make_window, qtbot):
        from src.ui.title_bar import BIBLIOTHEQUE
        win = make_window()
        onglet = win._title_bar.onglet(BIBLIOTHEQUE)
        qtbot.mouseClick(onglet, Qt.MouseButton.LeftButton)
        assert onglet.isChecked(), "plus aucun onglet n'était souligné"

    def test_recliquer_l_onglet_ouvert_ne_rebatit_pas_la_page(self, make_window, qtbot):
        from src.ui.title_bar import PARAMETRES
        win = make_window()
        onglet = win._title_bar.onglet(PARAMETRES)
        qtbot.mouseClick(onglet, Qt.MouseButton.LeftButton)
        page = win._pages.page
        page._nav.setCurrentRow(2)
        qtbot.mouseClick(onglet, Qt.MouseButton.LeftButton)
        assert win._pages.page is page and page._nav.currentRow() == 2
        assert onglet.isChecked()
        win._pages.fermer()

    def test_echap_depuis_un_onglet_ferme_la_page(self, make_window, qtbot):
        from src.ui.title_bar import ANNEES
        win = make_window()
        win.show()
        qtbot.waitExposed(win)
        onglet = win._title_bar.onglet(ANNEES)
        qtbot.mouseClick(onglet, Qt.MouseButton.LeftButton)
        assert win._pages.page is not None
        qtbot.keyClick(onglet, Qt.Key.Key_Escape)
        assert win._pages.page is None


class TestEffetsDerriereUnePage:
    def test_un_retour_de_partie_ne_relance_rien_derriere_une_page(self, make_window, qtbot):
        """Particules et fond de la fiche cachés par la page : les relancer au
        retour d'un jeu, c'était du calcul pour rien jusqu'à la fermeture."""
        win = make_window()
        win.show()
        qtbot.waitExposed(win)
        win.pause_all_effects()
        win._on_stats()
        win.resume_all_effects()
        assert not win._particles._ticking
        win._pages.fermer()
        assert win._particles._ticking, "la page fermée, tout repart"


class TestOnboardingImport:
    def test_perform_imports_moves_game(self, qtbot, tmp_path, monkeypatch):
        from src.ui.onboarding import OnboardingDialog, detect_installed_games
        from pathlib import Path

        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        from src.core.config import Config

        game = _CATALOG.games[0]
        parts = Path(game.executable).parts
        src_root = tmp_path / "vieux_jeux"
        (src_root / Path(*parts[:-1])).mkdir(parents=True)
        (src_root / Path(*parts)).write_bytes(b"exe")

        found = detect_installed_games(src_root, list(_CATALOG.games))
        assert [g.id for g, _ in found] == [game.id]

        (tmp_path / "launcher_games").mkdir()
        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg.install_path = tmp_path / "launcher_games"
        dlg.choisir_langue("fr")
        dlg._quitter_la_langue()
        # « Chercher ailleurs… » sans la boîte de dialogue du système.
        dlg._dossier_cherche = src_root
        dlg._regler_jeux()
        assert [g.id for g, _ in dlg.checked_imports()] == [game.id]

        config = Config(install_path=tmp_path / "launcher_games",
                        cache_path=tmp_path / "launcher_games" / ".cache")
        dlg.perform_imports(config)

        assert (tmp_path / "launcher_games" / Path(*parts)).exists()  # déplacé
        assert config.installed_versions[game.id] == game.recommended_version
        assert not (src_root / parts[0]).exists()  # source vidée (rename)


class TestConfirmationAvantDeFermer:
    """Fermer pendant un telechargement ou une installation demande confirmation.

    Demande de Ludo (2026-08-28) : « dans le doute ou la personne a oublie ».
    Le point non evident est qu'il n'y a qu'UN point de passage a garder, et
    c'est mesure : sous Qt 6.11, `QApplication.quit()` envoie un QCloseEvent
    aux fenetres et un `ignore()` ANNULE la sortie. La croix, Alt+F4 et le
    « Quitter » du menu du tray convergent donc tous sur `closeEvent`. Une
    garde posee sur un seul de ces chemins serait pire que pas de garde : elle
    apprendrait a l'utilisateur qu'il est protege.

    **Deux pieges d'outillage, tous deux payes en ecrivant ces tests.**

    · L'etat « occupe » doit etre RENDU dans le corps du test, jamais dans un
      finaliseur de fixture : `pytest-qt` ferme les widgets qu'on lui a confies
      depuis son hook `pytest_runtest_teardown`, qui passe AVANT les
      finaliseurs. La fenetre se refermait donc en etat occupe, la boite
      modale se rouvrait, et plus aucun minuteur ne l'attendait. Symptome a
      reconnaitre : le test AFFICHE son point (il a reussi) et le processus ne
      rend jamais la main — c'est le demontage qui bloque, pas le test.
    · Les boites sont pilotees par un QTimer et jamais par un monkeypatch de
      `QMessageBox.exec` : remplacer un attribut de CLASSE sur un type sip
      laisse un descripteur casse derriere lui et tue le processus plusieurs
      fichiers de tests plus loin (regle de la maison, payee deux fois).
    """

    @staticmethod
    @contextlib.contextmanager
    def _occupe(fen, phase="download"):
        """Rend `ops.is_busy` vrai sans fabriquer de thread, et le defait.

        Pas de vrai `Downloader` : le test porte sur la QUESTION, pas sur le
        reseau, et un thread rendrait ces tests lents et capricieux.
        """
        ops = fen._detail.ops
        ops._downloader = object()
        ops._phase = phase
        ops._active_game = fen.manager.get_games()[0].game
        try:
            yield ops
        finally:
            ops._downloader = None
            ops._phase = ""

    @staticmethod
    @contextlib.contextmanager
    def _repond(libelle, vu):
        """Clique le bouton `libelle` de la boite modale des qu'elle parait."""
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        from src.ui.fenetre_message import FenetreMessage
        minuteur = QTimer()
        minuteur.setInterval(10)

        def _essayer():
            for w in QApplication.topLevelWidgets():
                if isinstance(w, FenetreMessage) and w.isVisible():
                    vu["texte"], vu["detail"] = w.text(), w.informativeText()
                    for b in w.buttons():
                        if b.text() == libelle:
                            minuteur.stop()
                            b.click()
                            return
        minuteur.timeout.connect(_essayer)
        minuteur.start()
        try:
            yield vu
        finally:
            minuteur.stop()

    def test_rien_ne_se_passe_quand_il_n_y_a_rien_en_cours(self, make_window):
        """Aucune boite ne doit s'ouvrir dans le cas NORMAL.

        Posee a chaque fermeture, la question deviendrait un reflexe et ne
        protegerait plus de rien.
        """
        assert make_window()._confirmer_fermeture() is True

    def test_le_telechargement_annonce_qu_il_reprendra(self, make_window):
        fen = make_window()
        vu = {}
        with self._occupe(fen, "download"), self._repond("Continuer", vu):
            assert fen._confirmer_fermeture() is False
        assert "reprendra" in vu["detail"], vu
        assert fen.manager.get_games()[0].game.name in vu["texte"]

    def test_l_installation_annonce_qu_elle_est_a_refaire(self, make_window):
        """Le message DIFFERE selon la phase, parce que la perte differe.

        Un telechargement reprend ou il s'est arrete ; une installation est a
        refaire. Dire « etes-vous sur ? » sans dire ce qu'on risque fait
        deviner, et qui devine clique.
        """
        fen = make_window()
        vu = {}
        with self._occupe(fen, "install"), self._repond("Continuer", vu):
            fen._confirmer_fermeture()
        assert "refaite" in vu["detail"], vu
        assert "conserv" in vu["detail"], "il faut dire que l'archive est gardee"

    def test_repondre_continuer_annule_la_fermeture(self, make_window):
        fen = make_window()
        with self._occupe(fen), self._repond("Continuer", {}):
            assert fen.close() is False, "la fenetre ne doit PAS se fermer"

    def test_repondre_quitter_quand_meme_ferme(self, make_window):
        fen = make_window()
        with self._occupe(fen), self._repond("Quitter quand même", {}):
            assert fen._confirmer_fermeture() is True

    def test_le_quitter_du_tray_passe_par_la_meme_garde(self, make_window,
                                                       monkeypatch):
        """Le chemin le plus probable : quitter par le tray pendant qu'on joue.

        `_quit_app` ne doit appeler `QApplication.quit()` que si `close()` a
        ete accepte, sinon le launcher partirait malgre le refus. Le faux est
        pose sur le MODULE et non sur la classe Qt : monkeypatcher
        `QApplication.quit` reviendrait a remplacer un attribut de type sip.
        """
        from PyQt6.QtWidgets import QApplication

        appels = []
        # SOUS-CLASSE : `instance()`, `topLevelWidgets()` et le reste restent
        # ceux de Qt ; seul `quit` est detourne, et la classe reelle n'est pas
        # touchee. Un faux ecrit de zero manquait `instance()`, que `closeEvent`
        # appelle juste apres.
        faux = type("FauxApp", (QApplication,),
                    {"quit": staticmethod(lambda *a: appels.append(1))})
        fen = make_window()
        monkeypatch.setattr("src.ui.main_window.QApplication", faux)
        with self._occupe(fen), self._repond("Continuer", {}):
            fen._quit_app()
        assert not appels, "le launcher a quitte malgre un refus"

    def test_une_relance_deja_programmee_ne_repose_pas_la_question(
            self, make_window):
        """L'auto-update a deja ecrit son `.bat`, qui attend la mort du process.

        Reposer la question la permettrait de repondre non, et le script
        attendrait indefiniment. Elle est posee AVANT, la ou repondre non est
        encore sans consequence.
        """
        fen = make_window()
        with self._occupe(fen):
            fen._fermeture_confirmee = True
            assert fen._confirmer_fermeture() is True


class TestSansZoneDeNotification:
    """GNOME sans l'extension AppIndicator, certains compositeurs Wayland :
    aucune zone de notification. Y « ranger » la fenêtre au lancement d'un jeu
    la rendait INTROUVABLE jusqu'à la fin de la partie — aucune icône pour la
    rappeler. Le faux est posé sur l'INSTANCE (règle 12)."""

    def test_sans_zone_la_fenetre_est_reduite_pas_cachee(self, make_window, qtbot):
        win = make_window()
        win.show()
        win._tray.disponible = lambda: False
        win._minimize_to_tray()
        assert win.isVisible(), "cachée sans icône pour la rappeler"
        assert win.windowState() & Qt.WindowState.WindowMinimized
        win._restore_from_tray()
        assert not win.windowState() & Qt.WindowState.WindowMinimized

    def test_avec_zone_elle_s_y_range(self, make_window, qtbot):
        win = make_window()
        win.show()
        win._tray.disponible = lambda: True
        win._minimize_to_tray()
        assert not win.isVisible()

    def test_sous_windows_la_zone_existe_toujours(self, monkeypatch):
        """Le comportement Windows ne change pas : on ne demande même pas."""
        from src.ui.tray_manager import TrayManager
        monkeypatch.setattr(sys, "platform", "win32")
        assert TrayManager.disponible() is True

    def test_ailleurs_on_demande_a_qt(self, monkeypatch):
        from PyQt6.QtWidgets import QSystemTrayIcon

        from src.ui.tray_manager import TrayManager
        monkeypatch.setattr(sys, "platform", "linux")
        assert TrayManager.disponible() is QSystemTrayIcon.isSystemTrayAvailable()


class TestIdentifiantDeBureau:
    """Sous Wayland, `setWindowIcon` est ignoré : c'est l'`app_id` qui relie
    la fenêtre à son `.desktop`, donc à son icône et à son nom dans le dock."""

    def test_un_identifiant_de_bureau_valide(self):
        """Nom en DNS inversé, composants sans chiffre en tête : la règle des
        identifiants de fichiers `.desktop` (spécification freedesktop)."""
        import main
        assert re.fullmatch(r"[A-Za-z_][\w-]*(\.[A-Za-z_][\w-]*)+", main.DESKTOP_ID)

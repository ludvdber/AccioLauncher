"""Une VRAIE MainWindow : téléchargements, installations, mises à jour, hors ligne,
et ce que la fiche et le carrousel en disent.

Config temporaire (CONFIG_FILE_PATH patché), `_start_update_check` neutralisé,
autoplay=False. Fixtures `make_window*` dans `conftest.py`.
"""

import re

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from tests.fenetre_commune import (  # noqa: E402
    _CATALOG, _IDS, _libelles_du_layout,
)


class TestPhaseWiring:
    def test_ops_phase_drives_download_bar(self, make_window):
        win = make_window()
        ops = win._detail.ops
        ops._set_phase("download")
        assert win._download_bar._phase_label.text().startswith("1/4")
        ops._set_phase("verify")
        assert win._download_bar._phase_label.text().startswith("2/4")
        assert win._download_bar._progress.maximum() == 0  # indéterminé
        ops._set_phase("verify")  # dédupliqué : pas de double émission
        ops._set_phase("install")
        assert win._download_bar._phase_label.text().startswith("3/4")
        ops._set_phase("finalize")
        assert win._download_bar._phase_label.text().startswith("4/4")
        assert win._download_bar._progress.maximum() == 0  # indéterminé aussi

    def test_installer_finalizing_declenche_la_phase(self, make_window):
        """Le signal Installer.finalizing doit remonter jusqu'au stepper."""
        win = make_window()
        ops = win._detail.ops
        ops._set_phase("install")
        ops._on_finalizing()
        assert ops._phase == "finalize"
        assert win._download_bar._phase_label.text().startswith("4/4")


class TestCarteRebatieEnRoute:
    """Un aller-retour de jeu rebâtit la carte : elle repartait à « 0 % » pendant
    que la barre du bas disait 57 %, et perdait « partie 2 sur 3 »."""

    def _en_cours(self, win, etat, phase):
        from src.core.game_manager import GameState
        jeu = win._detail.game
        ops = win._detail.ops
        win.manager.set_game_state(jeu.id, getattr(GameState, etat))
        ops._active_game = jeu
        ops._set_phase(phase)
        win._detail.refresh_actions()
        return ops

    def _aller_retour(self, win):
        win._carousel.select_next()
        win._carousel.select_prev()

    def test_installation(self, make_window):
        win = make_window()
        ops = self._en_cours(win, "INSTALLING", "install")
        ops._on_install_progress(57)
        self._aller_retour(win)
        assert win._detail._action_panel._carte.pourcentage.text() == "57 %"

    def test_telechargement_et_parties(self, make_window):
        win = make_window()
        ops = self._en_cours(win, "DOWNLOADING", "download")
        ops._on_part_info(2, 3)
        ops._speed_tracker.should_update_ui = lambda: True
        ops._on_download_progress(500_000_000, 1_000_000_000)
        self._aller_retour(win)
        carte = win._detail._action_panel._carte
        assert carte.pourcentage.text() == "50 %"
        assert "partie 2 sur 3" in carte.detail.text()

    def test_une_nouvelle_operation_repart_de_zero(self, make_window):
        win = make_window()
        ops = self._en_cours(win, "INSTALLING", "install")
        ops._on_install_progress(57)
        ops._relacher_operation()
        assert ops.derniere_progression == {}


class TestDownloadCounts:
    """Le compteur vit DANS la ligne méta, à une place stable.

    En pastille séparée, le FlowLayout le renvoyait à la ligne selon la longueur
    du nom du studio : sa position sautait d'un jeu à l'autre.
    """

    def test_counts_appear_in_meta(self, make_window):
        win = make_window()
        win._updates._on_download_counts({_IDS[0]: 1234})
        meta = win._detail._info._meta
        # Le séparateur de milliers FR est une espace fine insécable (U+202F) ;
        # on retire tout espace pour comparer le nombre brut.
        assert "1234" in re.sub(r"\s", "", meta.text())
        assert "téléchargements" in meta.text()  # libellé explicite, pas un glyphe
        assert meta.toolTip()

    def test_singular_for_one_download(self, make_window):
        win = make_window()
        win._updates._on_download_counts({_IDS[0]: 1})
        meta = win._detail._info._meta
        # Espace INSÉCABLE : « 16 » ne doit jamais rester seul en fin de ligne
        # avec « téléchargements » renvoyé au-dessous (retour Ludo).
        assert "1\u00a0téléchargement</span>" in meta.text()

    def test_aucun_segment_ne_peut_se_couper(self, make_window):
        """La ligne méta se replie au séparateur ◆, JAMAIS au milieu d'une info.

        Le repli se produit sur les espaces ordinaires : il ne doit donc en
        rester aucun dans le texte affiché, hors ceux qui entourent le ◆.
        """
        import re as _re
        win = make_window()
        win._updates._on_download_counts({e.game.id: 4321 for e in win.manager.get_games()})
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            html = win._detail._info._meta.text()
            # Retirer les balises (leurs attributs contiennent des espaces
            # légitimes) puis les espaces autour du séparateur.
            texte = _re.sub(r"<[^>]+>", "", html)
            texte = texte.replace(" ◆ ", "◆")
            assert " " not in texte, (
                f"{entry.game.id} : espace sécable dans « {texte} »")

    def test_no_counter_when_unknown(self, make_window):
        win = make_window()
        meta = win._detail._info._meta
        assert "téléchargement" not in meta.text()
        # L'infobulle peut dire la manette (pictogramme), jamais un compte inconnu.
        assert "GitHub" not in meta.toolTip()

    def test_position_stable_entre_les_jeux(self, make_window):
        """Le compteur ne doit jamais changer de ligne d'un jeu à l'autre."""
        win = make_window()
        win._updates._on_download_counts({e.game.id: 4321 for e in win.manager.get_games()})
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            texte = win._detail._info._meta.text()
            assert "téléchargements" in texte, entry.game.id


class TestGameUpdateNotification:
    """Recompte LOCAL des mises à jour de jeux + toast cliquable (retour Ludo :
    la status bar seule passait inaperçue)."""

    def _force_installed(self, win, game_id, version):
        from src.core.game_manager import GameState
        win.config.installed_versions[game_id] = version
        win.manager.set_game_state(game_id, GameState.INSTALLED)

    def test_toast_single_update_names_the_game(self, make_window):
        win = make_window()
        self._force_installed(win, _IDS[0], "0.0.1")  # < recommandée → MàJ dispo
        assert win._notify_game_updates() is True
        assert not win._toast.isHidden()
        assert _CATALOG.games[0].name in win._toast.text()

    def test_toast_plural_counts_games(self, make_window):
        win = make_window()
        self._force_installed(win, _IDS[0], "0.0.1")
        self._force_installed(win, _IDS[1], "0.0.1")
        assert win._notify_game_updates() is True
        assert "2 jeux" in win._toast.text()

    def test_toast_click_selects_first_pending_game(self, make_window):
        win = make_window()
        self._force_installed(win, _IDS[1], "0.0.1")  # 2e jeu du carrousel
        win._notify_game_updates()
        win._toast._on_click()  # simule le clic sur le toast
        assert win._carousel._current_index == 1

    def test_no_updates_no_toast(self, make_window):
        win = make_window()
        assert win._notify_game_updates() is False
        assert win._toast.isHidden()


class TestJeuBientotDisponible:
    """Un jeu annoncé au catalogue mais sans archive publiée.

    Le launcher doit le DIRE, pas lancer un téléchargement qui échoue avec un
    message accusant la connexion internet de l'utilisateur.

    Le catalogue n'illustre plus ce cas depuis sa v0.18 (les huit jeux sont en
    ligne) : la sentinelle qui vivait ici l'a signalé, et les tests ont été
    rebranchés sur `make_window_jeu_a_venir`, qui fabrique le cas.
    """

    def test_la_fixture_produit_bien_un_jeu_sans_source(self, make_window_jeu_a_venir):
        """Sans cette garde, les trois tests suivants passeraient à vide.

        Ils cherchent tous « le jeu non téléchargeable » : si la fixture cessait
        d'en produire un, ils ne testeraient plus rien tout en restant verts.
        """
        _, jeu = make_window_jeu_a_venir()
        assert jeu.is_downloadable is False
        assert jeu.current_download is not None, (
            "le jeu doit garder une version : c'est sa SOURCE qui manque, pas elle")

    @staticmethod
    def _noms_du_layout(panel) -> list[str]:
        """objectName des widgets réellement dans le layout d'actions.

        On n'interroge PAS findChildren : clear_layout utilise deleteLater(),
        donc les boutons de la fiche précédente restent enfants jusqu'au tour
        de boucle suivant et fausseraient l'assertion.
        """
        layout = panel._action_layout
        noms = []
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is not None:
                noms.append(w.objectName())
        return noms

    def test_bouton_remplace_par_bientot_disponible(self, make_window_jeu_a_venir):
        win, game = make_window_jeu_a_venir()
        win._carousel.select(_IDS.index(game.id))
        noms = self._noms_du_layout(win._detail._action_panel)
        assert "btnComingSoon" in noms, f"attendu btnComingSoon, trouvé {noms}"
        assert "btnDownload" not in noms, "le bouton Télécharger ne doit pas être proposé"

    def test_download_refuse_par_lorchestrateur(self, make_window_jeu_a_venir):
        """Garde de dernier recours : même en appelant download() directement."""
        win, game = make_window_jeu_a_venir()
        ops = win._detail.ops
        messages: list[str] = []
        ops.status_message.connect(messages.append)
        ops.download(game, game.current_download)
        assert not ops.is_busy, "aucun Downloader ne doit démarrer sans source"
        assert ops.active_game is None
        assert messages and "bient" in messages[-1].lower()

    def test_jeu_normal_reste_telechargeable(self, make_window_jeu_a_venir):
        """Contrôle négatif : le durcissement ne doit rien casser ailleurs."""
        win, _ = make_window_jeu_a_venir()
        game = next(e.game for e in win.manager.get_games() if e.game.is_downloadable)
        win._carousel.select(_IDS.index(game.id))
        noms = self._noms_du_layout(win._detail._action_panel)
        assert "btnDownload" in noms
        assert "btnComingSoon" not in noms


class TestReprendre:
    def test_jouer_devient_reprendre_apres_une_session(self, make_window, qtbot):
        win = make_window()
        game = win.manager.get_games()[0].game
        # L'état INSTALLED se déduit du DISQUE : il faut un exécutable réel.
        from pathlib import Path
        exe = win.manager.config.install_path / Path(game.executable)
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"MZ")
        win.manager.config.installed_versions[game.id] = game.recommended_version
        win.manager.refresh_states()
        win._detail.set_game(game)
        qtbot.wait(10)
        libelles = _libelles_du_layout(win._detail._action_panel)
        assert any("Jouer" in t for t in libelles), libelles

        win.manager.add_playtime(game.id, 3600)
        win._detail.set_game(game)
        qtbot.wait(10)
        libelles = _libelles_du_layout(win._detail._action_panel)
        assert any("Reprendre" in t for t in libelles), libelles


class TestHorsLigneBoutEnBout:
    """Le launcher était MUET hors ligne : rien ne bougeait, et « Télécharger »
    échouait quelques secondes plus tard sur une erreur réseau générique."""

    def test_message_ambiant_et_bouton_grise(self, make_window, qtbot):
        win = make_window()
        win.show()
        win._on_network_status(False)
        qtbot.wait(20)
        assert "Hors ligne" in win._status_bar.currentMessage()
        # Ce qui se passe, pas ce qui reste normal (Ludo, 2026-10-29).
        assert "téléchargements attendent" in win._status_bar.currentMessage()

    def test_une_re_tentative_est_programmee(self, make_window):
        """Sans elle, rebrancher son câble laisserait l'UI grisée jusqu'au
        prochain démarrage — le launcher aurait l'air en panne."""
        win = make_window()
        win._on_network_status(False)
        assert win._updates._offline_retry.isActive()
        win._on_network_status(True)
        assert not win._updates._offline_retry.isActive()

    def test_la_re_tentative_est_re_armee_a_chaque_echec(self, make_window):
        """Le garde « seulement si l'état a changé » ne doit pas manger le
        ré-armement : sinon un seul essai serait fait, puis plus jamais rien."""
        win = make_window()
        win._on_network_status(False)
        win._updates._offline_retry.stop()
        win._on_network_status(False)   # état inchangé, mais nouvel échec
        assert win._updates._offline_retry.isActive()

    def test_retour_en_ligne_restaure_le_message(self, make_window, qtbot):
        win = make_window()
        win.show()
        win._on_network_status(False)
        win._on_network_status(True)
        qtbot.wait(20)
        assert "Hors ligne" not in win._status_bar.currentMessage()

    def test_la_fermeture_arrete_le_timer(self, make_window):
        """Sinon il ressuscite un UpdateChecker pendant qu'on attend justement
        la fin des threads (QThread détruit en cours d'exécution)."""
        win = make_window()
        win._on_network_status(False)
        assert win._updates._offline_retry.isActive()
        win.close()
        assert not win._updates._offline_retry.isActive()

    def test_l_etat_descend_jusqu_au_panneau_d_actions(self, make_window, qtbot):
        win = make_window()
        win.show()
        win._on_network_status(False)
        qtbot.wait(20)
        assert win._detail._action_panel._online is False


class TestToastsAuLieuDeModaux:
    """Ce qui n'appelle aucune décision ne doit plus bloquer sur un clic."""

    def test_notify_alimente_le_toast(self, make_window, qtbot):
        win = make_window()
        win.show()
        win._detail.notify.emit("Sauvegardes conservées")
        qtbot.waitUntil(win._toast.isVisible, timeout=3000)
        assert win._toast.text() == "Sauvegardes conservées"
        assert win._toast.isVisible()

    def test_l_alerte_disque_ouvre_les_parametres(self, make_window, monkeypatch):
        """Le lien « Changer de dossier » du bandeau doit mener quelque part."""
        ouvert = []
        monkeypatch.setattr("src.ui.main_window.MainWindow._on_settings",
                            lambda self: ouvert.append(1))
        win = make_window()
        win._detail._action_panel.settings_requested.emit()
        assert ouvert == [1]


class TestNoteBientotDisponible:
    """La note sous « BIENTÔT DISPONIBLE » ne doit pas être rognée.

    Contrainte à la largeur du bouton (300 px) elle passait sur deux lignes et
    n'en recevait qu'une : le bas de la seconde était tranché en français comme
    en espagnol. Troisième occurrence du piège `wordWrap` dans ce projet — d'où
    un test dédié plutôt qu'une relecture.
    """

    @staticmethod
    def _note(win):
        from PyQt6.QtWidgets import QLabel
        # clear_layout passe par deleteLater() : le libellé de l'état précédent
        # reste enfant un tour de boucle de plus et sort en premier.
        for lab in win._detail._action_panel.findChildren(QLabel):
            if lab.objectName() == "comingSoonNote" and lab.isVisible():
                return lab
        return None

    @pytest.mark.parametrize("taille", [(980, 660), (1200, 800), (1500, 950)])
    def test_hauteur_suffisante(self, make_window_jeu_a_venir, qtbot, taille, mise_en_page_stable):
        win, _ = make_window_jeu_a_venir()
        win.show()
        win.resize(*taille)
        mise_en_page_stable(win)
        vus = 0
        for entry in win.manager.get_games():
            if entry.game.is_downloadable:
                continue
            win._detail.set_game(entry.game)
            mise_en_page_stable(win)
            note = self._note(win)
            assert note is not None, f"{entry.game.id} : note introuvable"
            vus += 1
            besoin = note.heightForWidth(note.width())
            assert besoin <= note.height(), (
                f"{entry.game.id} à {taille} : la note réclame {besoin} px "
                f"de haut et n'en reçoit que {note.height()}")
        assert vus >= 1, "aucun jeu « bientôt disponible » dans le catalogue"


class TestBadgesDuCarrousel:
    """« NOUVEAU » et « BIENTÔT » sont peints au drawText, pas posés en setText.

    Le contrôle de couverture i18n extrait les appels à `tr()` par AST : il ne
    voit pas ce qui n'y passe pas. Ces deux libellés sont donc restés français
    dans les trois langues, en permanence sur l'écran d'accueil pour les jeux
    à venir. Le test vérifie qu'ils passent bien par `tr()` ET que la pastille
    tient dans la vignette, quelle que soit la longueur de la traduction.
    """

    def test_les_deux_libelles_sont_traduits(self):
        from src.core.i18n import available_languages, set_language
        from src.core.i18n import tr as _tr
        try:
            for info in available_languages():
                set_language(info.code)
                for cle in ("NOUVEAU", "BIENTÔT"):
                    assert _tr(cle), f"{info.code} : {cle!r} sans traduction"
        finally:
            set_language("fr")

    def test_la_pastille_tient_dans_la_vignette(self):
        """Même une traduction longue ne doit pas déborder les 90 px."""
        from src.ui.carousel_item import THUMB_W, _BADGE_PADDING, _badge_texte
        from PyQt6.QtGui import QFontMetrics
        for texte in ("NOUVEAU", "NEW", "NUEVO", "BIENTÔT", "SOON", "PRONTO",
                      "COMING SOON", "PRÓXIMAMENTE", "MUY PRONTO AQUÍ",
                      "UNE TRADUCTION VOLONTAIREMENT TRÈS LONGUE"):
            largeur_max = THUMB_W - 6
            police, affiche = _badge_texte(texte, largeur_max)
            pris = QFontMetrics(police).horizontalAdvance(affiche) + _BADGE_PADDING
            assert pris <= largeur_max, (
                f"{texte!r} : pastille de {pris} px pour {largeur_max} disponibles")


class TestVerificationForceeHorsLigne:
    """« Vérifier les mises à jour » ne doit pas AFFIRMER ce qu'il n'a pas vu.

    Hors ligne, aucun `catalog_updated` n'est émis — exactement comme lorsque
    le catalogue est réellement à jour. Le dialogue en déduisait « Catalogue
    déjà à jour », c'est-à-dire une affirmation que le launcher n'était pas en
    position de faire : mesuré le 2026-08-28, les deux situations rendaient la
    MÊME chaîne, donc l'utilisateur sans réseau était informé que tout allait
    bien. C'est le pendant du faux « hors ligne » que le projet s'interdit déjà
    — mentir dans l'autre sens n'est pas moins grave.
    """

    class _FauxChecker(QObject):
        """Checker qui ne trouve rien : ce que produit une coupure réseau."""
        catalog_updated = pyqtSignal(object)
        launcher_update = pyqtSignal(str, str, str, str)
        finished = pyqtSignal()

        def start(self):
            self.finished.emit()

    def _verifier(self, win, monkeypatch, *, en_ligne: bool):
        """Joue une vérification forcée et rend (message, succès) affichés."""
        from src.ui.settings_panel import SettingsDialog
        faux = self._FauxChecker()
        monkeypatch.setattr(win._updates, "forced_checker", lambda: faux)
        dlg = SettingsDialog(win.config, win.manager, win, store=win._trailers)
        vus: list[tuple] = []
        # Faux posé sur l'INSTANCE du dialogue, jamais sur la classe : un
        # attribut de classe d'un type sip laisse un descripteur cassé.
        dlg.show_update_status = lambda msg, success=True: vus.append((msg, success))
        win._online = en_ligne
        win._force_update_check(dlg, catalog_only=True)
        dlg.deleteLater()
        return vus[-1] if vus else ("", None)

    def test_hors_ligne_le_dit_au_lieu_de_rassurer(self, make_window, monkeypatch):
        win = make_window()
        message, succes = self._verifier(win, monkeypatch, en_ligne=False)
        assert "Hors ligne" in message
        assert succes is False, "un échec doit s'afficher comme un échec"

    def test_en_ligne_le_message_rassurant_reste(self, make_window, monkeypatch):
        """La correction ne doit pas avoir supprimé le cas nominal."""
        win = make_window()
        message, succes = self._verifier(win, monkeypatch, en_ligne=True)
        assert "à jour" in message
        assert succes is True

    def test_les_deux_situations_ne_disent_PAS_la_meme_chose(self, make_window,
                                                             monkeypatch):
        """Le cœur du défaut : c'est l'INDISTINCTION qui trompait."""
        win = make_window()
        hors = self._verifier(win, monkeypatch, en_ligne=False)
        dans = self._verifier(win, monkeypatch, en_ligne=True)
        assert hors[0] != dans[0]


class TestEchecDeLancementVisible:
    """Bout en bout : le message qui s'affiche après un lancement raté."""

    class _FauxProc:
        pid = 1
        args = ["C:/jeux/HP1/System/Harry.exe"]

        def poll(self):
            return None

    def _retour(self, win, qtbot, duree: float) -> str:
        win._session.demarrer(self._FauxProc(), "HP1", win._detail.game.id)
        win._session._monitor.game_exited.emit("HP1", 0, duree)
        qtbot.wait(20)
        return win._status_bar.currentMessage()

    def test_une_partie_normale_dit_partie_terminee(self, make_window, qtbot):
        win = make_window()
        win.show()
        assert "partie terminée" in self._retour(win, qtbot, 1200.0)

    def test_un_jeu_qui_ne_demarre_pas_ne_dit_PAS_partie_terminee(self, make_window, qtbot):
        """0,5 s et code 0 : la signature du dossier `pc` de HP7."""
        win = make_window()
        win.show()
        assert "partie terminée" not in self._retour(win, qtbot, 0.5)

    def test_et_il_le_signale_par_un_toast(self, make_window, qtbot):
        win = make_window()
        win.show()
        self._retour(win, qtbot, 0.5)
        assert win._toast.isVisible(), "l'échec passe inaperçu"
        assert "n'a pas démarré" in win._toast.text()

    def test_un_arret_fatal_hors_affichage_n_annonce_pas_partie_terminee(self, make_window, qtbot, monkeypatch):
        """M-04 de l'audit du 2026-10-07 : la boîte « Critical Error » d'UE1
        regardée longtemps gardait le jeu en vie, et le joueur recevait « Bon
        jeu ! ». Le journal du jeu est simulé (règle 78 : rien du catalogue)."""
        from src.core import config_cassee
        from src.ui import game_detail_handlers, game_session
        arret = config_cassee.Arret("Assertion failed: Bitmap.LoadFile(Filename)", config_cassee.AUTRE)
        monkeypatch.setattr(game_session.config_cassee, "apres_la_partie", lambda *_a: arret)
        boites = []
        monkeypatch.setattr(game_detail_handlers, "signaler_arret",
                            lambda _v, game, a: boites.append((game.id, a)))
        win = make_window()
        win.show()
        jeu = win._detail.game.id
        message = self._retour(win, qtbot, 120.0)
        assert "partie terminée" not in message
        assert not win._toast.isVisible(), "un toast par-dessus la boîte"
        assert boites == [(jeu, arret)]
        assert win.manager.get_playtime(jeu) == 0, "deux minutes devant l'erreur comptées comme partie"

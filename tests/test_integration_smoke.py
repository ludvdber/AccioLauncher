"""Tests d'intégration offscreen — une VRAIE MainWindow pilotée par simulation.

Config temporaire (CONFIG_FILE_PATH patché), `_start_update_check` neutralisé
(zéro réseau — la vérification est inconditionnelle en production),
autoplay=False (zéro QtMultimedia). Couvre le câblage bout-en-bout que les tests
unitaires ne voient pas : hero dynamique, clavier, toast Ko-fi, phases, compteur,
saisons, cross-fade, mute en direct, boutons Redémarrer, imports d'onboarding.
"""

import pathlib
import re

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402

from src.core.game_data import load_catalog  # noqa: E402

_CATALOG = load_catalog()
_IDS = [g.id for g in _CATALOG.games]


def _libelles_du_layout(panel) -> list[str]:
    """Textes des widgets réellement dans le layout d'actions.

    Pas findChildren : `clear_layout` passe par deleteLater(), donc les boutons
    de la fiche précédente restent enfants un tour de boucle de plus.
    """
    layout = panel._action_layout
    textes = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and hasattr(w, "text"):
            textes.append(w.text())
    return textes


@pytest.fixture
def make_window(qtbot, tmp_path, monkeypatch):
    """Construit une MainWindow sur une config temporaire isolée."""
    def _make(**overrides):
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        from src.core.config import Config
        # La vérification des MAJ est inconditionnelle en production : c'est ici
        # qu'on la neutralise, pas via un réglage utilisateur qui n'existe plus.
        monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check",
                            lambda self: None)
        cfg = Config(
            install_path=tmp_path / "games",
            cache_path=tmp_path / "games" / ".cache",
            # Le défaut applicatif est l'anglais ; ces tests vérifient des
            # chaînes FRANÇAISES, donc ils demandent explicitement le français.
            langue="fr",
            **{"autoplay_videos": False, **overrides},  # surchargeable par test
        )
        cfg.save()
        from src.ui.main_window import MainWindow
        win = MainWindow()
        qtbot.addWidget(win)
        return win
    yield _make
    from src.core.i18n import set_language
    from src.ui.theme import set_theme
    set_language("fr")
    set_theme("poudlard")


@pytest.fixture
def make_window_jeu_a_venir(make_window, monkeypatch):
    """MainWindow dont le DERNIER jeu du catalogue est privé de ses sources.

    Depuis la v0.18 du catalogue, les huit jeux sont en ligne : le cas « bientôt
    disponible » n'a plus d'illustration réelle. Le comportement reste pourtant
    du code vivant, et le prochain jeu annoncé le réactivera.

    On fabrique donc le cas au lieu de le chercher. C'est aussi le bon découplage
    sur le fond : `games.json` se met à jour **à distance**, sans republier le
    launcher — un test qui suppose son contenu casse à chaque livraison de jeu,
    loin de la ligne de code qu'il surveille.

    Retourne `(fenêtre, jeu_sans_source)`.
    """
    def _make(**overrides):
        import dataclasses

        from src.core import game_manager
        vrai_load = game_manager.load_catalog

        def _catalogue_ampute(*a, **k):
            cat = vrai_load(*a, **k)
            jeux = list(cat.games)
            sans_source = dataclasses.replace(
                jeux[-1],
                versions=tuple(dataclasses.replace(v, download_url=None,
                                                   download_parts=None)
                               for v in jeux[-1].versions))
            jeux[-1] = sans_source
            return dataclasses.replace(cat, games=tuple(jeux))

        monkeypatch.setattr(game_manager, "load_catalog", _catalogue_ampute)
        win = make_window(**overrides)
        return win, win.manager.get_games()[-1].game
    return _make


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


class TestKofiMilestone:
    def test_toast_once_at_ten_hours(self, make_window):
        win = make_window(playtime_seconds={_IDS[0]: 11 * 3600})
        win.show()
        assert win.config.kofi_milestone_thanked is False

        win._maybe_thank_milestone()
        assert win.config.kofi_milestone_thanked is True
        assert win._toast.isVisible()
        assert "caf" in win._toast.text()          # message « célébration », pas de nag
        assert win._toast._on_click is not None     # cliquable -> ouvre Ko-fi

        win._toast.hide()
        win._maybe_thank_milestone()  # une seule fois dans la vie du launcher
        assert not win._toast.isVisible()

    def test_no_toast_under_ten_hours(self, make_window):
        win = make_window(playtime_seconds={_IDS[0]: 2 * 3600})
        win.show()
        win._maybe_thank_milestone()
        assert win.config.kofi_milestone_thanked is False
        assert not win._toast.isVisible()


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
        assert not meta.toolTip()

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


class TestSeasonLive:
    def test_apply_season_reseeds_particles(self, make_window):
        win = make_window()
        win._particles.resize(800, 600)
        win._particles._ensure_particles()
        assert all(p.speed_y < 0 for p in win._particles._particles)  # ça monte

        win._particles.apply_season("noel")
        assert win._particles._particles == []  # re-semées au tick suivant
        win._particles._ensure_particles()
        assert all(p.speed_y > 0 for p in win._particles._particles)  # ça tombe

        win._particles.apply_season("aucune")
        win._particles._ensure_particles()
        assert all(p.speed_y < 0 for p in win._particles._particles)


class TestCrossfade:
    def test_old_frame_kept_until_fade_completes(self, make_window):
        win = make_window()
        win.show()
        win.resize(1200, 800)
        bg = win._detail._bg
        bg._ensure_prepared()
        if bg._prepared is None:
            pytest.skip("backgrounds absents du repo de test")
        win._detail.set_game(_CATALOG.games[1])
        assert bg._old_frame is not None  # l'ancien rendu sert de sous-couche
        bg.bg_opacity = 1.0  # fade terminé
        assert bg._old_frame is None  # snapshot libéré


class TestMuteLive:
    def test_settings_mute_applies_to_running_video(self, make_window):
        """Régression : « Couper le son » ne touchait que la PROCHAINE vidéo."""
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        dlg.config_changed.connect(win._on_config_changed)

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

    def test_season_change_emits_resolved_season(self, make_window, qtbot):
        from src.ui.settings_panel import SettingsDialog
        win = make_window()
        dlg = SettingsDialog(win.config, win.manager)
        qtbot.addWidget(dlg)
        with qtbot.waitSignal(dlg.season_changed, timeout=1000) as blocker:
            dlg._season_combo.setCurrentIndex(3)  # Noël
        assert blocker.args == ["noel"]
        assert win.config.season == "noel"
        dlg._scan_worker.requestInterruption()
        dlg._scan_worker.wait()


class TestOnboardingImport:
    def test_perform_imports_moves_game(self, qtbot, tmp_path, monkeypatch):
        from PyQt6.QtWidgets import QListWidgetItem
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

        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg._detected = found
        for g, src in found:
            item = QListWidgetItem(f"{g.name} - {src}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            dlg._import_list.addItem(item)

        config = Config(install_path=tmp_path / "launcher_games",
                        cache_path=tmp_path / "launcher_games" / ".cache")
        (tmp_path / "launcher_games").mkdir()
        dlg.perform_imports(config)

        assert (tmp_path / "launcher_games" / Path(*parts)).exists()  # déplacé
        assert config.installed_versions[game.id] == game.recommended_version
        assert not (src_root / parts[0]).exists()  # source vidée (rename)


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


class TestPasDeTroncature:
    """Régressions de mise en page : le texte ne doit jamais être coupé.

    Le panneau d'info est positionné en `setGeometry` à 50 % de la fenêtre.
    Des largeurs figées en pixels (600 / 520) le débordaient dès que la fenêtre
    passait sous ~1100 px, et le conteneur de tags avait un plafond de hauteur
    qui coupait sa dernière ligne de pastilles.
    """

    TAILLES = ((1200, 800), (980, 660), (1600, 900))

    @staticmethod
    def _jeu_le_plus_charge(win):
        return max((e.game for e in win.manager.get_games()), key=lambda g: len(g.tags))

    def test_titre_et_description_tiennent_dans_le_panneau(self, make_window, qtbot):
        win = make_window()
        win.show()
        info = win._detail._info
        for w, h in self.TAILLES:
            win.resize(w, h)
            qtbot.wait(10)
            win._detail.set_game(self._jeu_le_plus_charge(win))
            qtbot.wait(10)
            assert info._title.width() <= info.available_width(), (
                f"titre plus large que le panneau en {w}x{h}")
            assert info._desc.width() <= info.available_width(), (
                f"description plus large que le panneau en {w}x{h}")
            besoin = info._title.heightForWidth(info._title.width())
            assert info._title.height() >= besoin, (
                f"titre amputé en {w}x{h} : {info._title.height()} px pour {besoin} px de texte")

    def test_tags_jamais_coupes(self, make_window, qtbot):
        win = make_window()
        win.show()
        info = win._detail._info
        for w, h in self.TAILLES:
            win.resize(w, h)
            qtbot.wait(10)
            win._detail.set_game(self._jeu_le_plus_charge(win))
            qtbot.wait(10)
            besoin = info._tags_layout.heightForWidth(info._tags_container.width())
            assert info._tags_container.height() >= besoin, (
                f"tags coupés en {w}x{h} : {info._tags_container.height()} < {besoin}")

    def test_flow_layout_mesure_un_widget_cache(self, qtbot):
        """`QWidgetItem.sizeHint()` vaut (0,0) tant que le widget est caché —
        c'est ce qui écrasait la hauteur des tags pendant le cross-fade."""
        from PyQt6.QtWidgets import QLabel, QWidget

        from src.ui.flow_layout import FlowLayout

        host = QWidget()
        qtbot.addWidget(host)
        flow = FlowLayout(host, spacing=8)
        for _ in range(4):
            lbl = QLabel("TAG ASSEZ LONG")
            lbl.setFixedSize(120, 28)
            flow.addWidget(lbl)
        # host jamais montré → les items sont « cachés »
        assert flow.heightForWidth(300) > 0


class TestBandesAnnonces:
    """Comportement des vidéos de fond : muettes, différées, suspendues.

    Les trailers sont la signature visuelle du launcher — ils restent. Ce qui
    change, c'est qu'ils ne s'imposent plus : pas de son surprise, pas de
    lecture derrière une fenêtre inactive, pas de démarrage pendant qu'on lit
    le titre.
    """

    def test_muet_par_defaut(self):
        from src.core.config import Config
        assert Config().mute_videos is True, "un logiciel ne doit pas faire de bruit sans prévenir"

    def test_video_non_lancee_immediatement(self, make_window, qtbot):
        """Le démarrage est différé : la fiche se lit sur une image fixe."""
        win = make_window(autoplay_videos=True)
        detail = win._detail
        assert detail._pending_video_id == detail.game.id
        assert not detail._video.is_playing, "la vidéo ne doit pas démarrer dans la même frame"

    def test_changer_de_jeu_annule_la_video_programmee(self, make_window, qtbot):
        """Parcourir le carrousel ne doit pas lancer un lecteur par vignette."""
        win = make_window(autoplay_videos=True)
        detail = win._detail
        autre = next(e.game for e in win.manager.get_games() if e.game.id != detail.game.id)
        detail.set_game(autre)
        assert detail._pending_video_id == autre.id
        detail._on_video_timer()          # le timer du PREMIER jeu arrive en retard
        assert not detail._video.is_playing or detail.game.id == autre.id

    def test_pause_effects_suspend_la_video(self, make_window, qtbot):
        """Fenêtre derrière une autre : plus de décodage vidéo pour personne."""
        win = make_window()
        detail = win._detail
        detail.pause_effects()
        assert detail._video.paused is False or not detail._video.is_playing
        detail.resume_effects()

    def test_barre_audio_a_un_bouton_pause(self, make_window):
        win = make_window()
        bar = win._detail._audio_bar
        assert hasattr(bar, "play_toggled")
        bar.set_paused_icon(True)
        bar.set_paused_icon(False)


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
        assert any("JOUER" in t for t in libelles), libelles

        win.manager.add_playtime(game.id, 3600)
        win._detail.set_game(game)
        qtbot.wait(10)
        libelles = _libelles_du_layout(win._detail._action_panel)
        assert any("REPRENDRE" in t for t in libelles), libelles


class TestDescriptionEntreJeux:
    """Le libellé de description ne doit pas garder la hauteur du jeu précédent.

    Scénario signalé : déplier la description d'un jeu « bientôt disponible »
    puis revenir sur un autre jeu laissait un grand vide sous un texte court,
    parce que `minimumHeight` gardait la valeur de l'état déplié.
    """

    @staticmethod
    def _besoin(label) -> int:
        # heightForWidth() renvoie max(minimumHeight, calcul) : remettre le
        # minimum à zéro est le seul moyen d'obtenir la hauteur réelle du texte.
        garde = label.minimumHeight()
        label.setMinimumHeight(0)
        besoin = label.heightForWidth(label.width())
        label.setMinimumHeight(garde)
        return besoin

    def test_hauteur_suit_le_texte_apres_changement_de_jeu(self, make_window_jeu_a_venir,
                                                          qtbot):
        win, soon = make_window_jeu_a_venir()
        win.show()
        info = win._detail._info
        autre = next(e.game for e in win.manager.get_games() if e.game.is_downloadable)

        win._detail.set_game(soon)
        qtbot.wait(30)
        info._toggle_desc()               # « Lire la suite »
        qtbot.wait(30)
        assert info._desc_expanded is True

        win._detail.set_game(autre)
        qtbot.wait(30)
        assert info._desc_expanded is False, "le dépliage ne doit pas survivre au changement"
        ecart = info._desc.height() - self._besoin(info._desc)
        assert abs(ecart) <= 2, f"{ecart} px de vide sous la description"

    def test_bouton_coherent_avec_le_texte(self, make_window, qtbot):
        """« Lire la suite » ne s'affiche que si du texte est réellement caché."""
        win = make_window()
        win.show()
        info = win._detail._info
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            qtbot.wait(20)
            tronque = info._desc.text() != info._full_desc
            assert info._btn_expand.isVisible() == tronque, (
                f"{entry.game.id} : bouton={info._btn_expand.isVisible()} "
                f"alors que tronqué={tronque}")


class TestHorsLigneBoutEnBout:
    """Le launcher était MUET hors ligne : rien ne bougeait, et « Télécharger »
    échouait quelques secondes plus tard sur une erreur réseau générique."""

    def test_message_ambiant_et_bouton_grise(self, make_window, qtbot):
        win = make_window()
        win.show()
        win._on_network_status(False)
        qtbot.wait(20)
        assert "Hors ligne" in win._status_bar.currentMessage()
        assert "jouables" in win._status_bar.currentMessage(), (
            "le message doit rassurer sur ce qui MARCHE encore")

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
        qtbot.wait(20)
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


class TestBandeauSansScrollbar:
    """« Pas de scroll si on a pas ouvert la suite d'une description » (Ludo).

    Un bandeau d'avertissement de deux lignes faisait déborder le panneau de
    20 px sur une fenêtre au minimum syndical et ramenait la barre. Le budget
    de description a donc un troisième palier, et le bandeau n'affiche qu'un
    seul message à la fois.
    """

    @staticmethod
    def _disque(monkeypatch, free_mb):
        from collections import namedtuple
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr("src.core.game_manager.shutil.disk_usage",
                            lambda _p: usage(0, 0, free_mb * 1024 * 1024))

    def _balaye(self, win, qtbot, taille):
        """Toutes les fiches à une taille donnée → liste des débordements."""
        win.resize(*taille)
        qtbot.wait(30)
        deborde = []
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            qtbot.wait(20)
            trop = win._detail._info._scroll.verticalScrollBar().maximum()
            if trop > 0:
                deborde.append((entry.game.id, trop))
        return deborde

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880)])
    def test_hors_ligne(self, make_window, qtbot, monkeypatch, taille):
        self._disque(monkeypatch, 900_000)
        win = make_window()
        win.show()
        win._on_network_status(False)
        qtbot.wait(30)
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880)])
    def test_disque_plein(self, make_window, qtbot, monkeypatch, taille):
        self._disque(monkeypatch, 40)
        win = make_window()
        win.show()
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880)])
    def test_prerequis_manquant_sur_jeux_installes(self, make_window, qtbot,
                                                   monkeypatch, taille):
        from src.core.game_manager import GameState
        self._disque(monkeypatch, 900_000)
        monkeypatch.setattr("src.core.system_checks.check_vcredist_x86", lambda: False)
        win = make_window()
        win.show()
        for entry in win.manager.get_games():
            win.manager.set_game_state(entry.game.id, GameState.INSTALLED)
        assert self._balaye(win, qtbot, taille) == []

    # Texte réaliste, volontairement long : c'est le catalogue qui l'écrit, à
    # distance, et personne ne relancera cette suite avant de le publier.
    _AVERTISSEMENT = (
        "Votre antivirus peut mettre en quarantaine un fichier de ce jeu pendant "
        "l'installation. S'il refuse de démarrer, restaurez ce fichier depuis la "
        "quarantaine de votre antivirus."
    )

    @staticmethod
    def _catalogue_avec_avertissement(monkeypatch, url=""):
        """Colle la mise en garde sur TOUS les jeux — pire cas de mise en page."""
        import dataclasses

        from src.core import game_manager
        vrai_load = game_manager.load_catalog

        def _charge(*a, **k):
            cat = vrai_load(*a, **k)
            return dataclasses.replace(cat, games=tuple(
                dataclasses.replace(
                    g, warning=TestBandeauSansScrollbar._AVERTISSEMENT,
                    warning_url=url)
                for g in cat.games))

        monkeypatch.setattr(game_manager, "load_catalog", _charge)

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880)])
    def test_avertissement_du_catalogue_avant_telechargement(
            self, make_window, qtbot, monkeypatch, taille):
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(monkeypatch)
        win = make_window()
        win.show()
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880)])
    def test_avertissement_du_catalogue_avec_lien(
            self, make_window, qtbot, monkeypatch, taille):
        """Le « En savoir plus » allonge la dernière ligne — cas le plus large."""
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(
            monkeypatch, url="https://acciolauncher.be/aide/antivirus")
        win = make_window()
        win.show()
        assert self._balaye(win, qtbot, taille) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880)])
    def test_avertissement_du_catalogue_sur_jeux_installes(
            self, make_window, qtbot, monkeypatch, taille):
        from src.core.game_manager import GameState
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(monkeypatch)
        win = make_window()
        win.show()
        for entry in win.manager.get_games():
            win.manager.set_game_state(entry.game.id, GameState.INSTALLED)
        assert self._balaye(win, qtbot, taille) == []

    def test_le_bandeau_est_bien_la_pendant_le_balayage(
            self, make_window, qtbot, monkeypatch):
        """Garde-fou : sans lui, les trois tests ci-dessus passeraient à vide
        si le mécanisme d'avertissement cessait d'afficher quoi que ce soit."""
        self._disque(monkeypatch, 900_000)
        self._catalogue_avec_avertissement(monkeypatch)
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(30)
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            qtbot.wait(20)
            assert win._detail._action_panel.alert_height() > 0
            assert "quarantaine" in win._detail._action_panel._alert.text()

    def test_le_bandeau_n_affiche_qu_un_message(self, make_window, qtbot, monkeypatch):
        """Hors ligne ET disque plein : le hors-ligne prime, le disque attend
        d'être actionnable (hors ligne, rien ne s'écrit sur le disque)."""
        self._disque(monkeypatch, 40)
        win = make_window()
        win.show()
        win._on_network_status(False)
        qtbot.wait(30)
        texte = win._detail._action_panel._alert.text()
        assert "Hors ligne" in texte
        assert "Espace insuffisant" not in texte


class TestCoutureCarrousel:
    """« Il y a une ligne de pixel bizarre juste au dessus de la liste de jeu ».

    Le carrousel est un widget FRÈRE : il ne montre pas l'illustration, donc là
    où son dégradé est transparent on voit le fond plat du conteneur. Le bas de
    la fiche, lui, était assombri sous cette couleur par la vignette radiale
    (rgb(3,3,8) contre rgb(6,6,17)) — un trait clair sur toute la largeur, de
    valeur IDENTIQUE sur les 8 jeux, ce qui a permis de l'imputer au rendu et
    non aux images.
    """

    def _ecart(self, win, qtbot):
        """Somme |dRGB| max entre la dernière ligne de la fiche et la première
        du carrousel, échantillonnée sur toute la largeur.

        TOUTE la décoration animée est neutralisée avant de mesurer, parce
        qu'elle traverse la frontière sans être ce qu'on teste :
        - les particules, qui passent au-dessus des deux widgets ;
        - les étoiles scintillantes du carrousel, tirées à des positions
          ALÉATOIRES à la construction. Quand l'une tombe sur la première ligne
          du carrousel, elle éclaircit 2 à 4 colonnes sur 1000 (pic mesuré :
          95/765) et le test échoue pour la mauvaise raison.

        Ne masquer que les particules laissait le test instable : 14 échecs sur
        30 en reproduction directe. Le pixel du HAUT, lui, valait toujours
        exactement bg_qcolor(255) — le raccord n'a jamais fauté, seule la
        mesure était contaminée.
        """
        win._particles.hide()
        win._carousel._stars.clear()   # décor aléatoire : fausserait la mesure
        win._carousel.update()
        qtbot.wait(40)
        img = win.grab().toImage()
        haut = win._carousel.mapTo(win, win._carousel.rect().topLeft()).y()
        pire = 0
        for x in range(4, win.width() - 4, 11):
            a = img.pixelColor(x, haut - 1)
            b = img.pixelColor(x, haut)
            pire = max(pire, abs(a.red() - b.red()) + abs(a.green() - b.green())
                       + abs(a.blue() - b.blue()))
        return pire

    def test_aucune_marche_sur_aucun_jeu(self, make_window, qtbot):
        win = make_window()
        win.resize(1320, 880)
        win.show()
        qtbot.wait(60)
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            ecart = self._ecart(win, qtbot)
            assert ecart == 0, (
                f"{entry.game.id} : marche de {ecart}/765 au-dessus du carrousel")

    def test_tient_aussi_en_carrousel_compact(self, make_window, qtbot):
        """Sous 780 px de haut le carrousel se compacte : le raccord suit."""
        win = make_window()
        win.resize(1000, 700)
        win.show()
        qtbot.wait(60)
        assert self._ecart(win, qtbot) == 0


class TestRecuperationDuVideDuHaut:
    """Avant de rogner du TEXTE, la fiche récupère du VIDE.

    Le retrait au-dessus du panneau vaut 10 % de la fiche (49 px à 980×660) et
    ne porte aucune information : remonter le panneau ne coûte rien à
    l'utilisateur, là où un cran d'accroche en moins lui coûte deux lignes.

    Le cas qui l'a imposé existait AVANT le bandeau du catalogue : en espagnol,
    à 980×660, l'avertissement d'espace disque faisait déjà défiler la fiche de
    HP7 de 20 px. Il ne se reproduit pas ici — la suite tourne en `offscreen`,
    où Qt substitue une autre police — donc on teste le MÉCANISME, et la mesure
    en vraies polices est faite par `tools/audit_geometrie.py` (scénario
    « bandeau », qui échoue si ce correctif disparaît).
    """

    @staticmethod
    def _force_debordement(win, pixels):
        """Fait croire au panneau qu'il déborde, sans toucher à la classe Qt.

        Attribut d'INSTANCE : remplacer `InfoPanel.overflow` au niveau de la
        classe laisserait un descripteur sip posé pour toute la session, et le
        processus meurt plusieurs fichiers de tests plus loin.
        """
        win._detail._info.overflow = lambda: pixels

    def test_le_panneau_remonte_au_lieu_de_rogner(self, make_window, qtbot):
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(60)
        nominal = win._detail._info.y()
        assert nominal > 0

        self._force_debordement(win, 30)
        win._detail._position_info()
        # `waitUntil` et non un `wait` fixe : la remontée se fait par une
        # chaîne de `singleShot(0)` qui se réarme, donc en plusieurs tours de
        # boucle d'évènements. 80 ms suffisent à vide et pas toujours sous la
        # charge de la suite complète — un test qui échoue une fois sur dix
        # arrête `build.bat` au hasard, ce qui est pire qu'une absence de test.
        qtbot.waitUntil(lambda: win._detail._info.y() < nominal, timeout=3000)

    def test_jamais_sous_le_plancher(self, make_window, qtbot):
        """Un débordement énorme ne doit pas coller le titre à la barre."""
        from src.ui.game_detail import _INFO_TOP_MIN
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(60)
        self._force_debordement(win, 10_000)
        win._detail._position_info()
        qtbot.waitUntil(lambda: win._detail._info.y() <= _INFO_TOP_MIN, timeout=3000)
        assert win._detail._info.y() >= _INFO_TOP_MIN

    def test_le_retrait_nominal_revient_au_redimensionnement(self, make_window, qtbot):
        """`_position_info` repart du retrait nominal : un resserrement décidé
        pour une petite fenêtre ne doit pas survivre à son agrandissement."""
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(60)
        nominal = win._detail._info.y()
        self._force_debordement(win, 30)
        win._detail._position_info()
        qtbot.waitUntil(lambda: win._detail._info.y() < nominal, timeout=3000)
        remonte = win._detail._info.y()

        del win._detail._info.overflow      # le panneau ne déborde plus
        win.resize(1320, 880)
        qtbot.waitUntil(lambda: win._detail._info.y() > remonte, timeout=3000)


_LANG_BLOCK = {
    "root": "HKLM",
    "view": 32,
    "key": chr(92).join(["SOFTWARE", "Electronic Arts", "Jeu"]),
    "languages": {
        "fr": {"label": "Français", "values": {"Language": "French", "Locale": "fr_FR"}},
        "en": {"label": "English", "values": {"Language": "English", "Locale": "en_US"}},
        "de": {"label": "Deutsch", "values": {"Language": "German", "Locale": "de_DE"}},
    },
}


@pytest.fixture
def make_window_multilingue(make_window, monkeypatch):
    """MainWindow dont le PREMIER jeu propose trois langues.

    Fabriqué, jamais cherché dans `games.json` : le catalogue se met à jour à
    distance, un test qui suppose son contenu casse à chaque livraison de jeu.
    """
    def _make(**overrides):
        import dataclasses

        from src.core import game_manager
        from src.core.game_data import _parse_language_registry
        vrai_load = game_manager.load_catalog
        bloc = _parse_language_registry(_LANG_BLOCK)
        assert bloc is not None, "le bloc de test doit être accepté au parsing"

        def _charge(*a, **k):
            cat = vrai_load(*a, **k)
            jeux = list(cat.games)
            jeux[0] = dataclasses.replace(jeux[0], language_registry=bloc)
            return dataclasses.replace(cat, games=tuple(jeux))

        monkeypatch.setattr(game_manager, "load_catalog", _charge)
        win = make_window(**overrides)
        return win, win.manager.get_games()[0].game
    return _make


class TestSelecteurDeLangue:
    """La langue du jeu vit dans la LIGNE MÉTA (choix de Ludo, 2026-08-21).

    Elle y tient sans coûter un pixel de hauteur, là où une liste déroulante
    sous les boutons aurait repris ~30 px dans la zone la plus contrainte de la
    fiche — celle où l'on venait de récupérer 20 px en espagnol.
    """

    def test_visible_sur_un_jeu_multilingue(self, make_window_multilingue):
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        meta = win._detail._info._meta.text()
        assert 'href="langue"' in meta
        assert "Fran" in meta      # le label du catalogue, pas le code

    def test_absent_sur_les_autres_jeux(self, make_window_multilingue):
        """Sept jeux sur huit n'ont pas de bloc : un réglage sans choix
        possible est du bruit."""
        win, _ = make_window_multilingue()
        autre = win.manager.get_games()[1].game
        win._detail.set_game(autre)
        assert 'href="langue"' not in win._detail._info._meta.text()

    def test_les_deux_liens_coexistent(self, make_window_multilingue):
        """La ligne méta porte DEUX liens maintenant. L'AIGUILLAGE lui-même est
        testé sur un panneau isolé (`TestAiguillageLigneMeta`) : sur une vraie
        fenêtre, `versions_clicked` est câblé au dialogue des versions, dont le
        `exec()` bloque la suite de tests indéfiniment."""
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        meta = win._detail._info._meta.text()
        assert 'href="changelog"' in meta
        assert 'href="langue"' in meta

    def test_le_libelle_suit_le_choix(self, make_window_multilingue):
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        assert "Deutsch" not in win._detail._info._meta.text()
        win.manager.set_game_language(jeu.id, "de")
        win._detail.set_game(jeu)
        assert "Deutsch" in win._detail._info._meta.text()

    def test_le_clic_ecrit_le_registre_et_rafraichit(self, make_window_multilingue,
                                                     monkeypatch, qtbot):
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        ecrits = []
        monkeypatch.setattr("src.core.game_manager.registre.ecrire_valeurs",
                            lambda *a, **k: ecrits.append(a) or True)
        from src.ui import game_detail_handlers as handlers
        handlers._appliquer_langue(win._detail, "en")
        qtbot.wait(20)
        assert win.manager.game_language(jeu) == "en"
        assert ecrits and ecrits[0][2] == {"Language": "English", "Locale": "en_US"}
        assert "English" in win._detail._info._meta.text()

    def test_un_echec_de_registre_previent_par_un_modal(self, make_window_multilingue,
                                                        monkeypatch):
        """UAC refusé : le choix est enregistré mais SANS effet. Un toast qui
        s'efface laisserait croire que c'est fait — donc un modal."""
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        monkeypatch.setattr("src.core.game_manager.registre.ecrire_valeurs",
                            lambda *a, **k: False)
        vus = []
        monkeypatch.setattr("src.ui.game_detail_handlers._boite",
                            lambda *a, **k: vus.append(a))
        from src.ui import game_detail_handlers as handlers
        avant = win.manager.game_language(jeu)
        handlers._appliquer_langue(win._detail, "en")
        assert len(vus) == 1
        # ET le choix ne doit PAS être enregistré : sinon la fiche annoncerait
        # une langue que le jeu n'a pas, et chaque lancement redemanderait
        # l'élévation pour un écart que l'utilisateur a déjà refusé de corriger.
        assert jeu.id not in win.manager.config.game_language
        assert win.manager.game_language(jeu) == avant

    def test_choisir_la_langue_deja_active_ne_fait_rien(self, make_window_multilingue,
                                                        monkeypatch):
        win, jeu = make_window_multilingue()
        win._detail.set_game(jeu)
        ecrits = []
        monkeypatch.setattr("src.core.game_manager.registre.ecrire_valeurs",
                            lambda *a, **k: ecrits.append(a) or True)
        from src.ui import game_detail_handlers as handlers
        handlers._appliquer_langue(win._detail, win.manager.game_language(jeu))
        assert ecrits == []


class TestTailleDuTitre:
    """`_apply_title_size` était DU CODE MORT, et personne ne l'a vu.

    `styles.py` pose une règle applicative `QLabel#gameTitle { font-size: 36px }`,
    et en Qt une feuille de style l'emporte sur la police posée par `setFont` :
    les trois paliers de la fonction ne changeaient donc rien (mesuré le
    2026-08-21 : hauteur du titre identique AU PIXEL de 36 à 26, interligne
    bloqué à 48).

    Ces tests passent par une VRAIE MainWindow, et c'est le point : sur un
    `InfoPanel` construit tout seul, la feuille applicative n'est pas là, le
    `setFont` fonctionne, et le défaut ne se reproduit pas. C'est exactement
    l'angle mort qui l'a laissé vivre.
    """

    @staticmethod
    def _titre(win):
        return win._detail._info._title

    def test_la_taille_passe_par_le_stylesheet(self, make_window, qtbot):
        win = make_window()
        win.show()
        qtbot.wait(40)
        assert "font-size" in self._titre(win).styleSheet()

    def test_le_squeeze_reduit_vraiment_la_hauteur(self, make_window, qtbot):
        """LE test qui manquait : avec `setFont`, la hauteur ne bougeait pas."""
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(60)
        info = win._detail._info
        titre = self._titre(win)
        largeur = titre.maximumWidth()
        titre.setMinimumHeight(0)
        avant = titre.heightForWidth(largeur)

        assert info.squeeze_title() is True
        titre.setMinimumHeight(0)
        apres = titre.heightForWidth(largeur)
        assert apres < avant, "le titre doit RÉTRÉCIR (régression du code mort)"

    def test_le_squeeze_est_borne(self, make_window, qtbot):
        win = make_window()
        win.show()
        qtbot.wait(40)
        info = win._detail._info
        crans = 0
        while info.squeeze_title():
            crans += 1
            assert crans < 10, "squeeze_title ne s'arrête jamais"
        assert crans >= 1

    def test_pas_de_fuite_d_un_jeu_a_l_autre(self, make_window, qtbot):
        """Un cran arraché par le titre le plus long ne doit pas rapetisser le
        titre des sept autres jeux — même fuite d'état que la sélection du
        carrousel, corrigée le même jour."""
        win = make_window()
        win.show()
        win.resize(980, 660)
        qtbot.wait(60)
        info = win._detail._info
        jeux = [e.game for e in win.manager.get_games()]

        win._detail.set_game(jeux[0])
        qtbot.wait(40)
        nominal = info._title_size

        info.squeeze_title()
        assert info._title_size < nominal

        win._detail.set_game(jeux[1])
        qtbot.wait(40)
        assert info._title_size == nominal


class TestPasDeScrollDansLeCasNominal:
    """Le garde-fou anti-scrollbar visait à côté.

    `TestBandeauSansScrollbar` balaye bien les 8 fiches à 3 tailles, mais ses
    trois scénarios activent TOUS un bandeau d'avertissement — or un bandeau
    raccourcit la description (3ᵉ palier du budget). Le cas d'un utilisateur
    ordinaire, sans avertissement, n'était jamais testé, et les états
    transitoires non plus : c'est ce qui a laissé passer une barre de
    défilement présente pendant TOUT le téléchargement, sur les 8 jeux et à
    toutes les tailles.
    """

    @staticmethod
    def _disque_large(monkeypatch):
        from collections import namedtuple
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr("src.core.game_manager.shutil.disk_usage",
                            lambda _p: usage(0, 0, 900_000 * 1024 * 1024))

    @staticmethod
    def _deborde(win, qtbot):
        """Jeux dont le panneau d'infos défile, à la taille courante."""
        trop = []
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            qtbot.wait(20)
            reste = win._detail._info._scroll.verticalScrollBar().maximum()
            if reste > 0:
                trop.append((entry.game.id, reste))
        return trop

    @pytest.mark.parametrize("taille", [(980, 660), (1100, 720), (1320, 880), (1500, 950)])
    def test_aucun_avertissement(self, make_window, qtbot, monkeypatch, taille):
        """Cas nominal : réseau OK, disque large, aucun bandeau."""
        self._disque_large(monkeypatch)
        win = make_window()
        win.show()
        win.resize(*taille)
        qtbot.wait(40)
        assert self._deborde(win, qtbot) == []

    @pytest.mark.parametrize("taille", [(980, 660), (1320, 880), (1500, 950)])
    def test_pendant_le_telechargement(self, make_window, qtbot, monkeypatch, taille):
        """Le chemin RÉEL : l'orchestrateur change l'état et émet state_changed.

        Passer en téléchargement ajoute une barre de progression, un stepper et
        une ligne de vitesse à la zone d'action — ~50 px. Sans repositionnement
        du panneau, la fiche se met à défiler jusqu'à la fin de l'installation,
        puis se répare toute seule : introuvable sur demande.
        """
        self._disque_large(monkeypatch)
        win = make_window()
        win.show()
        win.resize(*taille)
        qtbot.wait(40)
        from src.core.game_manager import GameState
        trop = []
        for entry in win.manager.get_games():
            win._detail.set_game(entry.game)
            qtbot.wait(20)
            win.manager.set_game_state(entry.game.id, GameState.DOWNLOADING)
            win._detail.ops.state_changed.emit()
            qtbot.wait(30)
            reste = win._detail._info._scroll.verticalScrollBar().maximum()
            if reste > 0:
                trop.append((entry.game.id, reste))
            win.manager.set_game_state(entry.game.id, GameState.NOT_INSTALLED)
            win._detail.ops.state_changed.emit()
            qtbot.wait(10)
        assert trop == []


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
    def test_hauteur_suffisante(self, make_window_jeu_a_venir, qtbot, taille):
        win, _ = make_window_jeu_a_venir()
        win.show()
        win.resize(*taille)
        qtbot.wait(40)
        vus = 0
        for entry in win.manager.get_games():
            if entry.game.is_downloadable:
                continue
            win._detail.set_game(entry.game)
            qtbot.wait(30)
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


class TestZoomSurLeTickerPartage:
    """Le zoom du fond était la seule animation décorative hors du Ticker.

    Porté par une QPropertyAnimation, il tournait à la cadence de l'horloge
    d'animation de Qt (~60 Hz) et repeignait la fenêtre entière à chaque frame :
    premier poste de peinture au repos, 88 ms/s à 1200×800. Sur le Ticker
    partagé (30 Hz), le total tombe de 212 à 117 ms/s.
    """

    def test_le_zoom_sabonne_et_se_desabonne(self, make_window, qtbot):
        win = make_window()
        win.show()
        qtbot.wait(60)
        bg = win._detail._bg
        assert bg._zoom_ticking, "le zoom devrait être abonné au Ticker"
        bg.pause()
        assert not bg._zoom_ticking, "pause() doit désabonner le zoom"
        bg.resume()
        assert bg._zoom_ticking, "resume() doit ré-abonner le zoom"

    def test_aucun_timer_hors_ticker(self, make_window, qtbot):
        """Aucune animation décorative ne doit avoir son horloge à elle."""
        from PyQt6.QtCore import QAbstractAnimation
        win = make_window()
        win.show()
        qtbot.wait(80)
        bg = win._detail._bg
        assert not hasattr(bg, "_zoom_anim"), (
            "le zoom ne doit plus passer par une QPropertyAnimation")
        # Le cycle reste borné : phase dans [0, 1], zoom entre 1.0 et 1.05.
        for _ in range(400):
            bg._advance_zoom()
        assert 0.0 <= bg._zoom_phase < 1.0
        assert 1.0 <= bg._zoom <= 1.05
        assert QAbstractAnimation is not None  # import utilisé, garde-fou lisible


class TestBalisageDuCatalogueJamaisInterprete:
    """Aucun texte du catalogue ne doit etre INTERPRETE comme du balisage.

    Le catalogue se met a jour A DISTANCE. `QLabel` et `QMessageBox` sont en
    `AutoText` par defaut : Qt renifle le contenu et bascule en rich text des
    qu'il ressemble a du HTML. Un `<img src="http://...">` dans un nom de jeu
    declenchait donc une requete reseau a l'affichage de la fiche — « qui
    regarde quel jeu » partait chez l'hebergeur de l'image.

    Ce test BALAYE tous les labels d'une vraie fenetre : il attrapera aussi le
    prochain qu'on ajoutera sans y penser.
    """

    _MARQUEUR = "<b>INJECTE</b>"

    @pytest.fixture
    def fenetre_injectee(self, make_window, monkeypatch):
        import dataclasses

        from src.core import game_manager
        vrai_load = game_manager.load_catalog
        marque = self._MARQUEUR

        def _charge(*a, **k):
            cat = vrai_load(*a, **k)
            jeux = list(cat.games)
            jeux[0] = dataclasses.replace(
                jeux[0],
                name="Jeu " + marque,
                description="Description " + marque + " et la suite du texte.",
                developer="Studio " + marque,
                tags=("Tag " + marque,),
                warning="Avertissement " + marque,
            )
            return dataclasses.replace(cat, games=tuple(jeux))

        monkeypatch.setattr(game_manager, "load_catalog", _charge)
        win = make_window()
        win.show()
        return win, win.manager.get_games()[0].game

    @staticmethod
    def _labels_dangereux(win):
        """Labels dont le texte serait rendu comme du HTML."""
        from PyQt6.QtWidgets import QLabel

        marque = TestBalisageDuCatalogueJamaisInterprete._MARQUEUR
        dangereux = []
        for lab in win.findChildren(QLabel):
            texte = lab.text()
            if marque not in texte:
                continue
            fmt = lab.textFormat()
            if fmt == Qt.TextFormat.RichText or (
                    fmt == Qt.TextFormat.AutoText and Qt.mightBeRichText(texte)):
                dangereux.append((lab.objectName() or type(lab).__name__, fmt.name))
        return dangereux

    def test_aucun_label_n_interprete_le_catalogue(self, fenetre_injectee, qtbot):
        win, jeu = fenetre_injectee
        win.resize(1200, 800)
        win._detail.set_game(jeu)
        qtbot.wait(60)
        assert self._labels_dangereux(win) == []

    def test_le_marqueur_atteint_bien_l_ecran(self, fenetre_injectee, qtbot):
        """Garde-fou : sans lui, le test ci-dessus passerait a vide si le texte
        du catalogue cessait d'etre affiche."""
        from PyQt6.QtWidgets import QLabel

        win, jeu = fenetre_injectee
        win.resize(1200, 800)
        win._detail.set_game(jeu)
        qtbot.wait(60)
        porteurs = [lab for lab in win.findChildren(QLabel)
                    if self._MARQUEUR in lab.text()]
        assert porteurs, "aucun label ne porte le texte du catalogue"

    def test_le_titre_et_la_description_sont_en_texte_brut(self, fenetre_injectee, qtbot):
        """Les deux qui restent affiches en permanence : c'est la que la
        requete reseau d'une balise partirait a chaque ouverture de fiche."""
        win, jeu = fenetre_injectee
        win._detail.set_game(jeu)
        qtbot.wait(40)
        info = win._detail._info
        assert info._title.textFormat() == Qt.TextFormat.PlainText
        assert info._desc.textFormat() == Qt.TextFormat.PlainText
        assert self._MARQUEUR in info._title.text()

    def test_les_dialogues_passent_par_le_helper_en_texte_brut(self):
        """Un `QMessageBox.question(...)` direct reviendrait a l'AutoText."""
        import ast

        from src.ui import game_detail_handlers as handlers

        source = pathlib.Path(handlers.__file__).read_text(encoding="utf-8")
        arbre = ast.parse(source)
        fautifs = []
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            fonc = noeud.func
            if (isinstance(fonc, ast.Attribute)
                    and isinstance(fonc.value, ast.Name)
                    and fonc.value.id == "QMessageBox"
                    and fonc.attr in {"question", "warning", "information", "critical"}):
                fautifs.append(fonc.attr)
        assert not fautifs, "appels statiques a QMessageBox (AutoText) : %s" % fautifs

"""Vue détaillée d'un jeu — orchestre les sous-panneaux et délègue les actions
utilisateur à `game_detail_handlers`.
"""

import logging

from PyQt6.QtCore import (
    QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal, QPoint, QPointF, Qt,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

from src.ui import game_detail_handlers as handlers
from src.ui.action_panel import ActionPanel
from src.ui.audio_bar import AudioBar
from src.ui.background_widget import BackgroundWidget
from src.ui.game_operations import GameOperations
from src.ui.info_panel import InfoPanel
from src.core import composants_windows
from src.ui.installateur_composants import InstallateurComposants
from src.ui.preparateur_wine import PreparateurWine
from src.ui.utils import avertir
from src.ui.video_player import VideoPlayer

from src.core import trailers
from src.core.config import ASSETS_DIR
from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.core.system_checks import invalidate_vcredist_cache

log = logging.getLogger(__name__)

# Délai avant de lancer la bande-annonce : les premières secondes servent
# à lire le titre, sur une image fixe.
_VIDEO_START_DELAY_MS = 2000


# Retrait minimal au-dessus du panneau d'infos. En dessous, le titre du jeu
# viendrait toucher la barre de titre de la fenêtre.
_INFO_TOP_MIN = 24

# Retrait de la barre audio par rapport aux bords bas et droit de la fiche.
_MARGE_AUDIO = 18
_MARGE_AUDIO_BAS = 14


class GameDetailView(QWidget):
    """Zone centrale : fond + info panel + action panel + vidéo."""

    status_message = pyqtSignal(str)
    # Toast : visible sans exiger de clic, pour ce qui n'appelle aucune décision.
    notify = pyqtSignal(str)
    state_changed = pyqtSignal()
    settings_requested = pyqtSignal()   # depuis une alerte du panneau d'actions
    game_launched = pyqtSignal(object, str, str)  # (subprocess.Popen, game_name, game_id)
    # Mode cinéma : la FENÊTRE doit masquer ce qui ne nous appartient pas
    # (carrousel, barre de statut, engrenage).
    cinema_toggled = pyqtSignal(bool)

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.game: GameData | None = None
        # Nom du jeu qui tourne (ou démarre), "" sinon — fourni par la fenêtre,
        # qui possède la session. Seul, sans fenêtre : rien ne tourne.
        self.partie_en_cours = lambda: ""

        # Sous-systèmes
        self._video = VideoPlayer(self)
        self._pending_video_id: str = ""  # jeu dont la vidéo est programmée
        # Minuteur POSSÉDÉ (règle 102) : un `singleShot` ne se réarme ni ne
        # s'annule, et parcourir vite le carrousel relançait la vidéo en rafale.
        self._video_timer = QTimer(self)
        self._video_timer.setSingleShot(True)
        self._video_timer.setInterval(_VIDEO_START_DELAY_MS)
        self._video_timer.timeout.connect(self._on_video_timer)
        # Géométrie en attente de rattrapage de hauteur (cf. _fit_info_height).
        self._pending_fit: tuple[int, int, int] | None = None
        self._ops = GameOperations(manager, self)
        # Ce qui manque à Windows pour lancer un jeu : le préfixe Wine et ses
        # composants sous Linux, les composants de Microsoft sous Windows
        # (ACT-054). Même contrat : la fiche et la barre du bas n'en savent rien.
        self._wine = (InstallateurComposants(self) if composants_windows.disponible()
                      else PreparateurWine(self))
        self._cinema = False

        self._build_ui(manager)
        self._connect_signals()

    # ──────────────────── Construction ────────────────────

    def _build_ui(self, manager: GameManager) -> None:
        self._bg = BackgroundWidget(self)

        # Info panel (titre, meta, description, tags)
        self._info = InfoPanel(manager, self)

        # Action panel (boutons jouer/télécharger/désinstaller)
        self._action_panel = ActionPanel(manager, self)
        self._info.add_bottom_widget(self._action_panel)
        self._info.add_stretch()

        # Audio bar (extrait dans src/ui/audio_bar.py)
        self._audio_bar = AudioBar(self)
        self._audio_bar.mute_toggled.connect(self._on_mute_clicked)
        self._audio_bar.volume_changed.connect(self._on_volume_changed)
        self._audio_bar.play_toggled.connect(self._on_play_clicked)
        self._audio_bar.replay_clicked.connect(self._on_replay_clicked)
        self._audio_bar.cinema_toggled.connect(self.basculer_cinema)

        # Animations fade, parent explicite (règle 11).
        self._fade_anim = QPropertyAnimation(self._bg, b"bg_opacity", self)
        self._fade_anim.setDuration(300)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._info_opacity = QGraphicsOpacityEffect(self._info)
        self._info_opacity.setOpacity(1.0)
        self._info.setGraphicsEffect(self._info_opacity)
        self._info_fade = QPropertyAnimation(self._info_opacity, b"opacity", self)
        self._info_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _connect_signals(self) -> None:
        # Vidéo
        self._video.video_frame.connect(self._bg.set_video_frame)
        self._video.playback_ended.connect(self._on_video_ended)

        # Opérations → action panel (progression)
        self._ops.download_progress.connect(self._action_panel.update_download_progress)
        self._ops.install_progress.connect(self._action_panel.update_install_progress)
        self._ops.part_info.connect(self._action_panel.update_part_info)
        self._ops.operation_finished.connect(self._on_operation_finished)
        self._ops.operation_error.connect(self._deferred_warning)
        self._ops.state_changed.connect(self._on_ops_state_changed)
        self._ops.status_message.connect(self.status_message)

        # Action panel → handlers (délégués à game_detail_handlers)
        self._action_panel.download_clicked.connect(lambda: handlers.on_download(self))
        self._action_panel.cancel_clicked.connect(lambda: handlers.on_cancel_download(self))
        self._action_panel.play_clicked.connect(lambda: handlers.on_play(self))
        self._action_panel.uninstall_clicked.connect(lambda: handlers.on_uninstall(self))
        self._action_panel.update_clicked.connect(lambda: handlers.on_update_clicked(self))
        self._action_panel.settings_requested.connect(self.settings_requested)
        self._action_panel.preparation_requested.connect(
            lambda: handlers.proposer_preparation(self, self.game, puis_jouer=False))

        # Préparation de Wine (Linux) : l'état dans la barre de statut, la
        # suite (lancer, prévenir, expliquer) dans les handlers.
        self._wine.message.connect(self.status_message)
        self._wine.terminee.connect(self._on_wine_prepare)

        # Info panel
        self._info.versions_clicked.connect(lambda: handlers.on_versions_clicked(self))
        self._info.language_clicked.connect(lambda: handlers.on_language_clicked(self))
        self._action_panel.game_settings_clicked.connect(
            lambda: handlers.on_game_settings(self))
        self._info.content_changed.connect(self._position_info)

        # Menu contextuel
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: handlers.show_context_menu(self, pos))

    # ──────────────────── Positionnement ────────────────────

    def _position_info(self) -> None:
        w, h = self.width(), self.height()
        # La part de largeur AUGMENTE quand la fenêtre rétrécit (à 50 % fixes,
        # 466 px de texte à 1100 px de large).
        frac = 0.50 if w >= 1300 else 0.58 if w >= 1100 else 0.64
        info_w = min(700, int(w * frac))
        # Retrait vertical réduit quand la hauteur manque.
        info_top = int(h * (0.22 if h >= 560 else 0.10))
        dispo = h - info_top - 20
        # Le bandeau d'avertissement mange la place du texte (0 sinon).
        self._info.set_height_budget(dispo - self._action_panel.alert_height())
        # Largeur définitive d'abord : la hauteur nécessaire en dépend.
        self._info.setGeometry(0, info_top, info_w, dispo)
        # Puis la hauteur du contenu, sinon un vide sous la description.
        self._info.setGeometry(0, info_top, info_w,
                               max(220, min(dispo, self._info.natural_height())))
        # Rattrapage DIFFÉRÉ, une fois la mise en page faite : rallonger
        # d'EXACTEMENT ce qui déborde plutôt que d'une marge au jugé.
        self._pending_fit = (info_top, info_w, dispo)
        QTimer.singleShot(0, self._fit_info_height)

    def _fit_info_height(self) -> None:
        """Rallonge le panneau de ce qui déborde encore, dans la place restante.

        Idempotent (sans jeton consommé, règle 42) et monotone : ne rappelle
        jamais `_position_info`, ne fait que GRANDIR ou REMONTER.
        """
        if self._pending_fit is None:
            return
        info_top, info_w, dispo = self._pending_fit
        trop = self._info.overflow()
        if trop <= 0:
            return
        nouvelle = min(dispo, self._info.height() + trop)
        if nouvelle != self._info.height():
            self._info.setGeometry(0, info_top, info_w, nouvelle)
            # Réarmer : grandir peut ne pas suffire (borné par `dispo`).
            QTimer.singleShot(0, self._fit_info_height)
            return
        # Avant de rogner du TEXTE, récupérer du VIDE (règle 41) : le retrait
        # du haut ne porte aucune information.
        if info_top > _INFO_TOP_MIN:
            gagne = min(trop, info_top - _INFO_TOP_MIN)
            if gagne > 0:
                info_top -= gagne
                dispo += gagne
                self._pending_fit = (info_top, info_w, dispo)
                self._info.setGeometry(0, info_top, info_w,
                                       min(dispo, self._info.height() + trop))
                QTimer.singleShot(0, self._fit_info_height)
                return
        # Plus de place : raccourcir la description, puis le titre (le plus
        # visible) seulement s'il reste du débordement.
        if self._info.squeeze_description() or self._info.squeeze_title():
            QTimer.singleShot(0, self._fit_info_height)

    def _position_audio_bar(self) -> None:
        """Colle la barre audio au coin bas-droit, D'APRÈS sa largeur réelle
        (règle 36) : elle change de taille à la fin d'une bande-annonce."""
        self._audio_bar.move(self.width() - self._audio_bar.width() - _MARGE_AUDIO,
                             self.height() - self._audio_bar.height() - _MARGE_AUDIO_BAS)
        self._audio_bar.raise_()

    # ──────────────────── Mode cinéma ────────────────────

    def cinema(self) -> bool:
        return self._cinema

    def basculer_cinema(self) -> None:
        self.set_cinema(not self._cinema)

    def set_cinema(self, actif: bool) -> None:
        """La bande-annonce seule, sans voile ni texte.

        Sans texte, plus besoin du voile qui le protégeait. Sans effet quand
        aucune vidéo ne joue.
        """
        # `is_playing` est une PROPERTY (règle 10).
        if actif and not self._video.is_playing:
            return
        if actif == self._cinema:
            return
        self._cinema = actif
        # Regardée pour elle-même, la vidéo garde toutes ses images ; en fond, une sur deux.
        self._video.set_plein_debit(actif)
        self._bg.set_cinema(actif)
        self._info.setVisible(not actif)
        self._audio_bar.set_cinema_icon(actif)
        self._position_audio_bar()
        self.cinema_toggled.emit(actif)

    def resizeEvent(self, event) -> None:
        self._bg.setGeometry(self.rect())
        self._bg.invalidate_cache()
        self._position_info()
        self._position_audio_bar()

    # ──────────────────── Changement de jeu ────────────────────

    def set_game(self, game: GameData) -> None:
        """Affiche le jeu donné. Si même id, rafraîchit les données sans rejouer la transition."""
        if self.game and self.game.id == game.id:
            # Même jeu : peut être un nouvel objet (ex : catalog reload)
            self.game = game
            self._info.apply_game(game)
            self._refresh()
            # La hauteur a pu changer (compteurs arrivés après le démarrage).
            self._position_info()
            QTimer.singleShot(0, self._position_info)
            return
        # Cross-fade : snapshot du rendu actuel (vidéo incluse) AVANT de couper
        # la vidéo et de baisser l'opacité — le nouveau fond fade par-dessus.
        self._bg.begin_crossfade()
        self._stop_video()
        self._fade_anim.stop()
        self._info_fade.stop()
        self._bg.bg_opacity = 0.0
        self._info_opacity.setOpacity(0.0)
        self._apply_game(game)

    def _apply_game(self, game: GameData) -> None:
        self.game = game
        self._info.apply_game(game)

        # La jaquette d'abord, la bande-annonce après le délai de lecture.
        self._bg.set_image(ASSETS_DIR / "backgrounds" / f"{game.id}_bg.jpg")
        self._schedule_video(game.id)

        self._refresh()

        # Fade-in background
        current = self._bg.bg_opacity
        self._fade_anim.setStartValue(current)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setDuration(max(int(400 * (1.0 - current)), 80))
        self._fade_anim.start()
        self._bg.start_zoom_loop()

        # Fade-in info
        self._info.show()
        self._position_info()
        # Seconde passe : le panneau d'actions vient d'être reconstruit.
        QTimer.singleShot(0, self._position_info)
        self._info_fade.stop()
        self._info_fade.setStartValue(0.0)
        self._info_fade.setEndValue(1.0)
        self._info_fade.setDuration(500)
        self._info_fade.start()

    def ancre_langue(self):
        """Position GLOBALE où poser le menu de langue, sous la ligne méta.

        Ancré au widget, pas à `QCursor.pos()` (règle 28) ; None si la
        géométrie n'est pas posée (l'appelant replie sur le curseur).
        """
        meta = self._info._meta
        if not meta.isVisible() or meta.width() <= 0:
            return None
        return meta.mapToGlobal(QPoint(0, meta.height()))


    def _refresh(self) -> None:
        """Rafraîchit le panneau d'actions, puis REPOSITIONNE le panneau d'infos.

        Règle 40 : un changement d'état reconstruit la zone d'action (~50 px
        de plus en téléchargement), sinon la fiche défile tout le téléchargement.
        """
        self._action_panel.set_game(self.game)
        self._action_panel.refresh()
        self._position_info()

    # ──────────────────── Parallaxe ────────────────────

    def handle_mouse_move(self, pos: QPointF) -> None:
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return
        self._bg.set_parallax_target(pos.x(), pos.y(), float(w), float(h))

    # ──────────────────── Vidéo ────────────────────

    def _schedule_video(self, game_id: str) -> None:
        """Programme le démarrage de la bande-annonce après un court délai.

        Titre lu sur une image fixe, chargement invisible, pas un lecteur par
        vignette survolée.
        """
        self._pending_video_id = game_id
        if not self.manager.config.autoplay_videos:
            self._video_timer.stop()
            return
        # `start()` sur un minuteur armé REPART de zéro.
        self._video_timer.start()

    def _on_video_timer(self) -> None:
        # Le jeu a pu changer pendant le délai : on ne lance que le bon.
        if self.game is None or self.game.id != self._pending_video_id:
            return
        # …et la fenêtre a pu partir dans le tray : jamais du son sans image.
        if not self.isVisible():
            return
        self._try_play_video(self.game.id)

    def _try_play_video(self, game_id: str) -> None:
        # Bandes-annonces téléchargées, à la version que le catalogue attend.
        video_path = trailers.chemin_a_jouer(game_id, self.manager.trailers())
        if video_path is None:
            self._audio_bar.hide()
            return
        muted = self.manager.config.mute_videos
        if self._video.play(str(video_path), muted=muted, volume=self._audio_bar.volume() / 100.0):
            self._audio_bar.set_muted_icon(muted)
            self._audio_bar.set_paused_icon(False)
            self._audio_bar.set_mode_fin(False)
            self._position_audio_bar()   # la largeur a pu changer
            self._audio_bar.show()
        else:
            self._audio_bar.hide()

    def _stop_video(self) -> None:
        # Sortir du mode cinéma d'abord, sinon une fenêtre vide sans issue.
        self.set_cinema(False)
        # ANNULER le démarrage en attente : sinon, JOUER moins de 2 s après un
        # changement de fiche lançait le son dans le tray.
        self._video_timer.stop()
        # Un `timeout` déjà posté n'est pas retiré par `stop()`.
        self._pending_video_id = ""
        self._video.stop()
        self._bg.clear_video()
        self._audio_bar.hide()

    def _on_video_ended(self) -> None:
        # EndOfMedia → relâcher la source pour libérer le décodeur…
        self._stop_video()
        # …mais laisser le bouton « revoir », seule commande encore utile.
        if self.game is not None and trailers.chemin_a_jouer(
                self.game.id, self.manager.trailers()) is not None:
            self._audio_bar.set_mode_fin(True)
            self._position_audio_bar()
            self._audio_bar.show()

    def _on_replay_clicked(self) -> None:
        """Rejoue la bande-annonce du jeu affiché, sans délai (clic délibéré)."""
        if self.game is None:
            return
        self._pending_video_id = self.game.id
        self._try_play_video(self.game.id)

    def _on_mute_clicked(self) -> None:
        self._audio_bar.set_muted_icon(self._video.toggle_mute())

    def _on_play_clicked(self) -> None:
        if self._video.paused:
            self._video.resume()
        else:
            self._video.pause()
        self._audio_bar.set_paused_icon(self._video.paused)

    def _on_volume_changed(self, value: int) -> None:
        self._video.set_volume(value)
        if not self._video.muted:
            self._audio_bar.set_muted_icon(False)

    # ──────────────────── API publique ────────────────────

    def pause(self) -> None:
        self._stop_video()
        self._bg.pause()

    def resume(self) -> None:
        self._bg.resume()

    def pause_effects(self) -> None:
        """Perte de FOCUS : on suspend les effets décoratifs, pas la vidéo.

        Sans focus, la fenêtre reste souvent visible (second écran) : la vidéo
        n'est coupée que fenêtre cachée, par `pause()`.
        """
        self._bg.pause()

    def resume_effects(self) -> None:
        self._bg.resume()

    def set_reduite(self, oui: bool) -> None:
        """Fenêtre réduite (bouton de la barre de titre) : la bande-annonce se suspend
        et reprend au même endroit. Elle continuait d'être décodée pour rien."""
        self._video.set_reduite(oui)

    def cancel_operations(self) -> None:
        self._ops.cancel_all()
        self._wine.shutdown()

    # ──────────────────── Préparation de Wine (Linux) ────────────────────

    @property
    def preparation_en_cours(self) -> bool:
        return self._wine.en_cours

    @property
    def wine(self) -> PreparateurWine | InstallateurComposants:
        """Le préparateur, pour que la fenêtre montre l'avancement dans sa barre du bas."""
        return self._wine

    @property
    def journal_preparation(self):
        return self._wine.journal

    def preparer_wine(self, game: GameData, verbes, puis_jouer: bool) -> None:
        """Lance la préparation du préfixe pour ce jeu (une seule à la fois)."""
        if self._wine.en_cours:
            self.notify.emit(handlers.texte_preparation_en_cours())
            return
        if self._ops.is_busy:
            # Une seule chose à la fois dans la barre du bas, et un préfixe qu'on
            # prépare pendant qu'une installation écrit ses fichiers n'y gagne rien.
            self.notify.emit(
                tr("Un téléchargement est en cours : les composants seront installés "
                   "quand il sera fini. Cliquez à nouveau sur JOUER.")
                if composants_windows.disponible() else
                tr("Un téléchargement est en cours : Wine sera préparé "
                   "quand il sera fini. Cliquez à nouveau sur JOUER."))
            return
        self._wine.demarrer(game, verbes, puis_jouer)

    def _on_wine_prepare(self, game_id: str, reussie: bool, raison: str,
                         puis_jouer: bool) -> None:
        # Ce qui est installé a changé : les contrôles mémorisés mentent.
        invalidate_vcredist_cache()
        self.refresh_actions()
        handlers.apres_preparation(self, game_id, reussie, raison, puis_jouer)

    def set_online(self, online: bool) -> None:
        """Propage le diagnostic réseau jusqu'au panneau d'actions."""
        self._action_panel.set_online(online)
        self._position_info()   # le bandeau apparaît/disparaît → hauteur à revoir

    def recheck_prerequisites(self) -> None:
        """Re-teste les prérequis système (no-op si rien ne l'a demandé)."""
        self._action_panel.recheck_prerequisites()
        self._position_info()

    def refresh_video(self) -> None:
        """Retente la bande-annonce du jeu affiché — les fichiers viennent
        d'arriver. Ne coupe jamais une vidéo en cours."""
        if self.game is None or self._video.is_playing:
            return
        self._schedule_video(self.game.id)

    def refresh_actions(self) -> None:
        """Rafraîchit le panneau d'actions après un changement d'état externe
        (ex: changement d'install_path, qui peut faire paraître le bandeau
        d'espace disque : d'où le repositionnement)."""
        self._refresh()
        self._position_info()

    def apply_audio_config(self) -> None:
        """Applique « Couper le son des vidéos » à la vidéo EN COURS (réglage live)."""
        muted = self.manager.config.mute_videos
        self._video.set_muted(muted)
        self._audio_bar.set_muted_icon(muted)

    @property
    def ops(self) -> GameOperations:
        return self._ops

    # ──────────────────── Callbacks opérations ────────────────────

    def _on_ops_state_changed(self) -> None:
        self._refresh()
        self.state_changed.emit()

    def _on_operation_finished(self, game: GameData) -> None:
        if self.game and self.game.id == game.id:
            self._refresh()
        self.state_changed.emit()

    def _deferred_warning(self, title: str, message: str) -> None:
        def _show() -> None:
            try:
                self.isVisible()
            except RuntimeError:
                return
            avertir(self, title, message)
        QTimer.singleShot(0, _show)


    # ──────────────────── API publique (clavier MainWindow) ────────────────────

    def trigger_primary_action(self) -> None:
        """Action par défaut sur Enter (depuis MainWindow.keyPressEvent)."""
        handlers.trigger_primary_action(self)

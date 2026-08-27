"""Vue détaillée d'un jeu — orchestre les sous-panneaux et délègue les actions
utilisateur à `game_detail_handlers`.
"""

import logging

from PyQt6.QtCore import (
    QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal, QPoint, QPointF, Qt,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QMessageBox, QWidget

from src.ui import game_detail_handlers as handlers
from src.ui.action_panel import ActionPanel
from src.ui.audio_bar import AudioBar
from src.ui.background_widget import BackgroundWidget
from src.ui.game_operations import GameOperations
from src.ui.info_panel import InfoPanel
from src.ui.video_player import VideoPlayer

from src.core import trailers
from src.core.config import ASSETS_DIR
from src.core.game_data import GameData
from src.core.game_manager import GameManager

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
    # Message ÉPHÉMÈRE et visible (toast), pour ce qui méritait un dialogue
    # modal sans mériter d'interrompre : « déjà en cours », « sauvegardes
    # conservées »… La status bar, elle, passe inaperçue ; un modal, lui, exige
    # un clic pour dire quelque chose qui n'appelle aucune décision.
    notify = pyqtSignal(str)
    state_changed = pyqtSignal()
    settings_requested = pyqtSignal()   # depuis une alerte du panneau d'actions
    game_launched = pyqtSignal(object, str, str)  # (subprocess.Popen, game_name, game_id)
    # Mode cinéma : la bande-annonce seule, sans voile ni texte. La FENÊTRE
    # doit en être avertie — le carrousel, la barre de statut et l'engrenage
    # ne lui appartiennent pas, et les laisser en place ferait une fiche à
    # moitié effacée plutôt qu'un plein écran.
    cinema_toggled = pyqtSignal(bool)

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.game: GameData | None = None

        # Sous-systèmes
        self._video = VideoPlayer(self)
        self._pending_video_id: str = ""  # jeu dont la vidéo est programmée
        # Minuteur POSSÉDÉ, et non un `QTimer.singleShot` : celui-ci ne
        # s'annule pas et surtout ne se RÉARME pas. Chaque changement de jeu en
        # ajoutait donc un de plus, et le premier de la rafale tirait sur le jeu
        # affiché en DERNIER — parcourir vite le carrousel lançait la vidéo bien
        # avant la fin du délai, et les minuteurs suivants la relançaient depuis
        # le début (Ludo, 2026-08-23). `start()` sur un minuteur déjà armé
        # repart de zéro : le délai est enfin remis à zéro à chaque jeu, et
        # `stop()` l'annule pour de bon.
        self._video_timer = QTimer(self)
        self._video_timer.setSingleShot(True)
        self._video_timer.setInterval(_VIDEO_START_DELAY_MS)
        self._video_timer.timeout.connect(self._on_video_timer)
        # Géométrie en attente de rattrapage de hauteur (cf. _fit_info_height).
        self._pending_fit: tuple[int, int, int] | None = None
        self._ops = GameOperations(manager, self)
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

        # Animations fade
        self._fade_anim = QPropertyAnimation(self._bg, b"bg_opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._info_opacity = QGraphicsOpacityEffect(self._info)
        self._info_opacity.setOpacity(1.0)
        self._info.setGraphicsEffect(self._info_opacity)
        self._info_fade = QPropertyAnimation(self._info_opacity, b"opacity")
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
        # Part de largeur donnée au panneau. Elle AUGMENTE quand la fenêtre
        # rétrécit : à 50 % fixes, une fenêtre de 1100 px ne laissait que 466 px
        # utiles au texte, le titre passait à trois lignes et la description
        # sortait de l'écran — pendant que la moitié droite restait vide.
        frac = 0.50 if w >= 1300 else 0.58 if w >= 1100 else 0.64
        info_w = min(700, int(w * frac))
        # Retrait vertical : généreux sur grand écran (le panneau respire), réduit
        # quand la hauteur manque — 22 % de 427 px, c'est 94 px de vide au-dessus
        # du titre pendant que la description sortait par le bas.
        info_top = int(h * (0.22 if h >= 560 else 0.10))
        dispo = h - info_top - 20
        # Un bandeau d'avertissement mange la place du texte. Sans cette
        # soustraction, la description garde sa longueur de fenêtre confortable
        # et le panneau se remet à défiler dès qu'un avertissement s'affiche.
        # Vaut 0 en temps normal : le cas nominal est inchangé.
        self._info.set_height_budget(dispo - self._action_panel.alert_height())
        # Poser d'abord la largeur définitive : la hauteur nécessaire en dépend.
        self._info.setGeometry(0, info_top, info_w, dispo)
        # Puis rétrécir à ce que le contenu réclame — la zone d'action est
        # épinglée en bas du panneau, donc un panneau trop haut creuse un vide
        # entre la description et le bouton.
        self._info.setGeometry(0, info_top, info_w,
                               max(220, min(dispo, self._info.natural_height())))
        # Rattrapage DIFFÉRÉ : `natural_height()` sous-estime dans les cas
        # limites (titre sur trois lignes, note « bientôt disponible » sur
        # deux), et il est de toute façon calculé avant que la zone d'action
        # n'ait sa taille définitive. Plutôt que de regonfler une marge fixe au
        # jugé — ce qui ne ferait que déplacer le seuil — on repasse une fois la
        # mise en page faite et on rallonge d'EXACTEMENT ce qui déborde.
        self._pending_fit = (info_top, info_w, dispo)
        QTimer.singleShot(0, self._fit_info_height)

    def _fit_info_height(self) -> None:
        """Rallonge le panneau de ce qui déborde encore, dans la place restante.

        Idempotent : dès que tout tient, `overflow()` vaut 0 et l'appel ne fait
        rien. C'est ce qui permet de le laisser s'exécuter autant de fois qu'il
        est programmé, sans consommer de jeton — `_position_info` est appelé
        plusieurs fois d'affilée lors d'un changement de jeu, et une passe qui
        s'exécutait trop tôt (avant que la zone d'action ait sa taille finale)
        aurait sinon désamorcé toutes les suivantes.

        Ne rappelle JAMAIS `_position_info`, et ne fait que GRANDIR : aucune
        oscillation possible.
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
            # Réarmer : grandir peut ne pas suffire (on est borné par `dispo`),
            # et sans cette passe de plus la chaîne s'arrêtait là. Elle ne
            # convergeait que parce que `_position_info` est appelé plusieurs
            # fois d'affilée lors d'un changement de jeu — c'est-à-dire par
            # accident. Aucune boucle possible : chaque passe ne fait que
            # GRANDIR ou REMONTER, les deux sont bornées, et `overflow() <= 0`
            # sort immédiatement.
            QTimer.singleShot(0, self._fit_info_height)
            return
        # Le panneau occupe toute la hauteur qu'on lui a accordée. Avant de
        # rogner du TEXTE, récupérer du VIDE : le retrait du haut vaut 10 % de
        # la fiche (49 px à 980×660) et ne porte aucune information. Remonter le
        # panneau d'autant qu'il déborde ne coûte donc rien à l'utilisateur,
        # là où un cran d'accroche en moins lui coûte deux lignes de texte.
        #
        # Le cas qui l'a imposé existait AVANT le bandeau du catalogue : en
        # espagnol, à 980×660, l'avertissement d'espace disque faisait déjà
        # défiler la fiche de HP7 de 20 px. Invisible à la suite de tests (qui
        # mesure une police substituée) comme à `tools/audit_geometrie.py` (qui
        # écarte le bandeau par conception) — mesuré sur la plateforme native.
        #
        # Monotone et borné : on ne fait que remonter, jamais redescendre, et
        # `_position_info` repart du retrait nominal à chaque redimensionnement.
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
        # Le panneau occupe déjà toute la place que la fenêtre lui laisse : la
        # seule variable qui reste est la longueur de l'accroche. Mieux vaut
        # deux lignes de moins suivies de « Lire la suite » qu'une barre de
        # défilement qui cache le bouton principal.
        # La description d'abord — la moins coûteuse à raccourcir. Le titre
        # ensuite, et seulement s'il reste du débordement : c'est le plus gros
        # bloc du panneau, mais aussi le plus visible.
        if self._info.squeeze_description() or self._info.squeeze_title():
            QTimer.singleShot(0, self._fit_info_height)

    def _position_audio_bar(self) -> None:
        """Colle la barre audio au coin bas-droit, D'APRÈS sa largeur réelle.

        Elle était placée à `width() - 174` pour 192 px de large : 18 px
        passaient donc HORS de la fenêtre, et la poignée de volume disparaissait
        dès qu'on montait le son à fond (Ludo, 2026-08-23). Deux nombres qu'aucun
        calcul ne relie — exactement le défaut du carrousel, le même jour. La
        barre change en plus de taille à la fin d'une bande-annonce : lire sa
        largeur est la seule façon de rester juste.
        """
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

        Le voile de 30 % vient d'être posé sur le chemin vidéo pour rendre le
        titre et la description lisibles — c'est mesuré, et ce n'est pas
        négociable tant qu'il y a un texte à lire par-dessus. Mais quelqu'un qui
        veut simplement REGARDER la bande-annonce n'a aucune raison de la subir
        assombrie : ici on retire le texte, donc on retire aussi ce qui le
        protégeait. Le compromis disparaît au lieu d'être arbitré à la place de
        l'utilisateur.

        Sans effet quand aucune vidéo ne joue : un « plein écran » qui agrandit
        une image fixe déjà en plein écran ne fait que vider l'interface.
        """
        # `is_playing` est une PROPERTY, pas une méthode : l'appeler lèverait
        # `TypeError` au premier clic sur le bouton. Exactement le défaut qui
        # avait empêché toute installation pendant une journée
        # (`_speed_tracker.speed()`), et invisible ici pour la même raison —
        # l'autre chemin (`set_cinema(False)`, appelé par `_stop_video`)
        # court-circuite le `and` et ne l'évalue jamais.
        if actif and not self._video.is_playing:
            return
        if actif == self._cinema:
            return
        self._cinema = actif
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
            # Le contenu a pu changer de hauteur — c'est le cas quand les
            # compteurs de téléchargement arrivent quelques secondes après le
            # démarrage et rallongent la ligne méta. Sans ce repositionnement,
            # le panneau garde sa taille d'avant et rogne « Lire la suite ».
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

        # Background — la jaquette d'abord, la bande-annonce ensuite (voir
        # _schedule_video) : les premières secondes sont celles où on lit le
        # titre et la description, et du mouvement derrière le texte y nuit.
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
        # Deuxième passe au tour de boucle suivant : à la première, le panneau
        # d'actions vient d'être reconstruit et la hauteur réclamée par le
        # contenu n'est pas encore stabilisée — on gardait un panneau trop haut,
        # donc un vide entre la description et le bouton.
        QTimer.singleShot(0, self._position_info)
        self._info_fade.stop()
        self._info_fade.setStartValue(0.0)
        self._info_fade.setEndValue(1.0)
        self._info_fade.setDuration(500)
        self._info_fade.start()

    def ancre_langue(self):
        """Position GLOBALE où poser le menu de langue, sous la ligne méta.

        `QCursor.pos()` ne convient pas seul : la ligne méta est accessible au
        CLAVIER (`LinksAccessibleByKeyboard`), et un utilisateur qui active le
        lien à la touche Entrée verrait le menu s'ouvrir là où traîne la souris
        — potentiellement sur un autre écran. On ancre donc au widget, et on
        garde le curseur en repli si la géométrie n'est pas encore posée.
        """
        meta = self._info._meta
        if not meta.isVisible() or meta.width() <= 0:
            return None
        return meta.mapToGlobal(QPoint(0, meta.height()))

    def ancre_reglages(self):
        """Position GLOBALE où poser le menu des réglages, sous l'engrenage.

        Même raison que `ancre_langue` : le bouton s'active aussi à la touche
        Entrée, et un menu qui s'ouvre là où traîne la souris — voire sur un
        autre écran — n'a aucun rapport avec ce qu'on vient de faire.
        """
        btn = self._action_panel._btn_reglages
        if btn is None or not btn.isVisible() or btn.width() <= 0:
            return None
        return btn.mapToGlobal(QPoint(0, btn.height()))

    def _refresh(self) -> None:
        """Rafraîchit le panneau d'actions, puis REPOSITIONNE le panneau d'infos.

        Changer d'état reconstruit entièrement la zone d'action : passer en
        téléchargement y ajoute une barre de progression, un stepper et une
        ligne de vitesse, soit ~50 px de plus. Sans le repositionnement, la
        hauteur du panneau reste celle calculée pour l'ancien panneau d'actions
        et la fiche se met à défiler pendant TOUTE la durée du téléchargement
        (22 à 24 px de débordement, mesurés sur les 8 jeux à toutes les
        tailles) — puis la barre disparaît toute seule à la fin, ce qui rend le
        défaut irreproductible sur demande.

        Même discipline que `set_online()` et `recheck_prerequisites()` : dès
        que la zone d'action change de hauteur, la géométrie est à revoir.
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

        Trois bénéfices : la lecture du titre se fait sur une image fixe, le
        temps de chargement de la vidéo devient invisible, et parcourir le
        carrousel ne déclenche plus un lecteur par vignette survolée.
        """
        self._pending_video_id = game_id
        if not self.manager.config.autoplay_videos:
            self._video_timer.stop()
            return
        # Réarmement : `start()` sur un minuteur qui tourne déjà REPART de zéro.
        # C'est tout l'intérêt d'en posséder un — le délai appartient au jeu
        # affiché, pas au premier de la série.
        self._video_timer.start()

    def _on_video_timer(self) -> None:
        # Le jeu a pu changer pendant le délai : on ne lance que le bon.
        if self.game is None or self.game.id != self._pending_video_id:
            return
        # …et la fenêtre a pu disparaître. Second garde-fou, indépendant de
        # l'annulation faite par `_stop_video` : un `singleShot` déjà en vol au
        # moment où la fenêtre part dans le tray ne doit jamais aboutir à du son
        # sans image. `isVisible()` est faux pour toute la descendance dès que
        # `MainWindow.hide()` est appelé.
        if not self.isVisible():
            return
        self._try_play_video(self.game.id)

    def _try_play_video(self, game_id: str) -> None:
        # Les bandes-annonces ne sont plus embarquées : elles vivent dans
        # ~/Games/AccioLauncher/trailers, à la version que le catalogue attend.
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
        # Sortir du plein écran AVANT tout le reste : sans ça, une vidéo qui se
        # termine (ou un changement de jeu, ou un clic sur JOUER) laisserait une
        # fenêtre vide — une illustration fixe, sans titre, sans boutons et sans
        # carrousel — dont rien n'indiquerait comment sortir.
        self.set_cinema(False)
        # ANNULER d'abord le démarrage en attente : couper la vidéo ne
        # l'empêchait pas de repartir juste après. Cas réel (Ludo, 2026-08-23) :
        # un téléchargement en cours, on va lancer un AUTRE jeu — donc on change
        # de fiche puis on clique JOUER dans la foulée, en moins de deux
        # secondes. La fenêtre part dans le tray, le minuteur arrive derrière,
        # et la bande-annonce se met à jouer sans image. Sans téléchargement on
        # s'attarde sur la fiche, le minuteur a déjà tiré, et le défaut ne se
        # reproduit pas — d'où « ça marche pourtant d'habitude ».
        self._video_timer.stop()
        # Deuxième garde-fou, indépendant du minuteur : un `timeout` déjà posté
        # dans la file d'événements ne serait pas retiré par `stop()`.
        self._pending_video_id = ""
        self._video.stop()
        self._bg.clear_video()
        self._audio_bar.hide()

    def _on_video_ended(self) -> None:
        # EndOfMedia → relâcher la source pour libérer le décodeur…
        self._stop_video()
        # …mais laisser de quoi la revoir. Sans ce bouton, revoir une
        # bande-annonce obligeait à changer de jeu et à revenir : c'est la
        # seule commande qui ait encore un sens ici, donc la seule affichée.
        if self.game is not None and trailers.chemin_a_jouer(
                self.game.id, self.manager.trailers()) is not None:
            self._audio_bar.set_mode_fin(True)
            self._position_audio_bar()
            self._audio_bar.show()

    def _on_replay_clicked(self) -> None:
        """Rejoue la bande-annonce du jeu affiché, tout de suite.

        Pas de délai : il sert à laisser lire le titre à l'arrivée sur la
        fiche, or ici c'est un clic délibéré sur « revoir ».
        """
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

        La fenêtre reste souvent visible quand elle perd le focus — second
        écran, fenêtre côte à côte. Couper la bande-annonce dans ce cas se voit
        et fait mauvais effet. Les trailers durent moins de deux minutes et
        s'arrêtent d'eux-mêmes à la fin (`_on_video_ended` rend la main à
        l'image de fond) ; c'est suffisant. La vidéo n'est réellement coupée que
        lorsque la fenêtre n'est plus visible du tout — voir `pause()`, appelée
        par la mise en tray.
        """
        self._bg.pause()

    def resume_effects(self) -> None:
        self._bg.resume()

    def cancel_operations(self) -> None:
        self._ops.cancel_all()

    def set_online(self, online: bool) -> None:
        """Propage le diagnostic réseau jusqu'au panneau d'actions."""
        self._action_panel.set_online(online)
        self._position_info()   # le bandeau apparaît/disparaît → hauteur à revoir

    def recheck_prerequisites(self) -> None:
        """Re-teste les prérequis système (no-op si rien ne l'a demandé)."""
        self._action_panel.recheck_prerequisites()
        self._position_info()

    def refresh_video(self) -> None:
        """Retente la bande-annonce du jeu affiché — les fichiers viennent d'arriver.

        Sans ça, quelqu'un qui vient de télécharger les bandes-annonces
        garderait un fond fixe jusqu'à ce qu'il change de jeu, et croirait le
        téléchargement inutile. Ne coupe jamais une vidéo en cours.
        """
        if self.game is None or self._video.is_playing:
            return
        self._schedule_video(self.game.id)

    def refresh_actions(self) -> None:
        """Rafraîchit le panneau d'actions après un changement d'état externe
        (ex: re-détection des états suite à un changement d'install_path).

        Repositionne aussi : changer de dossier d'installation fait apparaître
        ou disparaître le bandeau d'espace disque, et la hauteur du panneau en
        dépend.
        """
        self._refresh()
        self._position_info()

    def apply_audio_config(self) -> None:
        """Applique « Couper le son des vidéos » à la vidéo EN COURS (réglage live).

        Sans ça, le toggle des Paramètres n'affectait que la prochaine vidéo —
        l'utilisateur avait l'impression qu'il ne fonctionnait pas.
        """
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
            QMessageBox.warning(self, title, message)
        QTimer.singleShot(0, _show)


    # ──────────────────── API publique (clavier MainWindow) ────────────────────

    def trigger_primary_action(self) -> None:
        """Action par défaut sur Enter (depuis MainWindow.keyPressEvent)."""
        handlers.trigger_primary_action(self)

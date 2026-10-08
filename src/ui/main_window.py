import logging

from PyQt6.QtCore import Qt, QEvent, QPointF, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from src.core import compat, manette
from src.core.config import Config
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.core.liens import DISCORD_URL, KOFI_URL
from src.ui import dialogues_fenetre, game_detail_handlers, verification_forcee
from src.ui.barre_de_statut import BarreDeStatut
from src.ui.carousel import Carousel
from src.ui.clavier_global import touche_globale
from src.ui.download_bar import DownloadBar
from src.ui.retrait_differe import RetraitDiffere
from src.ui.suivi_barre import SuiviBarre
from src.ui.fonts import load_fonts
from src.ui.game_detail import GameDetailView
from src.ui.game_session import GameSession
from src.ui.icon_button import IconButton
from src.ui.notification_bar import NotificationBar
from src.ui.particles import ParticleOverlay
from src.core.season import resolve as resolve_season
from src.ui.settings_panel import SettingsDialog
from src.ui.styles import MAIN_STYLE
from src.ui.theme import set_theme, themed
from src.ui.ticker import Ticker
from src.ui.title_bar import TitleBar
from src.ui.toast import Toast
from src.ui.trailer_store import TrailerStore
from src.ui.tray_manager import TrayManager
from src.ui.update_dispatcher import UpdateDispatcher
from src.ui.window_chrome import WindowChrome, geometrie_d_ouverture
from src.ui.utils import icone_application, open_url

log = logging.getLogger(__name__)

# Cap du remerciement Ko-fi unique. Nommé plutôt qu'écrit en clair : c'est un
# réglage de produit, pas une constante technique, et il a déjà bougé une fois.
_KOFI_CAP_SECONDES = 2 * 3600


class MainWindow(QMainWindow):
    """Fenêtre principale d'Accio Launcher — style launcher AAA."""

    def __init__(self) -> None:
        super().__init__()
        # Linux : se retirer quand le jeu prend la main (`retrait_differe`).
        # Posé AVANT tout : `changeEvent` peut partir pendant la construction.
        self._retrait = RetraitDiffere(self._retirer_si_en_jeu, self)
        self.setWindowTitle("Accio Launcher")
        self.setMinimumSize(980, 660)
        self._apply_default_geometry()
        self.setWindowIcon(icone_application())

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.setMouseTracking(True)
        # Bords saisissables d'une fenêtre sans cadre — curseur et
        # redimensionnement natif. Voir `src/ui/window_chrome.py`.
        self._chrome = WindowChrome(self)

        load_fonts()

        self.config = self._first_launch_or_load()
        # Langue et thème doivent être actifs AVANT la construction des widgets
        # (chaînes tr() et couleurs posées à la construction ; changement = redémarrage).
        from src.core.i18n import set_language
        set_language(self.config.langue)
        set_theme(self.config.theme)
        self.setStyleSheet(themed(MAIN_STYLE))
        self.manager = GameManager(self.config)

        # Tout ce qui concerne les vérifications de mise à jour vit dans le
        # dispatcher : threads, re-tentative hors ligne, téléchargement de l'exe.
        # La fenêtre n'en garde que ce qui s'affiche.
        self._updates = UpdateDispatcher(self.manager, self)
        self._launcher_update_asked = False          # dialogue posé une fois par session
        # Fermeture déjà tranchée : la question a été posée ailleurs, ou il n'y
        # a personne à qui la poser (relance déjà programmée). Voir closeEvent.
        self._fermeture_confirmee = False
        # État réseau — optimiste au départ : on n'affiche « hors ligne » que
        # sur une preuve, jamais par défaut (cf. UpdateChecker.is_online).
        self._online = True

        self._build_ui()
        self._build_tray()
        self._build_session()
        self._wire_updates()
        self._start_update_check()
        # Manette PlayStation branchée : couleur de la maison, dès l'ouverture.
        if self.config.couleur_manette:
            manette.colorer_en_fond(self.config.theme)

    @staticmethod
    def _first_launch_or_load() -> Config:
        if Config.exists():
            return Config.load()
        # Premier lancement : assistant 3 écrans (dossier, import en masse,
        # langue/thème — appliqués dès la suite de la construction).
        from src.ui.onboarding import run_onboarding
        return run_onboarding()

    # ──────────────────── Construction UI ────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralContainer")
        central.setMouseTracking(True)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._title_bar = TitleBar(self)
        root_layout.addWidget(self._title_bar)

        # Bandeau de mise à jour du launcher (caché par défaut)
        self._notif_bar = NotificationBar(self)
        self._notif_bar.download_clicked.connect(self._on_notif_download)
        self._notif_bar.dismissed.connect(self._dismiss_notif)
        root_layout.addWidget(self._notif_bar)

        games = [entry.game for entry in self.manager.get_games()]

        self._detail = GameDetailView(self.manager, self)
        self._detail.setMouseTracking(True)
        self._detail.status_message.connect(self._show_status)
        self._detail.state_changed.connect(self._on_state_changed)
        root_layout.addWidget(self._detail, stretch=1)

        # Barre de téléchargement persistante (visible pendant download/install)
        self._download_bar = DownloadBar(self)
        root_layout.addWidget(self._download_bar)
        self._suivi = SuiviBarre(self._download_bar, self._detail.ops, self._detail.wine,
                                 self.manager, lambda: int(self.winId()), self)

        self._carousel = Carousel(games, self.manager, self)
        self._carousel.game_selected.connect(self._on_carousel_select)
        root_layout.addWidget(self._carousel)

        self._status_bar = BarreDeStatut(self.config, self._detail.ops)
        self.setStatusBar(self._status_bar)

        # Overlay particules (+ saison décorative, changeable en direct dans Paramètres)
        self._particles = ParticleOverlay(self)
        self._particles.apply_season(resolve_season(self.config.season))
        self._particles.raise_()

        # Toast (notifications éphémères)
        self._toast = Toast(self)
        self._detail.ops.operation_finished.connect(self._notify_operation_finished)

        # Bandes-annonces : hors de l'exécutable depuis la 1.0. Tout le
        # pilotage vit dans le magasin ; ici, que ce qui SE VOIT.
        self._trailers = TrailerStore(self.manager, self._detail.ops, self)
        self._trailers.status_message.connect(self._toast.show_message)
        self._trailers.job_finished.connect(self._detail.refresh_video)
        self._trailers.progress.connect(self._status_bar.bandes_annonces)
        self._trailers.job_finished.connect(self._status_bar.bandes_annonces_finies)
        self._trailers.armer_rattrapage(self.config)
        # Ce qui informait par dialogue modal passe par le toast : rien à
        # décider, donc rien qui justifie d'arrêter l'utilisateur.
        self._detail.notify.connect(self._toast.show_message)
        self._detail.settings_requested.connect(self._on_settings)
        self._detail.cinema_toggled.connect(self._on_cinema)

        # Pictogrammes DESSINÉS (règle 60 : U+2699 sortait en couleur).
        self._btn_settings = self._commande("reglages", tr("Paramètres"), self._on_settings)
        self._btn_stats = self._commande("stats", tr("Statistiques"), self._on_stats)
        # Discord visible : enfoui dans À propos, personne ne le trouvait.
        self._btn_discord = self._commande(
            "discord", tr("Discord : aide et communauté"), lambda: open_url(DISCORD_URL))
        # De droite à gauche, dans l'ordre où `_position_settings` les pose.
        self._commandes = (self._btn_settings, self._btn_stats, self._btn_discord)

        # Event filter on QApplication for global mouse tracking
        QApplication.instance().installEventFilter(self)

        if games:
            # Hero dynamique : ouvrir sur le dernier jeu joué plutôt que toujours HP1.
            last_id = self.manager.last_played_game_id()
            idx = next((i for i, g in enumerate(games) if g.id == last_id), 0)
            if idx > 0:
                self._carousel.select(idx)  # émet game_selected → set_game
            else:
                self._detail.set_game(games[0])

        # Notification VISIBLE des mises à jour de jeux (recompte local, différé
        # après le fade-in). La status bar seule passait inaperçue — retour Ludo.
        QTimer.singleShot(2500, self._notify_game_updates)

    # ──────────────────── System Tray ────────────────────

    def _build_tray(self) -> None:
        self._tray = TrayManager(icone_application(), self)
        self._tray.restore_requested.connect(self._restore_from_tray)
        self._tray.quit_requested.connect(self._quit_app)

    def _notify_operation_finished(self, game) -> None:
        """Fin d'installation : toast, et notification système si on n'est pas devant."""
        self._toast.show_message(tr("{} installé avec succès ✓").format(game.name))
        if self.isHidden():
            # Minimisé dans le tray (souvent : en jeu) → vraie notification Windows
            self._tray.show_notification(
                tr("Téléchargement terminé"), tr("{} est prêt à jouer !").format(game.name)
            )
        elif not self.isActiveWindow():
            QApplication.alert(self)  # fait clignoter l'icône taskbar

    def _build_session(self) -> None:
        """Le cycle de vie d'une partie vit dans `GameSession` ; la fenêtre ne
        garde que ce qui se VOIT — se retirer, revenir, remercier."""
        self._session = GameSession(self.manager, self)
        # Le lancement part de la fiche et arrive DIRECTEMENT à la session :
        # la fenêtre n'a que faire du Popen, elle n'en voit que le nom.
        self._detail.game_launched.connect(self._session.demarrer)
        self._session.demarree.connect(self._on_game_launched)
        # Un second clic sur JOUER pendant que Wine démarre le jeu le lancerait
        # deux fois : la fiche demande à la session ce qui tourne.
        self._detail.partie_en_cours = lambda: self._session.nom_en_cours
        self._session.terminee.connect(self._on_game_exited)
        self._session.configuration_cassee.connect(self._on_configuration_cassee)
        self._session.arret_fatal.connect(self._on_arret_fatal)
        self._session.diagnostic.connect(self._on_diagnostic)

    # ──────────────────── Update checker ────────────────────

    def _apply_default_geometry(self) -> None:
        """Taille d'ouverture : voir `window_chrome.geometrie_d_ouverture`."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:  # sans écran (tests offscreen) : valeur historique
            self.resize(1200, 800)
            return
        self.setGeometry(geometrie_d_ouverture(screen.availableGeometry()))

    def _wire_updates(self) -> None:
        """Branche le dispatcher sur ce qui s'affiche.

        Tout ce que la fenêtre fait des mises à jour tient ici : le reste —
        threads, re-tentative, téléchargement — est dans `UpdateDispatcher`.
        """
        self._updates.catalog_updated.connect(self._on_catalog_updated)
        self._updates.launcher_update.connect(self._on_launcher_update)
        self._updates.update_counts.connect(self._on_update_counts)
        self._updates.download_counts.connect(self._rafraichir_fiche)
        self._updates.asset_sizes.connect(self._rafraichir_fiche)
        self._updates.network_status.connect(self._on_network_status)
        self._updates.launcher_message.connect(self._notif_bar.set_message)
        self._updates.launcher_busy.connect(self._notif_bar.set_busy)
        # L'exe est remplacé et le .bat attend notre mort : la question a déjà
        # été posée (jamais pendant une opération en cours).
        self._updates.launcher_ready.connect(self._fermer_sans_demander)

    def _start_update_check(self) -> None:
        """Lance la vérification de fond. Neutralisée par les tests, d'où le
        maintien de cette méthode : c'est le point d'entrée qu'ils remplacent."""
        self._updates.start()

    def _on_network_status(self, online: bool) -> None:
        """Aucun serveur joignable → le dire, et re-tester tout seul (règle
        110), le minuteur ré-armé à CHAQUE échec."""
        self._updates.schedule_retry(online)
        compat.signaler_reseau(online)
        if online == self._online:
            return
        self._online = online
        self._detail.set_online(online)
        log.info("État réseau : %s", "en ligne" if online else "hors ligne")
        # Recompte local plutôt que `_notify_game_updates` : on veut remettre le
        # bon message ambiant, pas re-jouer un toast déjà vu.
        pending = sum(1 for entry in self.manager.get_games()
                      if self.manager.has_update(entry.game.id))
        self._on_update_counts(pending)

    def _rafraichir_fiche(self, *_args) -> None:
        """Compteurs de téléchargements ou tailles réelles reçus : la fiche
        affichée se refait (même id = pas de transition), sinon le bouton
        garderait la taille INSTALLÉE du catalogue."""
        if self._detail.game is not None:
            self._detail.set_game(self._detail.game)

    def _on_catalog_updated(self, catalog) -> None:
        """Le catalogue distant est plus récent — recharger."""
        self.manager.reload_catalog(catalog)
        self._trailers.rattraper_apres_catalogue(self.config)
        games = [entry.game for entry in self.manager.get_games()]
        # Garder le jeu affiché s'il existe encore, décidé AVANT de
        # reconstruire la bande et passé à elle (règle 101).
        current_id = self._detail.game.id if self._detail.game else None
        updated = self.manager.get_game_by_id(current_id) if current_id else None
        if updated is None and games:
            updated = games[0]
        self._carousel.set_games(games, selected_id=updated.id if updated else None)
        if updated is not None:
            self._detail.set_game(updated)
        # Le toast « mise à jour de jeu dispo » (actionnable) prime sur le toast
        # « catalogue mis à jour » (informatif) — un seul Toast à la fois.
        if not self._notify_game_updates():
            self._toast.show_message(tr("Catalogue mis à jour (v{})").format(catalog.catalog_version))
        log.info("UI rafraîchie après mise à jour du catalogue")

    def _on_launcher_update(self, version: str, url: str, asset_url: str = "",
                            asset_sha256: str = "", notes: str = "") -> None:
        """Nouvelle version du launcher disponible."""
        if self.config.dismissed_launcher_version == version:
            return
        self._updates.remember(version, url, asset_url, asset_sha256, notes)
        self._notif_bar.announce(version, auto=self._updates.can_install_itself)
        self._position_settings()
        self._propose_launcher_update()

    def _propose_launcher_update(self) -> None:
        """Demande franchement s'il faut mettre à jour, une fois par session.

        Une vraie QUESTION, donc un dialogue (un bandeau se survole sans se
        lire). « Plus tard » laisse le bandeau ; sa croix écarte la version.
        """
        if self._launcher_update_asked or self._detail.ops.is_busy:
            return
        self._launcher_update_asked = True
        if dialogues_fenetre.proposer_mise_a_jour(
                self, self._updates.version, self._updates.notes,
                self._updates.can_install_itself):
            self._on_notif_download()

    def _on_update_counts(self, count: int) -> None:
        self._status_bar.ambiance(count, self._online)

    def _notify_game_updates(self) -> bool:
        """Toast cliquable si des jeux installés ont une mise à jour. Recompte LOCAL :
        contrairement au signal `update_counts` du checker (qui ne compte que si le
        catalogue DISTANT est plus récent), ceci couvre aussi un catalogue embarqué
        déjà à jour livré par une mise à jour du launcher. Retourne True si toast."""
        games = [entry.game for entry in self.manager.get_games()]
        pending = [(i, g) for i, g in enumerate(games) if self.manager.has_update(g.id)]
        self._on_update_counts(len(pending))
        if not pending:
            return False
        first_idx = pending[0][0]
        if len(pending) == 1:
            msg = tr("Mise à jour disponible pour {}").format(pending[0][1].name)
        else:
            msg = tr("{} jeux ont une mise à jour disponible").format(len(pending))
        # Clic → sélectionner le premier jeu concerné (son lien « Mettre à jour »
        # et le marqueur carrousel deviennent visibles immédiatement).
        self._toast.show_message(msg, duration_ms=6000,
                                 on_click=lambda: self._carousel.select(first_idx))
        return True

    def _on_notif_download(self) -> None:
        """Clic sur le bandeau — le dispatcher décide entre auto-update et
        ouverture de la page de release."""
        self._updates.download()

    def _dismiss_notif(self) -> None:
        """Écarte la version pour de bon — sans ça le bandeau reviendrait à
        chaque vérification. Appelable directement, d'où le `hide()` : le
        bandeau s'est déjà caché quand c'est sa croix qui a déclenché."""
        self._notif_bar.hide()
        self._position_settings()
        if self._updates.version:
            self.config.dismissed_launcher_version = self._updates.version
            self.config.save()

    def _minimize_to_tray(self) -> None:
        """Cache la fenêtre dans le system tray et pause tous les effets.

        Sans zone de notification (GNOME sans AppIndicator), cachée elle serait
        INTROUVABLE : elle est alors réduite.
        """
        if not self._tray.disponible():
            self.showMinimized()
            self.pause_all_effects()
            log.info("Pas de zone de notification : launcher réduit — en jeu : %s",
                     self._session.nom_en_cours)
            return
        self.hide()
        self._tray.show()
        self.pause_all_effects()
        log.info("Launcher minimisé dans le tray — en jeu : %s", self._session.nom_en_cours)

    def _restore_from_tray(self) -> None:
        """Restaure la fenêtre et reprend les effets."""
        self.showNormal()
        self.activateWindow()
        self._tray.hide()
        self.resume_all_effects()
        log.info("Launcher restauré depuis le tray")

    def _quit_app(self) -> None:
        """« Quitter » du menu du tray.

        Par `close()`, dont le retour dit si `closeEvent` a accepté : la règle
        reste visible là où elle s'applique.
        """
        if not self.close():
            return
        self._tray.hide()
        QApplication.quit()

    def bring_to_front(self) -> None:
        """Remet la fenêtre au premier plan (second lancement → instance unique)."""
        if self.isHidden():
            self._restore_from_tray()
            return
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # ──────────────────── Pause / Resume effets ────────────────────

    def pause_all_effects(self) -> None:
        """Met en pause TOUS les timers et animations pour consommation CPU ~0."""
        Ticker.instance().pause()
        self._particles.pause()
        self._detail.pause()
        self._carousel.pause()
        log.debug("Tous les effets sont en pause")

    def resume_all_effects(self) -> None:
        """Reprend tous les timers et animations."""
        Ticker.instance().resume()
        self._particles.resume()
        self._detail.resume()
        self._carousel.resume()
        log.debug("Tous les effets sont repris")

    def changeEvent(self, event) -> None:
        """Fenêtre désactivée (derrière une autre) → pause des effets décoratifs.

        La vidéo continue (l'utilisateur peut regarder un trailer en arrière-plan) ;
        seuls particules, étoiles, glow et zoom s'arrêtent — CPU/GPU quasi nul.
        """
        if event.type() == QEvent.Type.WindowStateChange:
            self._detail.set_reduite(self.isMinimized())
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                Ticker.instance().resume()
                self._detail.resume_effects()
                # Retour d'une installation de prérequis lancée depuis le
                # bandeau d'avertissement (no-op le reste du temps).
                self._detail.recheck_prerequisites()
            elif self._retrait.attend:
                # Le jeu vient de prendre la main : c'est maintenant qu'on se retire.
                self._retrait.desactivee()
            elif self.isVisible():  # pas via le tray (géré par pause_all_effects)
                Ticker.instance().pause()
                self._detail.pause_effects()
        super().changeEvent(event)

    # ──────────────────── Surveillance du processus de jeu ────────────────────

    def _on_game_launched(self, game_name: str) -> None:
        """Une partie commence : infobulle, puis la fenêtre s'efface — sous Linux
        seulement quand le jeu prend la main (`retrait_differe`)."""
        self._tray.set_tooltip(tr("Accio Launcher — En jeu : {}").format(game_name))
        if self._retrait.differer(game_name, self.isActiveWindow()):
            self._status_bar.showMessage(tr(
                "Démarrage de {}… Wine peut mettre jusqu'à une minute à ouvrir le jeu."
            ).format(game_name))
        else:
            self._minimize_to_tray()

    def _retirer_si_en_jeu(self) -> None:
        if self.isVisible() and self._session.nom_en_cours:
            self._minimize_to_tray()

    def _on_game_exited(self, game_name: str, partie: bool = True, arret: bool = False) -> None:
        """Retour de jeu : la fenêtre revient et rafraîchit ce qui a changé.

        `partie` vient d'`add_playtime`, seul arbitre du seuil. Faux : le jeu
        n'a pas démarré, donc pas de « partie terminée » (règle 108). `arret` : le
        jeu a écrit un arrêt fatal, la boîte qui suit dit tout — ni « partie terminée »
        ni toast par-dessus.
        """
        self._tray.set_tooltip("Accio Launcher")
        self._retrait.oublier()
        self._restore_from_tray()
        if arret:
            self._status_bar.showMessage(tr("Retour de {}").format(game_name))
        elif partie:
            self._status_bar.showMessage(
                tr("Retour de {} — partie terminée.").format(game_name))
        else:
            # Toast : l'œil est sur la fiche. On ignore pourquoi, mais on sait
            # qui peut aider. Deux lignes pour tenir à 980 px.
            self._status_bar.showMessage(tr("Retour de {}").format(game_name))
            self._toast.show_message(
                tr("{} s'est fermé aussitôt — le jeu n'a pas démarré.").format(game_name)
                + "\n" + tr("Besoin d'aide ? Cliquez : rapport copié, Discord ouvert."),
                duration_ms=12000, on_click=self._aide_apres_echec)
        # Rafraîchir la ligne stats du jeu affiché (set_game même id = refresh
        # sans transition) : le temps de cette partie vient d'être enregistré.
        if self._detail.game is not None:
            self._detail.set_game(self._detail.game)
        # Un remerciement juste avant une boîte d'erreur serait déplacé : il
        # attendra le prochain retour sans accroc.
        if not arret:
            self._maybe_thank_milestone()

    def _aide_apres_echec(self) -> None:
        """Clic sur le toast « n'a pas démarré » : le rapport part avec le joueur
        (Ctrl+V sur Discord le joint) au lieu d'une photo prise au téléphone."""
        game_detail_handlers.copier_le_rapport(self._detail)
        open_url(DISCORD_URL)

    def _on_configuration_cassee(self, game_id: str, ligne: str) -> None:
        """Le jeu s'est arrêté sur une erreur d'affichage : proposer la remise."""
        game = self.manager.get_game_by_id(game_id)
        if game is not None:
            game_detail_handlers.proposer_apres_plantage(self._detail, game, ligne)

    def _on_arret_fatal(self, game_id: str, arret: object) -> None:
        """Le jeu a écrit un arrêt fatal : le dire, avec le rapport à copier."""
        game = self.manager.get_game_by_id(game_id)
        if game is not None:
            game_detail_handlers.signaler_arret(self._detail, game, arret)

    def _on_diagnostic(self, game_id: str, constat: object) -> None:
        """Windows a noté pourquoi le jeu s'est arrêté : le dire."""
        game = self.manager.get_game_by_id(game_id)
        # Un autre jeu lancé entre-temps : la boîte arriverait en pleine partie.
        if game is not None and not self._session.nom_en_cours:
            game_detail_handlers.signaler_plantage(self._detail, game, constat)

    def _maybe_thank_milestone(self) -> None:
        """Un seul remerciement Ko-fi dans la vie du launcher, au cap de 2 h de jeu.

        Au retour de jeu, jamais répété, jamais culpabilisant (« pas de nag »).
        La règle « une seule fois » ne bouge pas.
        """
        if self.config.kofi_milestone_thanked:
            return
        if sum(self.config.playtime_seconds.values()) < _KOFI_CAP_SECONDES:
            return
        self.config.kofi_milestone_thanked = True
        self.config.save()
        self._toast.show_message(
            tr("Déjà 2 h de magie retrouvée. Si le launcher vous plaît, un café fait plaisir — cliquez ici."),
            duration_ms=9000,
            on_click=lambda: open_url(KOFI_URL),
        )

    # ──────────────────── Slots UI ────────────────────

    def _show_status(self, msg: str) -> None:
        self._status_bar.showMessage(msg)

    def _on_carousel_select(self, index: int) -> None:
        games = [entry.game for entry in self.manager.get_games()]
        if 0 <= index < len(games):
            self._detail.set_game(games[index])

    def _on_state_changed(self) -> None:
        self._carousel.refresh_indicators()

    def _on_config_changed(self) -> None:
        """Config modifiée (ex: dossier d'installation) — re-détecter les états.

        Sans re-détection, un jeu installé dans l'ancien dossier resterait
        affiché INSTALLED et « JOUER » échouerait silencieusement.
        """
        self.manager.refresh_states()
        self._detail.refresh_actions()
        self._detail.apply_audio_config()  # mute/unmute la vidéo en cours (live)
        self._carousel.refresh_indicators()

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.manager, self, store=self._trailers)
        dlg.config_changed.connect(self._on_config_changed)
        dlg.force_catalog_refresh.connect(lambda: self._force_update_check(dlg, catalog_only=True))
        dlg.force_launcher_check.connect(lambda: self._force_update_check(dlg, catalog_only=False))
        dlg.season_changed.connect(self._particles.apply_season)
        dlg.restart_requested.connect(lambda: self._restart_launcher(dlg))
        dlg.exec()

    def _on_stats(self) -> None:
        """Page de statistiques — lecture seule, aucun réglage, donc rien à recâbler."""
        from src.ui.stats_dialog import StatsDialog
        StatsDialog(self.manager, self).exec()

    def _restart_launcher(self, dlg: SettingsDialog | None = None) -> None:
        """« Redémarrer maintenant » (thème/langue) : relance programmée puis fermeture propre.

        La question se pose AVANT `relaunch_after_exit()`, jamais après : le
        script attend la mort du processus, donc un refus arrivé une fois
        qu'il tourne le laisserait attendre pour rien.
        """
        from src.core.self_update import relaunch_after_exit
        if not self._confirmer_fermeture():
            return
        if relaunch_after_exit():
            if dlg is not None:
                dlg.accept()
            self._fermer_sans_demander()
        else:
            self._show_status(tr("Relance automatique impossible — redémarrez manuellement."))

    def _force_update_check(self, dlg: SettingsDialog, *, catalog_only: bool) -> None:
        """« Vérifier les mises à jour » des Paramètres : voir `verification_forcee`.
        Compteurs, empreintes et état réseau sont déjà branchés par `forced_checker`."""
        def sur_launcher(*args) -> None:
            self.config.dismissed_launcher_version = ""  # check forcé → toujours montrer
            self._on_launcher_update(*args)
        verification_forcee.verifier(
            self._updates.forced_checker(), dlg, catalog_only=catalog_only,
            sur_catalogue=self._on_catalog_updated, sur_launcher=sur_launcher,
            en_ligne=lambda: self._online, url_launcher=lambda: self._updates.url)

    # ──────────────────── Événements ────────────────────

    def _commande(self, icone: str, libelle: str, slot) -> IconButton:
        """Bouton de fenêtre : posé en absolu par-dessus la fiche, pas dans un layout."""
        bouton = IconButton(icone, taille=36, parent=self, galet=True)
        bouton.setToolTip(libelle)
        bouton.setAccessibleName(libelle)
        bouton.clicked.connect(slot)
        bouton.raise_()
        return bouton

    def _position_settings(self) -> None:
        """Pose les commandes SOUS le bandeau de notification quand il est là.

        Règle 29 : posées en absolu, elles masquaient la croix du bandeau.
        """
        decalage = self._notif_bar.height() if self._notif_bar.isVisible() else 0
        for i, bouton in enumerate(self._commandes):
            bouton.move(self.width() - 52 - i * 44, 42 + decalage)
            bouton.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_settings()
        self._particles.setGeometry(self.centralWidget().geometry())
        self._particles.raise_()
        self._toast.reposition()
        # Fenêtre basse : le carrousel se compacte pour rendre sa hauteur à la
        # fiche de jeu, qui devait sinon défiler.
        self._carousel.set_compact(self.height() < 780)

    # ──────────────────── Redimensionnement fenêtre frameless ────────────────────

    def eventFilter(self, obj, event) -> bool:
        # Filtre posé sur QApplication : il voit les MouseMove de TOUS les widgets
        # enfants (un mouseMoveEvent ne tirerait que sur la surface nue).
        try:
            if event.type() == QEvent.Type.MouseMove:
                local = self.mapFromGlobal(event.globalPosition().toPoint())
                self._detail.handle_mouse_move(QPointF(local.x(), local.y()))
            if self._chrome.evenement(obj, event):
                return True
        except (AttributeError, RuntimeError) as exc:
            log.debug("eventFilter : %s", exc)
        if event.type() == QEvent.Type.KeyPress and self._handle_global_key(event):
            return True
        return super().eventFilter(obj, event)

    def _on_cinema(self, actif: bool) -> None:
        """Escamote ce qui n'appartient pas à la fiche pendant le plein écran.

        Ces widgets sont enfants de la FENÊTRE. La barre de téléchargement se
        DÉDUIT de `current_game` (un téléchargement peut finir pendant la vidéo).
        """
        self._carousel.setVisible(not actif)
        self._status_bar.setVisible(not actif)
        for bouton in self._commandes:
            bouton.setVisible(not actif)
        self._particles.setVisible(not actif)
        self._download_bar.setVisible(
            not actif and self._download_bar.current_game is not None)

    def _handle_global_key(self, event) -> bool:
        """←/→ et Échap avant les widgets : voir `clavier_global.touche_globale`."""
        return touche_globale(event, self._carousel, self._detail, self.isActiveWindow())

    def _confirmer_fermeture(self) -> bool:
        """Demande confirmation si une opération est en cours. True = on ferme.

        Point de passage unique : croix, Alt+F4 et « Quitter » du tray (Qt 6.11
        envoie un `QCloseEvent` dont `ignore()` annule la sortie).
        """
        ops = self._detail.ops
        if self._fermeture_confirmee or not ops.is_busy:
            return True
        jeu = ops.active_game
        return dialogues_fenetre.confirmer_fermeture(
            self, jeu.name if jeu is not None else None, ops.phase)

    def _fermer_sans_demander(self) -> None:
        """Ferme sans question — un `.bat` attend DÉJÀ la mort du processus.

        La question a été posée AVANT d'écrire le script.
        """
        self._fermeture_confirmee = True
        self.close()

    def closeEvent(self, event) -> None:
        """Attend la fin des threads avant de fermer."""
        if not self._confirmer_fermeture():
            event.ignore()
            return
        QApplication.instance().removeEventFilter(self)

        # Une partie en cours garde sa barre : c'est le jeu qui la tient.
        eteindre_manette = self.config.couleur_manette and not self._session.nom_en_cours
        # Timer, checkers et téléchargement de mise à jour, dans le bon ordre.
        self._updates.shutdown()
        self._session.shutdown()
        self._trailers.shutdown()
        self._detail.cancel_operations()
        self._tray.hide()
        if eteindre_manette:
            manette.eteindre()  # c'est nous qui l'avions allumée
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # ←/→ : consommées avant par `_handle_global_key`.
        match event.key():
            case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                self._detail.trigger_primary_action()
            case _:
                super().keyPressEvent(event)

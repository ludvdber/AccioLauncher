"""Panneau d'actions dynamique — boutons et barres de progression selon l'état du jeu."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.core.i18n import tr
from src.core.system_checks import (
    VCREDIST_URL, check_vcredist_x86, invalidate_vcredist_cache, needed_space_mb,
)
from src.ui.clickable_label import ClickableLabel
from src.ui.fonts import cinzel, body_font
from src.ui.glow_button import GlowButton
from src.core.formatting import (
    append_part_info, estimate_duration, format_progress_line, format_size,
)
from src.ui.theme import themed
from src.ui.utils import clear_layout, open_url

# Ambre-orangé : volontairement hors palette de maison. Un avertissement passé
# par `themed()` deviendrait vert chez Serpentard et bleu chez Serdaigle, où il
# ne se distinguerait plus de la décoration.
_WARN = "#e8955a"
_LINK = '<a href="{}" style="color:{}; text-decoration: underline;">{}</a>'

# Largeur du bloc « bientôt disponible » : le bouton ET la note en dessous.
# Une seule constante parce que la hauteur de la note se calcule à cette
# largeur-là — deux valeurs qui divergent, et la note se fait rogner.
_COMING_SOON_W = 300


class ActionPanel(QWidget):
    """Panneau d'actions qui s'adapte à l'état du jeu (télécharger/installer/jouer)."""

    download_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()
    play_clicked = pyqtSignal()
    uninstall_clicked = pyqtSignal()
    update_clicked = pyqtSignal()
    settings_requested = pyqtSignal()   # « Changer de dossier » depuis l'alerte disque

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._game: GameData | None = None
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

        # État réseau et prérequis. Optimistes par défaut : tant que rien ne
        # prouve un problème, on n'en invente pas un.
        self._online = True
        self._awaiting_vcredist = False

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

        # Bandeau d'avertissement, AU-DESSUS des boutons : on le lit avant d'agir.
        self._alert = QLabel()
        self._alert.setObjectName("actionAlert")
        self._alert.setFont(body_font(12))
        self._alert.setWordWrap(True)
        self._alert.setTextFormat(Qt.TextFormat.RichText)
        self._alert.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self._alert.setStyleSheet(
            # Pas de fond plein : la bande s'étirait sur toute la largeur du
            # panneau et laissait un grand rectangle ambre vide à droite du
            # texte. Le filet vertical suffit à marquer l'avertissement.
            f"QLabel {{ color: {_WARN}; background: transparent;"
            f" border-left: 3px solid {_WARN};"
            " padding: 2px 0px 2px 11px; }"
        )
        self._alert.linkActivated.connect(self._on_alert_link)
        self._alert.hide()
        self._layout.addWidget(self._alert)

        # Ligne principale des boutons
        self._action_container = QWidget()
        self._action_container.setStyleSheet("background: transparent;")
        self._action_layout = QHBoxLayout(self._action_container)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(14)
        self._action_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self._action_container)

        # Ligne de mise à jour
        self._update_row = QWidget()
        self._update_row.setStyleSheet("background: transparent;")
        self._update_row.hide()
        self._update_row_layout = QHBoxLayout(self._update_row)
        self._update_row_layout.setContentsMargins(0, 0, 0, 0)
        self._update_row_layout.setSpacing(8)
        self._update_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self._update_row)

        # Widgets dynamiques
        self._progress_bar: QProgressBar | None = None
        self._download_label: QLabel | None = None
        self._install_bar: QProgressBar | None = None
        # Note « bientôt disponible » : sa hauteur se recalcule à chaque
        # redimensionnement, donc on garde la référence (cf. _fit_coming_soon_note).
        self._coming_soon_note: QLabel | None = None

    def set_game(self, game: GameData | None) -> None:
        self._game = game

    def set_online(self, online: bool) -> None:
        """Reçoit le diagnostic réseau de l'UpdateChecker."""
        if online == self._online:
            return
        self._online = online
        self.refresh()

    def recheck_prerequisites(self) -> None:
        """Re-teste les prérequis au retour dans la fenêtre — sans rien faire
        si l'utilisateur n'est jamais parti en installer un.

        Rafraîchir à chaque activation de fenêtre reconstruirait les boutons à
        chaque alt-tab (et volerait le focus au passage) ; on ne le fait donc
        qu'après un clic sur « Installer », le seul cas où le résultat a pu
        changer.
        """
        if not self._awaiting_vcredist:
            return
        self._awaiting_vcredist = False
        invalidate_vcredist_cache()
        self.refresh()

    # ── Avertissements (affichés UNIQUEMENT en cas de manque) ──

    def _build_alerts(self, state: GameState) -> None:
        """Bandeau d'avertissement — rien à l'écran quand tout va bien.

        Un état ne s'affiche que lorsqu'il DÉVIE de la normale : une ligne
        « espace disque : 412 Go » ou une pastille « prérequis OK » n'apprend
        rien à personne et encombre. En revanche, découvrir qu'il manque 8 Go
        APRÈS avoir lancé un téléchargement de 12 Go, ou que le jeu ne démarre
        pas faute d'un redistribuable, ça mérite d'être dit avant le clic.

        UN SEUL message à la fois, par ordre de blocage. Empiler « hors ligne »
        et « espace insuffisant » coûtait 80 px sur une fenêtre de 980×660 et
        ramenait la barre de défilement que le panneau vient tout juste de
        perdre — pour un second conseil qui n'est même pas encore actionnable :
        hors ligne, il n'y a rien à écrire sur le disque.
        """
        message = ""

        if state == GameState.NOT_INSTALLED:
            dl = self._game.current_download
            if dl is not None and dl.is_available:
                if not self._online:
                    message = tr("Hors ligne — connexion requise pour télécharger.")
                else:
                    message = self._disk_alert(dl.size_mb)
        elif state == GameState.INSTALLED and not check_vcredist_x86():
            message = (
                tr("Visual C++ x86 manquant — requis pour lancer ce jeu.") + " "
                + _LINK.format("vcredist", _WARN, tr("Installer"))
            )

        if not message:
            self._alert.hide()
            self._alert.clear()
            return
        # Aucun pictogramme. Cinzel n'a pas de glyphe pour U+26A0 (rendu en
        # carré vide au test) : Windows part alors en repli de police, et
        # c'est exactement ce repli qui avait donné le bouton pause bleu
        # vif. Le filet ambre et la couleur du texte disent « attention »
        # sans dépendre de la police installée.
        self._alert.setText(message)
        self._alert.show()
        self._fit_alert_height()

    def _disk_alert(self, size_mb: int) -> str:
        """Avertissement d'espace disque, vide si la place suffit ou est inconnue."""
        free_mb = self._manager.free_space_mb()
        needed = needed_space_mb(size_mb)
        if free_mb is None or free_mb >= needed:
            return ""
        return (
            tr("Espace insuffisant : {} libres, il en faut environ {}.").format(
                format_size(free_mb), format_size(needed))
            + " " + _LINK.format("settings", _WARN, tr("Changer de dossier"))
        )

    def alert_height(self) -> int:
        """Hauteur occupée par le bandeau, 0 quand il n'y a rien à signaler.

        Le panneau d'info s'en sert pour raccourcir la description d'autant :
        cette place-là est prise, et l'ignorer ferait revenir la barre de
        défilement.
        """
        if self._alert.isHidden() or not self._alert.text():
            return 0
        return self._alert.minimumHeight() + self._layout.spacing()

    def _on_alert_link(self, href: str) -> None:
        if href == "settings":
            self.settings_requested.emit()
        elif href == "vcredist":
            # L'utilisateur part installer le paquet : on note qu'il faudra
            # re-tester à son retour (cf. recheck_prerequisites).
            self._awaiting_vcredist = True
            open_url(VCREDIST_URL)

    def _fit_alert_height(self) -> None:
        """Réserve la hauteur RÉELLE du bandeau (wordWrap ⇒ plusieurs lignes).

        `sizeHint()` d'un QLabel wordWrap est calculé à une largeur arbitraire ;
        sans hauteur minimale explicite, le panneau d'info sous-estime la place
        nécessaire et rogne le bandeau. `setMinimumHeight(0)` d'abord, sinon
        `heightForWidth` renvoie `max(minimumHeight, calculé)` et la hauteur ne
        redescend jamais (effet cliquet).
        """
        avail = self.width() - 24
        if avail <= 0 or not self._alert.text():
            return
        self._alert.setMinimumHeight(0)
        self._alert.setMinimumHeight(self._alert.heightForWidth(avail))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._alert.isVisible():
            self._fit_alert_height()
        self._fit_coming_soon_note()

    def refresh(self) -> None:
        """Reconstruit le panneau selon l'état courant du jeu."""
        self._clear_layout(self._action_layout)
        self._clear_layout(self._update_row_layout)
        self._update_row.hide()
        self._progress_bar = None
        self._download_label = None
        self._install_bar = None
        self._coming_soon_note = None
        self._action_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        self._action_layout.setSpacing(14)

        if self._game is None:
            self._alert.hide()
            return

        state = self._manager.get_state(self._game.id)
        self._build_alerts(state)
        match state:
            case GameState.NOT_INSTALLED:
                self._build_not_installed()
            case GameState.DOWNLOADING:
                self._build_downloading()
            case GameState.INSTALLING:
                self._build_installing()
            case GameState.INSTALLED:
                self._build_installed()

    # ── Callbacks de progression ──

    def update_download_progress(self, downloaded: int, total: int,
                                   speed: float, eta_seconds: float) -> None:
        pct = downloaded * 100 // total if total > 0 else 0
        if self._progress_bar is not None:
            self._progress_bar.setValue(pct)
        if self._download_label is not None:
            self._download_label.setText(
                format_progress_line(downloaded, total, speed, eta_seconds, with_label=True)
            )

    def update_install_progress(self, pct: int) -> None:
        if self._install_bar is not None:
            self._install_bar.setValue(pct)

    def update_part_info(self, current: int, total: int) -> None:
        if self._download_label is not None:
            self._download_label.setText(
                append_part_info(self._download_label.text(), current, total)
            )

    # ── Construction des états ──

    def _build_not_installed(self) -> None:
        dl = self._game.current_download
        if dl is None or not dl.is_available:
            self._build_coming_soon()
            return
        size = format_size(dl.size_mb)
        # Durée estimée à partir de la dernière vitesse réellement observée —
        # vide au tout premier téléchargement, jamais devinée.
        eta = estimate_duration(dl.size_mb, self._manager.config.last_download_speed)
        libelle = f"{tr('TÉLÉCHARGER')}  —  {size}"
        if eta:
            libelle += f"  ·  ≈ {eta}"
        btn = GlowButton(libelle, style="outline")
        btn.setObjectName("btnDownload")
        btn.setAccessibleName(tr("Télécharger {}").format(self._game.name))
        btn.setFont(cinzel(13, bold=True))
        btn.setFixedSize(300, 46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.download_clicked)
        if not self._online:
            # Le bandeau au-dessus dit pourquoi. Laisser le bouton actif ne
            # ferait qu'échanger une explication contre une erreur réseau
            # générique quelques secondes plus tard.
            btn.setEnabled(False)
            btn.setToolTip(tr("Hors ligne — connexion requise pour télécharger."))
        self._action_layout.addWidget(btn)

    def _build_coming_soon(self) -> None:
        """Jeu au catalogue dont aucune archive n'est encore publiée.

        Un bouton désactivé plutôt qu'un bouton actif qui échoue : le message
        d'erreur générique accusait la connexion de l'utilisateur alors que le
        launcher fonctionne très bien — c'est le catalogue qui est en avance
        sur les archives.
        """
        # En colonne, et non côte à côte : à droite d'un bouton de 300 px fixes
        # il ne restait que ~266 px pour une phrase qui en réclame 428, et elle
        # était coupée en plein mot — à TOUTES les tailles de fenêtre.
        self._action_layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        self._action_layout.setSpacing(6)

        btn = QPushButton(tr("BIENTÔT DISPONIBLE"))
        btn.setObjectName("btnComingSoon")
        btn.setEnabled(False)
        btn.setFont(cinzel(13, bold=True))
        btn.setFixedSize(_COMING_SOON_W, 46)
        btn.setStyleSheet(themed(
            "QPushButton { background: rgba(255,255,255,0.04); color: #8a8aaa;"
            " border: 1px solid #2c3e6b; border-radius: 6px; }"
        ))
        self._action_layout.addWidget(btn)

        note = QLabel(tr("Les fichiers de ce jeu ne sont pas encore en ligne."))
        note.setObjectName("comingSoonNote")
        note.setFont(body_font(12))
        note.setWordWrap(True)   # ceinture ET bretelles : traductions plus longues
        note.setStyleSheet("color: #8a8aaa; background: transparent;")
        # La note prend la LARGEUR RÉELLE du panneau, pas les 300 px du bouton.
        # Contrainte à 300 px elle passait sur deux lignes, et le layout ne lui
        # accordait que la hauteur d'une seule (32 px pour 38 nécessaires) : le
        # bas de la seconde ligne était tranché — le jambage du « g » de
        # « ligne », pareil en espagnol. À la largeur du panneau la phrase tient
        # sur une ligne, ce qui supprime la troncature ET rend la zone d'action
        # plus courte qu'avant.
        self._coming_soon_note = note
        self._action_layout.addWidget(note)
        self._fit_coming_soon_note()

    def _fit_coming_soon_note(self) -> None:
        """Donne à la note la hauteur que son texte réclame à sa largeur réelle.

        Un QLabel en `wordWrap` posé dans un layout reçoit la hauteur de son
        `sizeHint`, calculée à une largeur qui n'est pas la sienne. Il faut donc
        la lui imposer — et remettre le minimum à zéro avant de mesurer, sinon
        la valeur ne fait que cliqueter vers le haut à chaque redimensionnement.
        """
        note = self._coming_soon_note
        if note is None:
            return
        # Le layout est en AlignLeft : sans largeur imposée, la note reste à la
        # largeur du bouton (300 px) et repasse sur deux lignes. On lui donne la
        # largeur réelle du conteneur, puis la hauteur qu'elle réclame À CETTE
        # largeur-là. Les deux vont ensemble : mesurer à une largeur qu'on
        # n'applique pas, c'est exactement ce qui produisait la troncature.
        largeur = max(_COMING_SOON_W, self._action_container.width())
        note.setFixedWidth(largeur)
        note.setMinimumHeight(0)
        note.setMinimumHeight(note.heightForWidth(largeur))

    def _build_downloading(self) -> None:
        self._action_layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(400)
        self._action_layout.addWidget(self._progress_bar)

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)
        self._download_label = QLabel(f"{tr('Téléchargement :')} 0%")
        self._download_label.setObjectName("downloadLabel")
        row_layout.addWidget(self._download_label, stretch=1)
        btn_cancel = QPushButton(tr("Annuler"))
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.cancel_clicked)
        row_layout.addWidget(btn_cancel)
        self._action_layout.addWidget(row)

    def _build_installing(self) -> None:
        self._action_layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        self._install_bar = QProgressBar()
        self._install_bar.setRange(0, 100)
        self._install_bar.setValue(0)
        self._install_bar.setFormat(tr("Installation\u2026 %p%"))
        self._install_bar.setFixedWidth(400)
        self._action_layout.addWidget(self._install_bar)

    def _build_installed(self) -> None:
        # « REPRENDRE » quand le jeu a déjà été lancé : le même clic, mais
        # l'écran reconnaît un joueur qui revient au lieu de le traiter en
        # nouveau venu à chaque ouverture.
        deja_joue = self._manager.get_playtime(self._game.id) > 0
        libelle = tr("REPRENDRE") if deja_joue else tr("JOUER")
        btn_play = GlowButton(libelle, glow_color="#2ecc71", style="filled",
                              bg_stops=("#2ecc71", "#27ae60", "#1a9c54"), text_color="#ffffff")
        btn_play.setObjectName("btnPlay")
        btn_play.setAccessibleName(tr("Jouer à {}").format(self._game.name))
        btn_play.setFont(cinzel(15, bold=True))
        btn_play.setFixedSize(200, 48)
        btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_play.clicked.connect(self.play_clicked)
        self._action_layout.addWidget(btn_play)

        btn_uninstall = GlowButton(tr("DÉSINSTALLER"), glow_color="#8a8aaa", style="outline", text_color="#8a8aaa")
        btn_uninstall.setObjectName("btnUninstall")
        btn_uninstall.setAccessibleName(tr("Désinstaller {}").format(self._game.name))
        btn_uninstall.setFont(cinzel(10, bold=True))
        btn_uninstall.setFixedSize(160, 36)
        btn_uninstall.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_uninstall.clicked.connect(self.uninstall_clicked)
        self._action_layout.addWidget(btn_uninstall)

        if self._manager.has_update(self._game.id):
            installed_ver = self._manager.installed_version(self._game.id) or "?"
            recommended = self._game.recommended_version
            lbl = QLabel(tr("Mise à jour disponible : v{} → v{}").format(installed_ver, recommended))
            lbl.setFont(body_font(12))
            lbl.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
            link = ClickableLabel(tr("Mettre à jour"))
            link.setFont(body_font(12))
            link.setStyleSheet(themed(
                "QLabel { color: #d6a72c; background: transparent; text-decoration: underline; }"
                "QLabel:hover { color: #e8c547; }"
            ))
            link.clicked.connect(self.update_clicked)
            self._update_row_layout.addWidget(lbl)
            self._update_row_layout.addWidget(link)
            self._update_row.show()

    @staticmethod
    def _clear_layout(layout) -> None:
        clear_layout(layout)

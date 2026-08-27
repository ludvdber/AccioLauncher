"""Panneau d'actions dynamique — boutons et barres de progression selon l'état du jeu."""

from html import escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.core.i18n import tr
from src.core.system_checks import (
    PREREQUIS, invalidate_vcredist_cache, needed_space_mb, prerequis_manquants,
)
from src.ui.clickable_label import ClickableLabel
from src.ui.fonts import cinzel, body_font
from src.ui.glow_button import GlowButton
from src.ui.icon_button import IconButton
from src.core.formatting import (
    append_part_info, format_progress_line, format_size,
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

# Bornes du bouton d'action principal. Il s'élargit avec son libellé (la durée
# estimée n'apparaît qu'après un premier téléchargement) mais reste imposant
# quand le libellé est court, et ne dépasse jamais la moitié d'un panneau
# d'info de 700 px.
_BOUTON_MIN_W = 300
_BOUTON_MAX_W = 460
_MARGE_BOUTON = 34   # respiration intérieure de part et d'autre du texte

# Plafond du bandeau, en lignes. Mesuré sur la plateforme native, vraies
# polices : les bandeaux qui tiennent à 980×660 font 33 px (une ligne) ou 54 px
# (deux) ; un troisième rang en coûte 75 et ramène la barre de défilement — le
# même prix que les deux avertissements empilés que le projet s'interdit déjà.
# Le texte de la mise en garde venant du CATALOGUE, donc de l'extérieur et sans
# repasser par une build, la mise en page ne peut pas dépendre de sa longueur :
# on élide, et « En savoir plus » porte la suite.
_ALERTE_MAX_LIGNES = 2
# En deçà de quoi une archive déjà en cache vaut la peine d'être annoncée
# comme reprise. Au-delà, elle est complète et attend son installation :
# « REPRENDRE — 0 o restants » serait un contresens.
_REPRISE_SEUIL = 0.99

# Noms COURTS des prérequis, pour le bandeau : il tient sur une ligne, le
# dialogue de lancement peut se permettre la formulation longue.
_NOMS_COURTS = {
    "vcredist_x86": tr("Visual C++ x86"),
    "vcredist2005_x86": tr("Visual C++ 2005 x86"),
    "vcredist2008_x86": tr("Visual C++ 2008 x86"),
}


class ActionPanel(QWidget):
    """Panneau d'actions qui s'adapte à l'état du jeu (télécharger/installer/jouer)."""

    download_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()
    play_clicked = pyqtSignal()
    uninstall_clicked = pyqtSignal()
    update_clicked = pyqtSignal()
    settings_requested = pyqtSignal()   # « Changer de dossier » depuis l'alerte disque
    # Engrenage « Réglages du jeu », à côté des boutons d'un jeu installé. La
    # langue vivait UNIQUEMENT dans la ligne méta, en doré et sans pictogramme :
    # elle s'y lit très bien, mais rien ne dit qu'on peut cliquer dessus. Un
    # réglage qu'il faut deviner n'existe pas. L'engrenage est aussi le point
    # d'entrée des réglages graphiques à venir — d'où un menu, et non un
    # second sélecteur de langue.
    game_settings_clicked = pyqtSignal()

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
        # Détruit et reconstruit à chaque `refresh` : jamais de `hasattr`,
        # tout membre existe dès `__init__`.
        self._btn_reglages = None

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
                    message = self._disk_alert(dl)
        elif state == GameState.INSTALLED:
            # Socle commun + ce que le catalogue déclare pour CE jeu. HP7 exige
            # Visual C++ 2005, un runtime distinct du 2015-2022 : annoncer le
            # mauvais aurait envoyé l'utilisateur installer un paquet qu'il a
            # peut-être déjà, sans que le jeu démarre pour autant.
            manquants = prerequis_manquants(("vcredist_x86", *self._game.requires))
            if manquants:
                message = (
                    tr("{} manquant — requis pour lancer ce jeu.").format(
                        _NOMS_COURTS.get(manquants[0], tr("Composant Windows")))
                    + " " + _LINK.format(manquants[0], _WARN, tr("Installer"))
                )

        # Dernier rang : la mise en garde que le CATALOGUE attache à ce jeu.
        # Elle cède le pas à tout ce qui précède, qui est bloquant ici et
        # maintenant, mais elle survit aux deux états qui comptent — avant le
        # téléchargement (prévenir) et une fois installé (expliquer un jeu qui
        # refuse de démarrer). Le texte vient du catalogue et non d'un `tr()` :
        # il se met à jour à distance, sans republier l'exécutable, et voyage
        # déjà traduit dans le bloc `i18n` du jeu.
        if not message and state in (GameState.NOT_INSTALLED, GameState.INSTALLED):
            message = self._alerte_catalogue()

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

    def _alerte_catalogue(self) -> str:
        """Mise en garde déclarée par le catalogue pour ce jeu (vide sinon).

        Cas réel : une DLL de HP7 partie 2 est mise en quarantaine par les
        antivirus. L'installation réussit, puis le jeu ne démarre pas — et rien
        à l'écran ne relie les deux. Le dire AVANT le téléchargement était la
        demande de Ludo ; le redire une fois installé est ce qui rend le message
        utile au moment où l'utilisateur en a besoin.
        """
        texte = self._game.warning.strip()
        if not texte:
            return ""
        lien = ""
        if self._game.warning_url:
            lien = " " + _LINK.format("avertissement", _WARN, tr("En savoir plus"))
        return self._elide_alerte(texte, lien)

    def _elide_alerte(self, brut: str, lien: str) -> str:
        """Ramène le bandeau à `_ALERTE_MAX_LIGNES` lignes (élision par la fin).

        Le texte est ÉCHAPPÉ en HTML avant d'entrer dans le bandeau. Celui-ci
        est un QLabel en `RichText` et le texte vient du CATALOGUE, c'est-à-dire
        de l'extérieur : sans échappement, un `<img src="http://…">` déclenchait
        une requête réseau à l'affichage de la fiche (donc « qui regarde quel
        jeu » part chez l'hébergeur de l'image), et n'importe quel balisage
        pouvait défaire la mise en page qu'on vient de border. On l'affiche
        comme du TEXTE, ce qu'il est.

        L'élision porte sur le texte BRUT et l'échappement vient après : couper
        une chaîne déjà échappée trancherait une entité en deux (`&amp;` → `&am`).

        `quote=False` : guillemets et apostrophes n'ont besoin d'être échappés
        que DANS un attribut. Ici c'est du contenu d'élément — les échapper
        remplissait le bandeau de `&#x27;` (rendus correctement par Qt, vérifié,
        mais illisibles en journal comme en test).

        La mesure passe par le VRAI QLabel et non par `QFontMetrics` : le
        bandeau est en `RichText`, donc mis en page par un QTextDocument, dont
        le retour à la ligne ne suit pas celui d'un `boundingRect` en texte
        brut. Mesuré à côté : le texte élidé « tenait » en deux lignes selon
        `QFontMetrics` et s'en affichait trois. On interroge donc exactement la
        fonction qui décide de la hauteur finale, à la largeur qu'utilise
        `_fit_alert_height` — les deux ne peuvent plus diverger.

        Le lien entre dans la mesure : il s'ajoute à la dernière ligne et c'est
        lui qui la fait déborder.
        """
        def rendu(n: int | None = None) -> str:
            morceau = brut if n is None else brut[:n].rstrip() + "…"
            return escape(morceau, quote=False) + lien

        largeur = self.width() - 24
        if largeur <= 40 or not brut:
            return rendu()
        avant = self._alert.text()
        plafond = _ALERTE_MAX_LIGNES * QFontMetrics(self._alert.font()).lineSpacing() + 8

        def hauteur(essai: str) -> int:
            self._alert.setMinimumHeight(0)   # sinon heightForWidth fait cliquet
            self._alert.setText(essai)
            return self._alert.heightForWidth(largeur)

        try:
            if hauteur(rendu()) <= plafond:
                return rendu()
            bas, haut = 0, len(brut)
            while bas < haut:
                milieu = (bas + haut + 1) // 2
                if hauteur(rendu(milieu)) <= plafond:
                    bas = milieu
                else:
                    haut = milieu - 1
            return rendu(bas if bas else 1)
        finally:
            self._alert.setMinimumHeight(0)
            self._alert.setText(avant)

    def _disk_alert(self, version) -> str:
        """Avertissement d'espace disque, vide si la place suffit ou est inconnue.

        Prend la VERSION et non un nombre de Mo : le besoin réel est la somme de
        l'archive et du jeu installé, et seule la version permet de retrouver le
        poids réel de l'archive. Ce chiffre doit rester identique à celui de
        `GameOperations.check_disk_space`, sinon le bandeau prévient d'un
        blocage qui n'arrive pas.
        """
        free_mb = self._manager.free_space_mb()
        needed = needed_space_mb(version.size_mb,
                                 self._manager.archive_size_mb(version))
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
        elif href == "avertissement":
            # L'URL a été validée au PARSING (https uniquement) : le catalogue
            # est distant, c'est la seule de ses chaînes qui atteigne le
            # navigateur, et elle ne doit pas pouvoir être autre chose.
            if self._game.warning_url:
                open_url(self._game.warning_url)
        elif href in PREREQUIS:
            # L'utilisateur part installer le paquet : on note qu'il faudra
            # re-tester à son retour (cf. recheck_prerequisites). Le lien porte
            # l'IDENTIFIANT du prérequis manquant, donc on ouvre la bonne page
            # même quand il y en a plusieurs possibles.
            self._awaiting_vcredist = True
            open_url(PREREQUIS[href][1])

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
        self._btn_reglages = None
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
        # Le poids, et RIEN d'autre. Le bouton portait aussi une durée estimée
        # (« ≈ 18 s ») : elle allongeait le libellé jusqu'à le faire déborder,
        # et elle promettait un temps calculé sur la vitesse du DERNIER
        # téléchargement — une valeur qui n'a aucune raison de valoir encore.
        # Écartée à la demande de Ludo le 2026-08-20.
        # Le poids RÉEL de l'archive quand GitHub l'a publié, et non le
        # `size_mb` du catalogue : celui-ci est la taille du jeu une fois
        # INSTALLÉ, soit de 1,77 à 2,30 fois le téléchargement (mesuré sur les
        # six jeux en ligne). Le bouton promettait « 4,4 Go » là où la barre de
        # progression comptait ensuite jusqu'à 2,1 Go — l'interface se
        # contredisait d'un écran à l'autre. Repli sur le catalogue tant que
        # l'API n'a pas répondu.
        poids = self._manager.archive_size_mb(dl) or dl.size_mb
        # Reprise : le téléchargeur la fait depuis toujours (`.part` + Range),
        # mais RIEN ne le disait. Le bouton l'annonce quand — et seulement
        # quand — il y a réellement quelque chose à reprendre : c'est la règle
        # du projet, un état ne s'affiche que lorsqu'il DÉVIE de la normale.
        deja_mo = self._manager.octets_deja_telecharges(self._game.id, dl) / 1_048_576
        if poids and 0 < deja_mo < poids * _REPRISE_SEUIL:
            libelle = (f"{tr('REPRENDRE')}  —  "
                       + tr("{} restants").format(format_size(round(poids - deja_mo))))
        else:
            libelle = f"{tr('TÉLÉCHARGER')}  —  {format_size(poids)}"
        btn = GlowButton(libelle, style="outline")
        btn.setObjectName("btnDownload")
        btn.setAccessibleName(tr("Télécharger {}").format(self._game.name))
        btn.setFont(cinzel(13, bold=True))
        # Largeur SUIVIE SUR LE CONTENU, et non figée à 300 px. Le libellé
        # gagne une durée estimée dès qu'un premier téléchargement a abouti, et
        # il réclamait alors jusqu'à 403 px : le texte débordait des deux côtés
        # du cadre, si bien qu'on lisait « CHARGER — 463 Mo · ≈ ~19s resta ».
        # Mesuré sur les 6 jeux téléchargeables × 3 langues : débordement
        # systématique, de +8 px (anglais) à +103 px (français).
        btn.setFixedSize(self._largeur_bouton(libelle, cinzel(13, bold=True)), 46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.download_clicked)
        if not self._online:
            # Le bandeau au-dessus dit pourquoi. Laisser le bouton actif ne
            # ferait qu'échanger une explication contre une erreur réseau
            # générique quelques secondes plus tard.
            btn.setEnabled(False)
            btn.setToolTip(tr("Hors ligne — connexion requise pour télécharger."))
        self._action_layout.addWidget(btn)

    def _largeur_bouton(self, libelle: str, police) -> int:
        """Largeur qu'il faut au bouton pour afficher `libelle` en entier.

        Bornée des deux côtés : jamais moins que la largeur historique (le
        bouton principal doit rester imposant même avec un libellé court),
        jamais plus que la place réellement disponible dans le panneau — sans
        quoi on remplacerait une troncature par un débordement.
        """
        besoin = QFontMetrics(police).horizontalAdvance(libelle) + _MARGE_BOUTON
        dispo = self._action_container.width() or self.width()
        plafond = max(_BOUTON_MIN_W, dispo) if dispo else _BOUTON_MAX_W
        return max(_BOUTON_MIN_W, min(besoin, plafond, _BOUTON_MAX_W))

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

        # Engrenage : uniquement s'il y a réellement quelque chose à régler.
        # `game_language` rend None quand le jeu ne déclare pas de bloc, et
        # hors Windows (pas de registre atteignable) — dans les deux cas un
        # engrenage ouvrirait un menu vide, ce qui est pire que pas d'engrenage.
        # Roue PEINTE, plus U+2699. Ce caractère était réputé sûr parce que sa
        # propriété Unicode est `Emoji_Presentation=No` — mais la propriété dit
        # ce que le caractère DEMANDE, pas ce que la chaîne de repli de Windows
        # lui DONNE. Mesuré le 2026-08-26 en le rendant en anti-crénelage
        # niveaux de gris : 49 % de pixels colorés, contre 0 % pour une lettre
        # et 22 % pour 🔊 pris comme témoin. Il partait donc en couleur, comme
        # le haut-parleur de la barre audio, et plus franchement encore.
        if self._manager.game_language(self._game) is not None:
            btn_reglages = IconButton("reglages", taille=36, cadre="#8a8aaa")
            btn_reglages.setObjectName("btnGameSettings")
            btn_reglages.setAccessibleName(
                tr("Réglages de {}").format(self._game.name))
            btn_reglages.setToolTip(tr("Réglages du jeu"))
            btn_reglages.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_reglages.clicked.connect(self.game_settings_clicked)
            self._action_layout.addWidget(btn_reglages)
            self._btn_reglages = btn_reglages

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

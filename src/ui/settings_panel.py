"""Paramètres, « la salle commune » : rubriques à gauche, cartes à droite.

Rubriques : Général (dossier, langue, sauvegardes) · Affichage (vidéos, thème,
ambiance) · Téléchargements (archives, mises à jour) · Intégrations (Discord,
manette) · À propos. Refonte du 2026-10-09 sur la maquette validée : la page
parle Gelasio comme la fiche, chaque réglage est une ligne (titre, phrase
d'aide, commande à droite) dans une carte, et « ← Bibliothèque » remplace le
bouton Fermer en or plein, qui pesait plus que tout le contenu.

Le thème et la langue demandent un redémarrage (bouton « Redémarrer
maintenant ») ; la saison des particules s'applique EN DIRECT (signal
`season_changed`).
"""

import logging
import shutil
from pathlib import Path


from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config import APP_VERSION, Config, cache_pour
from src.core.game_manager import GameManager, GameState
from src.core import manette
from src.core import trailers as trailer_store
from src.core.formatting import format_bytes, format_size
from src.core.i18n import available_languages, tr
from src.ui.composants import (
    ENCRE_DISCRETE, ENCRE_DOUCE, Carte, LigneReglage, bouton, feuille_de_style,
    police, surtitre, texte,
)
from src.ui.fonts import cinzel_decorative
from src.ui import about_page, manette_nav
from src.ui.disk_scan_worker import DiskScanWorker
from src.core.season import (
    SEASON_LABELS, SEASONS, resolve as resolve_season,
)
from src.ui.icon_button import pixmap_icone
from src.ui.theme import THEMES, accent_qcolor, current as current_theme, themed
from src.ui.toggle_switch import ToggleSwitch
from src.ui.utils import avertir, is_writable_dir, liste_deroulante, open_local_path, zone_defilable

log = logging.getLogger(__name__)

_LARGEUR_RUBRIQUES = 236
_ENCRE_RUBRIQUE = "#a9a7c4"
# (libellé, pictogramme) de chaque rubrique, dans l'ordre des pages.
_RUBRIQUES = (("Général", "dossier"), ("Affichage", "ecran"),
              ("Téléchargements", "telechargement"), ("Intégrations", "integrations"),
              ("À propos", "infos"))

# Style partagé des QComboBox du panneau (langue, thème, saison)
# Le focus clavier et la ligne choisie d'une liste ouverte, en OR : `outline`
# n'est pas peint sur une QComboBox (la règle globale de styles.py ne s'y
# voyait pas), et la ligne choisie, #2c3e6b sur #16213e, ne se distinguait
# pas des autres. Mesuré sur capture, Ludo à la manette le 2026-10-07 : « tout
# n'est pas mis en évidence, surtout les paramètres graphiques et dropdown ».
# Le cadre passe à 2 px et le remplissage perd 1 px : rien ne bouge.
_COMBO_STYLE = (
    "QComboBox { background: #16213e; color: #ffffff; border: 1px solid #2c3e6b;"
    " border-radius: 6px; padding: 6px 12px; font-size: 13px; }"
    "QComboBox[focusClavier=\"true\"]:focus { border: 2px solid #d6a72c; padding: 5px 11px; }"
    "QComboBox QAbstractItemView { background: #16213e; color: #ffffff; outline: none;"
    " selection-background-color: rgba(214, 167, 44, 0.30); selection-color: #f0d060; }"
    # La liste peint ses lignes elle-même : `selection-*` seul n'y changeait rien
    # (ligne choisie au clavier, mesurée sans aucune différence de couleur).
    "QComboBox QAbstractItemView::item { padding: 4px 8px; }"
    "QComboBox QAbstractItemView::item:selected { background: rgba(214, 167, 44, 0.30);"
    " color: #f0d060; }"
)


def _disque(path: Path) -> tuple[int, int]:
    """(octets libres, octets au total) du volume ; (0, 0) si illisible.

    Le dossier n'existe pas forcément encore (rien d'installé) : c'est son
    plus proche parent existant qui dit sur quel volume il tombera.
    """
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return 0, 0
    return usage.free, usage.total


def _texte_disque(path: Path) -> str:
    libre, total = _disque(path)
    if not total:
        return tr("Espace libre inconnu")
    return tr("{libre} libres sur {total}").format(
        libre=format_bytes(libre), total=format_bytes(total))


class _BarreDisque(QWidget):
    """Le volume en une barre : vos jeux en or, le reste du disque en gris."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(8)
        self._jeux = 0.0
        self._reste = 0.0

    def regler(self, jeux: int, libre: int, total: int) -> None:
        if total <= 0:
            self._jeux = self._reste = 0.0
        else:
            self._jeux = min(1.0, jeux / total)
            self._reste = max(0.0, min(1.0 - self._jeux, (total - libre - jeux) / total))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        p.setBrush(QColor(255, 255, 255, 18))
        p.drawRoundedRect(rect, 4, 4)
        p.setClipRect(rect)
        largeur = rect.width()
        # Un jeu installé reste VISIBLE même s'il pèse 1 % du disque.
        jeux = max(3.0, largeur * self._jeux) if self._jeux > 0 else 0.0
        p.setBrush(accent_qcolor(255))
        p.drawRoundedRect(QRectF(0, 0, jeux + 4, rect.height()), 4, 4)
        p.setBrush(QColor(255, 255, 255, 56))
        p.drawRect(QRectF(jeux, 0, largeur * self._reste, rect.height()))
        p.end()


class _Pastille(QWidget):
    """Le petit carré de couleur d'une légende."""

    def __init__(self, couleur: QColor) -> None:
        super().__init__()
        self._couleur = couleur
        self.setFixedSize(9, 9)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._couleur)
        p.drawRoundedRect(QRectF(self.rect()), 2, 2)
        p.end()


class _Chemin(QLabel):
    """Le chemin du dossier, coupé AU MILIEU s'il ne tient pas.

    Il se cassait juste après « C: » en retour à la ligne (maquette « avant »).
    Coupé au milieu, on garde le lecteur ET le nom du dossier ; le chemin
    complet reste dans l'infobulle.
    """

    def __init__(self, chemin: str) -> None:
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setFont(police(14))
        self.setStyleSheet("color: #f2f2f4; background: transparent;")
        self.setMinimumWidth(1)
        self.definir(chemin)

    def definir(self, chemin: str) -> None:
        self._chemin = chemin
        self.setToolTip(chemin)
        self._couper()

    def text(self) -> str:  # le chemin ENTIER, pas sa forme coupée
        return self._chemin

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._couper()

    def _couper(self) -> None:
        super().setText(self.fontMetrics().elidedText(
            self._chemin, Qt.TextElideMode.ElideMiddle, max(1, self.width())))

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._chemin),
                     super().sizeHint().height())


class SettingsDialog(QDialog):
    """Panneau de paramètres Accio Launcher."""

    config_changed = pyqtSignal()
    force_catalog_refresh = pyqtSignal()   # demande un fetch forcé du catalogue
    force_launcher_check = pyqtSignal()    # demande une vérif forcée du launcher
    season_changed = pyqtSignal(str)       # saison RÉSOLUE, appliquée en direct
    restart_requested = pyqtSignal()       # « Redémarrer maintenant » (thème/langue)

    def __init__(self, config: Config, manager: GameManager, parent=None,
                 store=None) -> None:
        super().__init__(parent)
        self.config = config
        self.manager = manager
        # Magasin de bandes-annonces (src.ui.trailer_store.TrailerStore).
        # Optionnel : les tests ouvrent le dialogue sans, et la ligne se cache.
        self._store = store
        self._lbl_trailers = None
        self._btn_trailers = None
        self.setWindowTitle(tr("Paramètres"))
        self.setMinimumSize(840, 560)
        self.resize(1000, 680)
        self.setStyleSheet(themed(self._style()) + feuille_de_style())
        self._build_ui()

    def _style(self) -> str:
        return """
        QDialog { background-color: #060611; }
        QFrame#rubriques {
            background: #060611;
            border: none;
            border-right: 1px solid rgba(214, 167, 44, 0.12);
        }
        QListWidget#navList {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#navList::item {
            color: #a9a7c4;
            min-height: 42px;
            padding: 0 12px;
            border-radius: 8px;
            border-left: 2px solid transparent;
        }
        QListWidget#navList::item:hover {
            color: #f2f2f4;
            background: rgba(255, 255, 255, 0.04);
        }
        QListWidget#navList::item:selected {
            color: #f2e6c4;
            background: rgba(214, 167, 44, 0.10);
            border-left: 2px solid #d6a72c;
        }
        QPushButton#retour {
            background: transparent; border: none; color: #a9a7c4;
            text-align: left; padding: 4px 2px;
        }
        QPushButton#retour:hover { color: #f2f2f4; }
        QPushButton#retour[focusClavier="true"]:focus { color: #e8c547; }
        """

    # ──────────────────── Construction ────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._colonne_rubriques())

        # Chaque page DÉFILE au besoin (règle 52) : changer de thème ou de langue
        # fait apparaître « Redémarrer maintenant » et une ligne d'aide, et la page
        # Affichage ne tenait plus — Qt écrasait les lignes sous leur hauteur,
        # textes rognés par le bas (capture de Ludo, 2026-09-27).
        self._pages = QStackedWidget()
        for page in (self._page_general(), self._page_display(),
                     self._page_downloads(), self._page_integrations(),
                     about_page.construire(self.manager.catalog.contributors,
                                           manager=self.manager)):
            self._pages.addWidget(zone_defilable(self._marges(page)))

        droite = QVBoxLayout()
        droite.setContentsMargins(0, 0, 0, 0)
        droite.setSpacing(0)
        droite.addWidget(self._pages, stretch=1)
        # « Enregistré », pas « appliqué » : la langue et le thème attendent un
        # redémarrage, et la page le dit à leur ligne (règle 108).
        pied = texte(tr("Chaque changement est enregistré tout de suite. Échap pour revenir."),
                     12, ENCRE_DISCRETE)
        pied.setContentsMargins(48, 8, 48, 14)
        droite.addWidget(pied)
        root.addLayout(droite, stretch=1)

        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        # À propos ne règle rien : la phrase sur l'enregistrement n'y a pas lieu.
        self._nav.currentRowChanged.connect(
            lambda rang: pied.setVisible(rang != len(_RUBRIQUES) - 1))
        self._nav.setCurrentRow(0)

    def _colonne_rubriques(self) -> QFrame:
        colonne = QFrame()
        colonne.setObjectName("rubriques")
        colonne.setFixedWidth(_LARGEUR_RUBRIQUES)
        lay = QVBoxLayout(colonne)
        lay.setContentsMargins(18, 22, 18, 18)
        lay.setSpacing(4)

        # Le chemin du retour dit OÙ il mène : la bibliothèque, pas « Fermer ».
        retour = QPushButton(tr("Bibliothèque"))
        retour.setObjectName("retour")
        retour.setFont(police(13))
        retour.setIcon(QIcon(pixmap_icone("retour", 16, QColor(_ENCRE_RUBRIQUE))))
        retour.setIconSize(QSize(16, 16))
        retour.setCursor(Qt.CursorShape.PointingHandCursor)
        retour.clicked.connect(self.accept)
        lay.addWidget(retour, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(12)

        # Sans « Segoe UI » appelée par son NOM : elle n'existe pas sous Linux,
        # et sous `offscreen` Qt lui substitue Cinzel, 22 % plus large.
        titre = QLabel(tr("Paramètres"))
        titre.setFont(cinzel_decorative(17))
        titre.setStyleSheet("color: #f4f2f8; background: transparent;")
        titre.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(titre)
        lay.addSpacing(16)

        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setFont(police(14))
        self._nav.setIconSize(QSize(19, 19))
        self._nav.setSpacing(2)
        # Sans ça, un libellé large (« Téléchargements ») fait apparaître une
        # scrollbar horizontale disgracieuse sous la nav (vu à l'audit).
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setCursor(Qt.CursorShape.PointingHandCursor)
        for libelle, icone in _RUBRIQUES:
            pictogramme = QIcon()
            pictogramme.addPixmap(pixmap_icone(icone, 19, QColor(_ENCRE_RUBRIQUE)),
                                  QIcon.Mode.Normal)
            pictogramme.addPixmap(pixmap_icone(icone, 19, QColor(current_theme().accent_light)),
                                  QIcon.Mode.Selected)
            self._nav.addItem(QListWidgetItem(pictogramme, tr(libelle)))
        lay.addWidget(self._nav, stretch=1)

        version = texte(f"Accio Launcher {APP_VERSION}", 12, "#5f5d80")
        version.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(version)
        return colonne

    @staticmethod
    def _marges(page: QWidget) -> QWidget:
        """Les marges de lecture autour d'une page, et une largeur de lecture
        bornée : sur un grand écran, une ligne de réglage étirée sur 1 500 px
        sépare son titre de son interrupteur par un désert."""
        cadre = QWidget()
        cadre.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(cadre)
        lay.setContentsMargins(48, 32, 48, 16)
        page.setMaximumWidth(760)
        lay.addWidget(page, stretch=1)
        return cadre

    @staticmethod
    def _page(*sections) -> QWidget:
        """Une page de cartes : chaque section est un (surtitre, carte)."""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(26)
        for titre, carte in sections:
            bloc = QVBoxLayout()
            bloc.setSpacing(10)
            bloc.addWidget(surtitre(titre))
            bloc.addWidget(carte)
            lay.addLayout(bloc)
        lay.addStretch()
        return page

    def _combo(self) -> QComboBox:
        combo = liste_deroulante()
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(themed(_COMBO_STYLE))
        combo.setMinimumWidth(170)
        return combo

    @staticmethod
    def _interrupteur(titre: str, coche: bool, description: str = "") -> tuple[LigneReglage, ToggleSwitch]:
        """Ligne de réglage dont la commande est un interrupteur."""
        bascule = ToggleSwitch(coche)
        # Le libellé est à CÔTÉ, pas dedans : sans nom accessible, une aide
        # technique n'annonce qu'« interrupteur », sans dire de quoi.
        bascule.setAccessibleName(titre)
        bascule.setToolTip(titre)
        return LigneReglage(titre, description, bascule), bascule

    def _restart_button(self) -> QPushButton:
        btn = bouton(tr("Redémarrer maintenant"), principal=True)
        btn.clicked.connect(self.restart_requested)
        return btn

    def _ligne_redemarrage(self, phrase: str) -> tuple[LigneReglage, QPushButton]:
        """« Redémarrez le launcher pour appliquer… » + le bouton, cachée tant
        que rien n'a changé (montrée au premier changement de langue ou de thème)."""
        btn = self._restart_button()
        ligne = LigneReglage(phrase, "", btn)
        ligne.titre.setStyleSheet(themed("color: #e8c547; background: transparent;"))
        ligne.titre.setWordWrap(True)
        ligne.hide()
        return ligne, btn

    # ── Page Général ──

    def _page_general(self) -> QWidget:
        dossier = Carte()
        self._path_label = _Chemin(str(self.config.install_path))
        btn_open = bouton(tr("Ouvrir"))
        btn_open.clicked.connect(self._on_open_install_folder)
        btn_change = bouton(tr("Changer…"), principal=True)
        btn_change.clicked.connect(self._on_change_path)
        icone = QLabel()
        icone.setPixmap(pixmap_icone("dossier", 22, accent_qcolor(255)))
        icone.setStyleSheet("background: transparent;")
        # Le titre de la ligne EST le chemin, coupé au milieu.
        ligne_dossier = LigneReglage(self._path_label, tr("Calcul de l'espace utilisé…"),
                                     btn_open, btn_change, icone=icone)
        self._installed_label = ligne_dossier.description
        dossier.ajouter(ligne_dossier)

        disque = QWidget()
        disque.setStyleSheet("background: transparent;")
        lay_disque = QVBoxLayout(disque)
        lay_disque.setContentsMargins(20, 14, 20, 16)
        lay_disque.setSpacing(10)
        self._barre_disque = _BarreDisque()
        lay_disque.addWidget(self._barre_disque)
        legende = QHBoxLayout()
        legende.setSpacing(7)
        legende.addWidget(_Pastille(accent_qcolor(255)))
        self._legende_jeux = texte(tr("Vos jeux"), 12, ENCRE_DOUCE)
        legende.addWidget(self._legende_jeux)
        legende.addSpacing(16)
        legende.addWidget(_Pastille(QColor(255, 255, 255, 56)))
        legende.addWidget(texte(tr("Le reste du disque"), 12, ENCRE_DOUCE))
        legende.addStretch()
        self._free_label = texte(_texte_disque(self.config.install_path), 12, "#d9d6e8")
        legende.addWidget(self._free_label)
        lay_disque.addLayout(legende)
        dossier.ajouter(disque)
        self._octets_jeux = 0
        self._regler_disque()

        # Snapshot des chemins sur le thread principal (thread-safe)
        game_paths = [
            self.manager.get_game_path(entry.game.id)
            for entry in self.manager.get_games()
            if entry.state == GameState.INSTALLED
        ]
        game_paths = [p for p in game_paths if p is not None]
        self._scan_worker = DiskScanWorker(game_paths, parent=self)
        self._scan_worker.result.connect(self._on_scan_done)
        self._scan_worker.start()

        langue = Carte()
        self._lang_combo = self._combo()
        # Découverte : déposer un src/data/i18n/<code>.json suffit à ajouter une
        # langue, sans toucher à ce fichier (voir src/core/i18n.available_languages).
        for info in available_languages():
            self._lang_combo.addItem(info.name, info.code)
        current = self._lang_combo.findData(self.config.langue)
        self._lang_combo.setCurrentIndex(max(0, current))
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        langue.ajouter(LigneReglage(
            tr("Langue du launcher"),
            tr("Chaque jeu garde sa propre langue, dans ses réglages."), self._lang_combo))
        # Bouton et aide vivent SOUS la ligne du combo : en ligne, ils
        # écrasaient le bouton sous sa taille minimale et débordaient du dialogue.
        self._lang_hint, self._lang_restart = self._ligne_redemarrage(
            tr("Redémarrez le launcher pour appliquer la langue."))
        langue.ajouter(self._lang_hint)

        sauvegardes = Carte()
        ligne, self._tgl_copies = self._interrupteur(
            tr("Copier les sauvegardes avant chaque partie"), self.config.copies_sauvegardes,
            tr("Une copie de chaque sauvegarde qui a changé, rangée à part."))
        self._tgl_copies.toggled.connect(self._on_setting_changed)
        sauvegardes.ajouter(ligne)
        sauvegardes.ajouter(LigneReglage(
            tr("Revenir à une copie"),
            tr("Depuis les réglages de chaque jeu, rubrique Fichiers du jeu.")))

        return self._page((tr("Dossier des jeux"), dossier), (tr("Langue"), langue),
                          (tr("Sauvegardes"), sauvegardes))

    def _regler_disque(self) -> None:
        libre, total = _disque(self.config.install_path)
        self._barre_disque.regler(self._octets_jeux, libre, total)
        self._free_label.setText(_texte_disque(self.config.install_path))

    # ── Page Affichage ──

    def _page_display(self) -> QWidget:
        videos = Carte()
        ligne, self._tgl_autoplay = self._interrupteur(
            tr("Lecture automatique des vidéos"), self.config.autoplay_videos)
        self._tgl_autoplay.toggled.connect(self._on_setting_changed)
        videos.ajouter(ligne)
        ligne, self._tgl_mute = self._interrupteur(
            tr("Couper le son des vidéos"), self.config.mute_videos)
        self._tgl_mute.toggled.connect(self._on_setting_changed)
        videos.ajouter(ligne)

        self._btn_trailers = bouton("", principal=True)
        self._btn_trailers.clicked.connect(self._on_trailers_clicked)
        self._ligne_trailers = LigneReglage(tr("Bandes-annonces"), " ", self._btn_trailers)
        self._lbl_trailers = self._ligne_trailers.description
        videos.ajouter(self._ligne_trailers)
        if self._store is not None:
            self._store.state_changed.connect(self._refresh_trailers)
            self._store.progress.connect(self._on_trailer_progress)
            self._store.job_finished.connect(self._on_trailer_job_finished)
        self._refresh_trailers()

        theme = Carte()
        self._theme_combo = self._combo()
        for palette in THEMES.values():
            self._theme_combo.addItem(tr(palette.nom), palette.id)
        ids = list(THEMES.keys())
        self._theme_combo.setCurrentIndex(
            ids.index(self.config.theme) if self.config.theme in ids else 0)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme.ajouter(LigneReglage(tr("Couleurs du launcher"), "", self._theme_combo))
        self._theme_hint, self._theme_restart = self._ligne_redemarrage(
            tr("Redémarrez le launcher pour appliquer le thème."))
        theme.ajouter(self._theme_hint)

        ambiance = Carte()
        self._season_combo = self._combo()
        # La LISTE vient de `season.SEASONS`, jamais d'une copie locale : il y
        # en avait une ici, et deux listes qu'aucun calcul ne relie finissent
        # par diverger — ajouter une ambiance l'aurait laissée invisible dans
        # les Paramètres, sans que rien ne le signale.
        for value in SEASONS:
            self._season_combo.addItem(tr(SEASON_LABELS[value]), value)
        self._season_combo.setCurrentIndex(
            SEASONS.index(self.config.season)
            if self.config.season in SEASONS else 0)
        self._season_combo.currentIndexChanged.connect(self._on_season_changed)
        ambiance.ajouter(LigneReglage(tr("Particules saisonnières"),
                                      tr("Appliqué immédiatement."), self._season_combo))
        ligne, self._tgl_faits = self._interrupteur(
            tr("Fait du jour dans la barre de statut"), self.config.faits_du_jour)
        self._tgl_faits.toggled.connect(self._on_setting_changed)
        ambiance.ajouter(ligne)

        return self._page((tr("Vidéos"), videos), (tr("Thème"), theme),
                          (tr("Almanach"), ambiance))

    # ── Bandes-annonces ──

    def _trailers(self) -> tuple:
        """Bandes-annonces déclarées par le catalogue."""
        return self.manager.trailers()

    def _refresh_trailers(self) -> None:
        """Met la ligne à jour : ce qu'on a, ce qu'il manque, et quoi faire.

        Cachée quand le catalogue n'en déclare aucune : proposer de télécharger
        ce qui n'existe pas serait une promesse en l'air, et un launcher plus
        ancien que son catalogue doit rester silencieux, pas cassé.
        """
        if self._lbl_trailers is None or self._btn_trailers is None:
            return
        liste = self._trailers()
        self._ligne_trailers.setVisible(bool(liste))
        if not liste:
            return

        if self._store is not None and self._store.is_busy:
            self._btn_trailers.setText(tr("Annuler"))
            return

        presentes = trailer_store.nombre_present(liste)
        octets = trailer_store.poids_disque()
        if presentes == len(liste):
            self._lbl_trailers.setText(
                tr("Bandes-annonces : {n} sur le disque ({taille})").format(
                    n=presentes, taille=format_bytes(octets)))
            self._btn_trailers.setText(tr("Supprimer"))
        else:
            manque = trailer_store.poids_a_telecharger(liste)
            self._lbl_trailers.setText(
                tr("Bandes-annonces : {faites} sur {total}").format(
                    faites=presentes, total=len(liste)))
            self._btn_trailers.setText(
                tr("Télécharger ({taille})").format(taille=format_size(manque)))

    def _on_trailer_progress(self, faites: int, total: int, octets: int, sur: int) -> None:
        if self._lbl_trailers is None:
            return
        pct = round(octets * 100 / sur) if sur else 0
        self._lbl_trailers.setText(
            tr("Téléchargement des bandes-annonces… {faites}/{total} · {pct} %").format(
                faites=faites + 1, total=total, pct=pct))

    def _on_trailer_job_finished(self, _ok: int, _echecs: int) -> None:
        self._refresh_trailers()

    def _on_trailers_clicked(self) -> None:
        """Télécharger, annuler ou supprimer — selon ce que dit le bouton."""
        if self._store is None:
            return
        if self._store.is_busy:
            self._store.cancel()
            self._refresh_trailers()
            return
        liste = self._trailers()
        if trailer_store.nombre_present(liste) == len(liste):
            # Supprimer, c'est aussi dire non : sans ça le rattrapage du
            # prochain démarrage les re-téléchargerait aussitôt.
            self.config.trailers_optin = False
            self.config.save()
            self._store.supprimer_tout()
            self._refresh_trailers()
            return
        self.config.trailers_optin = True
        self.config.save()
        self._store.start(liste)
        self._refresh_trailers()

    # ── Page Téléchargements ──

    def _page_downloads(self) -> QWidget:
        archives = Carte()
        ligne, self._tgl_delete = self._interrupteur(
            tr("Supprimer les archives après installation"), self.config.delete_archives)
        self._tgl_delete.toggled.connect(self._on_setting_changed)
        archives.ajouter(ligne)

        majs = Carte()
        cat_ver = self.manager.catalog.catalog_version
        btn_catalog = bouton(tr("Actualiser le catalogue"))
        btn_catalog.clicked.connect(self._on_refresh_catalog)
        btn_launcher = bouton(tr("Vérifier les mises à jour"), principal=True)
        btn_launcher.clicked.connect(self._on_check_launcher)
        ligne_versions = LigneReglage(
            tr("Launcher v{}  ·  Catalogue v{}").format(APP_VERSION, cat_ver), "")
        self._versions_label = ligne_versions.titre
        majs.ajouter(ligne_versions)
        # Les deux boutons sur leur propre ligne : à côté des numéros, ils
        # écrasaient le titre à la largeur minimale du dialogue.
        boutons = QWidget()
        boutons.setStyleSheet("background: transparent;")
        rangee = QHBoxLayout(boutons)
        rangee.setContentsMargins(20, 0, 20, 14)
        rangee.setSpacing(10)
        rangee.addWidget(btn_catalog)
        rangee.addWidget(btn_launcher)
        rangee.addStretch()
        # Sans filet : les boutons appartiennent à la ligne des numéros.
        majs.layout().addWidget(boutons)
        self._update_status = texte("", 13, ENCRE_DOUCE, retour=True)
        self._update_status.setContentsMargins(20, 0, 20, 14)
        self._update_status.hide()
        majs.layout().addWidget(self._update_status)

        return self._page((tr("Téléchargement"), archives), (tr("Mises à jour"), majs))

    # ── Page Intégrations ──

    def _page_integrations(self) -> QWidget:
        discord = Carte()
        ligne, self._tgl_discord = self._interrupteur(
            tr("Afficher le jeu en cours sur Discord"), self.config.discord_presence)
        self._tgl_discord.toggled.connect(self._on_setting_changed)
        discord.ajouter(ligne)

        manette_carte = Carte()
        ligne, self._tgl_nav_manette = self._interrupteur(
            tr("Naviguer dans le launcher à la manette"), self.config.navigation_manette,
            tr("Croix directionnelle : changer de jeu et de bouton. Croix ou A : valider. "
               "Rond ou B : retour. Stick droit : faire défiler."))
        self._tgl_nav_manette.toggled.connect(self._on_setting_changed)
        self._tgl_nav_manette.toggled.connect(self._on_navigation_manette)
        manette_carte.ajouter(ligne)
        ligne, self._tgl_manette = self._interrupteur(
            tr("Barre lumineuse de la manette aux couleurs de votre maison"),
            self.config.couleur_manette)
        self._tgl_manette.toggled.connect(self._on_setting_changed)
        self._tgl_manette.toggled.connect(self._on_couleur_manette)
        manette_carte.ajouter(ligne)
        return self._page((tr("Discord"), discord), (tr("Manette"), manette_carte))

    # ── Page À propos ──

    # ──────────────────── Slots ────────────────────

    def _on_scan_done(self, count: int, total_bytes: int) -> None:
        """Callback quand le scan disque en arrière-plan est terminé."""
        # Une clé par nombre : « (x) » ne se traduit pas, et l'anglais met
        # 0 au pluriel quand le français le met au singulier.
        if count == 0:
            phrase = tr("Aucun jeu installé")
        elif count == 1:
            phrase = tr("1 jeu installé, {}").format(format_bytes(total_bytes))
        else:
            phrase = tr("{} jeux installés, {}").format(count, format_bytes(total_bytes))
        self._installed_label.setText(phrase)
        self._legende_jeux.setText(
            tr("Vos jeux · {}").format(format_bytes(total_bytes)) if count else tr("Vos jeux"))
        self._octets_jeux = total_bytes
        self._regler_disque()
        log.info("Total installé : %d jeu(x), %s", count, format_bytes(total_bytes))

    def _on_change_path(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, tr("Changer le dossier d'installation"), str(self.config.install_path)
        )
        if chosen:
            # MÊME garde que l'assistant de premier lancement, qui la posait
            # depuis toujours — pas ici. Or c'est par ce chemin qu'on choisit un
            # dossier APRÈS coup, donc celui par lequel arrivent « Program
            # Files », la racine d'un disque et les lecteurs réseau montés en
            # lecture seule. Sans elle, le réglage était accepté, sauvegardé, et
            # l'échec ne se manifestait qu'au téléchargement suivant, sous la
            # forme d'une erreur qui n'accusait pas le dossier.
            if not is_writable_dir(Path(chosen)):
                avertir(
                    self, tr("Dossier non inscriptible"),
                    tr("Impossible d'écrire dans :\n{}").format(chosen))
                return
            self.config.install_path = Path(chosen)
            self.config.cache_path = cache_pour(Path(chosen))
            self._path_label.definir(chosen)
            self._regler_disque()
            self._save()

    def _on_setting_changed(self) -> None:
        self.config.delete_archives = self._tgl_delete.isChecked()
        self.config.autoplay_videos = self._tgl_autoplay.isChecked()
        self.config.mute_videos = self._tgl_mute.isChecked()
        self.config.faits_du_jour = self._tgl_faits.isChecked()
        self.config.discord_presence = self._tgl_discord.isChecked()
        self.config.couleur_manette = self._tgl_manette.isChecked()
        self.config.navigation_manette = self._tgl_nav_manette.isChecked()
        self.config.copies_sauvegardes = self._tgl_copies.isChecked()
        self._save()

    @staticmethod
    def _on_navigation_manette(coche: bool) -> None:
        # Tout de suite : c'est en essayant qu'on voit si ça marche.
        navigation = manette_nav.navigation()
        if navigation is not None:
            navigation.set_actif(coche)

    def _on_couleur_manette(self, coche: bool) -> None:
        # Allumé : la manette prend la couleur tout de suite, c'est ce qui dit que ça marche.
        if coche:
            manette.colorer_en_fond(self.config.theme)

    def _on_language_changed(self) -> None:
        """Change la langue (effective au prochain démarrage — chaînes posées à la construction)."""
        self.config.langue = self._lang_combo.currentData()
        self._lang_hint.show()
        self._save()

    def _on_theme_changed(self) -> None:
        """Change le thème (effectif au prochain démarrage — couleurs posées à la construction)."""
        self.config.theme = self._theme_combo.currentData()
        # La fenêtre attend un redémarrage ; la manette, elle, change tout de suite.
        if self.config.couleur_manette:
            manette.colorer_en_fond(self.config.theme)
        self._theme_hint.show()
        self._save()

    def _on_season_changed(self) -> None:
        """Change la saison des particules — appliqué EN DIRECT (pas de redémarrage)."""
        self.config.season = self._season_combo.currentData()
        self._save()
        self.season_changed.emit(resolve_season(self.config.season))

    def done(self, result: int) -> None:
        """Arrête le scan disque sur TOUS les chemins de fermeture.

        accept() (bouton Fermer) et reject() (Échap) ne passent PAS par
        closeEvent — seul done() est commun aux trois sorties (vérifié
        empiriquement). Sans ça, le QThread de scan serait détruit avec le
        dialog alors qu'il tourne encore → crash.
        """
        self._shutdown_scan()
        super().done(result)

    def _shutdown_scan(self) -> None:
        """Interrompt et attend le DiskScanWorker (idempotent)."""
        self._scan_worker.blockSignals(True)
        try:
            self._scan_worker.result.disconnect(self._on_scan_done)
        except TypeError:
            pass
        if self._scan_worker.isRunning():
            # L'interruption est vérifiée à chaque fichier scanné,
            # le wait() est donc borné en pratique.
            self._scan_worker.requestInterruption()
            self._scan_worker.wait()

    def _on_open_install_folder(self) -> None:
        open_local_path(str(self.config.install_path))

    def _on_refresh_catalog(self) -> None:
        self._update_status.setText(tr("Actualisation du catalogue…"))
        self._update_status.setStyleSheet(themed("color: #d6a72c;"))
        self._update_status.show()
        self.force_catalog_refresh.emit()

    def _on_check_launcher(self) -> None:
        self._update_status.setText(tr("Vérification des mises à jour…"))
        self._update_status.setStyleSheet(themed("color: #d6a72c;"))
        self._update_status.show()
        self.force_launcher_check.emit()

    def update_catalog_version(self, version: str) -> None:
        """Met à jour l'affichage de la version du catalogue après un refresh."""
        self._versions_label.setText(
            tr("Launcher v{}  ·  Catalogue v{}").format(APP_VERSION, version)
        )
        self._update_status.setText(tr("Catalogue mis à jour en v{}").format(version))
        self._update_status.setStyleSheet("color: #2ecc71;")
        self._update_status.show()

    def show_update_status(self, message: str, success: bool = True) -> None:
        """Affiche un message de statut dans la section mises à jour."""
        color = "#2ecc71" if success else "#8a8aaa"
        self._update_status.setText(message)
        self._update_status.setStyleSheet(f"color: {color};")
        self._update_status.show()

    def _save(self) -> None:
        self.config.save()
        self.config_changed.emit()

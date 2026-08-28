"""Panneau de paramètres — sidebar de sections + pages empilées.

Sections : Général (dossier, espace, langue) · Affichage (vidéos, thème, saison)
· Téléchargements (archives, mises à jour) · Intégrations (Discord) · À propos.
Le thème et la langue demandent un redémarrage (bouton « Redémarrer maintenant ») ;
la saison des particules s'applique EN DIRECT (signal `season_changed`).
"""

import logging
import shutil
from pathlib import Path


from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config import APP_VERSION, Config, cache_pour
from src.core.game_manager import GameManager, GameState
from src.core import trailers as trailer_store
from src.core.formatting import format_bytes, format_size
from src.core.i18n import available_languages, tr
from src.ui.fonts import cinzel
from src.ui import about_page
from src.ui.disk_scan_worker import DiskScanWorker
from src.ui.season import resolve as resolve_season
from src.ui.theme import THEMES, themed
from src.ui.toggle_switch import toggle_row
from src.ui.utils import is_writable_dir, open_local_path

log = logging.getLogger(__name__)

# Style partagé des QComboBox du panneau (langue, thème, saison)
_COMBO_STYLE = (
    "QComboBox { background: #16213e; color: #ffffff; border: 1px solid #2c3e6b;"
    " border-radius: 6px; padding: 6px 12px; font-size: 13px; }"
    "QComboBox QAbstractItemView { background: #16213e; color: #ffffff;"
    " selection-background-color: #2c3e6b; }"
)


def _disk_free(path: Path) -> str:
    try:
        usage = shutil.disk_usage(path)
        return format_bytes(usage.free)
    except OSError:
        return "?"


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
        self.setMinimumSize(660, 470)
        self.setStyleSheet(themed(self._style()))
        self._build_ui()

    def _style(self) -> str:
        return """
        QDialog {
            background-color: #0d0d1a;
            color: #ffffff;
        }
        QLabel {
            color: #ffffff;
        }
        QLabel#sectionTitle {
            font-size: 16px;
            font-weight: bold;
            color: #d6a72c;
            padding-top: 4px;
        }
        QLabel#subtitle {
            font-size: 12px;
            color: #b0b0b0;
        }
        QListWidget#navList {
            background: transparent;
            border: none;
            outline: none;
            font-size: 14px;
        }
        QListWidget#navList::item {
            color: #b0b0b0;
            padding: 10px 14px;
            border-radius: 6px;
        }
        QListWidget#navList::item:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.05);
        }
        QListWidget#navList::item:selected {
            color: #e8c547;
            background: rgba(214, 167, 44, 0.12);
        }
        QPushButton#btnPath {
            background-color: #16213e;
            color: #ffffff;
            border: 1px solid #2c3e6b;
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 13px;
        }
        QPushButton#btnPath:hover {
            border-color: #d6a72c;
        }
        QPushButton#btnRestart {
            background-color: rgba(214, 167, 44, 0.15);
            color: #e8c547;
            border: 1px solid rgba(214, 167, 44, 0.5);
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 12px;
        }
        QPushButton#btnRestart:hover {
            background-color: rgba(214, 167, 44, 0.3);
        }
        QPushButton#btnKofi {
            background-color: rgba(214, 167, 44, 0.12);
            color: #e8c547;
            border: 1px solid rgba(214, 167, 44, 0.45);
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 13px;
        }
        QPushButton#btnKofi:hover {
            background-color: rgba(214, 167, 44, 0.25);
            border-color: #d6a72c;
        }
        QPushButton#btnClose {
            background-color: #d6a72c;
            color: #000000;
            font-weight: bold;
            border: none;
            border-radius: 6px;
            padding: 10px 24px;
            font-size: 14px;
        }
        QPushButton#btnClose:hover {
            background-color: #e6b422;
        }
        """

    # ──────────────────── Construction ────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 16, 20, 16)

        # Sans le ⚙ : il était rendu en couleur par Windows (49 % de pixels
        # colorés, mesuré le 2026-08-26), et un titre de fenêtre n'a de toute
        # façon pas besoin d'un pictogramme pour dire ce qu'il est. Et sans
        # « Segoe UI », appelée par son NOM : elle n'existe pas sous Linux, et
        # sous `offscreen` Qt lui substitue Cinzel, 22 % plus large — toute
        # mesure de mise en page portait donc sur une autre police.
        title = QLabel(tr("Paramètres"))
        title.setFont(cinzel(18, bold=True))
        title.setStyleSheet("color: #ffffff;")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(16)

        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setFixedWidth(170)
        # Sans ça, un libellé large (« Téléchargements ») fait apparaître une
        # scrollbar horizontale disgracieuse sous la nav (vu à l'audit).
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setCursor(Qt.CursorShape.PointingHandCursor)
        for label in (tr("Général"), tr("Affichage"), tr("Téléchargements"),
                      tr("Intégrations"), tr("À propos")):
            self._nav.addItem(label)
        body.addWidget(self._nav)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._page_general())
        self._pages.addWidget(self._page_display())
        self._pages.addWidget(self._page_downloads())
        self._pages.addWidget(self._page_integrations())
        self._pages.addWidget(about_page.construire(
            self.manager.catalog.contributors))
        body.addWidget(self._pages, stretch=1)
        root.addLayout(body, stretch=1)

        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._nav.setCurrentRow(0)

        btn_close = QPushButton(tr("Fermer"))
        btn_close.setObjectName("btnClose")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        root.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignCenter)

    @staticmethod
    def _page(*rows) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        for row in rows:
            if isinstance(row, QWidget):
                lay.addWidget(row)
            else:
                lay.addLayout(row)
        lay.addStretch()
        return page

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(themed(_COMBO_STYLE))
        return combo

    def _restart_button(self) -> QPushButton:
        btn = QPushButton(tr("Redémarrer maintenant"))
        btn.setObjectName("btnRestart")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.restart_requested)
        btn.hide()  # montré au premier changement de langue/thème
        return btn

    def _hint_label(self) -> QLabel:
        """Aide contextuelle pleine largeur, cachée tant qu'elle est vide."""
        lbl = QLabel("")
        lbl.setObjectName("subtitle")
        lbl.setWordWrap(True)
        lbl.hide()
        return lbl

    @staticmethod
    def _button_row(btn: QPushButton) -> QHBoxLayout:
        """Ligne dédiée à un bouton (aligné à gauche, jamais compressé)."""
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addStretch()
        return row

    # ── Page Général ──

    def _page_general(self) -> QWidget:
        path_row = QHBoxLayout()
        self._path_label = QLabel(str(self.config.install_path))
        self._path_label.setStyleSheet("color: #b0b0b0; font-size: 13px;")
        self._path_label.setWordWrap(True)
        path_row.addWidget(self._path_label, stretch=1)
        btn_open = QPushButton(tr("Ouvrir"))
        btn_open.setObjectName("btnPath")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self._on_open_install_folder)
        path_row.addWidget(btn_open)
        btn_change = QPushButton(tr("Changer…"))
        btn_change.setObjectName("btnPath")
        btn_change.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_change.clicked.connect(self._on_change_path)
        path_row.addWidget(btn_change)

        self._free_label = QLabel(tr("Espace libre : {}").format(_disk_free(self.config.install_path)))
        self._free_label.setObjectName("subtitle")

        self._installed_label = QLabel(tr("Calcul de l'espace utilisé…"))
        self._installed_label.setObjectName("subtitle")

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

        lang_row = QHBoxLayout()
        self._lang_combo = self._combo()
        # Découverte : déposer un src/data/i18n/<code>.json suffit à ajouter une
        # langue, sans toucher à ce fichier (voir src/core/i18n.available_languages).
        for info in available_languages():
            self._lang_combo.addItem(info.name, info.code)
        current = self._lang_combo.findData(self.config.langue)
        self._lang_combo.setCurrentIndex(max(0, current))
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        # Bouton et aide vivent SOUS la ligne du combo : en ligne, ils
        # écrasaient le bouton sous sa taille minimale et débordaient du dialogue.
        self._lang_restart = self._restart_button()
        self._lang_hint = self._hint_label()

        return self._page(
            self._section(tr("Dossier d'installation")), path_row,
            self._free_label, self._installed_label,
            self._section(tr("Langue")), lang_row,
            self._button_row(self._lang_restart), self._lang_hint,
        )

    # ── Page Affichage ──

    def _page_display(self) -> QWidget:
        row_autoplay, self._tgl_autoplay = toggle_row(
            tr("Lecture automatique des vidéos"), self.config.autoplay_videos)
        self._tgl_autoplay.toggled.connect(self._on_setting_changed)
        row_mute, self._tgl_mute = toggle_row(
            tr("Couper le son des vidéos"), self.config.mute_videos)
        self._tgl_mute.toggled.connect(self._on_setting_changed)

        theme_row = QHBoxLayout()
        self._theme_combo = self._combo()
        for palette in THEMES.values():
            self._theme_combo.addItem(tr(palette.nom), palette.id)
        ids = list(THEMES.keys())
        self._theme_combo.setCurrentIndex(
            ids.index(self.config.theme) if self.config.theme in ids else 0)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self._theme_combo)
        theme_row.addStretch()
        self._theme_restart = self._restart_button()  # sous la ligne — voir page Général
        self._theme_hint = self._hint_label()

        season_row = QHBoxLayout()
        self._season_combo = self._combo()
        for value, label in (
            ("auto", tr("Automatique (selon la date)")),
            ("aucune", tr("Aucune")),
            ("halloween", tr("Halloween")),
            ("noel", tr("Noël")),
        ):
            self._season_combo.addItem(label, value)
        season_ids = ["auto", "aucune", "halloween", "noel"]
        self._season_combo.setCurrentIndex(
            season_ids.index(self.config.season) if self.config.season in season_ids else 0)
        self._season_combo.currentIndexChanged.connect(self._on_season_changed)
        season_row.addWidget(self._season_combo)
        season_hint = QLabel(tr("Appliqué immédiatement."))
        season_hint.setObjectName("subtitle")
        season_row.addWidget(season_hint, stretch=1)

        trailer_row = QHBoxLayout()
        self._lbl_trailers = QLabel("")
        self._lbl_trailers.setObjectName("subtitle")
        self._btn_trailers = QPushButton("")
        self._btn_trailers.setObjectName("btnPath")
        self._btn_trailers.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_trailers.clicked.connect(self._on_trailers_clicked)
        trailer_row.addWidget(self._lbl_trailers, stretch=1)
        trailer_row.addWidget(self._btn_trailers)
        if self._store is not None:
            self._store.state_changed.connect(self._refresh_trailers)
            self._store.progress.connect(self._on_trailer_progress)
            self._store.job_finished.connect(self._on_trailer_job_finished)
        self._refresh_trailers()

        return self._page(
            self._section(tr("Vidéos")), row_autoplay, row_mute, trailer_row,
            self._section(tr("Thème")), theme_row,
            self._button_row(self._theme_restart), self._theme_hint,
            self._section(tr("Particules saisonnières")), season_row,
        )

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
        if not liste:
            self._lbl_trailers.hide()
            self._btn_trailers.hide()
            return
        self._lbl_trailers.show()
        self._btn_trailers.show()

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
        row_delete, self._tgl_delete = toggle_row(
            tr("Supprimer les archives après installation"), self.config.delete_archives)
        self._tgl_delete.toggled.connect(self._on_setting_changed)
        cat_ver = self.manager.catalog.catalog_version
        self._versions_label = QLabel(
            tr("Launcher v{}  ·  Catalogue v{}").format(APP_VERSION, cat_ver))
        self._versions_label.setObjectName("subtitle")

        update_row = QHBoxLayout()
        update_row.setSpacing(10)
        btn_catalog = QPushButton(tr("Actualiser le catalogue"))
        btn_catalog.setObjectName("btnPath")
        btn_catalog.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_catalog.clicked.connect(self._on_refresh_catalog)
        update_row.addWidget(btn_catalog)
        btn_launcher = QPushButton(tr("Vérifier les mises à jour"))
        btn_launcher.setObjectName("btnPath")
        btn_launcher.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_launcher.clicked.connect(self._on_check_launcher)
        update_row.addWidget(btn_launcher)
        update_row.addStretch()

        self._update_status = QLabel("")
        self._update_status.setObjectName("subtitle")
        self._update_status.setWordWrap(True)
        self._update_status.hide()

        return self._page(
            self._section(tr("Téléchargement")), row_delete,
            self._section(tr("Mises à jour")), self._versions_label,
            update_row, self._update_status,
        )

    # ── Page Intégrations ──

    def _page_integrations(self) -> QWidget:
        row_discord, self._tgl_discord = toggle_row(
            tr("Afficher le jeu en cours sur Discord"), self.config.discord_presence)
        self._tgl_discord.toggled.connect(self._on_setting_changed)
        return self._page(self._section(tr("Discord")), row_discord)

    # ── Page À propos ──

    # ──────────────────── Slots ────────────────────

    def _on_scan_done(self, count: int, total_bytes: int) -> None:
        """Callback quand le scan disque en arrière-plan est terminé."""
        self._installed_label.setText(
            tr("{} jeu(x) installé(s) — {} utilisés").format(count, format_bytes(total_bytes))
        )
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
                QMessageBox.warning(
                    self, tr("Dossier non inscriptible"),
                    tr("Impossible d'écrire dans :\n{}").format(chosen))
                return
            self.config.install_path = Path(chosen)
            self.config.cache_path = cache_pour(Path(chosen))
            self._path_label.setText(chosen)
            self._free_label.setText(tr("Espace libre : {}").format(_disk_free(Path(chosen))))
            self._save()

    def _on_setting_changed(self) -> None:
        self.config.delete_archives = self._tgl_delete.isChecked()
        self.config.autoplay_videos = self._tgl_autoplay.isChecked()
        self.config.mute_videos = self._tgl_mute.isChecked()
        self.config.discord_presence = self._tgl_discord.isChecked()
        self._save()

    def _on_language_changed(self) -> None:
        """Change la langue (effective au prochain démarrage — chaînes posées à la construction)."""
        self.config.langue = self._lang_combo.currentData()
        self._lang_hint.setText(tr("Redémarrez le launcher pour appliquer la langue."))
        self._lang_hint.show()
        self._lang_restart.show()
        self._save()

    def _on_theme_changed(self) -> None:
        """Change le thème (effectif au prochain démarrage — couleurs posées à la construction)."""
        self.config.theme = self._theme_combo.currentData()
        self._theme_hint.setText(tr("Redémarrez le launcher pour appliquer le thème."))
        self._theme_hint.show()
        self._theme_restart.show()
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

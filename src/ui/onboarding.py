"""Assistant de premier lancement — 3 écrans.

1. Bienvenue + choix du dossier d'installation (espace libre affiché).
2. « J'ai déjà certains jeux » — scan d'un dossier existant et import en masse
   (même disque : déplacement instantané, comme « J'ai déjà ce jeu »).
3. Préférences rapides : langue, thème, lecture auto des vidéos.

L'assistant lui-même s'affiche en français (aucune config n'existe encore),
mais la langue et le thème choisis s'appliquent dès la fin : MainWindow appelle
`set_language` / `set_theme` APRÈS `run_onboarding()`.
"""

import logging
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout,
    QWidget,
)

from src.core.config import Config, DEFAULT_CACHE_PATH, DEFAULT_INSTALL_PATH
from src.core.formatting import format_bytes
from src.core.game_data import GameData, load_catalog
from src.ui.fonts import cinzel_decorative
from src.ui.theme import THEMES
from src.ui.toggle_switch import toggle_row
from src.ui.utils import is_writable_dir

log = logging.getLogger(__name__)


def detect_installed_games(parent: Path, games: list[GameData]) -> list[tuple[GameData, Path]]:
    """Détecte les installations existantes sous `parent` (fonction pure).

    Un jeu est détecté si le dossier attendu (1er segment de `executable`)
    existe et contient l'exécutable relatif. Retourne [(jeu, dossier_source)].
    """
    found: list[tuple[GameData, Path]] = []
    for game in games:
        parts = Path(game.executable).parts
        if len(parts) < 2:
            continue
        candidate = parent / parts[0]
        if (candidate / Path(*parts[1:])).exists():
            found.append((game, candidate))
    return found


class OnboardingDialog(QDialog):
    """Assistant 3 écrans, modal, affiché avant la construction de MainWindow."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bienvenue dans Accio Launcher")
        self.setMinimumSize(560, 430)
        self.setStyleSheet(
            "QDialog { background: #0d0d1a; }"
            "QLabel { color: #eaeaea; font-size: 13px; }"
            "QLabel#wizTitle { color: #d4a017; }"
            "QLabel#wizHint { color: #8a8aaa; font-size: 12px; }"
            "QPushButton { background: #16213e; color: #eaeaea; border: 1px solid #2c3e6b;"
            " border-radius: 6px; padding: 8px 18px; font-size: 13px; }"
            "QPushButton:hover { border-color: #d4a017; color: #e8c547; }"
            "QPushButton#wizNext { background: #d4a017; color: #000; font-weight: bold; border: none; }"
            "QPushButton#wizNext:hover { background: #e6b422; }"
            "QListWidget { background: #060611; color: #eaeaea; border: 1px solid #1a2744;"
            " border-radius: 6px; font-size: 13px; }"
            "QComboBox { background: #16213e; color: #ffffff; border: 1px solid #2c3e6b;"
            " border-radius: 6px; padding: 6px 12px; font-size: 13px; }"
            "QComboBox QAbstractItemView { background: #16213e; color: #ffffff;"
            " selection-background-color: #2c3e6b; }"
        )

        # Résultats lus par run_onboarding() après accept()
        self.install_path: Path = DEFAULT_INSTALL_PATH
        self.langue = "fr"
        self.theme = "poudlard"
        self.autoplay = True
        self._games = list(load_catalog().games)
        self._detected: list[tuple[GameData, Path]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_page_welcome())
        self._pages.addWidget(self._build_page_import())
        self._pages.addWidget(self._build_page_prefs())
        layout.addWidget(self._pages, stretch=1)

        nav = QHBoxLayout()
        self._step_label = QLabel("1/3")
        self._step_label.setObjectName("wizHint")
        nav.addWidget(self._step_label)
        nav.addStretch()
        self._btn_back = QPushButton("Retour")
        self._btn_back.clicked.connect(self._go_back)
        nav.addWidget(self._btn_back)
        self._btn_next = QPushButton("Suivant")
        self._btn_next.setObjectName("wizNext")
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_next.clicked.connect(self._go_next)
        nav.addWidget(self._btn_next)
        layout.addLayout(nav)
        self._sync_nav()

    # ── Pages ──

    def _build_page_welcome(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)
        title = QLabel("⚡ Bienvenue dans Accio Launcher")
        title.setObjectName("wizTitle")
        title.setFont(cinzel_decorative(22))
        lay.addWidget(title)
        intro = QLabel("Les jeux Harry Potter PC, prêts à jouer en un clic.\n"
                       "Choisissez d'abord le dossier où les jeux seront installés.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        lay.addSpacing(8)

        row = QHBoxLayout()
        self._path_label = QLabel(str(self.install_path))
        self._path_label.setObjectName("wizHint")
        self._path_label.setWordWrap(True)
        row.addWidget(self._path_label, stretch=1)
        btn = QPushButton("Changer…")
        btn.clicked.connect(self._choose_install_dir)
        row.addWidget(btn)
        lay.addLayout(row)

        self._free_label = QLabel()
        self._free_label.setObjectName("wizHint")
        lay.addWidget(self._free_label)
        self._refresh_free_space()
        lay.addStretch()
        return page

    def _build_page_import(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)
        title = QLabel("Vous avez déjà certains jeux ?")
        title.setObjectName("wizTitle")
        title.setFont(cinzel_decorative(20))
        lay.addWidget(title)
        hint = QLabel("Indiquez le dossier qui contient vos installations existantes : "
                      "les jeux reconnus seront déplacés dans le launcher (même disque, "
                      "instantané). Vous pouvez passer cette étape.")
        hint.setWordWrap(True)
        hint.setObjectName("wizHint")
        lay.addWidget(hint)

        row = QHBoxLayout()
        btn_scan = QPushButton("Rechercher dans un dossier…")
        btn_scan.clicked.connect(self._scan_folder)
        row.addWidget(btn_scan)
        self._scan_label = QLabel("")
        self._scan_label.setObjectName("wizHint")
        row.addWidget(self._scan_label, stretch=1)
        lay.addLayout(row)

        self._import_list = QListWidget()
        lay.addWidget(self._import_list, stretch=1)
        return page

    def _build_page_prefs(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)
        title = QLabel("Dernières touches")
        title.setObjectName("wizTitle")
        title.setFont(cinzel_decorative(20))
        lay.addWidget(title)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Langue :"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("Français", "fr")
        self._lang_combo.addItem("English", "en")
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        lay.addLayout(lang_row)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Thème :"))
        self._theme_combo = QComboBox()
        for palette in THEMES.values():
            self._theme_combo.addItem(palette.nom, palette.id)
        theme_row.addWidget(self._theme_combo)
        theme_row.addStretch()
        lay.addLayout(theme_row)

        row, self._tgl_autoplay = toggle_row("Lire les bandes-annonces automatiquement", True)
        lay.addWidget(row)

        done = QLabel("C'est tout — bon retour à Poudlard ✨")
        done.setObjectName("wizHint")
        lay.addWidget(done)
        lay.addStretch()
        return page

    # ── Navigation ──

    def _sync_nav(self) -> None:
        i = self._pages.currentIndex()
        self._step_label.setText(f"{i + 1}/3")
        self._btn_back.setVisible(i > 0)
        self._btn_next.setText("Terminer" if i == 2 else "Suivant")

    def _go_back(self) -> None:
        self._pages.setCurrentIndex(max(0, self._pages.currentIndex() - 1))
        self._sync_nav()

    def _go_next(self) -> None:
        i = self._pages.currentIndex()
        if i == 0 and not is_writable_dir(self.install_path):
            QMessageBox.warning(self, "Dossier non inscriptible",
                                f"Impossible d'écrire dans :\n{self.install_path}")
            return
        if i == 2:
            self.langue = self._lang_combo.currentData()
            self.theme = self._theme_combo.currentData()
            self.autoplay = self._tgl_autoplay.isChecked()
            self.accept()
            return
        self._pages.setCurrentIndex(i + 1)
        self._sync_nav()

    # ── Écran 1 : dossier ──

    def _choose_install_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Dossier d'installation des jeux", str(self.install_path))
        if chosen:
            self.install_path = Path(chosen)
            self._path_label.setText(chosen)
            self._refresh_free_space()

    def _refresh_free_space(self) -> None:
        try:
            free = format_bytes(shutil.disk_usage(self.install_path.anchor or ".").free)
        except OSError:
            free = "?"
        self._free_label.setText(f"Espace libre : {free}")

    # ── Écran 2 : scan/import ──

    def _scan_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Dossier contenant vos jeux", str(Path.home()))
        if not chosen:
            return
        parent = Path(chosen)
        self._detected = detect_installed_games(parent, self._games)
        self._import_list.clear()
        if not self._detected:
            self._scan_label.setText("Aucun jeu reconnu dans ce dossier.")
            return
        self._scan_label.setText(f"{len(self._detected)} jeu(x) reconnu(s)")
        for game, src in self._detected:
            item = QListWidgetItem(f"{game.name} — {src}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._import_list.addItem(item)

    def checked_imports(self) -> list[tuple[GameData, Path]]:
        return [
            pair for row, pair in enumerate(self._detected)
            if self._import_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def perform_imports(self, config: Config) -> None:
        """Déplace les jeux cochés dans le dossier d'installation (config déjà créée)."""
        from src.ui.game_detail_handlers import find_import_error

        done: list[str] = []
        errors: list[str] = []
        for game, src in self.checked_imports():
            if src.parent.resolve() == config.install_path.resolve():
                done.append(game.name)  # déjà au bon endroit, rien à déplacer
                config.installed_versions[game.id] = game.recommended_version
                continue
            error = find_import_error(game, src, config.install_path)
            if error is not None:
                errors.append(f"{game.name} : {error.splitlines()[0]}")
                continue
            dest = config.install_path / Path(game.executable).parts[0]
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dest)  # même disque (validé) → instantané
            except OSError as exc:
                errors.append(f"{game.name} : {exc}")
                continue
            config.installed_versions[game.id] = game.recommended_version
            done.append(game.name)
            log.info("Onboarding : %s importé (%s → %s)", game.id, src, dest)
        if done or errors:
            config.save()
        if errors:
            QMessageBox.warning(
                self, "Import partiel",
                "Certains jeux n'ont pas pu être importés :\n\n" + "\n".join(errors))


def run_onboarding() -> Config:
    """Affiche l'assistant et retourne la Config créée (défauts si annulé)."""
    dlg = OnboardingDialog()
    if dlg.exec() == QDialog.DialogCode.Accepted and is_writable_dir(dlg.install_path):
        config = Config(
            install_path=dlg.install_path,
            cache_path=dlg.install_path / ".cache",
            langue=dlg.langue,
            theme=dlg.theme,
            autoplay_videos=dlg.autoplay,
        )
        config.save()
        dlg.perform_imports(config)
        return config
    # Annulé → défauts sûrs (toujours créable sous le home)
    DEFAULT_INSTALL_PATH.mkdir(parents=True, exist_ok=True)
    config = Config(install_path=DEFAULT_INSTALL_PATH, cache_path=DEFAULT_CACHE_PATH)
    config.save()
    return config

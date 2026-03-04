import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core.config import APP_VERSION, Config, DEFAULT_INSTALL_PATH
from src.core.game_manager import GameManager
from src.ui.game_card import GameCard
from src.ui.styles import MAIN_STYLE

GRID_COLUMNS = 3


def _make_icon() -> QIcon:
    """Génère une icône d'application avec un éclair."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(QFont("Segoe UI Emoji", 40))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "\u26a1")
    painter.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    """Fenêtre principale d'Accio Launcher."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Accio Launcher")
        self.resize(1200, 800)
        self.setWindowIcon(_make_icon())
        self.setStyleSheet(MAIN_STYLE)

        self.config = self._first_launch_or_load()
        self.manager = GameManager(self.config)

        self._build_menu()
        self._build_ui()
        self._populate_games()
        self.statusBar().showMessage("Prêt")

    # -------------------------------------------------------- Premier lancement

    @staticmethod
    def _first_launch_or_load() -> Config:
        """Dialogue de bienvenue au premier lancement, sinon charge la config."""
        if Config.exists():
            return Config.load()

        QMessageBox.information(
            None,
            "Bienvenue dans Accio Launcher !",
            "Bienvenue dans Accio Launcher !\n\n"
            "Veuillez choisir le dossier où les jeux seront installés.",
        )
        chosen = QFileDialog.getExistingDirectory(
            None,
            "Dossier d'installation des jeux",
            str(DEFAULT_INSTALL_PATH),
        )
        install_path = Path(chosen) if chosen else DEFAULT_INSTALL_PATH
        config = Config(
            install_path=install_path,
            cache_path=install_path / ".cache",
        )
        config.save()
        return config

    # -------------------------------------------------------- Menu

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        # --- Fichier ---
        file_menu = menu_bar.addMenu("Fichier")

        act_change_dir = QAction("Changer le dossier d'installation…", self)
        act_change_dir.triggered.connect(self._on_change_install_dir)
        file_menu.addAction(act_change_dir)

        act_open_dir = QAction("Ouvrir le dossier d'installation", self)
        act_open_dir.triggered.connect(self._on_open_install_dir)
        file_menu.addAction(act_open_dir)

        file_menu.addSeparator()

        act_quit = QAction("Quitter", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # --- Aide ---
        help_menu = menu_bar.addMenu("Aide")

        act_about = QAction("À propos d'Accio Launcher", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    def _on_change_install_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Changer le dossier d'installation",
            str(self.config.install_path),
        )
        if chosen:
            self.config.install_path = Path(chosen)
            self.config.cache_path = Path(chosen) / ".cache"
            self.config.save()
            self.statusBar().showMessage(f"Dossier d'installation : {chosen}")

    def _on_open_install_dir(self) -> None:
        path = self.config.install_path
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "À propos d'Accio Launcher",
            f"<h3>Accio Launcher v{APP_VERSION}</h3>"
            "<p>Launcher pour les jeux Harry Potter sur PC.</p>"
            "<p>Téléchargez, installez et lancez vos jeux "
            "préférés en un clic.</p>",
        )

    # -------------------------------------------------------- UI

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralContainer")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Header ---
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 24, 12)
        header_layout.setSpacing(4)

        title = QLabel("⚡ Accio Launcher")
        title.setObjectName("headerTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)

        subtitle = QLabel("Bibliothèque de jeux Harry Potter")
        subtitle.setObjectName("headerSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle)

        root_layout.addWidget(header)

        # --- Séparateur ---
        separator = QFrame()
        separator.setObjectName("headerSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        root_layout.addWidget(separator)

        # --- Scroll Area avec grille ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid_container.setObjectName("centralContainer")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(24, 16, 24, 24)
        self.grid_layout.setSpacing(16)

        scroll.setWidget(self.grid_container)
        root_layout.addWidget(scroll)

        # --- Barre de statut ---
        self.setStatusBar(QStatusBar())

    def _populate_games(self) -> None:
        """Charge les cartes de jeu dans la grille."""
        for i, entry in enumerate(self.manager.get_games()):
            card = GameCard(entry["game"], self.manager, parent=self.grid_container)
            card.status_message.connect(self.statusBar().showMessage)
            row, col = divmod(i, GRID_COLUMNS)
            self.grid_layout.addWidget(card, row, col, Qt.AlignmentFlag.AlignTop)

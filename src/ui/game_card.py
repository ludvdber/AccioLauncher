import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.downloader import Downloader
from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.core.installer import Installer

log = logging.getLogger(__name__)

COVER_WIDTH = 280
COVER_HEIGHT = 160
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"


def _format_size(size_mb: int) -> str:
    """Formate une taille en Mo ou Go."""
    if size_mb >= 1000:
        return f"{size_mb / 1000:.1f} Go"
    return f"{size_mb} Mo"


class GameCard(QFrame):
    """Carte visuelle d'un jeu avec actions contextuelles."""

    status_message = pyqtSignal(str)  # message pour la barre de statut

    def __init__(self, game: GameData, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        self.manager = manager
        self._downloader: Downloader | None = None
        self._installer: Installer | None = None

        self.setObjectName("gameCard")
        self.setFixedWidth(COVER_WIDTH + 24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        self._build_ui()
        self._refresh_state()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # -------------------------------------------------------------- Menu contextuel

    def _show_context_menu(self, pos) -> None:
        """Affiche le menu contextuel (clic droit) si le jeu n'est pas installé."""
        if self._current_state() != GameState.NOT_INSTALLED:
            return

        menu = QMenu(self)
        act_local = QAction("Installer depuis un fichier local…", self)
        act_local.triggered.connect(self._on_install_local)
        menu.addAction(act_local)
        menu.exec(self.mapToGlobal(pos))

    def _on_install_local(self) -> None:
        """Ouvre un sélecteur de fichier pour installer depuis une archive locale."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner une archive de jeu",
            "",
            "Archives (*.7z *.zip)",
        )
        if not path:
            return
        self.status_message.emit(f"Installation de {self.game.name} depuis un fichier local…")
        self._start_install(Path(path), delete_archive=False)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # --- Couverture ---
        self.cover = QLabel()
        self.cover.setFixedSize(COVER_WIDTH, COVER_HEIGHT)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background-color: #0f1626; border-radius: 8px;"
        )
        cover_path = ASSETS_DIR / self.game.cover_image
        if cover_path.exists():
            pix = QPixmap(str(cover_path)).scaled(
                COVER_WIDTH, COVER_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover.setPixmap(pix)
        else:
            placeholder = QLabel(self.game.name, self.cover)
            placeholder.setObjectName("placeholderText")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setWordWrap(True)
            ph_layout = QVBoxLayout(self.cover)
            ph_layout.addWidget(placeholder)

        layout.addWidget(self.cover)

        # --- Titre ---
        self.title_label = QLabel(self.game.name)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # --- Année / Développeur ---
        self.meta_label = QLabel(f"{self.game.year} — {self.game.developer}")
        self.meta_label.setObjectName("cardMeta")
        layout.addWidget(self.meta_label)

        # --- Description ---
        self.desc_label = QLabel(self.game.description)
        self.desc_label.setObjectName("cardDescription")
        self.desc_label.setWordWrap(True)
        self.desc_label.setMaximumHeight(50)
        layout.addWidget(self.desc_label)

        # --- Zone d'action (conteneur remplacé dynamiquement) ---
        self.action_container = QWidget()
        self.action_layout = QVBoxLayout(self.action_container)
        self.action_layout.setContentsMargins(0, 4, 0, 0)
        self.action_layout.setSpacing(4)
        layout.addWidget(self.action_container)

        layout.addStretch()

    # --------------------------------------------------------- État visuel

    def _refresh_state(self) -> None:
        """Met à jour la zone d'action selon l'état du jeu."""
        # Supprimer les anciens widgets
        while self.action_layout.count():
            item = self.action_layout.takeAt(0)
            if (w := item.widget()) is not None:
                w.deleteLater()

        state = self._current_state()

        match state:
            case GameState.NOT_INSTALLED:
                self._build_not_installed()
            case GameState.DOWNLOADING:
                self._build_downloading()
            case GameState.INSTALLING:
                self._build_installing()
            case GameState.INSTALLED:
                self._build_installed()

    def _current_state(self) -> GameState:
        games = self.manager.get_games()
        for entry in games:
            if entry["game"].id == self.game.id:
                return entry["state"]
        return GameState.NOT_INSTALLED

    # --- NOT_INSTALLED ---

    def _build_not_installed(self) -> None:
        size_label = QLabel(_format_size(self.game.archive_size_mb))
        size_label.setObjectName("cardSize")
        size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action_layout.addWidget(size_label)

        btn = QPushButton("Télécharger")
        btn.setObjectName("btnDownload")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_download)
        self.action_layout.addWidget(btn)

    # --- DOWNLOADING ---

    def _build_downloading(self) -> None:
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.action_layout.addWidget(self.progress_bar)

        self.download_label = QLabel("Téléchargement : 0%")
        self.download_label.setObjectName("downloadLabel")
        self.download_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action_layout.addWidget(self.download_label)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self._on_cancel_download)
        self.action_layout.addWidget(btn_cancel)

    # --- INSTALLING ---

    def _build_installing(self) -> None:
        self.install_bar = QProgressBar()
        self.install_bar.setRange(0, 100)
        self.install_bar.setValue(0)
        self.install_bar.setFormat("Installation… %p%")
        self.action_layout.addWidget(self.install_bar)

    # --- INSTALLED ---

    def _build_installed(self) -> None:
        btn_play = QPushButton("Jouer")
        btn_play.setObjectName("btnPlay")
        btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_play.clicked.connect(self._on_play)
        self.action_layout.addWidget(btn_play)

        btn_uninstall = QPushButton("Désinstaller")
        btn_uninstall.setObjectName("btnUninstall")
        btn_uninstall.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_uninstall.clicked.connect(self._on_uninstall)
        self.action_layout.addWidget(btn_uninstall)

    # ------------------------------------------------------- Actions

    def _on_download(self) -> None:
        self.manager.set_game_state(self.game.id, GameState.DOWNLOADING)
        self._refresh_state()
        self.status_message.emit(f"Téléchargement de {self.game.name}…")

        dest = self.manager.config.cache_path / self.game.archive_name
        self._downloader = Downloader(self.game.download_url, dest, parent=self)
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)
        self._downloader.start()

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            return
        pct = downloaded * 100 // total
        dl_str = _format_size(downloaded // (1024 * 1024))
        total_str = _format_size(total // (1024 * 1024))
        if hasattr(self, "progress_bar"):
            self.progress_bar.setValue(pct)
        if hasattr(self, "download_label"):
            self.download_label.setText(f"Téléchargement : {pct}% — {dl_str} / {total_str}")

    def _on_download_finished(self, archive_path_str: str) -> None:
        self._downloader = None
        self.status_message.emit(f"Installation de {self.game.name}…")
        self._start_install(Path(archive_path_str), delete_archive=True)

    def _on_download_error(self, message: str) -> None:
        self._downloader = None
        self.manager.set_game_state(self.game.id, GameState.NOT_INSTALLED)
        self._refresh_state()
        self.status_message.emit(f"Erreur : {message}")
        QMessageBox.warning(
            self,
            "Échec du téléchargement",
            "Le téléchargement a échoué.\n"
            "Vérifiez votre connexion internet et réessayez.",
        )

    def _on_cancel_download(self) -> None:
        if self._downloader is not None:
            self._downloader.cancel()
            self._downloader = None
        self.manager.set_game_state(self.game.id, GameState.NOT_INSTALLED)
        self._refresh_state()
        self.status_message.emit("Téléchargement annulé.")

    # --- Installation ---

    def _start_install(self, archive_path: Path, *, delete_archive: bool = True) -> None:
        self.manager.set_game_state(self.game.id, GameState.INSTALLING)
        self._refresh_state()

        dest = self.manager.config.install_path
        self._installer = Installer(
            archive_path,
            dest,
            registry_entries=list(self.game.post_install.registry),
            delete_archive=delete_archive,
            parent=self,
        )
        self._installer.progress.connect(self._on_install_progress)
        self._installer.finished.connect(self._on_install_finished)
        self._installer.error.connect(self._on_install_error)
        self._installer.start()

    def _on_install_progress(self, pct: int) -> None:
        if hasattr(self, "install_bar"):
            self.install_bar.setValue(pct)

    def _on_install_finished(self, _path: str) -> None:
        self._installer = None
        self.manager.set_game_state(self.game.id, GameState.INSTALLED)
        self._refresh_state()
        self.status_message.emit(f"{self.game.name} installé avec succès !")

    def _on_install_error(self, message: str) -> None:
        self._installer = None
        self.manager.set_game_state(self.game.id, GameState.NOT_INSTALLED)
        self._refresh_state()
        self.status_message.emit(f"Erreur d'installation : {message}")
        QMessageBox.warning(
            self,
            "Échec de l'installation",
            "L'installation a échoué.\n"
            "L'archive est peut-être corrompue. Réessayez le téléchargement.",
        )

    # --- Jouer / Désinstaller ---

    def _on_play(self) -> None:
        if self.manager.launch_game(self.game.id):
            self.status_message.emit(f"Lancement de {self.game.name}…")
        else:
            self.status_message.emit("Impossible de lancer le jeu.")

    def _on_uninstall(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmer la désinstallation",
            f"Voulez-vous vraiment désinstaller {self.game.name} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.uninstall_game(self.game.id)
            self._refresh_state()
            self.status_message.emit(f"{self.game.name} désinstallé.")

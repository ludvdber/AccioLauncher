"""Contrôleur des opérations de jeu — téléchargement, installation, mise à jour."""

import logging
import shutil
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.downloader import Downloader
from src.core.game_data import GameData, GameVersion
from src.core.game_manager import GameManager, GameState
from src.core.installer import Installer
from src.ui.speed_tracker import SpeedTracker

log = logging.getLogger(__name__)


class GameOperations(QObject):
    """Orchestre le téléchargement et l'installation des jeux.

    Gère le cycle : download → install → post-install patches.
    Communique avec la vue via des signaux Qt.
    """

    # Progression téléchargement : (octets téléchargés, octets total, vitesse bytes/s, eta secondes)
    download_progress = pyqtSignal(int, int, float, float)
    # Progression installation : pourcentage 0-100
    install_progress = pyqtSignal(int)
    # Info multi-parts : (part courante, total)
    part_info = pyqtSignal(int, int)
    # Opération terminée avec succès
    operation_finished = pyqtSignal(object)  # GameData
    # Erreur pendant l'opération
    operation_error = pyqtSignal(str, str)  # (titre, message)
    # État d'un jeu a changé (pour rafraîchir l'UI)
    state_changed = pyqtSignal()
    # Message de statut
    status_message = pyqtSignal(str)

    def __init__(self, manager: GameManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._downloader: Downloader | None = None
        self._installer: Installer | None = None
        self._speed_tracker = SpeedTracker()
        self._target_version: GameVersion | None = None
        self._active_game: GameData | None = None

    @property
    def is_busy(self) -> bool:
        """True si un téléchargement ou une installation est en cours."""
        return self._downloader is not None or self._installer is not None

    @property
    def active_game(self) -> GameData | None:
        return self._active_game

    # ──────────────────── Téléchargement ────────────────────

    def check_disk_space(self, version: GameVersion) -> int | None:
        """Vérifie l'espace disque. Retourne les Mo libres si insuffisant, None si OK."""
        needed_mb = version.size_mb * 2
        try:
            free_mb = shutil.disk_usage(self._manager.config.install_path).free // (1024 * 1024)
        except OSError:
            return None  # skip check
        return int(free_mb) if free_mb < needed_mb else None

    def download(self, game: GameData, version: GameVersion) -> None:
        """Lance le téléchargement d'une version de jeu."""
        if self.is_busy:
            self.status_message.emit("Un téléchargement ou installation est déjà en cours.")
            return

        self._target_version = version
        self._active_game = game
        self._manager.set_game_state(game.id, GameState.DOWNLOADING)
        self._speed_tracker.reset()
        self.state_changed.emit()
        self.status_message.emit(f"Téléchargement de {game.name} v{version.version}\u2026")

        archive_name = f"{game.id}_v{version.version}.7z"
        dest = self._manager.config.cache_path / archive_name
        self._downloader = Downloader(
            url=version.download_url, destination=dest,
            parts=version.download_parts, parent=self,
        )
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)
        if version.download_parts:
            self._downloader.part_info.connect(self._on_part_info)
        self._downloader.start()

    def cancel_download(self) -> None:
        """Annule le téléchargement en cours."""
        dest: Path | None = None
        if self._downloader is not None:
            dest = self._downloader.destination
            self._downloader.progress.disconnect(self._on_download_progress)
            self._downloader.finished.disconnect(self._on_download_finished)
            self._downloader.error.disconnect(self._on_download_error)
            try:
                self._downloader.part_info.disconnect(self._on_part_info)
            except TypeError:
                pass
            self._downloader.cancel()
            self._downloader = None
        # Nettoyer le fichier .part résiduel
        if dest is not None:
            part_path = dest.with_suffix(dest.suffix + ".part")
            part_path.unlink(missing_ok=True)
        game = self._active_game
        self._active_game = None
        self._target_version = None
        if game is not None:
            self._manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        self.state_changed.emit()
        self.status_message.emit("Téléchargement annulé.")

    def cancel_all(self) -> None:
        """Annule toute opération en cours (appelé à la fermeture)."""
        if self._downloader is not None:
            self._downloader.cancel()
            self._downloader.wait(3000)
        if self._installer is not None:
            self._installer.cancel()
            self._installer.wait(3000)

    # ──────────────────── Installation ────────────────────

    def install(self, game: GameData, archive_path: Path, *, delete_archive: bool = True) -> None:
        """Lance l'installation d'un jeu depuis une archive."""
        self._active_game = game
        self._manager.set_game_state(game.id, GameState.INSTALLING)
        self.state_changed.emit()

        dest = self._manager.config.install_path
        config_files = [
            (cf.source, cf.destination)
            for cf in game.post_install.config_files
        ]
        game_dir = Path(game.executable).parts[0] if game.executable else None
        self._installer = Installer(
            archive_path, dest,
            registry_entries=list(game.post_install.registry),
            config_files=config_files,
            game_dir=game_dir,
            delete_archive=delete_archive, parent=self,
        )
        self._installer.progress.connect(self._on_install_progress)
        self._installer.finished.connect(self._on_install_finished)
        self._installer.error.connect(self._on_install_error)
        self._installer.start()

    # ──────────────────── Version switch ────────────────────

    def switch_version(self, game: GameData, version: GameVersion) -> None:
        """Désinstalle la version actuelle si installée, puis télécharge la nouvelle."""
        if self.is_busy:
            self.status_message.emit("Un téléchargement ou installation est déjà en cours.")
            return
        if self._manager.is_installed(game.id):
            self._manager.uninstall_game(game.id)
        self.download(game, version)

    # ──────────────────── Callbacks téléchargement ────────────────────

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            return
        self._speed_tracker.update(downloaded)
        if not self._speed_tracker.should_update_ui():
            return
        self.download_progress.emit(
            downloaded, total,
            self._speed_tracker.speed,
            self._speed_tracker.eta(downloaded, total),
        )

    def _on_download_finished(self, archive_path_str: str) -> None:
        self._downloader = None
        game = self._active_game
        if game is None:
            return
        self.status_message.emit(f"Installation de {game.name}\u2026")
        self.install(game, Path(archive_path_str),
                     delete_archive=self._manager.config.delete_archives)

    def _on_download_error(self, message: str) -> None:
        self._downloader = None
        game = self._active_game
        self._active_game = None
        self._target_version = None
        if game is not None:
            self._manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        self.state_changed.emit()
        self.status_message.emit(f"Erreur : {message}")
        self.operation_error.emit(
            "Échec du téléchargement",
            "Le téléchargement a échoué.\nVérifiez votre connexion internet et réessayez.",
        )

    def _on_part_info(self, current: int, total: int) -> None:
        self.part_info.emit(current, total)

    # ──────────────────── Callbacks installation ────────────────────

    def _on_install_progress(self, pct: int) -> None:
        self.install_progress.emit(pct)

    def _on_install_finished(self, _path: str) -> None:
        self._installer = None
        game = self._active_game
        self._active_game = None
        if game is None:
            return

        exe_path = self._manager.config.install_path / game.executable
        if not exe_path.exists():
            log.warning("Exécutable introuvable après extraction : %s", exe_path)
            self._manager.set_game_state(game.id, GameState.NOT_INSTALLED)
            self.state_changed.emit()
            self.status_message.emit("Installation incomplète.")
            self.operation_error.emit(
                "Installation incomplète",
                "L'installation semble incomplète : l'exécutable du jeu est introuvable.\n"
                "L'archive est peut-être corrompue.",
            )
            return

        self._manager.apply_pre_launch_patches(game)
        self._manager.set_game_state(game.id, GameState.INSTALLED)
        target_ver = self._target_version
        self._target_version = None
        self._manager.save_installed_version(game.id, target_ver.version if target_ver else None)
        self.state_changed.emit()
        self.status_message.emit(f"{game.name} installé avec succès !")
        self.operation_finished.emit(game)

    def _on_install_error(self, message: str) -> None:
        self._installer = None
        game = self._active_game
        self._active_game = None
        self._target_version = None
        if game is not None:
            self._manager.set_game_state(game.id, GameState.NOT_INSTALLED)
        self.state_changed.emit()
        self.status_message.emit(f"Erreur d'installation : {message}")
        self.operation_error.emit(
            "Échec de l'installation",
            "L'installation a échoué.\nL'archive est peut-être corrompue. Réessayez le téléchargement.",
        )

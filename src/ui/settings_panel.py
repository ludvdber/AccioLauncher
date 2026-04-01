import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.config import APP_VERSION, Config
from src.core.game_manager import GameManager, GameState
from src.core.formatting import format_bytes
from src.ui.toggle_switch import toggle_row


class _DiskScanWorker(QThread):
    """Calcule la taille des jeux installés en arrière-plan."""
    result = pyqtSignal(int, int)  # (count, total_bytes)

    def __init__(self, game_paths: list[Path], parent=None) -> None:
        super().__init__(parent)
        self._game_paths = game_paths

    def run(self) -> None:
        count = len(self._game_paths)
        total_bytes = 0
        for game_path in self._game_paths:
            if game_path.exists():
                try:
                    total_bytes += sum(
                        f.stat().st_size for f in game_path.rglob("*") if f.is_file()
                    )
                except OSError:
                    pass
        self.result.emit(count, total_bytes)


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

    def __init__(self, config: Config, manager: GameManager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.manager = manager
        self.setWindowTitle("Paramètres")
        self.setMinimumWidth(480)
        self.setStyleSheet(self._style())
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
            color: #d4a017;
            padding-top: 12px;
        }
        QLabel#subtitle {
            font-size: 12px;
            color: #b0b0b0;
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
            border-color: #d4a017;
        }
        QPushButton#btnClose {
            background-color: #d4a017;
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

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── Titre
        title = QLabel("\u2699 Paramètres")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        # ── Dossier d'installation
        layout.addWidget(self._section("Dossier d'installation"))

        path_row = QHBoxLayout()
        self._path_label = QLabel(str(self.config.install_path))
        self._path_label.setStyleSheet("color: #b0b0b0; font-size: 13px;")
        self._path_label.setWordWrap(True)
        path_row.addWidget(self._path_label, stretch=1)

        btn_open = QPushButton("Ouvrir")
        btn_open.setObjectName("btnPath")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self._on_open_install_folder)
        path_row.addWidget(btn_open)

        btn_change = QPushButton("Changer…")
        btn_change.setObjectName("btnPath")
        btn_change.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_change.clicked.connect(self._on_change_path)
        path_row.addWidget(btn_change)
        layout.addLayout(path_row)

        self._free_label = QLabel(f"Espace libre : {_disk_free(self.config.install_path)}")
        self._free_label.setObjectName("subtitle")
        layout.addWidget(self._free_label)

        # ── Jeux installés (calcul asynchrone)
        self._installed_label = QLabel("Calcul de l'espace utilisé…")
        self._installed_label.setObjectName("subtitle")
        layout.addWidget(self._installed_label)

        # Snapshot des chemins sur le thread principal (thread-safe)
        game_paths = [
            self.manager.get_game_path(entry.game.id)
            for entry in self.manager.get_games()
            if entry.state == GameState.INSTALLED
        ]
        game_paths = [p for p in game_paths if p is not None]

        self._scan_worker = _DiskScanWorker(game_paths, parent=self)
        self._scan_worker.result.connect(self._on_scan_done)
        self._scan_worker.start()

        # ── Téléchargement
        layout.addWidget(self._section("Téléchargement"))

        row, self._tgl_delete = toggle_row("Supprimer les archives après installation", self.config.delete_archives)
        self._tgl_delete.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        row, self._tgl_resume = toggle_row("Reprendre les téléchargements interrompus", self.config.resume_downloads)
        self._tgl_resume.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        row, self._tgl_updates = toggle_row("Vérifier les mises à jour au démarrage", self.config.check_updates)
        self._tgl_updates.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        # ── Affichage
        layout.addWidget(self._section("Affichage"))

        row, self._tgl_autoplay = toggle_row("Lecture automatique des vidéos", self.config.autoplay_videos)
        self._tgl_autoplay.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        row, self._tgl_mute = toggle_row("Couper le son des vidéos", self.config.mute_videos)
        self._tgl_mute.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        # ── Mises à jour
        layout.addWidget(self._section("Mises à jour"))

        # Versions actuelles
        cat_ver = self.manager.catalog.catalog_version
        self._versions_label = QLabel(
            f"Launcher v{APP_VERSION}  ·  Catalogue v{cat_ver}"
        )
        self._versions_label.setObjectName("subtitle")
        layout.addWidget(self._versions_label)

        # Boutons d'action
        update_row = QHBoxLayout()
        update_row.setSpacing(10)

        btn_catalog = QPushButton("Actualiser le catalogue")
        btn_catalog.setObjectName("btnPath")
        btn_catalog.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_catalog.clicked.connect(self._on_refresh_catalog)
        update_row.addWidget(btn_catalog)

        btn_launcher = QPushButton("Vérifier les mises à jour")
        btn_launcher.setObjectName("btnPath")
        btn_launcher.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_launcher.clicked.connect(self._on_check_launcher)
        update_row.addWidget(btn_launcher)

        update_row.addStretch()
        layout.addLayout(update_row)

        self._update_status = QLabel("")
        self._update_status.setObjectName("subtitle")
        self._update_status.setWordWrap(True)
        self._update_status.hide()
        layout.addWidget(self._update_status)

        # ── À propos
        layout.addWidget(self._section("À propos"))

        about_text = QLabel("Launcher pour les jeux Harry Potter sur PC.")
        about_text.setObjectName("subtitle")
        about_text.setWordWrap(True)
        layout.addWidget(about_text)

        about_row = QHBoxLayout()
        about_row.setSpacing(10)

        btn_discord = QPushButton("Rejoindre le Discord")
        btn_discord.setObjectName("btnPath")
        btn_discord.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_discord.clicked.connect(self._on_discord)
        about_row.addWidget(btn_discord)

        about_row.addStretch()
        layout.addLayout(about_row)

        layout.addStretch()

        # ── Bouton fermer
        btn_close = QPushButton("Fermer")
        btn_close.setObjectName("btnClose")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignCenter)

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _on_scan_done(self, count: int, total_bytes: int) -> None:
        """Callback quand le scan disque en arrière-plan est terminé."""
        self._installed_label.setText(
            f"{count} jeu(x) installé(s) — {format_bytes(total_bytes)} utilisés"
        )
        log.info("Total installé : %d jeu(x), %s", count, format_bytes(total_bytes))

    def _on_change_path(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Changer le dossier d'installation", str(self.config.install_path)
        )
        if chosen:
            self.config.install_path = Path(chosen)
            self.config.cache_path = Path(chosen) / ".cache"
            self._path_label.setText(chosen)
            self._free_label.setText(f"Espace libre : {_disk_free(Path(chosen))}")
            self._save()

    def _on_setting_changed(self) -> None:
        self.config.delete_archives = self._tgl_delete.isChecked()
        self.config.resume_downloads = self._tgl_resume.isChecked()
        self.config.check_updates = self._tgl_updates.isChecked()
        self.config.autoplay_videos = self._tgl_autoplay.isChecked()
        self.config.mute_videos = self._tgl_mute.isChecked()
        self._save()

    def closeEvent(self, event) -> None:
        self._scan_worker.blockSignals(True)
        try:
            self._scan_worker.result.disconnect(self._on_scan_done)
        except TypeError:
            pass
        if self._scan_worker.isRunning():
            self._scan_worker.wait(2000)
        super().closeEvent(event)

    def _on_open_install_folder(self) -> None:
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config.install_path)))

    @staticmethod
    def _on_discord() -> None:
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("https://discord.gg/TNwDQd7KGe"))

    def _on_refresh_catalog(self) -> None:
        self._update_status.setText("Actualisation du catalogue…")
        self._update_status.setStyleSheet("color: #d4a017;")
        self._update_status.show()
        self.force_catalog_refresh.emit()

    def _on_check_launcher(self) -> None:
        self._update_status.setText("Vérification des mises à jour…")
        self._update_status.setStyleSheet("color: #d4a017;")
        self._update_status.show()
        self.force_launcher_check.emit()

    def update_catalog_version(self, version: str) -> None:
        """Met à jour l'affichage de la version du catalogue après un refresh."""
        self._versions_label.setText(
            f"Launcher v{APP_VERSION}  ·  Catalogue v{version}"
        )
        self._update_status.setText(f"Catalogue mis à jour en v{version}")
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

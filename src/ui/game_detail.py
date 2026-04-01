"""Vue détaillée d'un jeu — orchestre les sous-panneaux et gère les interactions."""

import logging
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QUrl, QTimer, pyqtSignal, QPointF,
)
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog, QGraphicsOpacityEffect, QMenu, QMessageBox,
    QPushButton, QSlider, QHBoxLayout, QWidget,
)

from src.ui.action_panel import ActionPanel
from src.ui.background_widget import BackgroundWidget
from src.ui.game_operations import GameOperations
from src.ui.info_panel import InfoPanel
from src.core.formatting import format_size
from src.ui.video_player import VideoPlayer
from src.ui.versions_dialog import VersionsDialog

from src.core.config import ASSETS_DIR
from src.core.game_data import GameData, GameVersion
from src.core.game_manager import GameManager, GameState

log = logging.getLogger(__name__)

_MUTE_ON = "\U0001f507"
_MUTE_OFF = "\U0001f50a"


class GameDetailView(QWidget):
    """Zone centrale : fond + info panel + action panel + vidéo."""

    status_message = pyqtSignal(str)
    state_changed = pyqtSignal()
    game_launched = pyqtSignal(object, str)  # (subprocess.Popen, game_name)

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.game: GameData | None = None

        # Sous-systèmes
        self._video = VideoPlayer(self)
        self._ops = GameOperations(manager, self)

        self._build_ui(manager)
        self._connect_signals()

    # ──────────────────── Construction ────────────────────

    def _build_ui(self, manager: GameManager) -> None:
        self._bg = BackgroundWidget(self)

        # Info panel (titre, meta, description, tags)
        self._info = InfoPanel(manager, self)

        # Action panel (boutons jouer/télécharger/désinstaller)
        self._action_panel = ActionPanel(manager, self)
        self._info.add_bottom_widget(self._action_panel)
        self._info.add_stretch()

        # Audio bar
        self._audio_bar = self._build_audio_bar()

        # Animations fade
        self._fade_anim = QPropertyAnimation(self._bg, b"bg_opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._info_opacity = QGraphicsOpacityEffect(self._info)
        self._info_opacity.setOpacity(1.0)
        self._info.setGraphicsEffect(self._info_opacity)
        self._info_fade = QPropertyAnimation(self._info_opacity, b"opacity")
        self._info_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _build_audio_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setStyleSheet("QWidget { background: rgba(0,0,0,0.55); border-radius: 14px; }")
        bar.setFixedSize(160, 32)
        bar.hide()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self._btn_mute = QPushButton(_MUTE_OFF)
        self._btn_mute.setFixedSize(26, 26)
        self._btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mute.setStyleSheet(
            "QPushButton { background: transparent; color: #eaeaea; border: none; font-size: 15px; }"
            "QPushButton:hover { color: #d4a017; }"
        )
        self._btn_mute.clicked.connect(self._on_mute_clicked)
        layout.addWidget(self._btn_mute)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(25)
        self._volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._volume_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: rgba(255,255,255,0.12); height: 4px; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #d4a017; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: rgba(212,160,23,0.5); border-radius: 2px; }"
        )
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self._volume_slider)
        return bar

    def _connect_signals(self) -> None:
        # Vidéo
        self._video.video_frame.connect(self._bg.set_video_frame)
        self._video.playback_ended.connect(self._on_video_ended)

        # Opérations → action panel (progression)
        self._ops.download_progress.connect(self._action_panel.update_download_progress)
        self._ops.install_progress.connect(self._action_panel.update_install_progress)
        self._ops.part_info.connect(self._action_panel.update_part_info)
        self._ops.operation_finished.connect(self._on_operation_finished)
        self._ops.operation_error.connect(self._deferred_warning)
        self._ops.state_changed.connect(self._on_ops_state_changed)
        self._ops.status_message.connect(self.status_message)

        # Action panel → handlers
        self._action_panel.download_clicked.connect(self._on_download)
        self._action_panel.cancel_clicked.connect(self._on_cancel_download)
        self._action_panel.play_clicked.connect(self._on_play)
        self._action_panel.uninstall_clicked.connect(self._on_uninstall)
        self._action_panel.update_clicked.connect(self._on_update_clicked)

        # Info panel
        self._info.versions_clicked.connect(self._on_versions_clicked)

        # Menu contextuel
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ──────────────────── Positionnement ────────────────────

    def _position_info(self) -> None:
        w, h = self.width(), self.height()
        info_w = min(650, int(w * 0.50))
        info_top = int(h * 0.22)
        self._info.setGeometry(0, info_top, info_w, h - info_top - 20)

    def resizeEvent(self, event) -> None:
        self._bg.setGeometry(self.rect())
        self._bg.invalidate_cache()
        self._position_info()
        self._audio_bar.move(self.width() - 174, self.height() - 46)
        self._audio_bar.raise_()

    # ──────────────────── Changement de jeu ────────────────────

    def update_game_data(self, game: GameData) -> None:
        self.game = game
        self._refresh()

    def set_game(self, game: GameData) -> None:
        if self.game and self.game.id == game.id:
            self._refresh()
            return
        self._stop_video()
        self._fade_anim.stop()
        self._info_fade.stop()
        self._bg._set_bg_opacity(0.0)
        self._info_opacity.setOpacity(0.0)
        self._apply_game(game)

    def _apply_game(self, game: GameData) -> None:
        self.game = game
        self._info.apply_game(game)

        # Background
        self._bg.set_image(ASSETS_DIR / "backgrounds" / f"{game.id}_bg.jpg")
        if self.manager.config.autoplay_videos:
            self._try_play_video(game.id)

        self._refresh()

        # Fade-in background
        current = self._bg.bg_opacity
        self._fade_anim.setStartValue(current)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setDuration(max(int(400 * (1.0 - current)), 80))
        self._fade_anim.start()
        self._bg.start_zoom_loop()

        # Fade-in info
        self._info.show()
        self._position_info()
        self._info_fade.stop()
        self._info_fade.setStartValue(0.0)
        self._info_fade.setEndValue(1.0)
        self._info_fade.setDuration(500)
        self._info_fade.start()

    def _refresh(self) -> None:
        """Rafraîchit le panneau d'actions."""
        self._action_panel.set_game(self.game)
        self._action_panel.refresh()

    # ──────────────────── Parallaxe ────────────────────

    def handle_mouse_move(self, pos: QPointF) -> None:
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return
        self._bg.set_parallax_target(pos.x(), pos.y(), float(w), float(h))

    # ──────────────────── Vidéo ────────────────────

    def _try_play_video(self, game_id: str) -> None:
        video_path = ASSETS_DIR / "videos" / f"{game_id}_video.mp4"
        if not video_path.exists():
            self._audio_bar.hide()
            return
        muted = self.manager.config.mute_videos
        if self._video.play(str(video_path), muted=muted, volume=self._volume_slider.value() / 100.0):
            self._btn_mute.setText(_MUTE_ON if muted else _MUTE_OFF)
            self._audio_bar.show()
            self._audio_bar.raise_()
        else:
            self._audio_bar.hide()

    def _stop_video(self) -> None:
        self._video.stop()
        self._bg.clear_video()
        self._audio_bar.hide()

    def _on_video_ended(self) -> None:
        self._bg.clear_video()
        self._audio_bar.hide()

    def _on_mute_clicked(self) -> None:
        self._btn_mute.setText(_MUTE_ON if self._video.toggle_mute() else _MUTE_OFF)

    def _on_volume_changed(self, value: int) -> None:
        self._video.set_volume(value)
        if not self._video.muted:
            self._btn_mute.setText(_MUTE_OFF)

    # ──────────────────── API publique ────────────────────

    def pause(self) -> None:
        self._stop_video()
        self._bg.pause()

    def resume(self) -> None:
        self._bg.resume()

    def cancel_operations(self) -> None:
        self._ops.cancel_all()

    # ──────────────────── Callbacks opérations ────────────────────

    def _on_ops_state_changed(self) -> None:
        self._refresh()
        self.state_changed.emit()

    def _on_operation_finished(self, game: GameData) -> None:
        if self.game and self.game.id == game.id:
            self._refresh()
        self.state_changed.emit()

    def _deferred_warning(self, title: str, message: str) -> None:
        def _show() -> None:
            try:
                self.isVisible()
            except RuntimeError:
                return
            QMessageBox.warning(self, title, message)
        QTimer.singleShot(0, _show)

    # ──────────────────── Handlers utilisateur ────────────────────

    def _on_download(self, version: GameVersion | None = None) -> None:
        if self.game is None or self._ops.is_busy:
            return
        ver = version or self.game.current_download
        if ver is None:
            self.status_message.emit("Aucune version disponible.")
            return
        free_mb = self._ops.check_disk_space(ver)
        if free_mb is not None:
            QMessageBox.warning(
                self, "Espace disque insuffisant",
                f"Il faut environ {format_size(ver.size_mb * 2)} d'espace libre.\n"
                f"Actuellement {format_size(free_mb)} disponibles.",
            )
            return
        self._ops.download(self.game, ver)
        self._refresh()

    def _on_cancel_download(self) -> None:
        self._ops.cancel_download()
        self._refresh()

    def _on_play(self) -> None:
        if self.game is None:
            return
        self._stop_video()
        try:
            proc = self.manager.launch_game(self.game.id)
        except RuntimeError as exc:
            if "vcredist_x86_missing" in str(exc):
                reply = QMessageBox.warning(
                    self, "Visual C++ manquant",
                    "Le Visual C++ Redistributable x86 (2015-2022) n'est pas installé.\n"
                    "Il est nécessaire pour lancer les jeux.\n\n"
                    "Voulez-vous ouvrir la page de téléchargement ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    from PyQt6.QtGui import QDesktopServices
                    QDesktopServices.openUrl(QUrl("https://aka.ms/vs/17/release/vc_redist.x86.exe"))
            else:
                log.error("Erreur au lancement : %s", exc)
                self.status_message.emit("Impossible de lancer le jeu.")
            return
        except OSError as exc:
            log.error("Impossible de lancer %s : %s", self.game.name, exc)
            self.status_message.emit("Impossible de lancer le jeu.")
            return
        if proc is not None:
            self.status_message.emit(f"Lancement de {self.game.name}\u2026")
            self.game_launched.emit(proc, self.game.name)
        else:
            self.status_message.emit("Impossible de lancer le jeu.")

    def _on_uninstall(self) -> None:
        if self.game is None:
            return
        reply = QMessageBox.question(
            self, "Confirmer la désinstallation",
            f"Voulez-vous vraiment désinstaller {self.game.name} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            has_config = bool(self.game.post_install.config_files)
            self.manager.uninstall_game(self.game.id)
            self._refresh()
            self.state_changed.emit()
            if has_config:
                QMessageBox.information(
                    self, "Sauvegardes conservées",
                    "Les sauvegardes et la configuration dans Mes Documents ont été conservées.",
                )
            self.status_message.emit(f"{self.game.name} désinstallé.")

    def _on_update_clicked(self) -> None:
        if self.game is None:
            return
        ver = self.game.get_version(self.game.recommended_version)
        if ver is None:
            return
        installed = self.manager.installed_version(self.game.id) or "?"
        changes = "\n".join(f"• {c}" for c in ver.changes)
        reply = QMessageBox.question(
            self, "Mise à jour disponible",
            f"Mettre à jour de v{installed} vers v{ver.version} ?\n\n"
            f"Changements :\n{changes}\n\n"
            f"La version actuelle sera supprimée avant l'installation.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._ops.switch_version(self.game, ver)

    def _on_install_specific_version(self, game_id: str, version: str) -> None:
        if self.game is None or self.game.id != game_id:
            return
        ver = self.game.get_version(version)
        if ver is not None:
            self._ops.switch_version(self.game, ver)

    def _on_versions_clicked(self) -> None:
        if self.game is not None:
            dlg = VersionsDialog(self.game, self.manager, self)
            dlg.install_version.connect(self._on_install_specific_version)
            dlg.exec()

    def _on_install_local(self) -> None:
        if self.game is None or self._ops.is_busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner une archive de jeu", "", "Archives (*.7z *.zip)",
        )
        if not path:
            return
        self.status_message.emit(f"Installation de {self.game.name} depuis un fichier local\u2026")
        self._ops.install(self.game, Path(path), delete_archive=False)
        self._refresh()

    # ──────────────────── Menu contextuel ────────────────────

    def _show_context_menu(self, pos) -> None:
        if self.game is None:
            return
        menu = QMenu(self)
        act_versions = QAction("Gérer les versions", self)
        act_versions.triggered.connect(self._on_versions_clicked)
        menu.addAction(act_versions)
        if self.manager.get_state(self.game.id) == GameState.NOT_INSTALLED:
            act_local = QAction("Installer depuis un fichier local\u2026", self)
            act_local.triggered.connect(self._on_install_local)
            menu.addAction(act_local)
        menu.exec(self.mapToGlobal(pos))

    def trigger_primary_action(self) -> None:
        if self.game is None:
            return
        match self.manager.get_state(self.game.id):
            case GameState.NOT_INSTALLED:
                self._on_download()
            case GameState.INSTALLED:
                self._on_play()

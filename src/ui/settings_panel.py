import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush
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


class ToggleSwitch(QWidget):
    """Interrupteur animé ON/OFF."""

    toggled = pyqtSignal(bool)

    _TRACK_W = 40
    _TRACK_H = 22
    _KNOB_R = 8   # rayon du cercle

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._knob_x = float(self._TRACK_W - 12 if checked else 12)
        self.setFixedSize(self._TRACK_W, self._TRACK_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"knob_x")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    # -- Propriété animable --
    def _get_knob_x(self) -> float:
        return self._knob_x

    def _set_knob_x(self, val: float) -> None:
        self._knob_x = val
        self.update()

    knob_x = pyqtProperty(float, _get_knob_x, _set_knob_x)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool) -> None:
        if val == self._checked:
            return
        self._checked = val
        self._animate()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._animate()
            self.toggled.emit(self._checked)

    def _animate(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(float(self._TRACK_W - 12 if self._checked else 12))
        self._anim.start()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Piste
        track_color = QColor("#d4a017") if self._checked else QColor("#2c3e6b")
        p.setBrush(QBrush(track_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, self._TRACK_W, self._TRACK_H), 11, 11)
        # Cercle
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QRectF(self._knob_x - self._KNOB_R, (self._TRACK_H - 2 * self._KNOB_R) / 2,
                              2 * self._KNOB_R, 2 * self._KNOB_R))
        p.end()


def _toggle_row(label_text: str, checked: bool) -> tuple[QWidget, ToggleSwitch]:
    """Crée une ligne [toggle] [label] et renvoie le widget-ligne + le toggle."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(12)
    toggle = ToggleSwitch(checked)
    lay.addWidget(toggle)
    lbl = QLabel(label_text)
    lbl.setStyleSheet("color: #ffffff; font-size: 13px; background: transparent;")
    lay.addWidget(lbl, stretch=1)
    return row, toggle


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


def _format_size_bytes(b: int) -> str:
    """Formate des octets en Mo ou Go."""
    mb = b / (1024 * 1024)
    if mb >= 1000:
        return f"{mb / 1000:.1f} Go"
    return f"{mb:.0f} Mo"


def _disk_free(path: Path) -> str:
    try:
        usage = shutil.disk_usage(path)
        return _format_size_bytes(usage.free)
    except OSError:
        return "?"


class SettingsDialog(QDialog):
    """Panneau de paramètres Accio Launcher."""

    config_changed = pyqtSignal()

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
            self.manager.get_game_path(entry["game"].id)
            for entry in self.manager.get_games()
            if entry["state"] == GameState.INSTALLED
        ]
        game_paths = [p for p in game_paths if p is not None]

        self._scan_worker = _DiskScanWorker(game_paths, parent=self)
        self._scan_worker.result.connect(self._on_scan_done)
        self._scan_worker.start()

        # ── Téléchargement
        layout.addWidget(self._section("Téléchargement"))

        row, self._tgl_delete = _toggle_row("Supprimer les archives après installation", self.config.delete_archives)
        self._tgl_delete.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        row, self._tgl_resume = _toggle_row("Reprendre les téléchargements interrompus", self.config.resume_downloads)
        self._tgl_resume.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        row, self._tgl_updates = _toggle_row("Vérifier les mises à jour au démarrage", self.config.check_updates)
        self._tgl_updates.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        # ── Affichage
        layout.addWidget(self._section("Affichage"))

        row, self._tgl_autoplay = _toggle_row("Lecture automatique des vidéos", self.config.autoplay_videos)
        self._tgl_autoplay.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        row, self._tgl_mute = _toggle_row("Couper le son des vidéos", self.config.mute_videos)
        self._tgl_mute.toggled.connect(self._on_setting_changed)
        layout.addWidget(row)

        # ── À propos
        layout.addWidget(self._section("À propos"))

        self._about_text = QLabel(
            f"Accio Launcher v{APP_VERSION}\n"
            "Launcher pour les jeux Harry Potter sur PC."
        )
        self._about_text.setObjectName("subtitle")
        self._about_text.setWordWrap(True)
        layout.addWidget(self._about_text)

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
            f"{count} jeu(x) installé(s) — {_format_size_bytes(total_bytes)} utilisés"
        )
        log.info("Total installé : %d jeu(x), %s", count, _format_size_bytes(total_bytes))

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
        if self._scan_worker.isRunning():
            self._scan_worker.wait(2000)
        super().closeEvent(event)

    def _save(self) -> None:
        self.config.save()
        self.config_changed.emit()

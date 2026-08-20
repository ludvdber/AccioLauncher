"""Barre de progression persistante en bas de la fenêtre, visible pendant les téléchargements."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from src.core.config import ASSETS_DIR
from src.core.formatting import append_part_info, format_progress_line
from src.core.game_data import GameData
from src.core.game_manager import GameState
from src.core.i18n import tr
from src.ui.fonts import body_font, cinzel
from src.ui.theme import themed

# Étapes affichées par le stepper (clé interne → libellé tr())
_PHASES = ("download", "verify", "install", "finalize")
# Phases sans progression chiffrée → barre indéterminée le temps qu'elles durent.
_INDETERMINATE_PHASES = ("verify", "finalize")


class DownloadBar(QWidget):
    """Barre de progression visible globalement pendant un téléchargement/installation."""

    cancel_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("downloadBar")
        self.setFixedHeight(56)
        self.setStyleSheet(themed(
            "#downloadBar { background: rgba(10, 10, 20, 0.92); "
            "border-top: 1px solid rgba(214,167,44,0.3); }"
        ))
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)

        self._cover = QLabel()
        self._cover.setFixedSize(40, 56)
        self._cover.setStyleSheet("background: transparent;")
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._cover)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("")
        self._title.setFont(cinzel(11, bold=True))
        self._title.setStyleSheet("color: #e0e0e0; background: transparent;")
        self._status = QLabel("")
        self._status.setFont(body_font(10))
        self._status.setStyleSheet("color: #8a8aaa; background: transparent;")
        text_box.addWidget(self._title)
        text_box.addWidget(self._status)
        layout.addLayout(text_box, stretch=1)

        # Stepper « 1/3 · Téléchargement » → « 2/3 · Vérification » → « 3/3 · Installation »
        self._phase_label = QLabel("")
        self._phase_label.setFont(body_font(10))
        self._phase_label.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        layout.addWidget(self._phase_label)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(220)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(themed(
            "QProgressBar { background: rgba(255,255,255,0.08); border: none; border-radius: 3px; height: 8px; }"
            "QProgressBar::chunk { background: #d6a72c; border-radius: 3px; }"
        ))
        layout.addWidget(self._progress)

        self._btn_cancel = QPushButton(tr("Annuler"))
        self._btn_cancel.setObjectName("btnCancel")
        self._btn_cancel.setAccessibleName(tr("Annuler le téléchargement"))
        self._btn_cancel.setToolTip(tr("Annuler"))
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.clicked.connect(self.cancel_clicked.emit)
        layout.addWidget(self._btn_cancel)

        self._game: GameData | None = None

    @property
    def current_game(self) -> GameData | None:
        return self._game

    def show_for_game(self, game: GameData, state: GameState) -> None:
        """Affiche la barre pour un jeu en cours de téléchargement/installation."""
        self._game = game
        self._title.setText(game.name)
        cover_path = ASSETS_DIR / "covers" / game.cover_image
        cover = QPixmap(str(cover_path))
        if not cover.isNull():
            # KeepAspectRatioByExpanding peut produire un pixmap > 40x56 — on crop au centre
            scaled = cover.scaled(40, 56, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                  Qt.TransformationMode.SmoothTransformation)
            x_off = (scaled.width() - 40) // 2
            y_off = (scaled.height() - 56) // 2
            self._cover.setPixmap(scaled.copy(x_off, y_off, 40, 56))
        else:
            self._cover.clear()
        self._set_state(state)
        self._progress.setValue(0)
        self.show()

    def _set_state(self, state: GameState) -> None:
        if state == GameState.DOWNLOADING:
            self._status.setText(tr("Téléchargement en cours…"))
            self._btn_cancel.show()
            self.set_phase("download")
        elif state == GameState.INSTALLING:
            self._status.setText(tr("Installation en cours…"))
            self._btn_cancel.hide()
            self.set_phase("install")

    def set_phase(self, phase: str) -> None:
        """Met à jour le stepper.

        La vérification (hash) et la finalisation (déblocage NTFS, copie des
        configs) n'ont pas de progression chiffrée → barre indéterminée, ce qui
        vaut infiniment mieux qu'une barre bloquée à 100 % sans explication.
        """
        if phase not in _PHASES:
            return
        labels = {
            "download": tr("1/4 · Téléchargement"),
            "verify": tr("2/4 · Vérification"),
            "install": tr("3/4 · Installation"),
            "finalize": tr("4/4 · Finalisation"),
        }
        self._phase_label.setText(labels[phase])
        if phase in _INDETERMINATE_PHASES:
            self._progress.setRange(0, 0)
            self._status.setText(
                tr("Vérification de l'archive…") if phase == "verify"
                else tr("Finalisation de l'installation…")
            )
        elif self._progress.maximum() == 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)

    def update_download_progress(self, downloaded: int, total: int,
                                  speed: float, eta_seconds: float) -> None:
        if total <= 0:
            return
        if self._progress.maximum() == 0:  # sortie du mode indéterminé (vérification)
            self._progress.setRange(0, 100)
        self._progress.setValue(downloaded * 100 // total)
        self._status.setText(format_progress_line(downloaded, total, speed, eta_seconds))

    def update_install_progress(self, pct: int) -> None:
        if self._progress.maximum() == 0:
            self._progress.setRange(0, 100)
        self._progress.setValue(pct)
        self._status.setText(tr("Installation… {}%").format(pct))
        self._btn_cancel.hide()

    def update_part_info(self, current: int, total: int) -> None:
        self._status.setText(append_part_info(self._status.text(), current, total))

    def hide_bar(self) -> None:
        self._game = None
        self._title.setText("")
        self._status.setText("")
        self._phase_label.setText("")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._cover.clear()
        self.hide()

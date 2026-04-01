"""Panneau d'actions dynamique — boutons et barres de progression selon l'état du jeu."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from src.core.game_data import GameData
from src.core.game_manager import GameManager, GameState
from src.ui.fonts import cinzel, body_font
from src.ui.glow_button import GlowButton
from src.core.formatting import format_size, format_bytes, format_speed, format_eta


class ActionPanel(QWidget):
    """Panneau d'actions qui s'adapte à l'état du jeu (télécharger/installer/jouer)."""

    download_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()
    play_clicked = pyqtSignal()
    uninstall_clicked = pyqtSignal()
    update_clicked = pyqtSignal()

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._game: GameData | None = None
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

        # Ligne principale des boutons
        self._action_container = QWidget()
        self._action_container.setStyleSheet("background: transparent;")
        self._action_layout = QHBoxLayout(self._action_container)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(14)
        self._action_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self._action_container)

        # Ligne de mise à jour
        self._update_row = QWidget()
        self._update_row.setStyleSheet("background: transparent;")
        self._update_row.hide()
        self._update_row_layout = QHBoxLayout(self._update_row)
        self._update_row_layout.setContentsMargins(0, 0, 0, 0)
        self._update_row_layout.setSpacing(8)
        self._update_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self._update_row)

        # Widgets dynamiques
        self._progress_bar: QProgressBar | None = None
        self._download_label: QLabel | None = None
        self._install_bar: QProgressBar | None = None

    def set_game(self, game: GameData | None) -> None:
        self._game = game

    def refresh(self) -> None:
        """Reconstruit le panneau selon l'état courant du jeu."""
        self._clear_layout(self._action_layout)
        self._clear_layout(self._update_row_layout)
        self._update_row.hide()
        self._progress_bar = None
        self._download_label = None
        self._install_bar = None
        self._action_layout.setDirection(QHBoxLayout.Direction.LeftToRight)

        if self._game is None:
            return

        state = self._manager.get_state(self._game.id)
        match state:
            case GameState.NOT_INSTALLED:
                self._build_not_installed()
            case GameState.DOWNLOADING:
                self._build_downloading()
            case GameState.INSTALLING:
                self._build_installing()
            case GameState.INSTALLED:
                self._build_installed()

    # ── Callbacks de progression ──

    def update_download_progress(self, downloaded: int, total: int,
                                   speed: float, eta_seconds: float) -> None:
        pct = downloaded * 100 // total if total > 0 else 0
        if self._progress_bar is not None:
            self._progress_bar.setValue(pct)
        if self._download_label is not None:
            parts = [
                f"Téléchargement : {pct}%",
                f"{format_bytes(downloaded)} / {format_bytes(total)}",
                format_speed(speed),
            ]
            eta_str = format_eta(eta_seconds)
            if eta_str:
                parts.append(eta_str)
            self._download_label.setText(" \u2014 ".join(parts))

    def update_install_progress(self, pct: int) -> None:
        if self._install_bar is not None:
            self._install_bar.setValue(pct)

    def update_part_info(self, current: int, total: int) -> None:
        if self._download_label is not None:
            text = self._download_label.text()
            if "partie" in text:
                text = text[:text.index("partie")].rstrip(" — ")
            self._download_label.setText(f"{text} — partie {current}/{total}")

    # ── Construction des états ──

    def _build_not_installed(self) -> None:
        dl = self._game.current_download
        size = format_size(dl.size_mb) if dl else "?"
        btn = GlowButton(f"TÉLÉCHARGER  \u2014  {size}", glow_color="#d4a017", style="outline")
        btn.setObjectName("btnDownload")
        btn.setFont(cinzel(13, bold=True))
        btn.setFixedSize(300, 46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.download_clicked)
        self._action_layout.addWidget(btn)

    def _build_downloading(self) -> None:
        self._action_layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(400)
        self._action_layout.addWidget(self._progress_bar)

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)
        self._download_label = QLabel("Téléchargement : 0%")
        self._download_label.setObjectName("downloadLabel")
        row_layout.addWidget(self._download_label, stretch=1)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.cancel_clicked)
        row_layout.addWidget(btn_cancel)
        self._action_layout.addWidget(row)

    def _build_installing(self) -> None:
        self._action_layout.setDirection(QVBoxLayout.Direction.TopToBottom)
        self._install_bar = QProgressBar()
        self._install_bar.setRange(0, 100)
        self._install_bar.setValue(0)
        self._install_bar.setFormat("Installation\u2026 %p%")
        self._install_bar.setFixedWidth(400)
        self._action_layout.addWidget(self._install_bar)

    def _build_installed(self) -> None:
        btn_play = GlowButton("JOUER", glow_color="#2ecc71", style="filled",
                              bg_stops=("#2ecc71", "#27ae60", "#1a9c54"), text_color="#ffffff")
        btn_play.setObjectName("btnPlay")
        btn_play.setFont(cinzel(15, bold=True))
        btn_play.setFixedSize(200, 48)
        btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_play.clicked.connect(self.play_clicked)
        self._action_layout.addWidget(btn_play)

        btn_uninstall = GlowButton("DÉSINSTALLER", glow_color="#8a8aaa", style="outline", text_color="#8a8aaa")
        btn_uninstall.setObjectName("btnUninstall")
        btn_uninstall.setFont(cinzel(10, bold=True))
        btn_uninstall.setFixedSize(160, 36)
        btn_uninstall.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_uninstall.clicked.connect(self.uninstall_clicked)
        self._action_layout.addWidget(btn_uninstall)

        if self._manager.has_update(self._game.id):
            installed_ver = self._manager.installed_version(self._game.id) or "?"
            recommended = self._game.recommended_version
            lbl = QLabel(f"Mise à jour disponible : v{installed_ver} → v{recommended}")
            lbl.setFont(body_font(12))
            lbl.setStyleSheet("color: #d4a017; background: transparent;")
            link = QLabel("Mettre à jour")
            link.setFont(body_font(12))
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setStyleSheet(
                "QLabel { color: #d4a017; background: transparent; text-decoration: underline; }"
                "QLabel:hover { color: #e8c547; }"
            )
            link.mousePressEvent = lambda e: self.update_clicked.emit() if e.button() == Qt.MouseButton.LeftButton else None
            self._update_row_layout.addWidget(lbl)
            self._update_row_layout.addWidget(link)
            self._update_row.show()

    @staticmethod
    def _clear_layout(layout) -> None:
        from src.ui.utils import clear_layout
        clear_layout(layout)

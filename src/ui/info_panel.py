"""Panneau d'informations du jeu — titre, metadata, description, tags, version."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from src.core.game_data import GameData
from src.core.game_manager import GameManager
from src.ui.flow_layout import FlowLayout
from src.ui.fonts import cinzel, cinzel_decorative, body_font
from src.core.formatting import format_size


class InfoPanel(QScrollArea):
    """Panneau scrollable affichant les infos du jeu sélectionné."""

    versions_clicked = pyqtSignal()

    def __init__(self, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._desc_expanded = False
        self._full_desc = ""

        self._setup_scroll()
        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(50, 0, 30, 0)
        self._layout.setSpacing(0)
        self._build_widgets()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(self._layout)
        self.setWidget(container)

    def _setup_scroll(self) -> None:
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 4px; border: none; }"
            "QScrollBar::handle:vertical { background: rgba(212,160,23,0.3); border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )

    def _build_widgets(self) -> None:
        lay = self._layout

        # Titre
        self._title = QLabel()
        self._title.setObjectName("gameTitle")
        self._title.setFont(cinzel_decorative(36))
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(600)
        self._title.setStyleSheet("QLabel { color: #eaeaea; background: transparent; }")
        lay.addWidget(self._title)
        lay.addSpacing(8)

        # Metadata (année · développeur · taille)
        self._meta = QLabel()
        self._meta.setObjectName("gameMeta")
        self._meta.setFont(cinzel(14))
        self._meta.setTextFormat(Qt.TextFormat.RichText)
        self._meta.setStyleSheet("QLabel { color: #8a8aaa; background: transparent; }")
        lay.addWidget(self._meta)
        lay.addSpacing(6)

        # Version + lien changelog
        lay.addWidget(self._build_version_row())
        lay.addSpacing(10)

        # Séparateur doré
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setFixedWidth(60)
        sep.setStyleSheet("background: rgba(212, 160, 23, 0.30);")
        lay.addWidget(sep)
        lay.addSpacing(14)

        # Description
        self._desc = QLabel()
        self._desc.setObjectName("gameDescription")
        self._desc.setFont(body_font(15))
        self._desc.setWordWrap(True)
        self._desc.setMaximumWidth(520)
        self._desc.setStyleSheet(
            "QLabel { color: rgba(176, 176, 200, 0.75); background: transparent;"
            " line-height: 1.5; }"
        )
        lay.addWidget(self._desc)

        # Expand/collapse
        self._btn_expand = QLabel()
        self._btn_expand.setFont(body_font(13))
        self._btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_expand.setStyleSheet(
            "QLabel { color: #d4a017; background: transparent; padding-top: 4px; }"
            "QLabel:hover { color: #e8c547; }"
        )
        self._btn_expand.setVisible(False)
        self._btn_expand.mousePressEvent = lambda e: self._toggle_desc() if e.button() == Qt.MouseButton.LeftButton else None
        lay.addWidget(self._btn_expand)
        lay.addSpacing(10)

        # Tags
        self._tags_container = QWidget()
        self._tags_container.setStyleSheet("background: transparent;")
        self._tags_container.setMaximumHeight(80)
        self._tags_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._tags_layout = FlowLayout(self._tags_container, spacing=8)
        lay.addWidget(self._tags_container)
        lay.addSpacing(20)

    def _build_version_row(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._version_label = QLabel()
        self._version_label.setFont(body_font(12))
        self._version_label.setStyleSheet(
            "QLabel { color: rgba(212, 160, 23, 0.70); background: transparent; }"
        )
        layout.addWidget(self._version_label)

        btn = QLabel("Versions et changelog")
        btn.setFont(body_font(12))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QLabel { color: rgba(212, 160, 23, 0.70); background: transparent; }"
            "QLabel:hover { color: #e8c547; text-decoration: underline; }"
        )
        btn.mousePressEvent = lambda e: self.versions_clicked.emit() if e.button() == Qt.MouseButton.LeftButton else None
        layout.addWidget(btn)
        return row

    # ──────────────────── API publique ────────────────────

    _DESC_TRUNCATE = 160

    def apply_game(self, game: GameData) -> None:
        """Met à jour tous les labels avec les données du jeu."""
        self._title.setText(game.name)

        # Metadata
        gold = "#d4a017"
        sep = f'<span style="color:{gold}; margin: 0 6px;"> \u25c6 </span>'
        dl = game.current_download
        size_str = format_size(dl.size_mb) if dl else "?"
        self._meta.setText(
            f'<span style="text-transform:uppercase; letter-spacing:2px;">'
            f'{game.year}{sep}{game.developer}{sep}{size_str}</span>'
        )

        # Version
        installed = self._manager.installed_version(game.id)
        self._version_label.setText(f"Version {installed or game.recommended_version}")

        # Description
        self._set_desc_text(game.description)

        # Tags
        self._refresh_tags(game)

    def add_bottom_widget(self, widget: QWidget) -> None:
        """Ajoute un widget en bas du panneau (avant le stretch)."""
        self._layout.addWidget(widget)

    def add_stretch(self) -> None:
        self._layout.addStretch()

    # ──────────────────── Description ────────────────────

    def _set_desc_text(self, text: str) -> None:
        self._full_desc = text
        self._desc_expanded = False
        if len(text) > self._DESC_TRUNCATE:
            self._desc.setText(text[:self._DESC_TRUNCATE].rstrip() + "…")
            self._btn_expand.setText("Lire la suite…")
            self._btn_expand.setVisible(True)
        else:
            self._desc.setText(text)
            self._btn_expand.setVisible(False)

    def _toggle_desc(self) -> None:
        self._desc_expanded = not self._desc_expanded
        if self._desc_expanded:
            self._desc.setText(self._full_desc)
            self._btn_expand.setText("Réduire")
        else:
            self._desc.setText(self._full_desc[:self._DESC_TRUNCATE].rstrip() + "…")
            self._btn_expand.setText("Lire la suite…")

    # ──────────────────── Tags ────────────────────

    def _refresh_tags(self, game: GameData) -> None:
        from src.ui.utils import clear_layout
        clear_layout(self._tags_layout)
        for tag in game.tags:
            badge = QLabel(tag.upper())
            badge.setFont(cinzel(10, bold=True))
            badge.setStyleSheet(
                "QLabel { background: rgba(212, 160, 23, 0.05); color: #d4a017;"
                " border: 1px solid rgba(212, 160, 23, 0.3); border-radius: 12px;"
                " padding: 4px 14px; letter-spacing: 2px; }"
            )
            self._tags_layout.addWidget(badge)
        self._tags_container.updateGeometry()

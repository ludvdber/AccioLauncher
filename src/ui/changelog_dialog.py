"""Dialog affichant l'historique des versions d'un jeu."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from src.core.game_data import GameData
from src.ui.fonts import cinzel, body_font


class ChangelogDialog(QDialog):
    """Historique des versions — style sombre coherent avec le launcher."""

    def __init__(self, game: GameData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Historique des versions \u2014 {game.name}")
        self.setFixedSize(500, 400)
        self.setStyleSheet(
            "QDialog { background: #0d0d1a; border: 1px solid rgba(212,160,23,0.3); }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(0)

        # Titre
        title = QLabel(f"Historique des versions \u2014 {game.name}")
        title.setFont(cinzel(14, bold=True))
        title.setStyleSheet("color: #d4a017; background: transparent;")
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addSpacing(16)

        # Zone scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "  background: rgba(255,255,255,0.03); width: 6px; border: none;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(212,160,23,0.3); border-radius: 3px; min-height: 20px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.addWidget(scroll, stretch=1)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(20)

        # Entries (plus recente en premier)
        entries = sorted(game.changelog, key=lambda e: e.date, reverse=True)
        for entry in entries:
            # Version + date sur la meme ligne
            header = QWidget()
            header.setStyleSheet("background: transparent;")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)

            ver_label = QLabel(f"Version {entry.version}")
            ver_label.setFont(cinzel(13, bold=True))
            ver_label.setStyleSheet("color: #d4a017; background: transparent;")
            header_layout.addWidget(ver_label)

            # Formater la date JJ/MM/AAAA
            date_str = entry.date
            if "-" in date_str:
                parts = date_str.split("-")
                if len(parts) == 3:
                    date_str = f"{parts[2]}/{parts[1]}/{parts[0]}"
            date_label = QLabel(date_str)
            date_label.setFont(body_font(12))
            date_label.setStyleSheet("color: #6a6a8a; background: transparent;")
            date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            header_layout.addWidget(date_label)

            content_layout.addWidget(header)

            # Separateur
            sep = QWidget()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: rgba(212,160,23,0.15);")
            content_layout.addWidget(sep)

            # Liste des changements
            for change in entry.changes:
                change_label = QLabel(f'<span style="color:#d4a017;">\u2022</span>  {change}')
                change_label.setFont(body_font(13))
                change_label.setStyleSheet("color: #b0b0c8; background: transparent; padding-left: 4px;")
                change_label.setWordWrap(True)
                change_label.setTextFormat(Qt.TextFormat.RichText)
                content_layout.addWidget(change_label)

        content_layout.addStretch()
        scroll.setWidget(content)

        layout.addSpacing(12)

        # Bouton Fermer
        btn_close = QPushButton("Fermer")
        btn_close.setFont(cinzel(11, bold=True))
        btn_close.setFixedSize(120, 34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            "QPushButton {"
            "  background: rgba(212,160,23,0.1); color: #d4a017;"
            "  border: 1px solid rgba(212,160,23,0.3); border-radius: 6px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(212,160,23,0.2); color: #e8c547;"
            "}"
        )
        btn_close.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()
        layout.addLayout(btn_row)

"""Dialog de gestion des versions d'un jeu — remplace l'ancien changelog_dialog."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.game_data import GameData, GameVersion
from src.core.i18n import tr
from src.core.game_manager import GameManager
from src.core.version_utils import compare_versions
from src.ui.fonts import cinzel, body_font
from src.ui.theme import current as current_theme, themed
from src.core.formatting import format_size


def _date_sort_key(date_str: str) -> tuple[int, ...]:
    """Tuple parsable depuis une date 'YYYY-MM-DD' ; tolérant aux formats cassés."""
    try:
        return tuple(int(x) for x in date_str.split("-"))
    except (ValueError, AttributeError):
        return (0,)


class VersionsDialog(QDialog):
    """Versions et changelog — permet upgrade et downgrade."""

    # Émis pour demander un swap de version (uninstall current → install target).
    switch_to_version = pyqtSignal(str, str)  # (game_id, version)

    def __init__(self, game: GameData, manager: GameManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = game
        self.manager = manager
        self._installed_version = manager.installed_version(game.id)

        self.setWindowTitle(tr("Versions — {}").format(game.name))
        self.setFixedSize(550, 500)
        self.setStyleSheet(themed(
            "QDialog { background: #0d0d1a; border: 1px solid rgba(212,160,23,0.3); }"
        ))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(0)

        title = QLabel(tr("Versions — {}").format(self.game.name))
        title.setFont(cinzel(14, bold=True))
        title.setStyleSheet(themed("color: #d4a017; background: transparent;"))
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addSpacing(16)

        # Zone scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(themed(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "  background: rgba(255,255,255,0.03); width: 6px; border: none;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(212,160,23,0.3); border-radius: 3px; min-height: 20px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        ))
        layout.addWidget(scroll, stretch=1)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(16)

        # Versions triées par date décroissante (parsing safe vs format cassé)
        versions = sorted(self.game.versions, key=lambda v: _date_sort_key(v.date), reverse=True)
        for ver in versions:
            content_layout.addWidget(self._build_version_card(ver))

        content_layout.addStretch()
        scroll.setWidget(content)

        layout.addSpacing(12)

        # Bouton Fermer
        btn_close = QPushButton(tr("Fermer"))
        btn_close.setFont(cinzel(11, bold=True))
        btn_close.setFixedSize(120, 34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(themed(
            "QPushButton {"
            "  background: rgba(212,160,23,0.1); color: #d4a017;"
            "  border: 1px solid rgba(212,160,23,0.3); border-radius: 6px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(212,160,23,0.2); color: #e8c547;"
            "}"
        ))
        btn_close.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _build_version_card(self, ver: GameVersion) -> QWidget:
        card = QWidget()
        card.setStyleSheet("background: transparent;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(4)

        # Header : symbole + version + annotations + date
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        is_installed = self._installed_version == ver.version
        is_recommended = ver.version == self.game.recommended_version

        # Symbole et version
        if is_installed:
            symbol = "✓"
            color = "#2ecc71"
        elif is_recommended:
            symbol = "●"
            color = current_theme().accent
        else:
            symbol = "○"
            color = "#8a8aaa"

        annotations = []
        if is_recommended:
            annotations.append(tr("recommandée"))
        if is_installed:
            annotations.append(tr("installée"))

        ver_text = f"{symbol} v{ver.version}"
        if annotations:
            ver_text += f" ({', '.join(annotations)})"

        ver_label = QLabel(ver_text)
        ver_label.setFont(cinzel(13, bold=True))
        ver_label.setStyleSheet(f"color: {color}; background: transparent;")
        header_layout.addWidget(ver_label)

        # Date formatée JJ/MM/AAAA
        date_str = ver.date
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                date_str = f"{parts[2]}/{parts[1]}/{parts[0]}"

        date_label = QLabel(date_str)
        date_label.setFont(body_font(12))
        date_label.setStyleSheet("color: #6a6a8a; background: transparent;")
        date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(date_label)

        card_layout.addWidget(header)

        # Séparateur
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(themed("background: rgba(212,160,23,0.15);"))
        card_layout.addWidget(sep)

        # Liste des changements
        for change in ver.changes:
            safe = change.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            change_label = QLabel(f'<span style="color:{current_theme().accent};">•</span>  {safe}')
            change_label.setFont(body_font(13))
            change_label.setStyleSheet("color: #b0b0c8; background: transparent; padding-left: 4px;")
            change_label.setWordWrap(True)
            change_label.setTextFormat(Qt.TextFormat.RichText)
            card_layout.addWidget(change_label)

        # Taille
        size_row = QWidget()
        size_row.setStyleSheet("background: transparent;")
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 4, 0, 0)

        size_label = QLabel(format_size(ver.size_mb))
        size_label.setFont(body_font(11))
        size_label.setStyleSheet("color: #6a6a8a; background: transparent;")
        size_layout.addStretch()
        size_layout.addWidget(size_label)

        card_layout.addWidget(size_row)

        # Bouton installer (sauf si déjà installée, ou si l'archive n'est pas publiée)
        if not is_installed and ver.is_available:
            btn_row = QWidget()
            btn_row.setStyleSheet("background: transparent;")
            btn_layout = QHBoxLayout(btn_row)
            btn_layout.setContentsMargins(0, 4, 0, 0)
            btn_layout.addStretch()

            if self._installed_version is not None:
                if compare_versions(ver.version, self._installed_version) > 0:
                    btn_text = tr("Mettre à jour vers v{}").format(ver.version)
                else:
                    btn_text = tr("Revenir à v{}").format(ver.version)
            else:
                btn_text = tr("Installer v{}").format(ver.version)

            btn = QPushButton(btn_text)
            btn.setFont(body_font(11))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(themed(
                "QPushButton {"
                "  background: rgba(212,160,23,0.1); color: #d4a017;"
                "  border: 1px solid rgba(212,160,23,0.3); border-radius: 4px;"
                "  padding: 4px 12px;"
                "}"
                "QPushButton:hover {"
                "  background: rgba(212,160,23,0.2); color: #e8c547;"
                "}"
            ))
            btn.clicked.connect(lambda checked, v=ver.version: self._on_install_version(v))
            btn_layout.addWidget(btn)

            card_layout.addWidget(btn_row)
        elif not is_installed:
            note = QLabel(tr("Pas encore en ligne"))
            note.setFont(body_font(11))
            note.setStyleSheet("color: #6a6a8a; background: transparent;")
            note.setAlignment(Qt.AlignmentFlag.AlignRight)
            card_layout.addWidget(note)

        return card

    def _on_install_version(self, version: str) -> None:
        action = tr("installer")
        if self._installed_version is not None:
            action = tr("supprimer la version actuelle et installer")

        reply = QMessageBox.question(
            self, tr("Confirmer"),
            tr("Ceci va {} la version {}.\nContinuer ?").format(action, version),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.switch_to_version.emit(self.game.id, version)
            self.accept()

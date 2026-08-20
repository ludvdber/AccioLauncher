"""Bandeau doré de mise à jour du launcher.

Extrait de `main_window.py` : la fenêtre en portait la construction, les deux
libellés et l'état du bouton, soit une soixantaine de lignes qui ne parlaient
que de ce ruban de 35 px.

Deux règles de comportement vivent ici et ne doivent pas être « simplifiées » :

- **Le bandeau ne s'efface jamais tout seul.** Il disparaissait au bout de 30 s :
  le temps de le lire et d'aller cliquer, il n'était plus là, et plus rien ne
  rappelait qu'une mise à jour attendait. Il reste jusqu'à ce que l'utilisateur
  tranche — mettre à jour, ou fermer.
- **La croix écarte la version pour de bon** (`dismissed`), elle ne se contente
  pas de cacher : sans ça le bandeau revenait à chaque vérification.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src.core.i18n import tr
from src.ui.theme import themed

_HAUTEUR = 35


class NotificationBar(QWidget):
    """Ruban d'annonce en haut de fenêtre. Caché tant qu'il n'a rien à dire."""

    download_clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_HAUTEUR)
        self.setStyleSheet(themed(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 rgba(214,167,44,0.15), stop:0.5 rgba(214,167,44,0.25),"
            "stop:1 rgba(214,167,44,0.15)); }"
        ))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(10)

        self._label = QLabel()
        self._label.setStyleSheet(themed(
            "color: #d6a72c; font-size: 12px; background: transparent;"))
        layout.addWidget(self._label, stretch=1)

        self._btn = QPushButton(tr("Télécharger"))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(themed(
            "QPushButton { background: rgba(214,167,44,0.2); color: #d6a72c;"
            " border: 1px solid rgba(214,167,44,0.4); border-radius: 4px;"
            " padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(214,167,44,0.35); color: #e8c547; }"
        ))
        self._btn.clicked.connect(self.download_clicked)
        layout.addWidget(self._btn)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(themed(
            "QPushButton { background: transparent; color: #d6a72c;"
            " border: none; font-size: 14px; }"
            "QPushButton:hover { color: #e8c547; }"
        ))
        btn_close.clicked.connect(self._on_close)
        layout.addWidget(btn_close)

        self.hide()

    # ──────────────────── API ────────────────────

    def announce(self, version: str, *, auto: bool) -> None:
        """Annonce une version du launcher et se montre.

        `auto` dit si la mise à jour peut s'installer toute seule : le bouton
        promet alors « Mettre à jour » plutôt que « Télécharger », qui ouvrirait
        seulement la page de release.
        """
        self._label.setText(tr("Accio Launcher v{} est disponible !").format(version))
        self._btn.setText(tr("Mettre à jour") if auto else tr("Télécharger"))
        self._btn.setEnabled(True)
        self.show()

    def set_message(self, texte: str) -> None:
        """Remplace le texte du bandeau (progression du téléchargement…)."""
        self._label.setText(texte)

    def message(self) -> str:
        return self._label.text()

    def set_busy(self, busy: bool) -> None:
        """Grise le bouton pendant le téléchargement de la mise à jour."""
        self._btn.setEnabled(not busy)

    def _on_close(self) -> None:
        self.hide()
        self.dismissed.emit()

"""Barre de titre custom pour fenêtre sans cadre."""

from PyQt6.QtCore import Qt, QPoint, QRectF
from PyQt6.QtGui import QMouseEvent, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QLabel, QWidget

from src.core.i18n import tr
from src.ui.fonts import cinzel
from src.ui import theme

# Débord opaque sous le bord bas, en pixels logiques — même remède que
# `background_widget._DEBORD_PX` pour la couture du carrousel : Qt découpe
# au rect réel, donc peindre au-delà garantit d'atteindre le bord physique
# quelle que soit l'échelle d'affichage.
_DEBORD_PX = 2.0


class TitleBar(QWidget):
    """Barre de titre draggable avec boutons min/max/close."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._window = parent
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(38)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(0)

        # Titre — Cinzel Decorative, doré. Sans pictogramme : le ⚡ (U+26A1)
        # est à présentation emoji par défaut, donc Windows le rendait en
        # couleur à côté d'un titre or — en permanence, sur l'élément de marque.
        self._title = QLabel("Accio Launcher")
        self._title.setFont(cinzel(13, bold=True))
        self._title.setStyleSheet("color: #d6a72c; background: transparent;")
        layout.addWidget(self._title)

        layout.addStretch()

        # Boutons minimalistes
        for text, slot, hover_bg, label in (
            ("\u2500", self._on_minimize, "rgba(255,255,255,0.08)", tr("Réduire")),
            ("\u25a1", self._on_maximize, "rgba(255,255,255,0.08)", tr("Agrandir")),
            ("\u2715", self._on_close, "#c0392b", tr("Fermer")),
        ):
            btn = QPushButton(text)
            btn.setAccessibleName(label)
            btn.setToolTip(label)
            btn.setFixedSize(44, 38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: #8a8aaa; border: none;"
                f" font-size: 13px; }}"
                f"QPushButton:hover {{ background: {hover_bg}; color: #eaeaea; }}"
            )
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def _on_minimize(self) -> None:
        self._window.showMinimized()

    def _on_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def _on_close(self) -> None:
        self._window.close()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme.bg_qcolor(217))  # rgba(6,6,17,0.85)
        # Séparateur à l'accent du thème (la ligne au-dessus le fait déjà pour
        # le fond ; l'or était codé en dur trois lignes plus bas).
        #
        # Peint en fillRect DÉBORDANT sous le bord, et non en drawLine à
        # `height() - 1`. Cette coordonnée est LOGIQUE : à une échelle
        # d'affichage fractionnaire, le bord bas du widget ne tombe pas sur un
        # pixel physique entier (38 px logiques × 1,25 = 47,5), et le filet se
        # posait une rangée physique au-dessus du vrai bord, laissant une bande
        # de fond nu entre lui et la fiche de jeu. Mesuré : présent à 1,25 et
        # 1,5 sur les 8 jeux et les 4 tailles, absent à 1,0. Même famille que
        # la couture du carrousel (pitfall #32) ; Qt découpe le débord au rect
        # réel du widget, donc la ligne atteint toujours le bord.
        p.fillRect(QRectF(0.0, self.height() - 1.0,
                          float(self.width()), 1.0 + _DEBORD_PX),
                   theme.accent_qcolor(25))
        p.end()

    # ── Drag de la fenêtre ──

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._window.isMaximized():
                # Restore first, reposition window so cursor stays on the title bar
                from PyQt6.QtGui import QGuiApplication
                global_pt = event.globalPosition().toPoint()
                self._window.showNormal()
                geo = self._window.frameGeometry()
                new_x = int(global_pt.x() - geo.width() * 0.5)
                # Borner aux limites de l'écran sous le curseur (multi-monitor safe)
                screen = QGuiApplication.screenAt(global_pt)
                if screen is not None:
                    sg = screen.availableGeometry()
                    new_x = max(sg.x(), min(new_x, sg.x() + sg.width() - geo.width()))
                self._window.move(new_x, 0)
                self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            else:
                self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._on_maximize()

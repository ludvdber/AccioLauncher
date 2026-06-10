"""Wrapper autour de QSystemTrayIcon : icône, menu, signaux haut-niveau."""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


class TrayManager(QObject):
    """Gère l'icône system tray + menu contextuel.

    Émet `restore_requested` (double-click ou item menu) et `quit_requested`.
    """

    restore_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon: QIcon, parent: QWidget) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(icon)
        self._tray.setToolTip("Accio Launcher")

        menu = QMenu()
        act_restore = QAction("Restaurer Accio Launcher", parent)
        act_restore.triggered.connect(self.restore_requested.emit)
        menu.addAction(act_restore)
        menu.addSeparator()
        act_quit = QAction("Quitter", parent)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_requested.emit()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_tooltip(self, tooltip: str) -> None:
        self._tray.setToolTip(tooltip)

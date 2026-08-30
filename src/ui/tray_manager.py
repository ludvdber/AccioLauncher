"""Wrapper autour de QSystemTrayIcon : icône, menu, signaux haut-niveau."""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from src.core.i18n import tr


class TrayManager(QObject):
    """Gère l'icône system tray + menu contextuel.

    Émet `restore_requested` (clic gauche, double-clic ou item menu) et
    `quit_requested`.
    """

    restore_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon: QIcon, parent: QWidget) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(icon)
        self._tray.setToolTip("Accio Launcher")

        menu = QMenu()
        act_restore = QAction(tr("Restaurer Accio Launcher"), parent)
        act_restore.triggered.connect(self.restore_requested.emit)
        menu.addAction(act_restore)
        menu.addSeparator()
        act_quit = QAction(tr("Quitter"), parent)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Clic gauche SIMPLE ou double : on restaure.

        Le simple clic manquait — seul `DoubleClick` était écouté —, et c'est
        la convention de la zone de notification sous Windows : Steam, Discord,
        Spotify et Teams rouvrent tous au PREMIER clic. Il fallait donc soit
        deviner qu'un double-clic était exigé là où tout le reste du système
        n'en demande pas, soit passer par « Restaurer » du menu contextuel.
        Signalé par Ludo le 2026-08-30.

        Le clic DROIT n'est volontairement pas listé : Qt le sert déjà par
        `setContextMenu`, et le faire restaurer ouvrirait la fenêtre EN MÊME
        TEMPS que le menu. `MiddleClick` non plus — il n'a pas de sens établi.

        Un vrai double-clic émet `Trigger` PUIS `DoubleClick`, donc restaure
        deux fois : sans conséquence, `_restore_from_tray` étant idempotente
        (`Ticker.resume` est gardé par `isActive`).
        """
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_requested.emit()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_tooltip(self, tooltip: str) -> None:
        self._tray.setToolTip(tooltip)

    def show_notification(self, title: str, message: str, msecs: int = 5000) -> None:
        """Notification système (visible uniquement si l'icône tray est affichée)."""
        self._tray.showMessage(
            title, message, QSystemTrayIcon.MessageIcon.Information, msecs,
        )

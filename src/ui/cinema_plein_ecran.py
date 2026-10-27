"""Une cinématique des Collections en plein écran (Ludo, 2026-10-27).

Une fenêtre à part, sans cadre, sur l'écran du launcher : l'image dans son
format sur du noir, rien d'autre. Le lecteur reste celui de la page
(`_VueCinematiques`) : cette fenêtre ne fait que peindre les images qu'on lui
pose et renvoyer les touches. Échap, F ou un double-clic ramènent à la page ;
Espace met en pause ; ←/→ reculent ou avancent de dix secondes. Le curseur
disparaît quand la souris ne bouge plus, l'aide du bas aussi.
"""

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QColor, QImage, QKeyEvent, QMouseEvent, QPainter
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from src.core.i18n import tr
from src.ui.composants import ENCRE_DOUCE, texte

SAUT_MS = 10_000
_DISCRET_MS = 2500


class PleinEcran(QWidget):
    fermee = pyqtSignal()
    pause_demandee = pyqtSignal()
    saut_demande = pyqtSignal(int)          # en millisecondes, négatif pour reculer

    def __init__(self, image: QImage | None = None) -> None:
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Cinématique"))
        self.setMouseTracking(True)
        self._image = image
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 28)
        lay.addStretch()
        self._aide = texte(tr("Échap pour revenir · Espace pour la pause · ← → dix secondes"),
                           13, ENCRE_DOUCE)
        self._aide.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._aide)
        self._discret = QTimer(self)
        self._discret.setSingleShot(True)
        self._discret.setInterval(_DISCRET_MS)
        self._discret.timeout.connect(self._se_faire_discret)
        self._discret.start()

    def ouvrir(self, voisin: QWidget | None) -> None:
        """Plein écran sur l'écran où se trouve `voisin` (le launcher)."""
        ecran = voisin.screen() if voisin is not None else None
        if ecran is not None:
            self.setGeometry(ecran.geometry())
        self.showFullScreen()
        self.activateWindow()

    def poser(self, image: QImage | None) -> None:
        self._image = image
        self.update()

    def _se_faire_discret(self) -> None:
        self._aide.hide()
        self.setCursor(Qt.CursorShape.BlankCursor)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802 (Qt)
        self._aide.show()
        self.unsetCursor()
        self._discret.start()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, _event: QMouseEvent | None) -> None:  # noqa: N802 (Qt)
        self.close()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802 (Qt)
        if event is None:
            return
        match event.key():
            case Qt.Key.Key_Escape | Qt.Key.Key_F:
                self.close()
            case Qt.Key.Key_Space:
                self.pause_demandee.emit()
            case Qt.Key.Key_Left:
                self.saut_demande.emit(-SAUT_MS)
            case Qt.Key.Key_Right:
                self.saut_demande.emit(SAUT_MS)
            case _:
                super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802 (Qt)
        self._discret.stop()
        self.fermee.emit()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#000000"))
        image = self._image
        if image is not None and not image.isNull():
            echelle = min(self.width() / image.width(), self.height() / image.height())
            larg, haut = image.width() * echelle, image.height() * echelle
            p.drawImage(QRectF((self.width() - larg) / 2, (self.height() - haut) / 2, larg, haut), image)
        p.end()

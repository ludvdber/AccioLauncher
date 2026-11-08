"""L'écran d'une cinématique dessiné par la carte graphique (Collections).

Une petite scène Qt Quick, un `VideoOutput` : le `VideoPlayer` lui relaie ses
images (`set_sortie`), sans `toImage()` ni peinture de widget. Mesuré en vraie
fenêtre sur une bande-annonce : 134 % d'un cœur par `toImage`, 28 % par
`VideoOutput` dans une `QQuickWidget`.

Suit le fond de l'accueil (`fond_gpu.actif()`) ; `ACCIO_MEDIA_GPU=0` l'éteint.
Sans Qt Quick, ou si la scène ne charge pas, `creer()` rend None et l'appelant
garde son chemin QPainter, sans rien dire à l'écran.
"""

import logging
import os

from PyQt6.QtCore import QObject, Qt, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget

from src.core.config import ASSETS_DIR
from src.ui import fond_gpu
from src.ui.video_player import MULTIMEDIA_DISPONIBLE, QVideoFrame

log = logging.getLogger(__name__)

_QML = ASSETS_DIR / "qml" / "EcranVideo.qml"


def actif() -> bool:
    """Les cinématiques passent-elles par la carte graphique ?"""
    return (fond_gpu.actif() and MULTIMEDIA_DISPONIBLE and _QML.exists()
            and os.environ.get("ACCIO_MEDIA_GPU") != "0")


class EcranVideoGPU(fond_gpu.QQuickWidget if fond_gpu.QUICK_DISPONIBLE else QWidget):  # type: ignore[misc]
    """Un `VideoOutput` posé sur un widget, qui garde la souris et les touches pour lui."""

    def __init__(self, parent: QWidget, *, coin: float = 0.0, fond: QColor | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)    # un QQuickWidget prend Tab, d'office
        # Le double-clic, le curseur qui s'efface et la souris qui bouge sont
        # ceux du widget dessous : la scène n'a rien à en faire.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setResizeMode(fond_gpu.QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setClearColor(QColor("#000000"))
        self.setSource(QUrl.fromLocalFile(str(_QML)))
        for erreur in self.errors():
            log.warning("Cinématique sur la carte graphique : %s", erreur.toString())
        self._racine = self.rootObject()
        if self._racine is not None:
            self._racine.setProperty("coin", coin)
            if fond is not None:
                self._racine.setProperty("fond", fond)

    def sortie_video(self) -> QObject | None:
        """Le `VideoOutput`, pour `VideoPlayer.set_sortie`."""
        return self._racine.findChild(QObject, "sortieVideo") if self._racine is not None else None

    def valide(self) -> bool:
        sortie = self.sortie_video()
        return sortie is not None and sortie.property("videoSink") is not None

    def vider(self) -> None:
        """Plus d'image : la suivante ne doit pas commencer sur celle-ci."""
        sortie = self.sortie_video()
        if sortie is not None:
            sortie.property("videoSink").setVideoFrame(QVideoFrame())


def creer(parent: QWidget, *, coin: float = 0.0, fond: QColor | None = None) -> EcranVideoGPU | None:
    """Un écran sur la carte graphique, ou None : l'appelant garde le chemin QPainter."""
    if not actif():
        return None
    ecran = EcranVideoGPU(parent, coin=coin, fond=fond)
    if not ecran.valide():
        ecran.setParent(None)
        ecran.deleteLater()
        return None
    return ecran

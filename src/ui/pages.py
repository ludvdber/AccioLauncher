"""Les pages de la fenêtre : la bibliothèque, et ce qui s'ouvre à sa place.

Refonte du 2026-10-09. Mes années, Paramètres et les réglages d'un jeu étaient
des fenêtres modales posées sur le launcher : une seconde barre de titre, une
ombre, et la fiche qui continuait de jouer sa bande-annonce derrière. Ce sont
maintenant des PAGES : elles prennent la place de la fiche et du carrousel,
sous la barre du haut, et leur bouton de retour ramène à la bibliothèque.

Les classes restent des `QDialog` : `accept()`/`reject()` ferment la page,
Échap aussi, et `done()` enregistre comme avant. Elles ont seulement cessé
d'être des fenêtres (`Qt.WindowType.Widget`). La barre de téléchargement,
elle, reste sous la pile : un téléchargement se suit depuis n'importe où.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QStackedWidget, QVBoxLayout, QWidget

from src.ui.title_bar import BIBLIOTHEQUE


class Pages(QStackedWidget):
    """La bibliothèque en page 0 ; une seule autre page à la fois par-dessus."""

    ouverte = pyqtSignal(str)
    fermee = pyqtSignal()

    def __init__(self, fiche, carrousel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        bibliotheque = QWidget()
        lay = QVBoxLayout(bibliotheque)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(fiche, stretch=1)
        lay.addWidget(carrousel)
        self.addWidget(bibliotheque)
        self._fiche = fiche
        self._particules = None
        self._barre = None
        self.cle = ""

    def brancher(self, particules, barre_titre) -> None:
        """Ce qui naît après la pile : les particules et la barre du haut."""
        self._particules = particules
        self._barre = barre_titre

    @property
    def page(self) -> QDialog | None:
        courante = self.currentWidget()
        return courante if isinstance(courante, QDialog) else None

    def ouvrir(self, dlg: QDialog, cle: str = "") -> None:
        """Pose `dlg` à la place de la bibliothèque. `cle` : l'onglet à souligner."""
        self.fermer()
        dlg.setParent(self)
        dlg.setWindowFlags(Qt.WindowType.Widget)
        # Ses minimums de FENÊTRE n'ont plus cours : la page défile, et la
        # fenêtre du launcher a les siens.
        dlg.setMinimumSize(0, 0)
        dlg.finished.connect(lambda _r, d=dlg: self._retirer(d))
        self.addWidget(dlg)
        self.cle = cle
        self.setCurrentWidget(dlg)
        dlg.show()
        dlg.setFocus(Qt.FocusReason.OtherFocusReason)
        # La fiche est cachée : sa bande-annonce ne doit pas jouer pour personne.
        self._fiche.pause()
        self._particules.hide()
        self._barre.set_onglet(cle or BIBLIOTHEQUE)
        self.ouverte.emit(cle)

    def fermer(self) -> None:
        page = self.page
        if page is not None:
            page.accept()

    def _retirer(self, dlg: QDialog) -> None:
        if self.indexOf(dlg) < 0:
            return
        self.removeWidget(dlg)
        dlg.deleteLater()
        if self.page is not None:
            return
        self.setCurrentIndex(0)
        self.cle = ""
        self._fiche.resume()
        self._fiche.refresh_video()
        self._particules.show()
        self._particules.raise_()
        self._barre.set_onglet(BIBLIOTHEQUE)
        self.fermee.emit()

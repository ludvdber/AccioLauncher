"""Le « ? » d'un réglage : une fiche complète, ouverte au clic.

Demandé par Ludo le 2026-09-30 : une phrase sous chaque réglage refaisait le mur
de texte qu'on retirait, une infobulle ne se trouve qu'en passant par hasard. Le
« ? » se VOIT à côté de chaque nom, et ce qu'il ouvre peut tout dire : ce que
fait le réglage, ce qu'il demande à la machine, de quoi il dépend.

La fiche est un `Popup` : un clic ailleurs ou Échap la referme, comme un menu.
"""

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from src.core.i18n import tr
from src.ui.fonts import body_font, cinzel
from src.ui.theme import themed

_LARGEUR_FICHE = 330

_BOUTON_STYLE = (
    "QPushButton { color: #b0b0c8; background: transparent; border: 1px solid #55556a;"
    " border-radius: 9px; padding: 0px; font-weight: bold; }"
    "QPushButton:hover { color: #e8c547; border-color: #d6a72c; }"
    "QPushButton[focusClavier=\"true\"]:focus { border: 2px solid #d6a72c; }"
)


class FicheAide(QFrame):
    """La fiche elle-même : un titre, puis des paragraphes (texte riche, NÔTRE)."""

    def __init__(self, titre: str, corps_html: str, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setObjectName("ficheAide")
        self.setStyleSheet(themed(
            "#ficheAide { background: #141428; border: 1px solid #d6a72c; border-radius: 6px; }"))
        self.setFixedWidth(_LARGEUR_FICHE)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(6)
        entete = QLabel(titre)
        entete.setTextFormat(Qt.TextFormat.PlainText)
        entete.setWordWrap(True)
        entete.setFont(cinzel(10, bold=True))
        entete.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        v.addWidget(entete)
        self.texte = QLabel(corps_html)
        self.texte.setTextFormat(Qt.TextFormat.RichText)
        self.texte.setWordWrap(True)
        self.texte.setFont(body_font(11))
        self.texte.setStyleSheet("color: #d0d0e0; background: transparent;")
        # Hauteur mesurée à la largeur RÉELLE (règle 38) : sans elle, la fiche
        # coupait sa dernière ligne.
        largeur = _LARGEUR_FICHE - 28
        for lbl in (entete, self.texte):
            lbl.setFixedWidth(largeur)
            lbl.setMinimumHeight(lbl.heightForWidth(largeur))
        v.addWidget(self.texte)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def ouvrir_sous(self, ancre: QWidget) -> None:
        """Sous le « ? », ramenée dans l'écran s'il le faut (bord droit, bas)."""
        self.adjustSize()
        pos = ancre.mapToGlobal(QPoint(0, ancre.height() + 4))
        ecran = ancre.screen() or QGuiApplication.primaryScreen()
        if ecran is not None:
            zone = ecran.availableGeometry()
            x = min(pos.x(), zone.right() - self.width())
            y = pos.y() if pos.y() + self.height() <= zone.bottom() \
                else ancre.mapToGlobal(QPoint(0, 0)).y() - self.height() - 4
            pos = QPoint(max(zone.left(), x), max(zone.top(), y))
        self.move(pos)
        self.show()


class BoutonAide(QPushButton):
    """« ? » rond à côté du nom d'un réglage ; clic, Espace ou Entrée ouvrent sa fiche."""

    def __init__(self, titre: str, corps_html: str, parent: QWidget | None = None) -> None:
        super().__init__("?", parent)
        self._titre = titre
        self._corps = corps_html
        self.fiche: FicheAide | None = None
        self.setFixedSize(18, 18)
        self.setFont(body_font(10))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(themed(_BOUTON_STYLE))
        self.setAccessibleName(tr("Aide : {}").format(titre))
        self.setToolTip(tr("Ce que fait ce réglage"))
        self.clicked.connect(self.ouvrir)

    def ouvrir(self) -> None:
        self.fiche = FicheAide(self._titre, self._corps, self)
        self.fiche.destroyed.connect(self._oublier)
        self.fiche.ouvrir_sous(self)

    def _oublier(self) -> None:
        self.fiche = None

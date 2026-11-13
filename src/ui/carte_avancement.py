"""La carte d'avancement des Collections : où en est le joueur dans ce jeu, et ce qui s'ouvre.

Commune aux quatre rubriques qui ouvrent leur contenu avec l'histoire (Musique,
Cinématiques, Personnages, Bestiaire). Elle n'existait qu'en Musique : une
cinématique ou une fiche fermée annonçait « S'ouvre à 75 % » sans que la rubrique
dise où en était le joueur, et « 26 personnages » comptait aussi les fiches
fermées (audit UI col14, 2026-11-13). Elle compte donc les OUVERTS sur le total,
et le seuil d'une ligne fermée s'écrit d'une seule façon (`texte_seuil`).

La carte prend le cadre des cartes de la page des Collections (`QFrame#carteAvancement`).
"""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import discographie
from src.core.i18n import tr
from src.ui.composants import ENCRE, ENCRE_DOUCE, texte, transparent
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor


def texte_seuil(seuil: int) -> str:
    """Ce qu'attend une ligne fermée, le même mot dans les quatre rubriques."""
    if seuil >= discographie.TOUT_A:
        return tr("S'ouvre à {} %").format(discographie.TOUT_A)
    return tr("S'ouvre vers {} %").format(seuil)


class Barre(QWidget):
    """L'avancement du jeu, avec le repère des 75 % où tout s'ouvre."""

    def __init__(self) -> None:
        super().__init__()
        self.pct = 0
        self.setFixedHeight(14)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        y = self.height() / 2 - 3
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(QRectF(0, y, self.width(), 6), 3, 3)
        p.setBrush(accent_qcolor())
        p.drawRoundedRect(QRectF(0, y, self.width() * self.pct / 100, 6), 3, 3)
        p.setBrush(QColor(242, 238, 226, 150))
        p.drawRect(QRectF(self.width() * discographie.TOUT_A / 100 - 1, 0, 2, self.height()))
        p.end()


class CarteAvancement(QFrame):
    """Le nom du jeu et le compte des ouverts ; la barre et la sauvegarde la plus avancée
    quand quelque chose attend encore l'histoire."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("carteAvancement")
        c = QVBoxLayout(self)
        c.setContentsMargins(18, 12, 18, 10)
        c.setSpacing(6)
        haut = QHBoxLayout()
        self.nom_jeu = QLabel()
        self.nom_jeu.setTextFormat(Qt.TextFormat.PlainText)
        self.nom_jeu.setFont(cinzel(11, bold=True))
        self.nom_jeu.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        haut.addWidget(self.nom_jeu, stretch=1)
        self.compte = texte("", 13, ENCRE_DOUCE)
        haut.addWidget(self.compte)
        c.addLayout(haut)
        self.barre = Barre()
        c.addWidget(self.barre)
        self.bas = QWidget()
        transparent(self.bas, "basAvancement")
        bas = QHBoxLayout(self.bas)
        bas.setContentsMargins(0, 0, 0, 0)
        self.avance = texte("", 12, ENCRE_DOUCE)
        bas.addWidget(self.avance, stretch=1)
        bas.addWidget(texte(tr("{} % : tout s'ouvre").format(discographie.TOUT_A), 12, ENCRE_DOUCE))
        c.addWidget(self.bas)

    def poser(self, nom_jeu: str, compte: str, avance: int | None, a_des_seuils: bool) -> None:
        """`a_des_seuils` faux (tout est ouvert d'office, HP4) : ni barre ni sauvegarde."""
        self.nom_jeu.setText(nom_jeu)
        self.compte.setText(compte)
        self.barre.pct = avance or 0
        self.barre.update()
        self.barre.setVisible(a_des_seuils)
        self.bas.setVisible(a_des_seuils)
        self.avance.setText(tr("Votre sauvegarde la plus avancée : {} %").format(avance)
                            if avance is not None else tr("Aucune partie lue pour l'instant"))

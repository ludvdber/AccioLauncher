"""« Ce fond cherche un artiste · Voir l'atelier » : la pastille de la fiche.

Maquette « La fiche quand son image cherche un artiste », validée avec l'atelier
le 2026-10-14. Le fond trop petit de HP3 se voit en grand derrière la fiche ;
c'est là, et pas au bout des Paramètres, qu'un artiste qui passe se demande
s'il pourrait mieux faire. La pastille le lui dit et ouvre l'atelier.

Elle n'apparaît que pour un jeu dont la jaquette ou le fond est mesuré trop
petit (`atelier.besoins_mesures`) : elle disparaît d'elle-même quand l'image
arrive. Posée au-dessus de la barre audio, d'après la position RÉELLE de
celle-ci (règle 36).
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QPushButton, QWidget

from src.core import atelier
from src.core.i18n import tr
from src.ui.composants import police
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, current as current_theme

_ECART = 12   # au-dessus de la barre audio


class PastilleAtelier(QPushButton):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("pastilleAtelier")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(police(14))
        self.setFixedHeight(40)
        # Pictogramme et libellé ensemble : l'écart passe par le padding et
        # l'icône, jamais par des espaces dans le texte (règle 30).
        self.setIcon(QIcon(pixmap_icone("pinceau", 18, accent_qcolor())))
        self.setIconSize(QSize(18, 18))
        clair = current_theme().accent_light
        self.setStyleSheet(
            "QPushButton#pastilleAtelier { background: rgba(6,6,17,0.86); color: #f2e6c4;"
            " border: 1px solid rgba(214,167,44,0.5); border-radius: 20px;"
            " padding: 0 16px 0 12px; text-align: left; }"
            f"QPushButton#pastilleAtelier:hover {{ color: {clair};"
            " border-color: rgba(214,167,44,0.85); }")
        self._mesures: list[atelier.Besoin] | None = None
        self.hide()

    def pour(self, id_jeu: str, jeux) -> None:
        """Montre la pastille si l'image de ce jeu cherche un artiste, sinon la cache."""
        if self._mesures is None:
            # Une fois : la taille des images embarquées ne change pas en cours de route.
            from src.ui.atelier_page import besoins_mesures
            self._mesures = besoins_mesures(jeux)
        besoin = atelier.pour_le_jeu(self._mesures, id_jeu)
        if besoin is None:
            self.hide()
            return
        phrase = (tr("Ce fond cherche un artiste") if besoin.genre == atelier.FOND
                  else tr("Cette jaquette cherche un artiste"))
        voir = tr("Voir l'atelier")
        texte = f"{phrase}  ·  {voir}"
        self.setText(texte)
        self.setAccessibleName(texte)
        self.adjustSize()
        self.show()

    def placer(self, au_dessus_de: QWidget, marge_droite: int) -> None:
        """Contre le bord droit, juste au-dessus de `au_dessus_de` (la barre audio)."""
        parent = self.parentWidget()
        self.move(parent.width() - self.width() - marge_droite,
                  au_dessus_de.y() - self.height() - _ECART)
        self.raise_()

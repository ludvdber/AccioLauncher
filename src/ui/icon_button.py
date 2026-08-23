"""Boutons à pictogramme DESSINÉ, pour la barre de la bande-annonce.

Pourquoi peindre plutôt qu'écrire un caractère : les trois boutons de la barre
étaient des glyphes posés dans des `QPushButton` — deux barres, un triangle, un
haut-parleur. Deux conséquences, toutes deux visibles à l'écran. D'abord le
haut-parleur est un EMOJI (U+1F50A) : Windows le rend en couleur via Segoe UI
Emoji, insensible au `setPen`, donc bleu au milieu d'une interface or et
blanche — c'est le piège déjà documenté dans CLAUDE.md, et il était ici depuis
le début. Ensuite un
glyphe dépend de la police qui finit par le servir : ni sa graisse, ni sa
taille optique, ni son centrage ne sont les nôtres, et rien ne garantit qu'ils
seront les mêmes d'un pictogramme à l'autre — d'où trois symboles qui ne
paraissaient pas de la même famille.

Dessinés, ils partagent une épaisseur de trait, une boîte et une couleur, ils
suivent l'accent du thème au survol, et ils restent nets à toutes les échelles
d'affichage (celle de Ludo est à 125 %).
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QWidget

from src.ui import theme
from src.ui.focus_visible import PROPRIETE as _FOCUS_CLAVIER

# Les tracés sont écrits dans une boîte de 24 × 24 puis mis à l'échelle du
# bouton : une seule géométrie à relire, quelle que soit la taille demandée.
_BOITE = 24.0
_TRAIT = 1.7
_COULEUR = QColor(234, 234, 234)

ICONES = ("play", "pause", "replay", "volume", "muet")


class IconButton(QAbstractButton):
    """Bouton carré au pictogramme peint, accordé au thème.

    Survol : la couleur passe à l'accent de la maison et un disque très discret
    apparaît dessous — assez pour désigner la cible, pas assez pour faire une
    tache sur une bande-annonce.
    """

    def __init__(self, icone: str, taille: int = 26,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if icone not in ICONES:
            raise ValueError(f"icône inconnue : {icone!r}")
        self._icone = icone
        self._survol = False
        self.setFixedSize(taille, taille)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def icone(self) -> str:
        return self._icone

    def set_icone(self, icone: str) -> None:
        if icone not in ICONES:
            raise ValueError(f"icône inconnue : {icone!r}")
        if icone != self._icone:
            self._icone = icone
            self.update()

    # ── Survol ──

    def enterEvent(self, event) -> None:
        self._survol = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._survol = False
        self.update()
        super().leaveEvent(event)

    # ── Peinture ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        actif = self._survol or self.isDown()
        if actif:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.accent_qcolor(30 if self._survol else 52))
            p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

        # L'anneau de focus reste réservé au CLAVIER (cf. focus_visible) : un
        # bouton peint n'est pas atteint par la règle `:focus` du stylesheet,
        # il doit donc le dessiner lui-même ou l'utilisateur au clavier perd
        # son seul repère.
        if self.property(_FOCUS_CLAVIER):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.accent_qcolor(210), 1.2))
            p.drawEllipse(QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0))

        couleur = theme.accent_qcolor() if actif else _COULEUR
        echelle = min(self.width(), self.height()) / _BOITE
        p.translate((self.width() - _BOITE * echelle) / 2.0,
                    (self.height() - _BOITE * echelle) / 2.0)
        p.scale(echelle, echelle)

        stylo = QPen(couleur, _TRAIT)
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
        stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(stylo)
        p.setBrush(couleur)

        getattr(self, "_peindre_" + self._icone)(p)
        p.end()

    # ── Tracés (boîte 24 × 24) ──

    @staticmethod
    def _peindre_play(p: QPainter) -> None:
        chemin = QPainterPath()
        chemin.moveTo(9.0, 5.6)
        chemin.lineTo(18.6, 12.0)
        chemin.lineTo(9.0, 18.4)
        chemin.closeSubpath()
        # Rempli ET tracé : le trait à bouts ronds arrondit les trois pointes,
        # qui piquent sinon dans une barre par ailleurs toute en courbes.
        p.drawPath(chemin)

    @staticmethod
    def _peindre_pause(p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(8.0, 6.0, 3.2, 12.0), 1.6, 1.6)
        p.drawRoundedRect(QRectF(12.8, 6.0, 3.2, 12.0), 1.6, 1.6)

    @staticmethod
    def _peindre_replay(p: QPainter) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        cercle = QRectF(5.4, 5.4, 13.2, 13.2)
        chemin = QPainterPath()
        # Ouverture en haut : c'est là que se pose la pointe, et une boucle
        # fermée ne dirait plus dans quel sens elle tourne.
        chemin.arcMoveTo(cercle, 62)
        chemin.arcTo(cercle, 62, -300)
        p.drawPath(chemin)

        # Pointe posée sur la TANGENTE de fin de course, calculée et non
        # devinée : un triangle placé à la main se voit tout de suite de
        # travers, et c'est ce qui rendait le pictogramme bancal.
        fin = chemin.pointAtPercent(1.0)
        angle = math.radians(chemin.angleAtPercent(1.0))
        dx, dy = math.cos(angle), -math.sin(angle)     # Qt : y vers le bas
        px, py = -dy, dx                               # perpendiculaire
        base = QPointF(fin.x() - dx * 1.1, fin.y() - dy * 1.1)
        pointe = QPainterPath()
        pointe.moveTo(base.x() + dx * 4.3, base.y() + dy * 4.3)
        pointe.lineTo(base.x() + px * 2.6, base.y() + py * 2.6)
        pointe.lineTo(base.x() - px * 2.6, base.y() - py * 2.6)
        pointe.closeSubpath()
        p.setBrush(p.pen().color())
        p.drawPath(pointe)

    @staticmethod
    def _corps_haut_parleur(p: QPainter) -> None:
        chemin = QPainterPath()
        chemin.moveTo(4.4, 9.4)
        chemin.lineTo(7.6, 9.4)
        chemin.lineTo(11.4, 5.6)
        chemin.lineTo(11.4, 18.4)
        chemin.lineTo(7.6, 14.6)
        chemin.lineTo(4.4, 14.6)
        chemin.closeSubpath()
        p.drawPath(chemin)

    @classmethod
    def _peindre_volume(cls, p: QPainter) -> None:
        cls._corps_haut_parleur(p)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for rayon in (4.2, 7.2) :
            arc = QRectF(11.0 - rayon, 12.0 - rayon, rayon * 2, rayon * 2)
            chemin = QPainterPath()
            chemin.arcMoveTo(arc, -50)
            chemin.arcTo(arc, -50, 100)
            p.drawPath(chemin)

    @classmethod
    def _peindre_muet(cls, p: QPainter) -> None:
        cls._corps_haut_parleur(p)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Une croix plutôt qu'une barre en travers : la barre traverse le corps
        # du haut-parleur et le rend illisible à 26 px.
        p.drawLine(QPointF(14.6, 9.2), QPointF(20.0, 14.6))
        p.drawLine(QPointF(20.0, 9.2), QPointF(14.6, 14.6))

"""L'écu de la maison, dessiné : un bouclier « parti » aux deux couleurs de la maison.

Demandé par Ludo le 2026-09-27 (« on peut tenter l'écu aussi… élève de Serdaigle »).
Trois limites tenues exprès :
- **Aucun animal ni blason officiel** : le lion, le serpent, l'aigle, le blaireau et
  les armoiries des films sont des marques de Warner Bros. (voir TRADEMARKS.md). Deux
  couleurs héraldiques sur un écu nu n'appartiennent à personne.
- **Peint, pas téléchargé** : aucun fichier, aucune image trouvée en ligne ; la forme
  est calculée à la taille demandée, nette à toute échelle d'affichage.
- **Jamais sur la fiche** (règle 127 : la fiche porte déjà son illustration) : l'écu
  vit dans la barre de titre, à côté du nom, et n'apparaît qu'avec un thème de maison.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from src.ui import theme

# Les deux « émaux » de chaque maison, dans l'ordre héraldique (dextre, senestre).
# Couleurs des LIVRES : écarlate et or, vert et argent, bleu et bronze, jaune et noir.
EMAUX = {
    "gryffondor": ("#a3201f", "#d6a72c"),
    "serpentard": ("#1f6b40", "#c3cbc7"),
    "serdaigle": ("#1f3f8f", "#b07a3a"),
    "poufsouffle": ("#e3bf45", "#1b1a17"),
}


def emaux(theme_id: str) -> tuple[str, str] | None:
    """Les deux couleurs de la maison, ou None (Poudlard, thème inconnu : pas d'écu)."""
    return EMAUX.get(theme_id)


def contour(r: QRectF) -> QPainterPath:
    """Un écu : chef droit, flancs droits sur les deux tiers, pointe en ogive."""
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    chemin = QPainterPath(QPointF(x, y))
    chemin.lineTo(x + w, y)
    chemin.lineTo(x + w, y + h * 0.55)
    chemin.cubicTo(QPointF(x + w, y + h * 0.82), QPointF(x + w * 0.62, y + h * 0.93), QPointF(x + w / 2, y + h))
    chemin.cubicTo(QPointF(x + w * 0.38, y + h * 0.93), QPointF(x, y + h * 0.82), QPointF(x, y + h * 0.55))
    chemin.closeSubpath()
    return chemin


class Ecu(QWidget):
    """L'écu peint, à la taille du widget (proportion 5/6)."""

    def __init__(self, theme_id: str, parent: QWidget | None = None, hauteur: int = 22) -> None:
        super().__init__(parent)
        self._emaux = emaux(theme_id)
        self.setFixedSize(round(hauteur * 5 / 6) + 2, hauteur + 2)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _event) -> None:
        if self._emaux is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        forme = contour(r)
        p.setClipPath(forme)
        dextre, senestre = (QColor(c) for c in self._emaux)
        p.fillRect(QRectF(r.x(), r.y(), r.width() / 2, r.height()), dextre)
        p.fillRect(QRectF(r.center().x(), r.y(), r.width() / 2 + 1, r.height()), senestre)
        p.setClipping(False)
        p.setPen(QPen(theme.accent_qcolor(230), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(forme)
        p.end()

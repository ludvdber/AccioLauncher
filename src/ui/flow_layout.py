"""FlowLayout — layout qui wrap les items à la ligne suivante."""

from PyQt6.QtCore import QRect, QRectF, QSize
from PyQt6.QtWidgets import QLayout


class FlowLayout(QLayout):
    """Simple flow layout that wraps items to the next line."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        # Hauteurs déjà calculées, par largeur. Qt interroge `heightForWidth`
        # en BOUCLE pendant une négociation de mise en page — mesuré ici :
        # 107 appels pour un seul rafraîchissement de la fiche, chacun refaisant
        # un passage complet sur les pastilles avec un `sizeHint()` par item.
        # Le résultat ne dépend que de la largeur et du contenu, donc il se
        # retient. Vidé par `invalidate()`, que Qt appelle dès qu'un enfant
        # change de taille souhaitée, et par toute mutation de la liste.
        self._hauteurs: dict[int, int] = {}

    def addItem(self, item):
        self._items.append(item)
        self._hauteurs.clear()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            self._hauteurs.clear()
            return self._items.pop(index)
        return None

    def invalidate(self):
        """Qt signale qu'un enfant a changé de taille souhaitée."""
        self._hauteurs.clear()
        super().invalidate()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        hauteur = self._hauteurs.get(width)
        if hauteur is None:
            hauteur = self._do_layout(QRectF(0, 0, width, 0), test_only=True)
            self._hauteurs[width] = hauteur
        return hauteur

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(QRectF(rect), test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect, test_only=False):
        x = rect.x()
        y = rect.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            widget = item.widget()
            if widget is not None and (hint.isEmpty() or hint.height() == 0):
                # QWidgetItem.sizeHint() vaut (0, 0) tant que son widget est
                # caché — c'est le cas des pastilles de tags pendant le
                # cross-fade du panneau d'info. Le widget, lui, sait déjà
                # quelle taille il veut : sans ce repli, heightForWidth()
                # renvoyait 0 et le conteneur écrasait toutes ses lignes.
                hint = widget.sizeHint()
            w = hint.width()
            h = hint.height()
            if x + w > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(int(x), int(y), int(w), int(h)))
            x += w + self._spacing
            line_height = max(line_height, h)
        return int(y + line_height - rect.y())

"""FlowLayout — layout qui wrap les items à la ligne suivante."""

from PyQt6.QtCore import QRectF, QSize
from PyQt6.QtWidgets import QLayout


class FlowLayout(QLayout):
    """Simple flow layout that wraps items to the next line."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRectF(0, 0, width, 0), test_only=True)

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
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._spacing
                line_height = 0
            if not test_only:
                from PyQt6.QtCore import QRect as QR
                item.setGeometry(QR(int(x), int(y), int(w), int(h)))
            x += w + self._spacing
            line_height = max(line_height, h)
        return int(y + line_height - rect.y())

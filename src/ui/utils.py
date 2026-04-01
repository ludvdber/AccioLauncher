"""Utilitaires Qt partagés entre les widgets UI."""

from PyQt6.QtWidgets import QLayout


def clear_layout(layout: QLayout) -> None:
    """Retire et détruit tous les widgets d'un layout."""
    while layout.count():
        item = layout.takeAt(0)
        if (w := item.widget()) is not None:
            w.hide()
            w.deleteLater()

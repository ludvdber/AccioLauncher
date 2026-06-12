"""Utilitaires Qt partagés entre les widgets UI."""

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QLayout


def clear_layout(layout: QLayout) -> None:
    """Retire et détruit tous les widgets d'un layout."""
    while layout.count():
        item = layout.takeAt(0)
        if (w := item.widget()) is not None:
            w.hide()
            w.deleteLater()


def open_url(url: str) -> None:
    """Ouvre une URL dans le navigateur par défaut. Helper unique pour tout le projet."""
    QDesktopServices.openUrl(QUrl(url))


def open_local_path(path: str) -> None:
    """Ouvre un dossier local dans l'explorateur."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def is_writable_dir(path) -> bool:
    """Crée le dossier si nécessaire et vérifie qu'on peut y écrire."""
    from pathlib import Path

    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".accio_write_test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False

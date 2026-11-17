"""Les filtres d'événements posés sur TOUTE l'application, suspendus le temps de bâtir une page.

Deux filtres voient chaque événement de chaque widget : celui de la fenêtre
(souris, bords, touches globales : `MainWindow.eventFilter`) et celui de
l'anneau de focus (`focus_visible`). Bâtir une page en envoie des dizaines de
milliers (26 000 pour les réglages de HP6 : enfant ajouté, style changé,
police, mise en page), et chacun traversait ces deux fonctions Python pour
rien : 260 des 1 040 ms de l'ouverture des réglages de HP6, un quart de toute
page (mesuré le 2026-11-16, avec et sans eux).

`batie(fabrique)` bâtit la page filtres retirés, puis les repose dans leur
ordre. Rien ne leur échappe : la construction est d'un seul tenant dans le fil
de l'interface, aucune touche ni souris n'y est traitée, et le focus ne bouge
qu'à l'affichage de la page (`Pages.ouvrir`), filtres reposés.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

_filtres: list[QObject] = []        # dans l'ordre de leur pose : Qt appelle le dernier posé d'abord


def poser(filtre: QObject) -> None:
    app = QApplication.instance()
    if app is not None and filtre not in _filtres:
        _filtres.append(filtre)
        app.installEventFilter(filtre)


def retirer(filtre: QObject) -> None:
    if filtre in _filtres:
        _filtres.remove(filtre)
        _detacher(filtre)


def _detacher(filtre: QObject) -> None:
    app = QApplication.instance()
    if app is not None:
        try:
            app.removeEventFilter(filtre)
        except RuntimeError:        # le filtre est déjà détruit côté Qt
            pass


@contextmanager
def suspendus() -> Iterator[None]:
    """Sans filtre global le temps du bloc ; reposés ensuite, dans le même ordre."""
    app = QApplication.instance()
    suspendus_ici = list(_filtres) if app is not None else []
    for filtre in suspendus_ici:
        _detacher(filtre)
    try:
        yield
    finally:
        for filtre in suspendus_ici:
            if filtre in _filtres and app is not None:
                try:
                    app.installEventFilter(filtre)
                except RuntimeError:
                    _filtres.remove(filtre)


def batie[T](fabrique: Callable[[], T]) -> T:
    """La page rendue par `fabrique`, bâtie sans les filtres globaux."""
    with suspendus():
        return fabrique()

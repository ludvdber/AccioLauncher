"""Les filtres d'événements globaux se retirent le temps de bâtir une page (`ui/filtres_globaux`).

Mesuré le 2026-11-16 : ils voyaient 26 000 événements à l'ouverture des réglages de HP6, un
quart du temps de toute construction de page."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QEvent, QObject  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from src.ui import filtres_globaux  # noqa: E402


class _Compteur(QObject):
    def __init__(self, journal: list[str], nom: str) -> None:
        super().__init__()
        self.vus = 0
        self._journal, self._nom = journal, nom

    def eventFilter(self, _objet, event) -> bool:  # noqa: N802 (Qt)
        self.vus += 1
        if event.type() == QEvent.Type.User:
            self._journal.append(self._nom)
        return False


@pytest.fixture
def deux_filtres(qapp):
    journal: list[str] = []
    premier, second = _Compteur(journal, "premier"), _Compteur(journal, "second")
    filtres_globaux.poser(premier)
    filtres_globaux.poser(second)
    yield premier, second, journal
    filtres_globaux.retirer(premier)
    filtres_globaux.retirer(second)


def _batir() -> QWidget:
    page = QWidget()
    for _ in range(20):
        QLabel("ligne", page)
    return page


def test_une_page_se_batit_sans_passer_par_les_filtres(qtbot, deux_filtres):
    premier, second, _journal = deux_filtres
    qtbot.addWidget(_batir())
    assert premier.vus > 0 and second.vus > 0, "posés, ils voient chaque événement de la construction"
    premier.vus = second.vus = 0
    qtbot.addWidget(filtres_globaux.batie(_batir))
    assert (premier.vus, second.vus) == (0, 0)


def test_reposes_dans_le_meme_ordre(qtbot, deux_filtres):
    """Qt appelle le dernier filtre posé d'abord : la fenêtre passe avant l'anneau de focus, qui
    ne voit pas une touche qu'elle a prise."""
    _premier, _second, journal = deux_filtres
    cible = QObject()
    QApplication.sendEvent(cible, QEvent(QEvent.Type.User))
    assert journal == ["second", "premier"]
    with filtres_globaux.suspendus():
        QApplication.sendEvent(cible, QEvent(QEvent.Type.User))
    assert journal == ["second", "premier"], "suspendus : rien vu"
    QApplication.sendEvent(cible, QEvent(QEvent.Type.User))
    assert journal == ["second", "premier", "second", "premier"]


def test_une_construction_qui_leve_les_repose_quand_meme(qtbot, deux_filtres):
    premier, _second, _journal = deux_filtres

    def casse() -> QWidget:
        raise RuntimeError("page impossible")
    with pytest.raises(RuntimeError):
        filtres_globaux.batie(casse)
    premier.vus = 0
    qtbot.addWidget(_batir())
    assert premier.vus > 0


def test_un_filtre_retire_pendant_la_suspension_ne_revient_pas(qtbot, deux_filtres):
    premier, second, _journal = deux_filtres
    with filtres_globaux.suspendus():
        filtres_globaux.retirer(second)        # la fenêtre se ferme pendant qu'une page se bâtit
    premier.vus = second.vus = 0
    qtbot.addWidget(_batir())
    assert premier.vus > 0 and second.vus == 0

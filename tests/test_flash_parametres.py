"""Ouvrir une page ne doit montrer AUCUNE fenêtre à part, même un instant.

Ludo, 2026-11-15, sur la 1.3.4 publiée : « une mini fenêtre qui s'ouvre un quart de seconde avant d'ouvrir les
paramètres ». C'était la tête de l'onglet Image (`page_image`, 378 × 304) rendue visible AVANT d'être posée dans
la page : sans parent, `setVisible(True)` en fait une fenêtre. Relevé sur la vraie plateforme Windows ; l'évènement
Show d'une fenêtre de premier niveau se voit aussi sous offscreen, d'où ce filet.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QEvent, QObject  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402


class _Guet(QObject):
    def __init__(self, principale):
        super().__init__()
        self.principale = principale
        self.vues: list[str] = []

    def eventFilter(self, obj, ev):  # noqa: N802 (nom Qt)
        if ev.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow() \
                and obj is not self.principale:
            self.vues.append(f"{type(obj).__name__} {obj.objectName()!r}")
        return False


def _guetter(w, qtbot, ouvrir) -> list[str]:
    guet = _Guet(w)
    QApplication.instance().installEventFilter(guet)
    try:
        ouvrir()
        qtbot.wait(50)
    finally:
        QApplication.instance().removeEventFilter(guet)
    return guet.vues


def test_ouvrir_les_parametres_ne_montre_aucune_autre_fenetre(make_window, qtbot):
    w = make_window()
    w.show()
    qtbot.waitExposed(w)
    assert _guetter(w, qtbot, w._on_settings) == []


def test_ouvrir_les_reglages_de_chaque_jeu_ne_montre_aucune_autre_fenetre(make_window, qtbot):
    from src.ui.game_detail_handlers import on_game_settings

    w = make_window()
    w.show()
    qtbot.waitExposed(w)
    vues = {}
    for rang, jeu in enumerate(w.manager.catalog.games):
        w._carousel.select(rang)
        qtbot.wait(10)
        if (v := _guetter(w, qtbot, lambda: on_game_settings(w._detail))):
            vues[jeu.id] = v
        w._pages.fermer()
    assert vues == {}


def test_la_page_image_d_un_jeu_a_correctif_ne_montre_aucune_fenetre(qtbot, tmp_path):
    """Le cas de Ludo : un jeu à correctif INSTALLÉ, dont la page Image a sa tête (onglets, recherche)."""
    from tests.test_reglages_finitions import _fenetre

    guet = _Guet(None)
    QApplication.instance().installEventFilter(guet)
    try:
        dlg, _ini = _fenetre(qtbot, tmp_path)
    finally:
        QApplication.instance().removeEventFilter(guet)
    assert dlg.findChild(QWidget, "teteImage") is not None, "la page Image n'a pas été bâtie"
    assert guet.vues == []

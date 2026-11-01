"""Fenêtre réduite : les effets décoratifs s'arrêtent (`MainWindow.changeEvent`).

Qt annonce la perte d'activation AVANT la réduction, fenêtre encore « active » :
la pause était ratée et les effets tournaient, réduits, à 3-6 % d'un cœur
(mesuré en vraie fenêtre le 2026-11-01).
"""
import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QEvent  # noqa: E402

from src.ui.ticker import Ticker  # noqa: E402


def _etat(win, monkeypatch, reduite: bool, active: bool) -> None:
    monkeypatch.setattr(win, "isMinimized", lambda: reduite)
    monkeypatch.setattr(win, "isActiveWindow", lambda: active)
    monkeypatch.setattr(win, "isVisible", lambda: True)


def test_reduite_les_effets_s_arretent_puis_reprennent(make_window, monkeypatch):
    win = make_window()
    Ticker.instance().resume()
    # L'ordre relevé sous Windows : activation (encore active, déjà réduite), puis état.
    _etat(win, monkeypatch, reduite=True, active=True)
    win.changeEvent(QEvent(QEvent.Type.ActivationChange))
    win.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    assert not Ticker.instance()._timer.isActive()
    _etat(win, monkeypatch, reduite=False, active=True)
    win.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    win.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert Ticker.instance()._timer.isActive()

"""Tests pour src/ui/toggle_switch.py."""

import pytest

pytest.importorskip("pytestqt")

from src.ui.toggle_switch import ToggleSwitch, toggle_row  # noqa: E402


class TestToggleSwitch:
    def test_initial_state_off(self, qtbot):
        t = ToggleSwitch(checked=False)
        qtbot.addWidget(t)
        assert t.isChecked() is False

    def test_initial_state_on(self, qtbot):
        t = ToggleSwitch(checked=True)
        qtbot.addWidget(t)
        assert t.isChecked() is True

    def test_set_checked_changes_state(self, qtbot):
        t = ToggleSwitch(checked=False)
        qtbot.addWidget(t)
        t.setChecked(True)
        assert t.isChecked() is True

    def test_set_checked_no_op(self, qtbot):
        t = ToggleSwitch(checked=True)
        qtbot.addWidget(t)
        t.setChecked(True)  # déjà True
        assert t.isChecked() is True

    def test_toggle_row_returns_pair(self, qtbot):
        row, toggle = toggle_row("Mon réglage", checked=True)
        qtbot.addWidget(row)
        assert toggle.isChecked() is True

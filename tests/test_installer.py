"""Tests pour src/core/installer.py — fonctions utilitaires uniquement (pas de QThread)."""

from pathlib import Path

from src.core.installer import _check_path_traversal


class TestCheckPathTraversal:
    def test_safe_path(self, tmp_path):
        assert _check_path_traversal(tmp_path, "HP1/System/Game.exe") is True

    def test_traversal(self, tmp_path):
        assert _check_path_traversal(tmp_path, "../../etc/passwd") is False

    def test_absolute_in_archive(self, tmp_path):
        assert _check_path_traversal(tmp_path, "/etc/passwd") is False

    def test_nested_safe(self, tmp_path):
        assert _check_path_traversal(tmp_path, "game/data/maps/level1.unr") is True

    def test_backslash_traversal(self, tmp_path):
        assert _check_path_traversal(tmp_path, "..\\..\\evil.dll") is False

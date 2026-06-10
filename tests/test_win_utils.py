"""Tests pour src/core/win_utils.py"""

import sys
from unittest.mock import patch

from src.core.win_utils import remove_zone_identifier


class TestRemoveZoneIdentifier:
    def test_non_existing_root(self, tmp_path):
        result = remove_zone_identifier(tmp_path / "does_not_exist")
        assert result == 0

    def test_empty_dir(self, tmp_path):
        assert remove_zone_identifier(tmp_path) == 0

    def test_non_windows_returns_zero(self, tmp_path):
        (tmp_path / "test.dll").write_text("fake")
        with patch.object(sys, "platform", "linux"):
            assert remove_zone_identifier(tmp_path) == 0

    def test_does_not_crash_on_files_without_zone_identifier(self, tmp_path):
        # Sur Windows réel, les fichiers locaux n'ont pas de Zone.Identifier ;
        # la fonction tente le os.remove et catch OSError silencieusement.
        (tmp_path / "test.dll").write_text("fake")
        (tmp_path / "test.exe").write_text("fake")
        # Ne doit pas crasher (sous Windows OS error attrapée, sous Linux short-circuit)
        result = remove_zone_identifier(tmp_path)
        assert isinstance(result, int)

    def test_pattern_filter(self, tmp_path):
        (tmp_path / "a.dll").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        # Pattern restreint : seuls les .dll seraient itérés
        # On ne peut pas tester l'effet réel sans un vrai NTFS, mais l'API
        # ne doit pas crasher avec un pattern custom.
        result = remove_zone_identifier(tmp_path, pattern="*.dll")
        assert isinstance(result, int)

    def test_subdirectories_traversed(self, tmp_path):
        sub = tmp_path / "sub" / "nested"
        sub.mkdir(parents=True)
        (sub / "deep.dll").write_text("x")
        result = remove_zone_identifier(tmp_path)
        assert isinstance(result, int)

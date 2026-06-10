"""Tests pour les helpers d'extraction (pas de QThread)."""

import sys

import pytest

from src.core.extractors import check_path_traversal, extract_7z, find_7z_exe
from src.core.installer import Installer


class TestCheckPathTraversal:
    def test_safe_path(self, tmp_path):
        assert check_path_traversal(tmp_path, "HP1/System/Game.exe") is True

    def test_traversal(self, tmp_path):
        assert check_path_traversal(tmp_path, "../../etc/passwd") is False

    def test_absolute_in_archive(self, tmp_path):
        assert check_path_traversal(tmp_path, "/etc/passwd") is False

    def test_nested_safe(self, tmp_path):
        assert check_path_traversal(tmp_path, "game/data/maps/level1.unr") is True

    def test_backslash_traversal(self, tmp_path):
        assert check_path_traversal(tmp_path, "..\\..\\evil.dll") is False


class TestInstallerSignals:
    def test_finished_not_shadowed(self, tmp_path):
        """Régression : le signal métier ne doit PAS s'appeler `finished` —
        ça masquerait QThread.finished."""
        inst = Installer(tmp_path / "a.7z", tmp_path / "dest")
        assert inst.finished.signal == "2finished()"  # natif QThread, sans argument
        assert inst.install_finished.signal == "2install_finished(QString)"


@pytest.mark.skipif(sys.platform != "win32", reason="7z.exe bundlé Windows uniquement")
class TestExtract7z:
    def test_extract_via_7z_exe(self, tmp_path):
        """extract_7z passe par 7z.exe en priorité (progression + annulation)."""
        import py7zr

        assert find_7z_exe() is not None, "7z.exe bundlé manquant dans assets/7z/"

        src = tmp_path / "src" / "Game"
        src.mkdir(parents=True)
        (src / "data.txt").write_text("hello", encoding="utf-8")
        archive = tmp_path / "a.7z"
        with py7zr.SevenZipFile(archive, "w") as z:
            z.writeall(src, arcname="Game")

        dest = tmp_path / "out"
        dest.mkdir()
        progress_values: list[int] = []
        extract_7z(archive, dest, progress_values.append, lambda: False)

        assert (dest / "Game" / "data.txt").read_text(encoding="utf-8") == "hello"
        assert progress_values, "7z.exe doit émettre au moins une progression"

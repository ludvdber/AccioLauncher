"""Tests pour les helpers d'extraction (pas de QThread)."""

import os
import subprocess
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


def _make_7z(tmp_path, *, volume_size: str | None = None):
    """Crée une archive 7z de test via 7z.exe (py7zr retiré du projet)."""
    exe = find_7z_exe()
    assert exe is not None, "7z.exe bundlé manquant dans assets/7z/"

    src = tmp_path / "src" / "Game"
    src.mkdir(parents=True)
    (src / "data.txt").write_text("hello", encoding="utf-8")
    # Données incompressibles pour que -v10k produise réellement plusieurs volumes
    (src / "big.bin").write_bytes(os.urandom(30_000))

    archive = tmp_path / "a.7z"
    cmd = [exe, "a", str(archive), "Game"]
    if volume_size:
        cmd.append(f"-v{volume_size}")
    kwargs: dict = {"cwd": str(tmp_path / "src"), "capture_output": True, "timeout": 60}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(cmd, **kwargs)
    assert result.returncode == 0, result.stdout
    return archive


@pytest.mark.skipif(sys.platform != "win32", reason="7z.exe bundlé Windows uniquement")
class TestExtract7z:
    def test_extract_simple(self, tmp_path):
        archive = _make_7z(tmp_path)
        dest = tmp_path / "out"
        dest.mkdir()
        progress_values: list[int] = []
        extract_7z(archive, dest, progress_values.append, lambda: False)

        assert (dest / "Game" / "data.txt").read_text(encoding="utf-8") == "hello"
        assert progress_values, "7z.exe doit émettre au moins une progression"

    def test_extract_multivolume_001(self, tmp_path):
        """7z.exe lit nativement les archives découpées — le downloader émet le .001 brut."""
        _make_7z(tmp_path, volume_size="10k")
        first_part = tmp_path / "a.7z.001"
        assert first_part.exists(), "le découpage -v10k doit produire a.7z.001"
        assert (tmp_path / "a.7z.002").exists()

        dest = tmp_path / "out"
        dest.mkdir()
        extract_7z(first_part, dest, lambda _: None, lambda: False)

        assert (dest / "Game" / "data.txt").read_text(encoding="utf-8") == "hello"
        assert (dest / "Game" / "big.bin").stat().st_size == 30_000

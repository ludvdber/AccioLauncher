"""Tests pour src/ui/disk_scan_worker.py — scan disque en arrière-plan."""

import pytest

pytest.importorskip("pytestqt")

from src.ui.disk_scan_worker import DiskScanWorker  # noqa: E402


class TestDiskScanWorker:
    def test_result_emitted(self, qtbot, tmp_path):
        game_dir = tmp_path / "HPTest"
        game_dir.mkdir()
        (game_dir / "a.bin").write_bytes(b"x" * 1000)
        (game_dir / "b.bin").write_bytes(b"y" * 500)

        worker = DiskScanWorker([game_dir])
        with qtbot.waitSignal(worker.result, timeout=3000) as blocker:
            worker.start()
        worker.wait()

        count, total = blocker.args
        assert count == 1
        assert total == 1500

    def test_missing_path_skipped(self, qtbot, tmp_path):
        worker = DiskScanWorker([tmp_path / "inexistant"])
        with qtbot.waitSignal(worker.result, timeout=3000) as blocker:
            worker.start()
        worker.wait()

        count, total = blocker.args
        assert count == 1  # compté comme jeu, mais 0 octet
        assert total == 0

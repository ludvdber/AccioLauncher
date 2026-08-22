"""Tests pour src/core/formatting.py et src/ui/speed_tracker.py"""

from src.core.formatting import (
    format_size, format_bytes, format_speed, format_eta,
    format_progress_line, append_part_info,
)
from src.ui.speed_tracker import SpeedTracker


class TestFormatSize:
    def test_megabytes(self):
        assert format_size(500) == "500 Mo"

    def test_gigabytes(self):
        assert format_size(1500) == "1,5 Go"

    def test_exact_threshold(self):
        assert format_size(1000) == "1,0 Go"

    def test_zero(self):
        assert format_size(0) == "0 Mo"


class TestFormatBytes:
    def test_megabytes(self):
        result = format_bytes(500 * 1024 * 1024)
        assert "Mo" in result

    def test_gigabytes(self):
        result = format_bytes(2 * 1024 * 1024 * 1024)
        assert "Go" in result

    def test_zero(self):
        assert format_bytes(0) == "0 Mo"


class TestFormatSpeed:
    def test_mbps(self):
        result = format_speed(5 * 1024 * 1024)
        assert "Mo/s" in result

    def test_kbps(self):
        result = format_speed(500 * 1024)
        assert "Ko/s" in result

    def test_zero(self):
        result = format_speed(0)
        assert "Ko/s" in result


class TestFormatEta:
    def test_seconds(self):
        result = format_eta(30)
        assert "30s" in result

    def test_minutes(self):
        result = format_eta(120)
        assert "min" in result

    def test_hours(self):
        result = format_eta(7200)
        assert "h" in result

    def test_negative(self):
        assert format_eta(-1) == ""

    def test_too_large(self):
        assert format_eta(100000) == ""


class TestFormatProgressLine:
    def test_returns_empty_for_zero_total(self):
        assert format_progress_line(0, 0, 0.0, -1.0) == ""

    def test_negative_total(self):
        assert format_progress_line(100, -1, 1024.0, 5.0) == ""

    def test_with_label(self):
        result = format_progress_line(50_000_000, 100_000_000, 5_000_000.0, 10.0,
                                       with_label=True)
        assert result.startswith("Téléchargement : 50%")
        assert "Mo/s" in result
        assert "10s" in result

    def test_without_label(self):
        result = format_progress_line(50, 100, 0.0, -1.0)
        assert result.startswith("50%")
        assert "Téléchargement" not in result

    def test_no_eta_when_negative(self):
        result = format_progress_line(50, 100, 1024.0, -1.0)
        assert "restantes" not in result


class TestAppendPartInfo:
    def test_appends_when_absent(self):
        result = append_part_info("50% — 50 Mo / 100 Mo", 1, 3)
        assert result.endswith("partie 1/3")
        assert "50%" in result

    def test_replaces_existing(self):
        line = "50% — 50 Mo / 100 Mo — partie 1/3"
        result = append_part_info(line, 2, 3)
        assert result.count("partie") == 1
        assert "partie 2/3" in result

    def test_empty_line(self):
        result = append_part_info("", 1, 5)
        assert result == " — partie 1/5"


class TestSpeedTracker:
    def test_initial_speed_zero(self):
        t = SpeedTracker()
        assert t.speed == 0.0

    def test_eta_no_data(self):
        t = SpeedTracker()
        assert t.eta(0, 1000) == -1.0

    def test_reset(self):
        t = SpeedTracker()
        t.update(100)
        t.reset()
        assert t.speed == 0.0

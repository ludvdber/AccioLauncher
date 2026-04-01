"""Tests pour src/core/formatting.py et src/ui/speed_tracker.py"""

from src.core.formatting import format_size, format_bytes, format_speed, format_eta
from src.ui.speed_tracker import SpeedTracker


class TestFormatSize:
    def test_megabytes(self):
        assert format_size(500) == "500 Mo"

    def test_gigabytes(self):
        assert format_size(1500) == "1.5 Go"

    def test_exact_threshold(self):
        assert format_size(1000) == "1.0 Go"

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

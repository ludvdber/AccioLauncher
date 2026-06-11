"""Tests pour src/core/formatting.py — helpers purs (langue par défaut : fr)."""

from datetime import date

from src.core.formatting import (
    append_part_info,
    format_playtime,
    format_progress_line,
    format_relative_date,
)


class TestFormatPlaytime:
    def test_minutes(self):
        assert format_playtime(45 * 60) == "45 min de jeu"

    def test_minimum_one_minute(self):
        assert format_playtime(15) == "1 min de jeu"

    def test_hours_with_minutes(self):
        assert format_playtime(90 * 60) == "1 h 30 min de jeu"

    def test_round_hours(self):
        assert format_playtime(2 * 3600) == "2 h de jeu"

    def test_many_hours_drop_minutes(self):
        # Au-delà de 10 h, les minutes n'apportent rien
        assert format_playtime(14 * 3600 + 25 * 60) == "14 h de jeu"


class TestFormatRelativeDate:
    _TODAY = date(2026, 6, 11)

    def test_today(self):
        assert format_relative_date("2026-06-11", today=self._TODAY) == "aujourd'hui"

    def test_yesterday(self):
        assert format_relative_date("2026-06-10", today=self._TODAY) == "hier"

    def test_two_days_ago(self):
        assert format_relative_date("2026-06-09", today=self._TODAY) == "avant-hier"

    def test_days_ago(self):
        assert format_relative_date("2026-06-01", today=self._TODAY) == "il y a 10 jours"

    def test_old_date_absolute(self):
        assert format_relative_date("2026-01-15", today=self._TODAY) == "15/01/2026"

    def test_invalid_passthrough(self):
        assert format_relative_date("???", today=self._TODAY) == "???"


class TestAppendPartInfo:
    def test_appends_suffix(self):
        assert append_part_info("42%", 2, 3) == "42% — partie 2/3"

    def test_replaces_existing_suffix(self):
        line = append_part_info("42% — partie 1/3", 2, 3)
        assert line == "42% — partie 2/3"


class TestFormatProgressLine:
    def test_zero_total_empty(self):
        assert format_progress_line(0, 0, 0.0, -1.0) == ""

    def test_with_label_prefix(self):
        line = format_progress_line(50, 100, 1024.0, -1.0, with_label=True)
        assert line.startswith("Téléchargement : 50%")

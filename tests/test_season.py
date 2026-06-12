"""Tests pour src/ui/season.py — résolution de saison, sans Qt."""

from datetime import date

from src.ui.season import current_season, resolve


class TestCurrentSeason:
    def test_october_is_halloween(self):
        assert current_season(date(2026, 10, 15)) == "halloween"

    def test_december_is_noel(self):
        assert current_season(date(2026, 12, 25)) == "noel"

    def test_early_january_is_noel(self):
        assert current_season(date(2027, 1, 5)) == "noel"

    def test_late_january_is_none(self):
        assert current_season(date(2027, 1, 7)) == "aucune"

    def test_june_is_none(self):
        assert current_season(date(2026, 6, 11)) == "aucune"


class TestResolve:
    def test_auto_follows_date(self):
        assert resolve("auto", date(2026, 10, 1)) == "halloween"
        assert resolve("auto", date(2026, 6, 11)) == "aucune"

    def test_manual_choice_wins(self):
        assert resolve("noel", date(2026, 6, 11)) == "noel"
        assert resolve("aucune", date(2026, 12, 25)) == "aucune"

    def test_unknown_value_falls_back(self):
        assert resolve("citrouille", date(2026, 10, 1)) == "aucune"

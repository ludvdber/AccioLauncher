"""Tests pour le helper de tri date utilisé par versions_dialog.

Le helper est gardé hors classe pour rester testable sans Qt.
"""

from src.ui.versions_dialog import _date_sort_key


class TestDateSortKey:
    def test_iso_format(self):
        assert _date_sort_key("2026-04-29") == (2026, 4, 29)

    def test_zero_padded(self):
        # Les deux formats donnent la même clé sémantique (4 < 12 quel que soit le pad)
        a = _date_sort_key("2026-3-08")
        b = _date_sort_key("2026-03-08")
        assert a == b == (2026, 3, 8)

    def test_invalid_returns_zero_tuple(self):
        # Ne crash pas, retourne un tuple bas pour pousser l'entrée en bas du tri.
        assert _date_sort_key("not-a-date") == (0,)
        assert _date_sort_key("") == (0,)
        assert _date_sort_key(None) == (0,)  # type: ignore[arg-type]

    def test_sort_stability(self):
        dates = ["2026-04-29", "2025-12-31", "2026-01-01", "2026-04-29"]
        sorted_dates = sorted(dates, key=_date_sort_key, reverse=True)
        assert sorted_dates[0] == "2026-04-29"
        assert sorted_dates[1] == "2026-04-29"
        assert sorted_dates[-1] == "2025-12-31"

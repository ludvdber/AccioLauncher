"""Tests pour src/core/formatting.py — helpers purs (langue par défaut : fr)."""

from datetime import date

import pytest

from src.core.formatting import (
    append_part_info,
    format_bytes,
    format_eta,
    format_playtime,
    format_progress_line,
    format_relative_date,
    format_size,
    format_speed,
)
from src.core.i18n import set_language


class TestUnitsI18n:
    """Régression : les unités de taille/vitesse doivent suivre la langue.

    Bug d'audit : « 431 Mo » / « 132 Go » / « Ko/s » restaient français même en EN.
    """

    @pytest.fixture(autouse=True)
    def _restore_lang(self):
        yield
        set_language("fr")

    def test_size_french(self):
        set_language("fr")
        assert format_size(431) == "431 Mo"
        assert format_size(2500) == "2,5 Go"

    def test_size_english(self):
        set_language("en")
        assert format_size(431) == "431 MB"
        assert format_size(2500) == "2.5 GB"

    def test_bytes_english(self):
        set_language("en")
        assert format_bytes(500 * 1024 * 1024) == "500 MB"

    def test_speed_english(self):
        set_language("en")
        assert format_speed(5 * 1024 * 1024) == "5.0 MB/s"
        assert format_speed(200 * 1024) == "200 KB/s"


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


class TestSeparateurDecimal:
    """« 1.1 Go » dans une interface française est une faute, et elle se voit sur
    chaque poids de jeu — donc partout.

    Le séparateur vient du bloc `_meta` du fichier de langue : ajouter une langue
    doit rester un fichier à déposer, jamais une table à éditer dans le Python.
    """

    @pytest.fixture(autouse=True)
    def _restore_lang(self):
        yield
        set_language("fr")

    def test_virgule_en_francais_point_en_anglais(self):
        set_language("fr")
        assert format_size(2500) == "2,5 Go"
        set_language("en")
        assert format_size(2500) == "2.5 GB"

    def test_l_espagnol_aussi_prend_la_virgule(self):
        set_language("es")
        assert format_size(2500).startswith("2,5")

    def test_toutes_les_valeurs_a_virgule_suivent(self):
        """Quatre fonctions affichent une décimale : les quatre doivent suivre,
        sinon on lit « 4,6 Go » et « 3.4 Mo/s » sur le même écran."""
        set_language("fr")
        assert format_bytes(2500 * 1024 * 1024).startswith("2,5")
        assert format_speed(3.4 * 1024 * 1024) == "3,4 Mo/s"
        assert "2,5" in format_eta(9000)

    def test_une_valeur_aberrante_ne_passe_pas(self):
        """Un fichier de langue contribué peut tout contenir : un séparateur
        fantaisiste au milieu d'un nombre serait illisible."""
        from src.core.i18n import LanguageInfo, decimal_separator
        assert LanguageInfo("xx", "X", ()).decimal == ","
        set_language("fr")
        assert decimal_separator() == ","

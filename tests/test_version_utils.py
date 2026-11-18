"""Tests pour src/core/version_utils.py"""

from src.core.version_utils import compare_versions


class TestCompareVersions:
    def test_equal(self):
        assert compare_versions("1.0", "1.0") == 0

    def test_greater(self):
        assert compare_versions("1.1", "1.0") > 0

    def test_less(self):
        assert compare_versions("1.0", "1.1") < 0

    def test_multi_digit(self):
        assert compare_versions("0.11", "0.7") > 0

    def test_different_length(self):
        assert compare_versions("1.0.0", "1.0") == 0
        assert compare_versions("1.0.1", "1.0") > 0

    def test_v_prefix(self):
        assert compare_versions("v1.2", "1.2") == 0
        assert compare_versions("v2.0", "v1.9") > 0

    def test_major(self):
        assert compare_versions("2.0", "1.9") > 0

    def test_patch(self):
        assert compare_versions("1.0.2", "1.0.1") > 0


class TestComposantsDouteux:
    """Audit du 2026-11-16."""

    def test_un_chiffre_unicode_vaut_zero_sans_lever(self):
        # « ² » passe `str.isdigit()`, mais `int("²")` lève ValueError.
        assert compare_versions("1.²", "1.0") == 0

    def test_un_suffixe_garde_le_numero_qui_le_precede(self):
        assert compare_versions("1.0.5-rc1", "1.0.4") > 0

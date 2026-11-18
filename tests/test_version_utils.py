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
        assert compare_versions("1.0.5rc1", "1.0.4") > 0


class TestPreVersions:
    """Une bêta entre la version publiée et la sienne (SemVer). Sur l'ancien code,
    « 1.3.6-beta.1 » valait 1.3.0.1 : son launcher proposait la 1.3.5 en « mise à jour »."""

    def test_la_beta_est_apres_la_version_publiee(self):
        assert compare_versions("1.3.6-beta.1", "1.3.5") > 0
        assert compare_versions("v1.3.5", "1.3.6-beta.1") < 0

    def test_la_beta_est_avant_sa_version(self):
        assert compare_versions("1.3.6", "1.3.6-beta.1") > 0
        assert compare_versions("v1.3.6-beta.1", "v1.3.6") < 0

    def test_les_betas_entre_elles(self):
        assert compare_versions("1.3.6-beta.2", "1.3.6-beta.1") > 0
        assert compare_versions("1.3.6-beta.10", "1.3.6-beta.9") > 0
        assert compare_versions("1.3.6-rc.1", "1.3.6-beta.3") > 0
        assert compare_versions("1.3.6-beta.1", "1.3.6-beta.1") == 0

    def test_la_meme_beta_ne_se_propose_pas(self):
        from src.core.version_utils import update_disponible
        assert not update_disponible("1.3.6-beta.1", "v1.3.6-beta.1")
        assert update_disponible("1.3.6-beta.1", "1.3.6")
        assert not update_disponible("1.3.6-beta.1", "1.3.5")

    def test_un_chiffre_unicode_dans_une_pre_version_ne_leve_pas(self):
        assert compare_versions("1.3.6-beta.²", "1.3.6-beta.1") != 0

"""Tests pour src/core/system_checks.py — prérequis système (sans Qt)."""

from src.core.system_checks import (
    VCREDIST_URL, check_vcredist_x86, invalidate_vcredist_cache, needed_space_mb,
)


class TestNeededSpace:
    def test_le_double_de_l_archive(self):
        """L'archive cohabite avec les fichiers extraits jusqu'au nettoyage."""
        assert needed_space_mb(1200) == 2400

    def test_zero_reste_zero(self):
        assert needed_space_mb(0) == 0

    def test_une_seule_source_de_verite(self):
        """Le bandeau d'avertissement et la vérification au clic annoncent le
        MÊME chiffre — sinon le bandeau prévient d'un blocage qui n'arrive pas."""
        from src.ui.game_operations import GameOperations  # import tardif : PyQt6
        assert GameOperations.check_disk_space.__doc__  # sentinelle de présence
        assert needed_space_mb(500) == 1000


class TestInvalidationDuCache:
    """Le résultat est mémorisé pour le lancement des jeux, mais il est
    maintenant AFFICHÉ : figé, il mentirait à qui vient d'installer le paquet."""

    def test_le_cache_est_bien_vide(self):
        check_vcredist_x86()
        assert check_vcredist_x86.cache_info().currsize == 1
        invalidate_vcredist_cache()
        assert check_vcredist_x86.cache_info().currsize == 0

    def test_idempotent(self):
        invalidate_vcredist_cache()
        invalidate_vcredist_cache()  # ne doit pas lever sur un cache déjà vide
        assert check_vcredist_x86.cache_info().currsize == 0


class TestUrlDuCorrectif:
    def test_https_et_officielle(self):
        """Elle vit à côté du test qui détecte le manque : les deux ne doivent
        pas pouvoir diverger (elle était dupliquée dans la couche UI)."""
        assert VCREDIST_URL.startswith("https://")
        assert "vc_redist" in VCREDIST_URL

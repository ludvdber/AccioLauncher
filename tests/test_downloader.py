"""Tests pour src/core/downloader.py — fonctions utilitaires."""

import pytest

from src.core.downloader import Downloader, SIZE_OVERHEAD_FACTOR, _validate_url


class TestValidateUrl:
    def test_https_valid(self):
        _validate_url("https://example.com/file.7z")  # No exception

    def test_http_rejected(self):
        with pytest.raises(ValueError, match="Protocole non autorisé"):
            _validate_url("http://example.com/file.7z")

    def test_ftp_rejected(self):
        with pytest.raises(ValueError, match="Protocole non autorisé"):
            _validate_url("ftp://example.com/file.7z")

    def test_no_hostname(self):
        with pytest.raises(ValueError, match="pas de hostname"):
            _validate_url("https://")

    def test_empty(self):
        with pytest.raises(ValueError):
            _validate_url("")

    def test_file_protocol(self):
        with pytest.raises(ValueError, match="Protocole non autorisé"):
            _validate_url("file:///etc/passwd")


class TestSizeCap:
    """expected_size_mb=N → cap interne = N * 1.5 * 1MiB."""

    def test_zero_means_no_cap(self, tmp_path):
        dl = Downloader(url="https://x.test/a.7z", destination=tmp_path / "a.7z",
                        expected_size_mb=0)
        assert dl._max_total_bytes == 0

    def test_positive_sets_cap(self, tmp_path):
        dl = Downloader(url="https://x.test/a.7z", destination=tmp_path / "a.7z",
                        expected_size_mb=100)
        expected = int(100 * SIZE_OVERHEAD_FACTOR * 1024 * 1024)
        assert dl._max_total_bytes == expected

    def test_negative_treated_as_unbounded(self, tmp_path):
        dl = Downloader(url="https://x.test/a.7z", destination=tmp_path / "a.7z",
                        expected_size_mb=-50)
        assert dl._max_total_bytes == 0

    def test_default_overhead_factor(self):
        # Régression : si quelqu'un baisse le facteur sous 1.0, des téléchargements
        # légitimes seront refusés. Le facteur doit rester ≥ 1.2 (marge 20 %).
        assert SIZE_OVERHEAD_FACTOR >= 1.2


class TestSignals:
    def test_finished_not_shadowed(self, tmp_path):
        """Régression : le signal métier ne doit PAS s'appeler `finished` —
        ça masquerait QThread.finished (utilisé pour le nettoyage différé)."""
        dl = Downloader(url="https://x.test/a.7z", destination=tmp_path / "a.7z")
        assert dl.finished.signal == "2finished()"  # natif QThread, sans argument
        assert dl.download_finished.signal == "2download_finished(QString)"

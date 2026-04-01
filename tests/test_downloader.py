"""Tests pour src/core/downloader.py — fonctions utilitaires."""

import pytest

from src.core.downloader import _validate_url


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

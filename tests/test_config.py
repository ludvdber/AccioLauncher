"""Tests pour src/core/config.py"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.config import Config, get_documents_dir, APP_VERSION


class TestGetDocumentsDir:
    def test_returns_path(self):
        result = get_documents_dir()
        assert isinstance(result, Path)
        assert result.is_absolute()

    def test_fallback_on_non_windows(self):
        with patch.object(sys, "platform", "linux"):
            result = get_documents_dir()
            assert "Documents" in str(result)


class TestConfig:
    def test_defaults(self):
        c = Config()
        assert c.langue == "fr"
        assert c.delete_archives is True
        assert c.resume_downloads is True
        assert c.check_updates is True
        assert c.autoplay_videos is True
        assert c.mute_videos is False
        assert c.dismissed_launcher_version == ""
        assert c.installed_versions == {}

    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            c = Config(install_path=tmp_path / "games", cache_path=tmp_path / "cache")
            c.installed_versions = {"hp1": "1.0", "hp3": "1.1"}
            c.save()

            assert config_file.exists()
            loaded = Config.load()
            assert loaded.installed_versions == {"hp1": "1.0", "hp3": "1.1"}
            assert loaded.install_path == tmp_path / "games"

    def test_load_corrupted(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("NOT JSON", encoding="utf-8")
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            c = Config.load()
            # Doit retourner les valeurs par défaut
            assert c.langue == "fr"
            assert c.installed_versions == {}

    def test_load_missing(self, tmp_path):
        config_file = tmp_path / "nonexistent.json"
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            c = Config.load()
            assert c.langue == "fr"

    def test_exists(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            assert Config.exists() is False
            config_file.write_text("{}", encoding="utf-8")
            assert Config.exists() is True

    def test_app_version_format(self):
        parts = APP_VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

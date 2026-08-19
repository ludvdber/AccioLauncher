"""Tests pour src/core/config.py"""

import sys
from pathlib import Path
from unittest.mock import patch


from src.core.config import APP_VERSION, Config, DEFAULT_LANGUAGE, get_documents_dir


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
        assert c.langue == DEFAULT_LANGUAGE
        assert c.delete_archives is True
        assert c.autoplay_videos is True
        # Muet par défaut : un logiciel ne doit pas faire de bruit à sa
        # première ouverture (le son se rétablit d'un clic).
        assert c.mute_videos is True
        assert c.dismissed_launcher_version == ""
        assert c.installed_versions == {}

    def test_load_ignores_obsolete_resume_downloads(self, tmp_path):
        """Tolérant aux configs antérieures avec resume_downloads."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            '{"langue":"fr","resume_downloads":true,"delete_archives":false}',
            encoding="utf-8",
        )
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            c = Config.load()
            assert c.delete_archives is False
            assert not hasattr(c, "resume_downloads")

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

    def test_roundtrip_champs_2026_06(self, tmp_path):
        """Régression : chaque nouveau champ doit survivre à save() → load().

        Un champ ajouté au dataclass mais oublié dans save() ou load() retombe
        silencieusement sur sa valeur par défaut au redémarrage.
        """
        config_file = tmp_path / "config.json"
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            c = Config(install_path=tmp_path, cache_path=tmp_path / ".cache")
            c.theme = "serpentard"
            c.season = "noel"
            c.kofi_milestone_thanked = True
            c.discord_presence = False
            c.playtime_seconds = {"hp1": 3600}
            c.last_played = {"hp1": "2026-06-11"}
            c.save()

            loaded = Config.load()
            assert loaded.theme == "serpentard"
            assert loaded.season == "noel"
            assert loaded.kofi_milestone_thanked is True
            assert loaded.discord_presence is False
            assert loaded.playtime_seconds == {"hp1": 3600}
            assert loaded.last_played == {"hp1": "2026-06-11"}

    def test_load_corrupted(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("NOT JSON", encoding="utf-8")
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            c = Config.load()
            # Doit retourner les valeurs par défaut
            assert c.langue == DEFAULT_LANGUAGE
            assert c.installed_versions == {}

    def test_load_type_invalid_json_falls_back(self, tmp_path):
        """Régression d'audit : un JSON valide mais mal typé (config éditée à la
        main) ne doit JAMAIS crasher le boot — repli sur les défauts."""
        import json
        config_file = tmp_path / "config.json"
        cases = [
            {"install_path": 42},              # int au lieu de str -> Path(int) crashait
            [1, 2, 3],                          # racine liste -> .get() crashait
            {"installed_versions": "oops"},    # str au lieu de dict -> .get() crashait ensuite
            {"playtime_seconds": [1, 2]},      # liste au lieu de dict
        ]
        for payload in cases:
            config_file.write_text(json.dumps(payload), encoding="utf-8")
            with patch("src.core.config.CONFIG_FILE_PATH", config_file):
                c = Config.load()
                assert c.langue == DEFAULT_LANGUAGE
                assert isinstance(c.install_path, Path)
                assert isinstance(c.installed_versions, dict)
                assert isinstance(c.playtime_seconds, dict)

    def test_load_missing(self, tmp_path):
        config_file = tmp_path / "nonexistent.json"
        with patch("src.core.config.CONFIG_FILE_PATH", config_file):
            c = Config.load()
            assert c.langue == DEFAULT_LANGUAGE

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

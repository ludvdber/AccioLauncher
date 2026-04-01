"""Tests pour src/core/game_data.py"""

import json
import pytest

from src.core.game_data import (
    GameData, GameVersion, Catalog, ConfigFile, IniPatch,
    PreLaunch, PostInstall, _parse_catalog,
)


MINIMAL_GAME = {
    "id": "hp_test",
    "name": "HP Test",
    "year": 2001,
    "description": "Test game",
    "developer": "TestDev",
    "executable": "HPTest/Game.exe",
    "cover_image": "test_cover.jpg",
}

FULL_GAME = {
    **MINIMAL_GAME,
    "tags": ["Action", "Aventure"],
    "latest_version": "1.1",
    "recommended_version": "1.1",
    "versions": [
        {
            "version": "1.1",
            "date": "2026-01-01",
            "download_url": "https://example.com/v1.1.7z",
            "download_parts": None,
            "size_mb": 500,
            "changes": ["Fix A", "Fix B"],
        },
        {
            "version": "1.0",
            "date": "2025-01-01",
            "download_url": "https://example.com/v1.0.7z",
            "download_parts": None,
            "size_mb": 480,
            "changes": ["Initial release"],
        },
    ],
    "pre_launch": {
        "create_files": ["%DOCUMENTS%\\Test\\Running.ini"],
        "ini_patches": [
            {
                "file": "%DOCUMENTS%\\Test\\Game.ini",
                "section": "Engine.Engine",
                "key": "GameRenderDevice",
                "value": "D3D11Drv.D3D11RenderDevice",
                "fallback": "D3DDrv.D3DRenderDevice",
            },
        ],
    },
    "post_install": {
        "registry": ["HKCU\\Software\\Test=value"],
        "config_files": [
            {"source": "config/Game.ini", "destination": "~/Documents/Test/Game.ini"},
        ],
    },
}


class TestGameVersion:
    def test_from_dict(self):
        v = GameVersion.from_dict(FULL_GAME["versions"][0])
        assert v.version == "1.1"
        assert v.size_mb == 500
        assert len(v.changes) == 2
        assert v.download_parts is None

    def test_from_dict_defaults(self):
        v = GameVersion.from_dict({})
        assert v.version == "1.0"
        assert v.size_mb == 0
        assert v.changes == ()


class TestIniPatch:
    def test_from_dict_with_fallback(self):
        p = IniPatch.from_dict(FULL_GAME["pre_launch"]["ini_patches"][0])
        assert p.key == "GameRenderDevice"
        assert p.fallback == "D3DDrv.D3DRenderDevice"

    def test_from_dict_without_fallback(self):
        p = IniPatch.from_dict({
            "file": "test.ini", "section": "S", "key": "K", "value": "V",
        })
        assert p.fallback is None


class TestGameData:
    def test_from_dict_minimal(self):
        g = GameData.from_dict(MINIMAL_GAME)
        assert g.id == "hp_test"
        assert g.tags == ()
        assert g.pre_launch is None

    def test_from_dict_full(self):
        g = GameData.from_dict(FULL_GAME)
        assert len(g.versions) == 2
        assert len(g.tags) == 2
        assert g.pre_launch is not None
        assert len(g.pre_launch.ini_patches) == 1
        assert g.pre_launch.ini_patches[0].fallback == "D3DDrv.D3DRenderDevice"
        assert len(g.post_install.config_files) == 1

    def test_missing_fields_raises(self):
        with pytest.raises(ValueError, match="Champs manquants"):
            GameData.from_dict({"id": "x"})

    def test_current_download(self):
        g = GameData.from_dict(FULL_GAME)
        dl = g.current_download
        assert dl is not None
        assert dl.version == "1.1"  # recommended_version

    def test_get_version(self):
        g = GameData.from_dict(FULL_GAME)
        assert g.get_version("1.0") is not None
        assert g.get_version("1.0").size_mb == 480
        assert g.get_version("9.9") is None


class TestParseCatalog:
    def test_dict_format(self):
        raw = {
            "catalog_version": "0.7",
            "catalog_url": "https://example.com/games.json",
            "games": [MINIMAL_GAME],
        }
        cat = _parse_catalog(raw)
        assert cat.catalog_version == "0.7"
        assert len(cat.games) == 1

    def test_list_format_legacy(self):
        raw = [MINIMAL_GAME]
        cat = _parse_catalog(raw)
        assert cat.catalog_version == "0"
        assert len(cat.games) == 1

    def test_empty(self):
        cat = _parse_catalog({"games": []})
        assert cat.games == ()

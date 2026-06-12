"""Tests pour src/ui/onboarding.py — détection des installations existantes (pur)."""

from src.core.game_data import GameData
from src.ui.onboarding import detect_installed_games


def _game(game_id: str, executable: str) -> GameData:
    return GameData.from_dict({
        "id": game_id, "name": game_id.upper(), "year": 2001, "description": "d",
        "developer": "Dev", "executable": executable, "cover_image": f"{game_id}.jpg",
    })


class TestDetectInstalledGames:
    def test_detects_game_with_exe(self, tmp_path):
        (tmp_path / "HP1" / "System").mkdir(parents=True)
        (tmp_path / "HP1" / "System" / "HP.exe").write_bytes(b"x")
        games = [_game("hp1", "HP1/System/HP.exe"), _game("hp2", "HP2/System/Game.exe")]

        found = detect_installed_games(tmp_path, games)

        assert len(found) == 1
        game, src = found[0]
        assert game.id == "hp1"
        assert src == tmp_path / "HP1"

    def test_folder_without_exe_ignored(self, tmp_path):
        (tmp_path / "HP1" / "System").mkdir(parents=True)  # pas d'exe dedans
        found = detect_installed_games(tmp_path, [_game("hp1", "HP1/System/HP.exe")])
        assert found == []

    def test_empty_parent(self, tmp_path):
        assert detect_installed_games(tmp_path, [_game("hp1", "HP1/System/HP.exe")]) == []

"""Tests pour find_import_error (« J'ai déjà ce jeu ») — fonction pure, sans Qt."""

from src.core.game_data import GameData
from src.ui.game_detail_handlers import find_import_error

_GAME_DICT = {
    "id": "hp_test", "name": "HP Test", "year": 2001, "description": "d",
    "developer": "Dev", "executable": "HPTest/System/Game.exe", "cover_image": "x.jpg",
}


def _game() -> GameData:
    return GameData.from_dict(_GAME_DICT)


class TestFindImportError:
    def test_valid_source(self, tmp_path):
        source = tmp_path / "MonVieuxJeu"
        (source / "System").mkdir(parents=True)
        (source / "System" / "Game.exe").write_text("fake")
        install = tmp_path / "install"
        install.mkdir()
        assert find_import_error(_game(), source, install) is None

    def test_missing_exe(self, tmp_path):
        source = tmp_path / "DossierVide"
        source.mkdir()
        install = tmp_path / "install"
        install.mkdir()
        err = find_import_error(_game(), source, install)
        assert err is not None
        assert "introuvable" in err

    def test_destination_already_exists(self, tmp_path):
        source = tmp_path / "MonVieuxJeu"
        (source / "System").mkdir(parents=True)
        (source / "System" / "Game.exe").write_text("fake")
        install = tmp_path / "install"
        (install / "HPTest").mkdir(parents=True)
        err = find_import_error(_game(), source, install)
        assert err is not None
        assert "existe déjà" in err

    def test_single_file_executable_unsupported(self, tmp_path):
        game = GameData.from_dict({**_GAME_DICT, "executable": "game.exe"})
        err = find_import_error(game, tmp_path, tmp_path)
        assert err is not None
        assert "supporte pas" in err

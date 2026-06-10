"""Tests pour src/ui/carousel.py — focus sur set_games() (CRITICAL #4)."""

import pytest

pytest.importorskip("pytestqt")

from src.core.game_data import GameData  # noqa: E402
from src.ui.carousel import Carousel  # noqa: E402


_GAME_DICT = {
    "id": "x", "name": "X", "year": 2001, "description": "d",
    "developer": "Dev", "executable": "X/x.exe", "cover_image": "x.jpg",
}


class _FakeManager:
    def is_installed(self, _: str) -> bool: return False
    def has_update(self, _: str) -> bool: return False
    def installed_version(self, _: str) -> str | None: return None


def _make_game(game_id: str) -> GameData:
    return GameData.from_dict({**_GAME_DICT, "id": game_id, "name": game_id.upper()})


class TestCarouselSetGames:
    def test_initial_population(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b")], _FakeManager())
        qtbot.addWidget(c)
        assert len(c._items) == 2
        assert c.current_index == 0

    def test_grow(self, qtbot):
        c = Carousel([_make_game("a")], _FakeManager())
        qtbot.addWidget(c)
        c.set_games([_make_game("a"), _make_game("b"), _make_game("c")])
        assert len(c._items) == 3

    def test_shrink(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b"), _make_game("c")],
                     _FakeManager())
        qtbot.addWidget(c)
        c.set_games([_make_game("a")])
        assert len(c._items) == 1
        assert c.current_index == 0

    def test_replace_completely(self, qtbot):
        c = Carousel([_make_game("hp1")], _FakeManager())
        qtbot.addWidget(c)
        c.set_games([_make_game("hp7a"), _make_game("hp7b")])
        assert [item.game.id for item in c._items] == ["hp7a", "hp7b"]

    def test_empty_list(self, qtbot):
        c = Carousel([_make_game("a")], _FakeManager())
        qtbot.addWidget(c)
        c.set_games([])
        assert c._items == []

    def test_select_emits_signal(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b"), _make_game("c")],
                     _FakeManager())
        qtbot.addWidget(c)
        with qtbot.waitSignal(c.game_selected, timeout=500) as sig:
            c.select(2)
        assert sig.args == [2]

    def test_select_no_signal_on_same_index(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b")], _FakeManager())
        qtbot.addWidget(c)
        with qtbot.assertNotEmitted(c.game_selected):
            c.select(0)  # déjà current

    def test_select_navigation(self, qtbot):
        c = Carousel([_make_game("a"), _make_game("b"), _make_game("c")],
                     _FakeManager())
        qtbot.addWidget(c)
        c.select_next()
        assert c.current_index == 1
        c.select_next()
        assert c.current_index == 2
        c.select_next()  # wrap
        assert c.current_index == 0
        c.select_prev()  # wrap arrière
        assert c.current_index == 2

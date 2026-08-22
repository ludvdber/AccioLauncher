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
    def is_new(self, _: str) -> bool: return False
    def mark_seen(self, _: str) -> None: pass


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


class TestSelectionPreserveeAuReload:
    """Reconstruire la bande ne doit pas ramener la surbrillance sur l'item 0.

    Cas réel (capture de Ludo, 2026-08-21) : la fiche s'ouvre sur le dernier
    jeu joué (HP6), puis le catalogue distant arrive, `set_games` reconstruit
    la bande et remet l'index à 0. Résultat : HP1 surligné, HP6 affiché
    au-dessus. Le second effet est pire que le premier — `select` sort tôt
    quand l'index ne change pas, donc cliquer sur HP1 ne faisait RIEN et
    l'utilisateur ne pouvait plus revenir au jeu qu'il voyait surligné.
    """

    def test_garde_le_jeu_courant(self, qtbot):
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        c.set_games(jeux)
        assert c.current_index == 2
        assert c.current_game_id() == "hp6"
        assert [item.selected for item in c._items] == [False, False, True]

    def test_id_explicite_prioritaire(self, qtbot):
        """L'appelant décide : c'est lui qui pose la fiche, la bande le suit."""
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.set_games(jeux, selected_id="hp2")
        assert c.current_index == 1
        assert c.current_game_id() == "hp2"

    def test_repli_sur_zero_si_le_jeu_disparait(self, qtbot):
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        c.set_games([_make_game("hp1"), _make_game("hp2")])
        assert c.current_index == 0
        assert c._items[0].selected is True

    def test_reload_reste_muet(self, qtbot):
        """Contrat inchangé : `set_games` n'emet pas, l'appelant pose la fiche."""
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        with qtbot.assertNotEmitted(c.game_selected):
            c.set_games(jeux)

    def test_clic_sur_le_jeu_affiche_apres_reload(self, qtbot):
        """Un clic sur l'item VOISIN doit encore basculer la fiche.

        Garde-fou contre la correction inverse (figer l'index sans bouger la
        surbrillance) : la bande doit rester navigable apres reconstruction.
        """
        jeux = [_make_game("hp1"), _make_game("hp2"), _make_game("hp6")]
        c = Carousel(jeux, _FakeManager())
        qtbot.addWidget(c)
        c.select(2)
        c.set_games(jeux)
        with qtbot.waitSignal(c.game_selected, timeout=500) as sig:
            c.select(0)
        assert sig.args == [0]
        assert c.current_game_id() == "hp1"

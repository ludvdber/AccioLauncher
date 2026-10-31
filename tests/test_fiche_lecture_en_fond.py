"""La partie de la fiche se lit dans un fil, jamais dans celui de l'interface
(Ludo, 2026-10-31). Sur une vraie MainWindow : la ligne « Dernière partie »
au-dessus de JOUER et le bloc du folio arrivent quand la lecture revient, une
lecture dépassée ne s'affiche pas, et rien ne s'affiche si rien n'est lisible
(règle 107)."""
import threading
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from src.core import folio  # noqa: E402
from src.core.game_manager import GameState  # noqa: E402


def _resume(lieu: str = "Parc de Poudlard") -> folio.Resume:
    releve = folio.Releve(1, Path("Save1.usa"), datetime(2026, 10, 30), lu=True,
                          cartes=frozenset({1, 2, 3}))
    return folio.Resume(releve, lieu, trouvees=3, total=25, quand=datetime(2026, 10, 30))


def _fiche(win, game_id: str):
    jeu = win.manager.get_game_by_id(game_id)
    win.manager._states[game_id] = GameState.INSTALLED
    win._detail.set_game(jeu)
    win._detail._refresh()
    return jeu


def _attendre(qtbot, win):
    qtbot.waitUntil(lambda: not win._detail._info.lecture_en_cours(), timeout=5000)


def test_la_sauvegarde_est_lue_hors_du_fil_de_l_interface(make_window, qtbot, monkeypatch):
    fils = []

    def lire(game, system, langue):
        fils.append(threading.current_thread())
        return _resume() if game.id == "hp1" else None
    monkeypatch.setattr("src.ui.info_panel.lire_resume", lire)
    win = make_window()
    _fiche(win, "hp1")
    _attendre(qtbot, win)
    info = win._detail._info
    assert fils and threading.main_thread() not in fils
    assert info._derniere.isVisibleTo(info) and "Parc de Poudlard" in info._derniere.text()
    assert info._bloc.texte_compte() == "3 cartes sur 25"
    assert win._detail._action_panel.partie_dans_la_fiche, "les statistiques passent dans le bloc"


def test_rien_de_lisible_rien_ne_s_affiche(make_window, qtbot, monkeypatch):
    def illisible(game, system, langue):
        raise ValueError("paquet tronqué")
    monkeypatch.setattr("src.ui.info_panel.lire_resume", illisible)
    win = make_window()
    _fiche(win, "hp1")
    _attendre(qtbot, win)
    info = win._detail._info
    assert info._desc.isVisibleTo(info), "la description reste"
    assert not info._bloc.isVisibleTo(info)
    assert not info.partie_affichee()


def test_une_lecture_depassee_ne_s_affiche_pas_sur_l_autre_fiche(make_window, qtbot, monkeypatch):
    """HP1 se lit lentement ; on passe sur HP3 avant qu'il revienne."""
    lache = threading.Event()

    def lire(game, system, langue):
        if game.id == "hp1":
            lache.wait(5)
            return _resume()
        return None
    monkeypatch.setattr("src.ui.info_panel.lire_resume", lire)
    win = make_window()
    win.manager._states["hp3"] = GameState.INSTALLED
    _fiche(win, "hp1")
    _fiche(win, "hp3")
    lache.set()
    _attendre(qtbot, win)
    info = win._detail._info
    assert win._detail.game.id == "hp3"
    assert not info.partie_affichee() and not info._bloc.isVisibleTo(info)
    # Gardée pour HP1 : y revenir la montre aussitôt, sans repasser par la description.
    _fiche(win, "hp1")
    assert info.partie_affichee() and "Parc de Poudlard" in info._derniere.text()
    _attendre(qtbot, win)


def test_desinstalle_la_partie_s_en_va_sans_lecture(make_window, qtbot, monkeypatch):
    monkeypatch.setattr("src.ui.info_panel.lire_resume", lambda *a: _resume())
    win = make_window()
    _fiche(win, "hp1")
    _attendre(qtbot, win)
    assert win._detail._info.partie_affichee()
    win.manager._states["hp1"] = GameState.NOT_INSTALLED
    win._detail._refresh()
    assert not win._detail._info.lecture_en_cours()
    assert not win._detail._info.partie_affichee()
    assert not win._detail._action_panel.partie_dans_la_fiche

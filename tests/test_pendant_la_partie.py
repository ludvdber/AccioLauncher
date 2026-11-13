"""Pendant une partie, le launcher se fait oublier (audit du 2026-11-13).

- la question « Mise à jour disponible » ne s'ouvre plus par-dessus le jeu : elle revient au retour ;
- les fonds préchargés (≈ 106 Mo) sont rendus au jeu, et reviennent au retour ;
- les paquets des jeux lus par le Carnet et les Collections sont rendus au lancement.
Contre-épreuve : ces tests échouent sur l'ancien code.
"""

from src.core import textures_ue1
from src.ui import dialogues_fenetre
from src.ui.game_session import GameSession


class _PartieFactice:
    """Un jeu qui tourne : `poll()` ne rend rien (comme dans test_parcours)."""
    pid = 4242
    args = ["Game.exe"]

    def poll(self):
        return None


def test_la_mise_a_jour_attend_la_fin_de_la_partie(make_window, monkeypatch):
    win = make_window()
    questions = []
    monkeypatch.setattr(dialogues_fenetre, "proposer_mise_a_jour",
                        lambda *a, **k: questions.append(a) or False)
    win._updates.version = "9.9.9"
    monkeypatch.setattr(GameSession, "nom_en_cours", property(lambda self: "HP3"))
    win._propose_launcher_update()
    assert questions == [], "posée par-dessus le jeu"
    monkeypatch.setattr(GameSession, "nom_en_cours", property(lambda self: ""))
    win._propose_launcher_update()
    assert len(questions) == 1


def test_les_fonds_precharges_sont_rendus_pendant_la_partie(make_window, monkeypatch):
    win = make_window()
    poses = []
    monkeypatch.setattr(win._detail._bg, "precharger", lambda chemins: poses.append(list(chemins)))
    win._on_game_launched("HP3")
    assert poses and poses[-1] == [], "les fonds restaient décodés pendant la partie"
    win._on_game_exited("HP3")
    assert poses[-1], "les fonds ne reviennent pas au retour"


def test_les_paquets_sont_rendus_au_lancement(make_window, monkeypatch):
    win = make_window()
    rendus = []
    monkeypatch.setattr(textures_ue1, "liberer", lambda: rendus.append(True))
    try:
        win._session.demarrer(_PartieFactice(), "HP3", "hp3")
        assert rendus == [True]
    finally:
        win._session.shutdown()

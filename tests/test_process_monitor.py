"""La grâce de 10 s du moniteur de processus n'existe que pour les jeux qui se relancent.

Mesuré par l'audit du 2026-10-07 (P6-005) : « Process initial terminé (code 0),
grâce de 10s… » puis la fin 10 s plus tard, pour HP3, HP4, HP5 et HP6, qui ne se
relancent pas. Seuls HP1 et HP2 ré-exécutent un enfant au chargement d'une
sauvegarde, et c'est pour eux que la grâce existe — la raccourcir ferait croire
leur partie finie en plein chargement.
"""

import pytest

from src.ui.process_monitor import ProcessMonitor


class _Processus:
    args = ["Game.exe"]
    code = None

    def poll(self):
        return self.code


@pytest.fixture
def moniteur(qtbot):
    m = ProcessMonitor()
    m._is_exe_running = lambda nom: False      # sur l'INSTANCE (règle 12)
    yield m
    m.stop()


def _sorties(moniteur):
    vus = []
    moniteur.game_exited.connect(lambda *a: vus.append(a))
    return vus


def test_un_jeu_qui_ne_se_relance_pas_finit_au_premier_sondage(moniteur):
    vus = _sorties(moniteur)
    jeu = _Processus()
    moniteur.start(jeu, "HP5", relance=False)
    jeu.code = 0
    moniteur._poll()
    assert [(n, c) for n, c, _ in vus] == [("HP5", 0)]


def test_un_jeu_qui_se_relance_garde_sa_grace(moniteur):
    vus = _sorties(moniteur)
    jeu = _Processus()
    moniteur.start(jeu, "HP1", relance=True)
    jeu.code = 0
    moniteur._poll()
    moniteur._poll()
    assert vus == [], "10 s pour qu'UE1 redémarre après le chargement d'une sauvegarde"


def test_un_jeu_qui_se_relance_finit_une_fois_la_grace_ecoulee(moniteur, monkeypatch):
    vus = _sorties(moniteur)
    jeu = _Processus()
    moniteur.start(jeu, "HP2", relance=True)
    jeu.code = 0
    moniteur._poll()
    moniteur._grace_until -= 11
    moniteur._poll()
    assert [(n, c) for n, c, _ in vus] == [("HP2", 0)]


def test_un_jeu_relance_sous_le_meme_nom_est_retrouve(moniteur):
    """Le repli par nom reste actif sans relance déclarée : un lanceur qui passe
    la main à l'exe du jeu ne doit pas être pris pour une fin de partie."""
    vus = _sorties(moniteur)
    jeu = _Processus()
    moniteur.start(jeu, "HP6", relance=False)
    jeu.code = 0
    moniteur._is_exe_running = lambda nom: True
    moniteur._poll()
    assert vus == []

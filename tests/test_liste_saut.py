"""« Jouer à … » dans la liste de raccourcis de l'icône Windows (`src.core.liste_saut`).

Rien n'écrit sur la vraie icône : `ecrire` n'est appelé qu'espionné, et
`mettre_a_jour` reste muet tant que main.py n'a pas appelé `activer`.
"""

from pathlib import Path

import pytest

from src.core import liste_saut
from src.core.liste_saut import Entree, commande, entrees, id_demande
from src.ui import raccourci_jouer


def _titre(nom: str) -> str:
    return f"Jouer à {nom}"


class TestEntrees:
    def test_le_plus_recent_d_abord_puis_jamais_joues_dans_l_ordre(self):
        jeux = [("hp1", "HP1", None), ("hp2", "HP2", "2026-10-20"), ("hp3", "HP3", "2026-10-26"),
                ("hp4", "HP4", None)]
        assert [e.titre for e in entrees(jeux, _titre, "A.exe", True, None)] == [
            "Jouer à HP3", "Jouer à HP2", "Jouer à HP1", "Jouer à HP4"]

    def test_a_date_egale_l_ordre_du_catalogue(self):
        jeux = [("hp5", "HP5", "2026-10-26"), ("hp6", "HP6", "2026-10-26")]
        assert [e.titre for e in entrees(jeux, _titre, "A.exe", True, None)] == ["Jouer à HP5", "Jouer à HP6"]

    def test_cinq_au_plus(self):
        jeux = [(f"hp{i}", f"HP{i}", None) for i in range(1, 9)]
        assert len(entrees(jeux, _titre, "A.exe", True, None)) == liste_saut.MAX_ENTREES

    def test_exe_gele_se_relance_lui_meme_avec_son_icone(self):
        (e,) = entrees([("hp5", "HP5", None)], _titre, r"C:\Program Files\Accio\AccioLauncher.exe", True, None)
        assert e == Entree("Jouer à HP5", r"C:\Program Files\Accio\AccioLauncher.exe", "--jouer hp5",
                           r"C:\Program Files\Accio\AccioLauncher.exe")

    def test_depuis_les_sources_python_et_main_py_entre_guillemets(self):
        programme, arguments = commande("hp2", "python.exe", False, Path(r"C:\Mes jeux\main.py"))
        assert programme == "python.exe"
        assert arguments == '"C:\\Mes jeux\\main.py" --jouer hp2'


class TestIdDemande:
    @pytest.mark.parametrize("argv, attendu", [
        (["main.py"], None),
        (["main.py", "--jouer"], None),
        (["main.py", "--jouer", "hp7a"], "hp7a"),
        (["AccioLauncher.exe", "--jouer", "hp5"], "hp5"),
        (["main.py", "--jouer", "../hp5"], None),
        (["main.py", "--jouer", "hp5 & calc"], None),
        (["main.py", "--jouer", "x" * 40], None),
    ])
    def test_seul_un_identifiant_sain_passe(self, argv, attendu):
        assert id_demande(argv) == attendu


class TestEcriture:
    def test_un_refus_de_windows_ne_remonte_pas(self, monkeypatch):
        monkeypatch.setattr(liste_saut.sys, "platform", "win32")

        def refus(_liste):
            raise OSError("BeginList → HRESULT 0x80004005")
        monkeypatch.setattr(liste_saut, "_ecrire", refus)
        assert liste_saut.ecrire([]) is False

    def test_hors_windows_rien(self, monkeypatch):
        monkeypatch.setattr(liste_saut.sys, "platform", "linux")
        monkeypatch.setattr(liste_saut, "_ecrire", lambda _l: pytest.fail("COM appelé hors Windows"))
        assert liste_saut.ecrire([]) is False

    def test_rien_tant_que_main_py_n_a_pas_active(self, monkeypatch):
        monkeypatch.setattr(liste_saut, "_actif", False)
        monkeypatch.setattr(liste_saut, "ecrire", lambda _l: pytest.fail("écrit pendant les tests"))
        liste_saut.mettre_a_jour(object())  # type: ignore[arg-type]


class TestRelaisInstanceUnique:
    def test_le_second_lancement_transmet_le_jeu(self, qtbot, tmp_path):
        """Un vrai second processus : dans le même fil, le tube de Windows perd le message
        (le client raccroche avant que le serveur ait tourné), ce que la poignée de main évite
        entre deux processus — le seul cas réel."""
        import subprocess
        import sys
        import uuid

        from src.ui.single_instance import SingleInstance
        key = f"accio-test-{uuid.uuid4().hex}"
        first = SingleInstance(key)
        assert first.try_acquire() is True
        client = tmp_path / "second.py"
        client.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})\n"
            "from PyQt6.QtCore import QCoreApplication\n"
            "from src.ui.single_instance import SingleInstance\n"
            "app = QCoreApplication([])\n"
            f"sys.exit(0 if SingleInstance({key!r}).try_acquire(jouer='hp4') is False else 1)\n",
            encoding="utf-8")
        with qtbot.waitSignal(first.jouer_requested, timeout=10000) as signal:
            proc = subprocess.Popen([sys.executable, str(client)])
        assert signal.args == ["hp4"]
        assert proc.wait(10) == 0
        first.release()


class TestJouerDemande:
    def test_la_fiche_s_ouvre_et_un_jeu_absent_ne_se_lance_pas(self, make_window, qtbot, monkeypatch):
        lances = []
        monkeypatch.setattr("src.ui.game_detail_handlers.on_play", lambda view, *a: lances.append(view.game.id))
        win = make_window()
        raccourci_jouer.jouer_demande(win, "hp3")
        qtbot.waitUntil(lambda: win._detail.game is not None and win._detail.game.id == "hp3", timeout=3000)
        qtbot.wait(600)
        assert lances == []   # rien d'installé dans la config de test

    def test_un_jeu_installe_se_lance(self, make_window, qtbot, monkeypatch):
        lances = []
        monkeypatch.setattr("src.ui.game_detail_handlers.on_play", lambda view, *a: lances.append(view.game.id))
        from src.core.game_manager import GameState
        win = make_window()
        monkeypatch.setitem(win.manager._states, "hp5", GameState.INSTALLED)
        raccourci_jouer.jouer_demande(win, "hp5")
        qtbot.waitUntil(lambda: lances == ["hp5"], timeout=3000)

    def test_un_identifiant_inconnu_ne_fait_que_montrer_la_fenetre(self, make_window, qtbot, monkeypatch):
        monkeypatch.setattr("src.ui.game_detail_handlers.on_play", lambda *a: pytest.fail("lancé"))
        win = make_window()
        avant = win._detail.game
        raccourci_jouer.jouer_demande(win, "hp99")
        qtbot.wait(500)
        assert win._detail.game is avant

    def test_brancher_refait_la_liste_apres_chaque_partie(self, make_window, monkeypatch):
        refaites = []
        monkeypatch.setattr(liste_saut, "mettre_a_jour", lambda manager: refaites.append(manager))
        monkeypatch.setattr(liste_saut, "activer", lambda: None)
        win = make_window()
        guard = raccourci_jouer.SingleInstance("accio-test-brancher")
        raccourci_jouer.brancher(win, guard)
        assert refaites == [win.manager]
        win._session.terminee.emit("Harry Potter", True, False)
        assert refaites == [win.manager, win.manager]

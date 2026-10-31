"""Reprendre en un clic (`src/core/reprise.py`) : les arguments, et leur trajet jusqu'au jeu."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core import compat, reprise
from src.core.compat import Lanceur
from src.core.config import Config
from src.core.game_data import GameData
from tests.test_game_manager import GAME_DICT, _make_manager

_SAVES = {"root": "documents", "folders": ["Harry Potter"], "files": "Save*.usa"}


@dataclass(frozen=True)
class _Partie:
    emplacement: int
    chemin: Path
    modifie: datetime
    lu: bool = True


def _jeu(jeu_id: str, saves: dict | None = _SAVES) -> GameData:
    return GameData.from_dict({**GAME_DICT, "id": jeu_id, "saves": saves})


class TestArgumentsPour:
    @pytest.mark.parametrize("jeu", ["hp1", "hp3"])
    def test_ue_charge_par_numero_de_fichier(self, jeu):
        assert reprise.arguments_pour(jeu, Path("Save") / "Save2.usa") == ("?load=2",)
        assert reprise.arguments_pour(jeu, Path("save9.USA")) == ("?load=9",)

    def test_hp2_veut_les_deux_arguments(self):
        """`?load=0` seul ouvre la boîte « Menu principal » (essai R2 du 2026-10-15)."""
        assert reprise.arguments_pour("hp2", Path("Slot3") / "Save0.usa") == ("-LOADGAME=0", "-SAVESLOT=3")

    @pytest.mark.parametrize("jeu, chemin", [
        ("hp1", Path("Save.usa")), ("hp1", Path("Save1.bak")), ("hp2", Path("Slot1") / "Save1.usa"),
        ("hp2", Path("Autre") / "Save0.usa"), ("hp4", Path("Save0.usa")),
    ])
    def test_forme_inattendue_menu_du_jeu(self, jeu, chemin):
        assert reprise.arguments_pour(jeu, chemin) == ()


class TestArguments:
    def _avec(self, monkeypatch, parties):
        monkeypatch.setattr(reprise, "_releves", lambda game: parties)

    def test_la_plus_recente(self, monkeypatch):
        self._avec(monkeypatch, [_Partie(1, Path("Save0.usa"), datetime(2026, 10, 1)),
                                 _Partie(3, Path("Save2.usa"), datetime(2026, 10, 20)),
                                 _Partie(2, Path("Save1.usa"), datetime(2026, 10, 5))])
        assert reprise.arguments(_jeu("hp1")) == ("?load=2",)

    def test_plus_recente_illisible_menu_du_jeu(self, monkeypatch):
        """La fiche montre la dernière LISIBLE : ouvrir une autre partie que celle annoncée tromperait."""
        self._avec(monkeypatch, [_Partie(1, Path("Save0.usa"), datetime(2026, 10, 1)),
                                 _Partie(2, Path("Save1.usa"), datetime(2026, 10, 20), lu=False)])
        assert reprise.arguments(_jeu("hp3")) == ()

    def test_sans_partie_menu_du_jeu(self, monkeypatch):
        self._avec(monkeypatch, [])
        assert reprise.arguments(_jeu("hp1")) == ()

    def test_lecture_qui_leve_menu_du_jeu(self, monkeypatch):
        """Le lancement ne dépend jamais de la lecture des sauvegardes."""
        def casse(game):
            raise ValueError("paquet tronqué")
        monkeypatch.setattr(reprise, "_releves", casse)
        assert reprise.arguments(_jeu("hp2")) == ()

    def test_jeux_hors_reprise(self, monkeypatch):
        self._avec(monkeypatch, [_Partie(1, Path("Save0.usa"), datetime(2026, 10, 1))])
        assert reprise.arguments(_jeu("hp4")) == ()
        assert reprise.arguments(_jeu("hp1", saves=None)) == ()


class TestLancement:
    def _lancer(self, tmp_path, monkeypatch, directe: bool):
        m = _make_manager(tmp_path, [_jeu("hp1")])
        m.config.reprise = {"hp1": directe}
        exe = tmp_path / "HPTest" / "System" / "Game.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        monkeypatch.setattr("src.core.game_manager.prerequis_manquants", lambda _r: [])
        for nom in ("unblock_game_dlls", "delete_pre_launch_files",
                    "create_pre_launch_files", "apply_ini_patches"):
            monkeypatch.setattr("src.core.game_manager." + nom, lambda *a: None)
        monkeypatch.setattr(reprise, "arguments", lambda game: ("?load=1",))
        vus: list = []
        monkeypatch.setattr("src.core.game_manager.subprocess.Popen",
                            lambda args, **k: vus.append(args) or object())
        monkeypatch.setattr("src.core.game_manager.GameManager._lancer_sous_wine",
                            staticmethod(lambda g, e, lanceur, k, arguments=(): vus.append([str(e), *arguments]) or object()))
        assert m.launch_game("hp1") is not None
        return vus[0], exe

    def test_les_arguments_vont_au_jeu(self, tmp_path, monkeypatch):
        args, exe = self._lancer(tmp_path, monkeypatch, directe=True)
        assert args == [str(exe), "?load=1"]

    def test_reglage_coupe_menu_du_jeu(self, tmp_path, monkeypatch):
        args, exe = self._lancer(tmp_path, monkeypatch, directe=False)
        assert args == [str(exe)]

    def test_sous_wine(self, tmp_path):
        exe = tmp_path / "HP2" / "System" / "Game.exe"
        commande = compat.commande_jeu(Lanceur("umu", "/usr/bin/umu-run"), exe, ("-LOADGAME=0", "-SAVESLOT=1"))
        assert commande == ["/usr/bin/umu-run", str(exe), "-LOADGAME=0", "-SAVESLOT=1"]


def test_reglage_survit_au_redemarrage(tmp_path):
    """Rien par défaut ; un choix PAR JEU survit à save() puis load() (règle 99)."""
    fichier = tmp_path / "config.json"
    with patch("src.core.config.CONFIG_FILE_PATH", fichier):
        c = Config(install_path=tmp_path, cache_path=tmp_path / ".cache")
        assert c.reprise == {}
        c.reprise = {"hp1": True, "hp2": False}
        c.save()
        assert Config.load().reprise == {"hp1": True, "hp2": False}


def test_un_oui_jamais_choisi_redevient_non(tmp_path):
    """Avant la question (2026-10-27), le « oui » n'était que le défaut : il ne
    vaut plus tant que la personne n'a pas répondu."""
    fichier = tmp_path / "config.json"
    with patch("src.core.config.CONFIG_FILE_PATH", fichier):
        fichier.write_text('{"reprise_directe": true}', encoding="utf-8")
        assert Config.load().reprise == {}


def test_l_ancien_choix_commun_vaut_pour_chaque_jeu(tmp_path):
    """Avant le 2026-10-31, un seul choix pour HP1 à HP3 : il est repris pour chacun."""
    fichier = tmp_path / "config.json"
    with patch("src.core.config.CONFIG_FILE_PATH", fichier):
        fichier.write_text('{"reprise_directe": true, "reprise_demandee": true}', encoding="utf-8")
        assert Config.load().reprise == {"hp1": True, "hp2": True, "hp3": True}
        fichier.write_text('{"reprise_directe": false, "reprise_demandee": true}', encoding="utf-8")
        assert Config.load().reprise == {"hp1": False, "hp2": False, "hp3": False}


class TestQuestion:
    """La question d'après la première partie (`ui/question_reprise.py`)."""

    def _fenetre(self, make_window, monkeypatch, sauvegarde=True):
        win = make_window()
        monkeypatch.setattr(reprise, "arguments", lambda game: ("?load=1",) if sauvegarde else ())
        return win

    def test_posee_une_fois_puis_retenue(self, make_window, monkeypatch):
        from src.ui import question_reprise
        win = self._fenetre(make_window, monkeypatch)
        vues = []
        monkeypatch.setattr(question_reprise, "message", lambda *a, **k: vues.append(a) or 0)
        assert question_reprise.a_demander(win, "hp1", True, False)
        question_reprise.demander(win, "hp1", True, False)
        assert len(vues) == 1
        assert win.manager.config.reprise == {"hp1": True}
        question_reprise.demander(win, "hp1", True, False)
        assert len(vues) == 1, "une seule fois par jeu"
        question_reprise.demander(win, "hp2", True, False)
        assert len(vues) == 2 and win.manager.config.reprise == {"hp1": True, "hp2": True}, \
            "chaque jeu a son choix"

    def test_garder_le_menu(self, make_window, monkeypatch):
        from src.ui import question_reprise
        win = self._fenetre(make_window, monkeypatch)
        monkeypatch.setattr(question_reprise, "message", lambda *a, **k: 1)
        question_reprise.demander(win, "hp3", True, False)
        assert win.manager.config.reprise == {"hp3": False}

    def test_pas_de_question_sans_raison(self, make_window, monkeypatch):
        from src.ui import question_reprise
        win = self._fenetre(make_window, monkeypatch)
        assert not question_reprise.a_demander(win, "hp4", True, False), "HP4 ne sait pas reprendre"
        assert not question_reprise.a_demander(win, "hp1", False, False), "pas une partie"
        assert not question_reprise.a_demander(win, "hp1", True, True), "arrêt fatal"
        sans = self._fenetre(make_window, monkeypatch, sauvegarde=False)
        assert not question_reprise.a_demander(sans, "hp1", True, False), "rien à rouvrir"


class TestReglageDuJeu:
    """Dans l'onglet Jeu de HP1 à HP3, plus dans les Paramètres (Ludo, 2026-10-31)."""

    def _dialogue(self, qtbot, tmp_path, jeu):
        from src.core.game_data import load_catalog
        from src.core.game_manager import GameManager
        from src.ui.game_settings_dialog import GameSettingsDialog
        cfg = Config(install_path=tmp_path, cache_path=tmp_path / ".cache")
        game = next(g for g in load_catalog().games if g.id == jeu)
        dlg = GameSettingsDialog(game, GameManager(cfg), lambda c: True)
        qtbot.addWidget(dlg)
        dlg.ouvrir_onglet("jeu")
        return dlg, cfg

    def test_hp1_porte_le_reglage_et_il_ne_vaut_que_pour_lui(self, qtbot, tmp_path):
        from src.ui.toggle_switch import ToggleSwitch
        with patch("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json"):
            dlg, cfg = self._dialogue(qtbot, tmp_path, "hp1")
            bascule = next(b for b in dlg.findChildren(ToggleSwitch)
                           if b.accessibleName() == "Reprendre ouvre la dernière partie")
            assert not bascule.isChecked()
            bascule._basculer()      # un clic (setChecked n'émet rien)
            assert cfg.reprise == {"hp1": True}
            assert Config.load().reprise == {"hp1": True}

    def test_hp4_ne_l_a_pas(self, qtbot, tmp_path):
        from src.ui.toggle_switch import ToggleSwitch
        with patch("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json"):
            dlg, _ = self._dialogue(qtbot, tmp_path, "hp4")
            assert not any(b.accessibleName() == "Reprendre ouvre la dernière partie"
                           for b in dlg.findChildren(ToggleSwitch))

    def test_plus_dans_les_parametres_du_launcher(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "ui" / "settings_panel.py").read_text(encoding="utf-8")
        assert "reprise" not in source

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
        m.config.reprise_directe = directe
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
    """Oui par défaut ; un « non » survit à save() puis load() (règle 99)."""
    fichier = tmp_path / "config.json"
    with patch("src.core.config.CONFIG_FILE_PATH", fichier):
        c = Config(install_path=tmp_path, cache_path=tmp_path / ".cache")
        assert c.reprise_directe is True
        c.reprise_directe = False
        c.save()
        assert Config.load().reprise_directe is False

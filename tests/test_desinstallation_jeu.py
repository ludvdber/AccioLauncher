"""Désinstaller un jeu sans figer la fenêtre (`src/ui/desinstallation_jeu.py`).

Grand audit du 2026-11-02 : `shutil.rmtree` d'un jeu de 1,6 Go tournait dans
le fil de l'interface. Le dossier s'efface sur un fil ; l'état se pose après,
dans le fil de l'interface, et la fiche reste désactivée entre les deux.
"""
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.config import Config
from src.core.game_data import Catalog, GameData
from src.core.game_manager import GameManager, GameState
from src.ui import desinstallation_jeu

_JEU = {
    "id": "hp_test", "name": "HP Test", "year": 2001, "description": "", "developer": "Dev",
    "executable": "HPTest/System/Game.exe", "cover_image": "test.jpg",
    "latest_version": "1.0", "recommended_version": "1.0",
    "versions": [{"version": "1.0", "date": "2026-01-01", "download_url": "https://example.com/g.7z",
                  "download_parts": None, "size_mb": 100, "changes": []}],
}


class _Signal:
    def __init__(self):
        self.recus = []

    def emit(self, *args):
        self.recus.append(args)


@pytest.fixture
def poste(tmp_path):
    (tmp_path / "HPTest" / "System").mkdir(parents=True)
    (tmp_path / "HPTest" / "System" / "Game.exe").write_text("x")
    catalogue = Catalog(catalog_version="1.0", catalog_url="", games=(GameData.from_dict(_JEU),))
    with patch("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json"), \
            patch("src.core.game_manager.load_catalog", return_value=catalogue):
        manager = GameManager(Config(install_path=tmp_path, cache_path=tmp_path / ".cache"))
        manager.save_installed_version("hp_test", "1.0")
        yield manager, tmp_path


def _vue(manager):
    actif = []
    return SimpleNamespace(game=manager.get_game_by_id("hp_test"), manager=manager,
                           setEnabled=actif.append, _refresh=lambda: None,
                           state_changed=_Signal(), status_message=_Signal()), actif


def test_le_dossier_s_efface_sur_un_autre_fil(poste, qtbot, monkeypatch):
    manager, racine = poste
    fils, vraie = [], GameManager.effacer_dossier
    monkeypatch.setattr(GameManager, "effacer_dossier",
                        staticmethod(lambda d: (fils.append(threading.current_thread()), vraie(d))[1]))
    vue, actif = _vue(manager)
    desinstallation_jeu.desinstaller(vue)
    assert actif == [False], "la fiche est désactivée pendant l'effacement"
    assert manager.get_state("hp_test") == GameState.INSTALLED, "l'état attend la fin"
    qtbot.waitUntil(lambda: actif == [False, True], timeout=5000)
    assert fils and fils[0] is not threading.main_thread()
    assert not (racine / "HPTest").exists()
    assert manager.get_state("hp_test") == GameState.NOT_INSTALLED
    assert manager.installed_version("hp_test") is None
    assert vue.status_message.recus[-1] == ("HP Test désinstallé.",)


def test_un_echec_garde_le_jeu_installe(poste, qtbot, monkeypatch):
    manager, racine = poste
    monkeypatch.setattr(GameManager, "effacer_dossier", staticmethod(lambda d: False))
    vue, actif = _vue(manager)
    desinstallation_jeu.desinstaller(vue)
    qtbot.waitUntil(lambda: actif == [False, True], timeout=5000)
    assert manager.get_state("hp_test") == GameState.INSTALLED
    assert "n'a pas abouti" in vue.status_message.recus[-1][0]


def test_rien_a_desinstaller_ne_desactive_rien(poste):
    manager, racine = poste
    (racine / "HPTest" / "System" / "Game.exe").unlink()
    for f in sorted((racine / "HPTest").rglob("*"), reverse=True):
        f.rmdir()
    (racine / "HPTest").rmdir()
    vue, actif = _vue(manager)
    desinstallation_jeu.desinstaller(vue)
    assert actif == []
    assert "n'a pas abouti" in vue.status_message.recus[-1][0]

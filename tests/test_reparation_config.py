"""Remettre la configuration d'un jeu sans rien retélécharger.

Le cas réel : HP1/HP2, options graphiques changées dans le jeu → « Assertion
failed: RenDev » et le jeu ne redémarre plus, alors que « Vérifier / réparer »
ne touchait pas au `.ini` de Documents. Documents et `_Launcher` sont ceux du
conftest (jamais les vrais).
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.core import config as config_module
from src.core import reparation_config as rc
from src.core.catalogue_blocs import ConfigFile, PostInstall


@pytest.fixture
def jeu(tmp_path):
    install = tmp_path / "Jeux"
    modeles = install / "HP2" / "config"
    modeles.mkdir(parents=True)
    (modeles / "Game.ini").write_bytes(b"[Engine.Engine]\r\nGameRenderDevice=D3D11Drv.D3D11RenderDevice\r\n")
    (modeles / "User.ini").write_bytes(b"[Engine.Input]\r\nJoy2=Jump\r\n")
    game = SimpleNamespace(
        id="hp2", name="Harry Potter II", executable="HP2/system/Game.exe",
        post_install=PostInstall(config_files=(
            ConfigFile("config/Game.ini", "~/Documents/Harry Potter II/Game.ini"),
            ConfigFile("config/User.ini", "~/Documents/Harry Potter II/User.ini"),
        )))
    return game, install


def _documents(tmp_path):
    return tmp_path / "Documents" / "Harry Potter II"


def test_le_ini_casse_est_remis_et_l_ancien_garde(jeu, tmp_path):
    game, install = jeu
    docs = _documents(tmp_path)
    docs.mkdir(parents=True)
    casse = b"[Engine.Engine]\r\nGameRenderDevice=SoftDrv.SoftwareRenderDevice\r\n"
    (docs / "Game.ini").write_bytes(casse)
    resultat = rc.remettre(game, install, datetime(2026, 10, 3, 15, 30, 0))

    assert (docs / "Game.ini").read_bytes() == (install / "HP2/config/Game.ini").read_bytes()
    assert (docs / "User.ini").is_file()                 # absent avant : posé aussi
    assert len(resultat.remis) == 2 and not resultat.echoues
    gardes = config_module.CONFIG_FILE_PATH.parent / "configs_remplacees" / "hp2" / "2026-10-03_153000"
    assert resultat.gardes == gardes
    assert (gardes / "Game.ini").read_bytes() == casse    # jamais perdu
    assert not (gardes / "User.ini").exists()             # il n'existait pas


def test_deux_reparations_gardent_deux_copies(jeu, tmp_path):
    game, install = jeu
    docs = _documents(tmp_path)
    docs.mkdir(parents=True)
    (docs / "Game.ini").write_bytes(b"premier")
    rc.remettre(game, install, datetime(2026, 10, 3, 15, 0, 0))
    (docs / "Game.ini").write_bytes(b"second")
    rc.remettre(game, install, datetime(2026, 10, 3, 16, 0, 0))
    racine = config_module.CONFIG_FILE_PATH.parent / "configs_remplacees" / "hp2"
    assert (racine / "2026-10-03_150000" / "Game.ini").read_bytes() == b"premier"
    assert (racine / "2026-10-03_160000" / "Game.ini").read_bytes() == b"second"


def test_un_fichier_en_lecture_seule_est_remis(jeu, tmp_path):
    """Le User.ini de HP2 est livré en lecture seule (cf. post_install._rendre_remplacable)."""
    game, install = jeu
    docs = _documents(tmp_path)
    docs.mkdir(parents=True)
    (docs / "User.ini").write_bytes(b"vieux")
    (docs / "User.ini").chmod(0o444)
    resultat = rc.remettre(game, install)
    assert not resultat.echoues
    assert (docs / "User.ini").read_bytes() == (install / "HP2/config/User.ini").read_bytes()


def test_sans_copie_de_cote_rien_n_est_remplace(jeu, tmp_path, monkeypatch):
    game, install = jeu
    docs = _documents(tmp_path)
    docs.mkdir(parents=True)
    (docs / "Game.ini").write_bytes(b"reglage precieux")

    def refuse(*_a, **_k):
        raise PermissionError("disque plein")
    monkeypatch.setattr(rc.shutil, "copy2", refuse)
    resultat = rc.remettre(game, install)
    assert resultat.echoues and not resultat.remis
    assert (docs / "Game.ini").read_bytes() == b"reglage precieux"


def test_disponible(jeu, tmp_path):
    game, install = jeu
    assert rc.disponible(game, install)
    assert not rc.disponible(game, tmp_path / "ailleurs")             # jeu pas installé là
    sans = SimpleNamespace(id="hp5", executable="HP5/hp.exe", post_install=PostInstall())
    assert not rc.disponible(sans, install)
    assert rc.remettre(sans, install) == rc.Resultat((), (), None)


def test_les_fichiers_sont_nommes(jeu):
    game, _ = jeu
    assert [f.name for f in rc.fichiers(game)] == ["Game.ini", "User.ini"]


class _Vue:
    """Le strict nécessaire de GameDetailView pour `on_repair`."""
    def __init__(self, game, install, en_cours=None):
        self.game = game
        self.manager = SimpleNamespace(config=SimpleNamespace(install_path=install))
        self._ops = SimpleNamespace(is_busy=False, repair=self._repair)
        self.notes, self.reparations, self._en_cours = [], [], en_cours
        self.notify = SimpleNamespace(emit=self.notes.append)

    def _repair(self, game):
        self.reparations.append(game.id)

    def _refresh(self):
        pass

    def partie_en_cours(self):
        return self._en_cours


@pytest.fixture
def handlers(monkeypatch):
    from src.ui import game_detail_handlers as h
    monkeypatch.setattr(h, "_preparation_bloque", lambda _v: False)
    return h


@pytest.mark.parametrize("choix, remise, retelechargee", [(0, True, False), (1, False, True), (2, False, False)])
def test_la_question_propose_d_abord_la_configuration(handlers, monkeypatch, jeu, tmp_path,
                                                       choix, remise, retelechargee):
    game, install = jeu
    vue = _Vue(game, install)
    questions = []
    monkeypatch.setattr(handlers, "_boite", lambda *a, **k: questions.append(a[4]) or choix)
    handlers.on_repair(vue)
    assert questions[0] == ("Remettre la configuration", "Retélécharger le jeu", "Annuler")
    assert (_documents(tmp_path) / "Game.ini").exists() is remise
    assert bool(vue.reparations) is retelechargee
    assert bool(vue.notes) is remise


def test_pas_pendant_une_partie(handlers, monkeypatch, jeu, tmp_path):
    game, install = jeu
    vue = _Vue(game, install, en_cours="HP2")
    monkeypatch.setattr(handlers, "_boite", lambda *a, **k: 0)
    handlers.on_repair(vue)
    assert not (_documents(tmp_path) / "Game.ini").exists()
    assert vue.notes == ["Fermez HP2 avant de remettre sa configuration."]

"""Tests de l'orchestrateur téléchargement → installation.

`GameOperations` pilote toute la chaîne qui amène un jeu sur le disque, et
c'était le SEUL module du projet sans aucun test. C'est ce trou qui a laissé
passer, pendant un jour et un build publié, un appel de méthode sur une
propriété (`self._speed_tracker.speed()`) : chaque téléchargement réussi levait
`TypeError` AVANT `install()`, donc plus aucun jeu ne pouvait s'installer, et
l'utilisateur recevait un rapport de plantage à 100 % de la barre.

Les tests ci-dessous couvrent les trois transitions qui portent l'essentiel de
la valeur : la fin du téléchargement, la fin de l'installation, et l'annulation.
"""

import pytest

pytest.importorskip("pytestqt")

from pathlib import Path  # noqa: E402

from src.core.config import Config  # noqa: E402
from src.core.game_data import Catalog, GameData  # noqa: E402
from src.core.game_manager import GameManager, GameState  # noqa: E402
from src.ui.game_operations import GameOperations  # noqa: E402

JEU = {
    "id": "hp_test", "name": "Jeu de test", "year": 2001,
    "description": "d", "developer": "dev",
    "executable": "HPTest/System/Game.exe", "cover_image": "c.png",
    "latest_version": "1.0", "recommended_version": "1.0",
    "versions": [{"version": "1.0", "download_url": "https://x/a.7z", "size_mb": 10}],
}


@pytest.fixture
def ops(tmp_path, monkeypatch):
    """GameOperations sur un catalogue d'un seul jeu, tout en tmp_path."""
    monkeypatch.setattr("src.core.game_data.load_catalog",
                        lambda *a, **k: Catalog("1.0", "", (GameData.from_dict(JEU),)))
    monkeypatch.setattr("src.core.game_manager.load_catalog",
                        lambda *a, **k: Catalog("1.0", "", (GameData.from_dict(JEU),)))
    config = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache")
    config.cache_path.mkdir(parents=True)
    manager = GameManager(config)
    return GameOperations(manager), manager


def _archive(ops_tuple) -> Path:
    operations, manager = ops_tuple
    chemin = manager.config.cache_path / "hp_test_v1.0.7z"
    chemin.write_bytes(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 64)
    return chemin


def _en_cours_de_telechargement(ops_tuple):
    """Place l'orchestrateur dans l'état « téléchargement en cours »."""
    operations, manager = ops_tuple
    jeu = manager.get_games()[0].game
    operations._active_game = jeu
    operations._target_version = jeu.current_download
    manager.set_game_state(jeu.id, GameState.DOWNLOADING)
    operations._speed_tracker.reset()
    operations._speed_tracker.update(0)
    operations._speed_tracker.update(20_000_000)
    return jeu


class TestFinDeTelechargement:
    """La transition téléchargement → installation, celle qui était cassée."""

    def test_l_installation_demarre(self, ops):
        operations, manager = ops
        jeu = _en_cours_de_telechargement(ops)

        operations._on_download_finished(str(_archive(ops)))

        assert operations._installer is not None, (
            "l'installation n'a pas démarré après un téléchargement réussi")
        assert manager.get_state(jeu.id) == GameState.INSTALLING
        operations._installer.cancel()
        operations._installer.wait(5000)

    def test_aucune_exception(self, ops):
        """Ce slot tourne dans la boucle d'événements : une exception qui en
        sort est affichée à l'utilisateur en rapport de plantage."""
        operations, manager = ops
        _en_cours_de_telechargement(ops)
        operations._on_download_finished(str(_archive(ops)))  # ne doit pas lever
        if operations._installer is not None:
            operations._installer.cancel()
            operations._installer.wait(5000)

    def test_la_vitesse_observee_est_memorisee(self, ops):
        """Elle sert à annoncer une durée AVANT le clic suivant."""
        operations, manager = ops
        _en_cours_de_telechargement(ops)
        operations._on_download_finished(str(_archive(ops)))
        assert manager.config.last_download_speed > 0
        if operations._installer is not None:
            operations._installer.cancel()
            operations._installer.wait(5000)

    def test_le_downloader_est_relache(self, ops):
        operations, manager = ops
        _en_cours_de_telechargement(ops)
        operations._on_download_finished(str(_archive(ops)))
        assert operations._downloader is None
        if operations._installer is not None:
            operations._installer.cancel()
            operations._installer.wait(5000)


class TestFinDInstallation:
    def test_etat_et_version_enregistres(self, ops, tmp_path):
        operations, manager = ops
        jeu = manager.get_games()[0].game
        exe = manager.config.install_path / jeu.executable
        exe.parent.mkdir(parents=True)
        exe.write_text("faux")
        operations._active_game = jeu
        operations._target_version = jeu.current_download

        operations._on_install_finished(str(manager.config.install_path))

        assert manager.get_state(jeu.id) == GameState.INSTALLED
        assert manager.installed_version(jeu.id) == "1.0"

    def test_executable_absent_signale_une_installation_incomplete(self, ops):
        operations, manager = ops
        jeu = manager.get_games()[0].game
        operations._active_game = jeu
        operations._target_version = jeu.current_download
        erreurs = []
        operations.operation_error.connect(lambda t, m: erreurs.append(t))

        operations._on_install_finished(str(manager.config.install_path))

        assert erreurs, "une installation sans exécutable doit être signalée"
        assert manager.get_state(jeu.id) == GameState.NOT_INSTALLED


class TestAnnulation:
    def test_l_etat_est_redetecte_et_non_force(self, ops):
        """Annuler une MISE À JOUR ne doit pas faire croire à une désinstallation :
        l'ancienne version est toujours sur le disque."""
        operations, manager = ops
        jeu = manager.get_games()[0].game
        exe = manager.config.install_path / jeu.executable
        exe.parent.mkdir(parents=True)
        exe.write_text("faux")          # version précédente encore installée
        _en_cours_de_telechargement(ops)

        operations.cancel_download()

        assert manager.get_state(jeu.id) == GameState.INSTALLED
        assert operations.is_busy is False
        assert operations.active_game is None


class TestVersionSansSource:
    def test_refus_avant_de_lancer_un_thread(self, ops):
        """Un jeu annoncé sans archive publiée : aucun Downloader ne doit
        partir, sous peine d'une erreur réseau qui accuse la connexion."""
        operations, manager = ops
        sans_source = GameData.from_dict(
            {**JEU, "versions": [{"version": "1.0", "size_mb": 10}]})
        messages = []
        operations.status_message.connect(messages.append)

        operations.download(sans_source, sans_source.versions[0])

        assert operations._downloader is None
        assert messages and "bientôt" in messages[0]

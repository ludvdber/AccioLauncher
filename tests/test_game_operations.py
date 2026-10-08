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

import errno
import time

import pytest

pytest.importorskip("pytestqt")

from pathlib import Path  # noqa: E402

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

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
    # Jusqu'à Python 3.12, `time.monotonic()` n'avance sous Windows que par pas
    # de 15,6 ms : deux relevés consécutifs tombaient sur le même instant, et
    # la vitesse (octets / durée nulle) valait 0. Un vrai téléchargement dure
    # des secondes ; il faut ici laisser passer au moins un pas d'horloge.
    time.sleep(0.05)
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


class TestAucuneOperationNeFuit:
    """Tout chemin de sortie remet l'état d'opération à zéro, en entier.

    Le ménage se faisait à la main sur QUATRE chemins (annulation, erreur de
    téléchargement, fin d'installation, erreur d'installation) et ils ne le
    faisaient déjà pas pareil : la fin d'installation n'effaçait pas
    `_uninstall_first`. Ce n'était pas un défaut vivant — le drapeau est
    consommé plus tôt — mais c'est la forme que prend le suivant, et il
    tomberait sur le chemin du SUCCÈS, donc le plus fréquent et le moins
    suspecté. Ce test vaut pour tout champ qu'on ajoutera : il les lit sur
    l'objet plutôt que de les nommer un par un.
    """

    CHAMPS = ("_active_game", "_target_version", "_uninstall_first", "_phase")

    def _salir(self, operations, manager):
        """Pose un état d'opération en cours, comme le ferait un vrai switch."""
        jeu = manager.get_game_by_id("hp_test")
        operations._active_game = jeu
        operations._target_version = jeu.versions[0]
        operations._uninstall_first = True
        operations._phase = "download"

    def _propre(self, operations) -> bool:
        return not any(getattr(operations, c) for c in self.CHAMPS)

    @pytest.mark.parametrize("sortie, args", [
        ("_on_download_error", ("boum",)), ("_on_install_error", ("boum", "inconnu")),
    ])
    def test_les_chemins_d_erreur_ne_laissent_rien(self, ops, sortie, args):
        operations, manager = ops
        self._salir(operations, manager)
        getattr(operations, sortie)(*args)
        assert self._propre(operations), (
            f"{sortie} a laissé un état d'opération derrière lui")

    def test_la_fin_d_installation_ne_laisse_rien(self, ops):
        operations, manager = ops
        self._salir(operations, manager)
        operations._on_install_finished("")
        assert self._propre(operations)

    def test_la_version_survit_assez_pour_etre_enregistree(self, ops, tmp_path):
        """Le ménage ne doit pas emporter ce dont la fin d'installation a
        besoin JUSTE APRÈS : sans la version, le jeu s'installerait sans
        numéro et `has_update` resterait muet à vie."""
        operations, manager = ops
        self._salir(operations, manager)
        exe = manager.config.install_path / "HPTest" / "System"
        exe.mkdir(parents=True)
        (exe / "Game.exe").write_bytes(b"MZ")
        operations._on_install_finished("")
        assert manager.installed_version("hp_test") == "1.0"



class _FauxDownloader(QObject):
    """Un téléchargeur qui ne part jamais sur le réseau."""
    progress = pyqtSignal(object, object)
    download_finished = pyqtSignal(str)
    error = pyqtSignal(str, object)
    verifying = pyqtSignal()
    part_info = pyqtSignal(int, int)

    def __init__(self, **kwargs):
        super().__init__()
        self.destination = kwargs["destination"]

    def start(self):
        pass


class TestQuiEcouteVoitUneOperationEnCours:
    """Parcours du 2026-09-30 (`test_parcours.py`) : `state_changed` partait
    AVANT la création du fil. La barre du bas, qui exige `is_busy`, lisait donc
    « rien en cours » et restait cachée pendant tout le téléchargement ET toute
    l'installation — depuis que cette condition existe (2026-06-10)."""

    def test_au_telechargement(self, ops, monkeypatch):
        operations, manager = ops
        monkeypatch.setattr("src.ui.game_operations.Downloader", _FauxDownloader)
        vus = []
        operations.state_changed.connect(lambda: vus.append(operations.is_busy))
        jeu = manager.get_games()[0].game
        operations.download(jeu, jeu.current_download)
        assert vus == [True]

    def test_a_l_installation(self, ops):
        operations, manager = ops
        vus = []
        operations.state_changed.connect(lambda: vus.append(operations.is_busy))
        operations.install(manager.get_games()[0].game, _archive(ops), delete_archive=False)
        try:
            assert vus[0] is True
        finally:
            operations._installer.cancel()
            operations._installer.wait(5000)


class TestUnEchecDInstallationDitSaCause:
    """M-05 / ACT-003 : la boîte disait « L'archive est peut-être corrompue.
    Réessayez le téléchargement » quelle que soit la cause. Retélécharger 4 Go
    ne libère pas un disque plein. Ici, une VRAIE installation (le fil de
    l'installeur, son classement, le slot de l'orchestrateur) dont seule
    l'extraction est remplacée par l'erreur à éprouver."""

    @staticmethod
    def _echouer(ops_tuple, qtbot, monkeypatch, exc, archive=None):
        operations, manager = ops_tuple

        def extraction(*_a, **_k):
            raise exc
        monkeypatch.setattr("src.core.installer.extract_7z", extraction)
        archive = archive or _archive(ops_tuple)
        with qtbot.waitSignal(operations.operation_error, timeout=10_000) as recu:
            operations.install(manager.get_games()[0].game, archive, delete_archive=False)
        return recu.args[1], archive

    @pytest.fixture(autouse=True)
    def _francais(self):
        from src.core.i18n import get_language, set_language
        avant = get_language()
        set_language("fr")
        yield
        set_language(avant)

    @pytest.mark.parametrize("exc, attendu", [
        (PermissionError(errno.EACCES, "Accès refusé"), "Windows a refusé l'écriture"),
        (OSError(errno.ENOSPC, "No space left on device"), "Le disque est plein"),
        (OSError(errno.ENAMETOOLONG, "File name too long"), "trop long"),
    ])
    def test_seule_l_archive_illisible_accuse_l_archive(self, ops, qtbot, monkeypatch, exc, attendu):
        texte, archive = self._echouer(ops, qtbot, monkeypatch, exc)
        assert attendu in texte
        assert "abîmée" not in texte and "corrompue" not in texte
        assert archive.exists(), "une archive saine ne doit pas être supprimée"

    def test_une_archive_illisible_du_cache_est_retiree(self, ops, qtbot, monkeypatch):
        """Sinon le téléchargeur, qui reprend ce qu'il trouve, la resservirait."""
        from src.core.extractors import ExtractionEchouee
        exc = ExtractionEchouee("7z.exe a échoué (code 2)",
                                "Open ERROR: Cannot open the file as [7z] archive\n"
                                "ERRORS:\nUnexpected end of archive")
        texte, archive = self._echouer(ops, qtbot, monkeypatch, exc)
        assert "abîmée" in texte and "supprimée" in texte
        assert not archive.exists()

    def test_une_archive_choisie_par_la_personne_n_est_jamais_supprimee(
            self, ops, qtbot, monkeypatch, tmp_path):
        from src.core.extractors import ExtractionEchouee
        choisie = tmp_path / "Mes archives" / "hp1.7z"
        choisie.parent.mkdir()
        choisie.write_bytes(b"7z\xbc\xaf\x27\x1c")
        exc = ExtractionEchouee("code 2", "ERRORS:\nIs not archive")
        texte, archive = self._echouer(ops, qtbot, monkeypatch, exc, archive=choisie)
        assert "L'archive choisie est abîmée" in texte
        assert choisie.exists()

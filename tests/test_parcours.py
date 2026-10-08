"""Parcours fonctionnels : ce que fait un joueur, de bout en bout, dans une VRAIE fenêtre.

Chaque étape a ses tests unitaires ; aucun ne suivait un jeu d'un bout à
l'autre. Or les défauts les plus chers de ce projet vivaient AUX JOINTURES :
une propriété appelée comme une méthode entre la fin du téléchargement et
l'installation (règle 10), une barre du bas partagée entre deux sources
(revue du 2026-09-30). Ici rien n'est simulé entre les étapes — seulement le
réseau (une archive locale) et le processus du jeu (un faux Popen).

Le jeu est FABRIQUÉ : `games.json` se met à jour à distance, et un test qui
suppose son contenu casse loin de ce qu'il surveille (règle 78).
"""

import subprocess
import sys
import zipfile
from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")

from src.core.game_data import Catalog, GameData, load_catalog  # noqa: E402
from src.core.game_manager import GameState  # noqa: E402

_COUVERTURE = load_catalog().games[0].cover_image

JEU = {
    "id": "hp_parcours", "name": "Jeu du parcours", "year": 2001,
    "description": "Un jeu fabriqué pour ce test.", "developer": "Accio",
    "executable": "HPParcours/System/Game.exe", "cover_image": _COUVERTURE,
    "latest_version": "1.0", "recommended_version": "1.0",
    "versions": [{"version": "1.0", "download_url": "https://x/p.7z", "size_mb": 1}],
}


class _FauxJeu:
    """Le processus d'un jeu qui tourne jusqu'à ce que le test le ferme."""
    pid = 424_242
    args = ["Game.exe"]
    code = None

    def poll(self):
        return self.code


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    catalogue = Catalog("1.0", "", (GameData.from_dict(JEU),))
    monkeypatch.setattr("src.core.game_manager.load_catalog", lambda *a, **k: catalogue)
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check", lambda self: None)
    from src.core.config import Config
    from src.core.i18n import set_language
    Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "jeux" / ".cache",
           langue="fr", autoplay_videos=False).save()
    from src.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._launcher_update_asked = True
    win.show()
    yield win
    set_language("fr")


def _archive(tmp_path):
    chemin = tmp_path / "parcours.zip"
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("HPParcours/System/Game.exe", b"MZ faux executable")
        z.writestr("HPParcours/System/Game.ini", "[Engine]\r\nLanguage=fre\r\n")
    return chemin


class TestDuTelechargementAuRetourDePartie:
    """Installer une archive locale → JOUER → la partie → le retour → désinstaller."""

    def test_le_parcours_complet(self, fenetre, qtbot, tmp_path, monkeypatch):
        from src.ui import game_detail_handlers as gdh
        win, vue = fenetre, fenetre._detail
        jeu = vue.game
        assert jeu.id == "hp_parcours"
        assert win.manager.get_state(jeu.id) == GameState.NOT_INSTALLED

        # ① Installer depuis une archive : le vrai extracteur, sur un vrai fichier.
        archive = _archive(tmp_path)
        monkeypatch.setattr(gdh, "QFileDialog", SimpleNamespace(
            getOpenFileName=lambda *a, **k: (str(archive), "")))
        gdh.on_install_local(vue)
        assert win._download_bar.isVisible(), "l'installation doit se voir en bas"
        qtbot.waitUntil(lambda: win.manager.get_state(jeu.id) == GameState.INSTALLED,
                        timeout=15000)
        exe = win.config.install_path / jeu.executable
        assert exe.read_bytes() == b"MZ faux executable"
        assert archive.exists(), "une archive LOCALE appartient à l'utilisateur"
        assert win.manager.installed_version(jeu.id) == "1.0"
        qtbot.waitUntil(lambda: not win._download_bar.isVisible(), timeout=3000)
        assert "installé avec succès" in win._toast.text()

        # ② JOUER : le lancement part par le vrai `launch_game`, jusqu'au Popen.
        lances, processus = [], _FauxJeu()

        def popen(args, **kwargs):
            lances.append((args, kwargs))
            return processus
        # Seul `Popen` est faux : le chemin Wine lit aussi `DEVNULL`, et un faux
        # module qui n'énumère que ce que lit Windows cassait la CI Linux.
        faux_subprocess = SimpleNamespace(
            **{nom: getattr(subprocess, nom) for nom in dir(subprocess) if nom.isupper()},
            Popen=popen)
        faux_subprocess.DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)
        faux_subprocess.CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        monkeypatch.setattr("src.core.game_manager.subprocess", faux_subprocess)
        monkeypatch.setattr("src.core.game_manager.prerequis_manquants", lambda ids: [])
        gdh.on_play(vue)
        assert len(lances) == 1
        args, kwargs = lances[0]
        assert args[-1] == str(exe)
        assert kwargs["cwd"] == str(exe.parent), "UE1 cherche ses paquets depuis System/"
        assert win._session.nom_en_cours == jeu.name
        if sys.platform == "win32":
            qtbot.waitUntil(lambda: not win.isVisible(), timeout=3000)

        # ③ Un second clic pendant la partie ne relance rien.
        gdh.on_play(vue)
        assert len(lances) == 1, "deux instances du même jeu"

        # ④ Le jeu se ferme, et c'est le VRAI moniteur qui le constate : le
        # processus rend son code, la grâce (10 s pour les relances d'UE1) est
        # ramenée à zéro, plus rien ne tourne sous ce nom. 25 minutes de jeu
        # sans les attendre : le début de la partie est reculé d'autant.
        moniteur = win._session._monitor
        moniteur._debut -= 1500
        moniteur._is_exe_running = lambda nom: False      # sur l'INSTANCE (règle 12)
        monkeypatch.setattr("src.ui.process_monitor._GRACE_S", 0.0)
        processus.code = 0
        moniteur._poll()      # le processus initial s'est terminé → grâce
        moniteur._poll()      # plus rien ne tourne → fin de partie
        qtbot.waitUntil(win.isVisible, timeout=3000)
        assert "partie terminée" in win._status_bar.currentMessage()
        assert win.manager.get_playtime(jeu.id) >= 1500
        assert not win._session.nom_en_cours

        # ⑤ Désinstaller : le dossier part, l'état suit, le temps de jeu reste.
        monkeypatch.setattr(gdh, "_boite", lambda *a, **k: 0)
        gdh.on_uninstall(vue)
        assert win.manager.get_state(jeu.id) == GameState.NOT_INSTALLED
        assert not exe.parent.parent.exists()
        assert win.manager.get_playtime(jeu.id) >= 1500, "désinstaller n'efface pas l'histoire"

    def test_une_archive_corrompue_ne_laisse_rien_derriere(self, fenetre, qtbot, tmp_path,
                                                          monkeypatch):
        """L'échec d'installation revient à l'état d'AVANT, sans dossier à moitié posé."""
        from src.ui import game_detail_handlers as gdh
        win, vue = fenetre, fenetre._detail
        casse = tmp_path / "casse.zip"
        casse.write_bytes(b"PK\x03\x04 ceci n'est pas une archive")
        monkeypatch.setattr(gdh, "QFileDialog", SimpleNamespace(
            getOpenFileName=lambda *a, **k: (str(casse), "")))
        # La boîte d'erreur est MODALE : le faux, sur le nom du module, relève
        # ce qu'elle aurait dit au lieu de bloquer la suite.
        avertis = []
        monkeypatch.setattr("src.ui.game_detail.avertir", lambda *a: avertis.append(a[1]))
        gdh.on_install_local(vue)
        qtbot.waitUntil(lambda: bool(avertis), timeout=15000)
        assert avertis == ["Échec de l'installation"]
        assert not vue.ops.is_busy
        assert win.manager.get_state(vue.game.id) == GameState.NOT_INSTALLED
        assert not (win.config.install_path / "HPParcours").exists()
        qtbot.waitUntil(lambda: not win._download_bar.isVisible(), timeout=3000)


class _Wine:
    """Ce que la barre du bas lit du préparateur de Wine."""

    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Signaux(QObject):
            commencee = pyqtSignal(object)
            progression = pyqtSignal(str, str)
            terminee = pyqtSignal(str, bool, str, bool)
        self._s = _Signaux()
        self.commencee = self._s.commencee
        self.progression = self._s.progression
        self.terminee = self._s.terminee
        self.annulations = 0

    def annuler(self):
        self.annulations += 1


class TestLaBarreDuBasPendantLaPreparationDeWine:
    """`SuiviBarre` n'avait AUCUN test, et c'est là que vivait le défaut de la
    revue du 2026-09-30 : la barre suit deux sources, jamais en même temps."""

    def _pose(self, qtbot, fenetre):
        from src.ui.download_bar import DownloadBar
        from src.ui.suivi_barre import SuiviBarre
        barre = DownloadBar()
        qtbot.addWidget(barre)
        wine = _Wine()
        suivi = SuiviBarre(barre, fenetre._detail.ops, wine, fenetre.manager, lambda: 0)
        return barre, wine, suivi

    def test_la_preparation_occupe_la_barre_jusqu_a_sa_fin(self, fenetre, qtbot):
        barre, wine, suivi = self._pose(qtbot, fenetre)
        ops, jeu = fenetre._detail.ops, fenetre._detail.game
        wine.commencee.emit(jeu)
        assert barre.en_preparation
        # Une opération qui change d'état pendant ce temps ne reprend pas la barre.
        ops._downloader, ops._active_game = object(), jeu
        fenetre.manager.set_game_state(jeu.id, GameState.DOWNLOADING)
        try:
            ops.state_changed.emit()
            assert barre.en_preparation, "l'opération a volé la barre à la préparation"
            # Fin de la préparation : la barre passe à l'opération qui attendait.
            wine.terminee.emit(jeu.id, True, "", False)
            assert not barre.en_preparation
            assert barre.current_game is jeu
        finally:
            ops._downloader = None
            fenetre.manager.set_game_state(jeu.id, GameState.NOT_INSTALLED)
        ops.state_changed.emit()
        assert barre.current_game is None

    def test_annuler_pendant_la_preparation_arrete_la_preparation(self, fenetre, qtbot):
        barre, wine, suivi = self._pose(qtbot, fenetre)
        annulees = []
        fenetre._detail.ops.cancel_download = lambda: annulees.append(1)
        wine.commencee.emit(fenetre._detail.game)
        barre._btn_cancel.click()
        assert wine.annulations == 1
        assert not annulees, "« Annuler » a visé le téléchargement"

    def test_aucune_operation_ne_demarre_depuis_la_fenetre(self, fenetre, qtbot, monkeypatch):
        """Bout en bout, dans la vraie fenêtre : préparation en cours, puis
        réparer, mettre à jour, télécharger. Seuls des toasts ; aucune opération."""
        from src.ui import game_detail_handlers as gdh
        vue = fenetre._detail
        monkeypatch.setattr(gdh, "_boite", lambda *a, **k: pytest.fail("question posée"))
        # « En cours », et rendu DANS le corps du test : pytest-qt ferme la
        # fenêtre avant les finaliseurs, et sa fermeture annule la préparation.
        vue.wine._fil = object()
        try:
            for porte in (gdh.on_repair, gdh.on_update_clicked, gdh.on_download,
                          gdh.on_install_local):
                porte(vue)
                assert not vue.ops.is_busy, porte.__name__
            assert gdh.texte_preparation_en_cours() == fenetre._toast.text()
        finally:
            vue.wine._fil = None

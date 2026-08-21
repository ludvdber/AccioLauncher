"""Fermer le launcher pendant un téléchargement bloqué ne doit pas tuer le processus.

Ce défaut ne peut pas se tester en direct : il ne lève rien, il **abandonne le
processus** (`0xC0000409` sous Windows, SIGABRT ailleurs). Un test ordinaire
emporterait pytest avec lui, et le rapport ne dirait même pas quel test a fauté.
D'où le sous-processus, comme pour `test_rendu_dpi.py`.

Le programme rejoue la séquence EXACTE de `main.py` — `app.exec()`, fermeture,
puis sortie de la fonction, moment où la fenêtre est réellement détruite. C'est
cette dernière étape qui compte : `window.close()` seul ne détruit rien, et une
sonde qui s'arrêtait là concluait à tort que tout allait bien.

Le cas « naif » rejoue l'ancien code (attente dont on jette le résultat) et doit
ÉCHOUER : sans lui, ce fichier ne prouverait pas qu'il sait détecter le défaut.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

RACINE = Path(__file__).resolve().parent.parent

PROGRAMME = r'''
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, %(racine)r)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication

CAS = sys.argv[1]        # "jeu" | "update"
MODE = sys.argv[2]       # "corrige" | "naif"


class Bloque(QThread):
    """Un read reseau mort : cancel() est pose, mais rien ne le relit."""
    def __init__(self, parent, dest):
        super().__init__(parent)
        self.destination = dest
    def cancel(self):
        pass
    def run(self):
        self.sleep(10)


def lancer():
    app = QApplication([])
    tmp = Path(tempfile.mkdtemp(prefix="accio_fermeture_"))
    import src.core.config as cfgmod
    cfgmod.CONFIG_FILE_PATH = tmp / "config.json"
    from src.core.config import Config
    Config(install_path=tmp / "jeux", cache_path=tmp / "jeux" / ".cache",
           langue="fr", autoplay_videos=False).save()

    if MODE == "naif":
        # L'ancien code, restaure : on attend, et on jette le resultat.
        from src.ui.game_operations import GameOperations
        from src.ui.update_dispatcher import UpdateDispatcher

        def cancel_all(self):
            if self._downloader is not None:
                self._downloader.cancel()
                self._downloader.wait(3000)
            if self._installer is not None:
                self._installer.cancel()
                self._installer.wait(3000)
            for z in self._zombies:
                z.wait(1000)
            self._zombies.clear()
        GameOperations.cancel_all = cancel_all

        def shutdown(self):
            self._offline_retry.stop()
            if self._checker is not None:
                self.shutdown_checker(self._checker)
            for c in list(self._extra_checkers):
                self.shutdown_checker(c)
            self._extra_checkers.clear()
            if self._download is not None:
                self._download.cancel()
                self._download.wait(3000)
                self._download = None
        UpdateDispatcher.shutdown = shutdown

    from src.ui.main_window import MainWindow
    MainWindow._start_update_check = lambda self: None
    window = MainWindow()
    window.show()

    if CAS == "jeu":
        proprietaire = window._detail.ops
        faux = Bloque(proprietaire, tmp / "hp3.7z")
        proprietaire._downloader = faux
    else:
        proprietaire = window._updates
        faux = Bloque(proprietaire, tmp / "maj.exe")
        proprietaire._download = faux
    faux.start()
    QThread.msleep(150)

    QTimer.singleShot(200, window.close)
    QTimer.singleShot(300, app.quit)
    app.exec()
    del faux
    return 0


code = lancer()   # la frame meurt ici : la fenetre est detruite, comme main.py
print("FERMETURE PROPRE", flush=True)
sys.exit(code)
'''


def _executer(cas: str, mode: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-c", PROGRAMME % {"racine": str(RACINE)}, cas, mode],
        capture_output=True, text=True, timeout=180, cwd=str(RACINE), env=env,
    )


@pytest.mark.parametrize("cas", ["jeu", "update"])
def test_la_fermeture_survit_a_un_thread_bloque(cas):
    """Un téléchargement sourd à `cancel()` ne doit pas emporter le processus."""
    r = _executer(cas, "corrige")
    assert r.returncode == 0, (
        f"sortie {r.returncode} (0x{r.returncode & 0xFFFFFFFF:08X}) — "
        f"le processus a été abandonné.\n{r.stdout}\n{r.stderr}")
    assert "FERMETURE PROPRE" in r.stdout


@pytest.mark.parametrize("cas", ["jeu", "update"])
def test_le_garde_fou_detecte_bien_l_ancien_code(cas):
    """Sans le correctif, le même scénario DOIT planter.

    Sinon ce fichier passerait au vert sans rien surveiller — le pire des
    tests, celui qui rassure à tort.
    """
    r = _executer(cas, "naif")
    assert r.returncode != 0, (
        "l'ancien code ne plante plus : le scénario ne reproduit plus rien, "
        "ce test ne garde donc plus rien.")
    assert "FERMETURE PROPRE" not in r.stdout


class TestArretBorne:
    """`arreter_a_la_fermeture` — le geste partagé, testé en direct."""

    def test_un_thread_deja_fini_ne_coute_rien(self, qtbot):
        from PyQt6.QtCore import QThread

        from src.core.thread_utils import arreter_a_la_fermeture
        th = QThread()
        assert arreter_a_la_fermeture(th, "inerte") is True

    def test_un_thread_docile_s_arrete_sans_etre_tue(self, qtbot):
        """Le chemin normal : l'interruption suffit, `terminate()` n'est pas atteint."""
        from PyQt6.QtCore import QThread

        from src.core.thread_utils import arreter_a_la_fermeture

        class Docile(QThread):
            tue = False
            def terminate(self):
                Docile.tue = True
                super().terminate()
            def run(self):
                while not self.isInterruptionRequested():
                    self.msleep(10)

        th = Docile()
        th.start()
        qtbot.waitUntil(th.isRunning, timeout=2000)
        assert arreter_a_la_fermeture(th, "docile") is True
        assert not Docile.tue, "un thread qui obéit ne doit jamais être tué"

    def test_un_thread_sourd_est_tue_plutot_que_laisse_vivant(self, qtbot):
        """Le chemin de secours. Le laisser tourner, c'est le plantage à la fermeture."""
        from PyQt6.QtCore import QThread

        from src.core.thread_utils import arreter_a_la_fermeture

        class Sourd(QThread):
            def run(self):
                self.sleep(30)

        th = Sourd()
        th.start()
        qtbot.waitUntil(th.isRunning, timeout=2000)
        assert arreter_a_la_fermeture(th, "sourd") is True
        assert not th.isRunning()

"""Un `QThread` ne se détruit pas depuis le slot de son propre signal de fin.

Les signaux de fin nommés (`download_finished`, `install_finished`, `error`,
`preparation_terminee`) partent de `run()` JUSTE AVANT son retour. Le slot
s'exécute sur le thread principal, donc peut tourner pendant que le thread vit
encore. Le détruire à ce moment — `deleteLater()`, ou la mort du parent dont il
est resté l'enfant après qu'on a oublié sa référence — abandonne le processus :
« QThread: Destroyed while thread is still running », qFatal, code 134. Payé en
CI Linux le 2026-09-24 sur la préparation de Wine, une exécution sur deux.

En production la fenêtre ne dure que quelques microsecondes, d'où l'aléa. Ici
on l'ÉLARGIT : le faux thread émet puis dort 300 ms, et le propriétaire est
détruit pendant ce sommeil. Le défaut devient déterministe.

Sous-processus obligatoire : un qFatal emporterait pytest (cf.
`test_fermeture_threads.py`). Aucun `terminate()` n'est en jeu (règle 3).

Le mode « naif » rétablit l'ancien code — `deleteLater()` nu pour la file des
bandes-annonces et la préparation de Wine, référence simplement oubliée pour
`GameOperations` et `UpdateDispatcher` — et DOIT planter : sans cette
contre-épreuve, ce fichier ne prouverait pas qu'il sait voir le défaut.
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
from types import SimpleNamespace
sys.path.insert(0, %(racine)r)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

CAS = sys.argv[1]
MODE = sys.argv[2]        # "corrige" | "naif"
FENETRE_MS = 300          # ce que dure le « juste avant son retour »

app = QApplication([])
tmp = Path(tempfile.mkdtemp(prefix="accio_fin_de_thread_"))
import src.core.config as cfgmod
cfgmod.CONFIG_FILE_PATH = tmp / "config.json"

from src.core.downloader import Downloader
from src.core.echecs import Echec
from src.core.installer import Installer
from src.core.preparation_wine import PreparationWine


def lent(base, signal, *args):
    """`base` dont run() émet `signal` puis tarde à revenir."""
    class Lent(base):
        def run(self):
            getattr(self, signal).emit(*args)
            self.msleep(FENETRE_MS)
    return Lent


def naif(module, ancien):
    module.liberer_apres_fin = ancien


def detruire_bientot(proprietaire):
    # Pendant le sommeil du faux thread : c'est la mort du parent.
    QTimer.singleShot(100, lambda: sip.delete(proprietaire))


def ops_et_jeu():
    from src.core.game_data import Catalog, GameData
    jeu = GameData.from_dict({
        "id": "hp_test", "name": "Jeu de test", "year": 2001,
        "description": "d", "developer": "dev",
        "executable": "HPTest/System/Game.exe", "cover_image": "c.png",
        "latest_version": "1.0", "recommended_version": "1.0",
        "versions": [{"version": "1.0", "download_url": "https://x/a.7z", "size_mb": 10}],
    })
    import src.core.game_manager as gm
    gm.load_catalog = lambda *a, **k: Catalog("1.0", "", (jeu,))
    from src.core.config import Config
    config = Config(install_path=tmp / "jeux", cache_path=tmp / "cache")
    config.cache_path.mkdir(parents=True)
    from src.ui import game_operations as mod
    return mod, mod.GameOperations(gm.GameManager(config)), jeu


if CAS == "trailer_fini" or CAS == "trailer_erreur":
    from src.core import trailers as store
    from src.core.game_data import Trailer
    from src.ui import trailer_store as mod
    store.TRAILERS_DIR = tmp
    t = Trailer(game_id="hp1", version="1.0", url="https://x/hp1_video.mp4", size_mb=1)
    mod.Downloader = (lent(Downloader, "download_finished", "x") if CAS == "trailer_fini"
                      else lent(Downloader, "error", "hors ligne", Echec()))
    if MODE == "naif":
        naif(mod, lambda th: th.deleteLater())
    manager = SimpleNamespace(trailers=lambda: (t,), trailer_hash=lambda _t: None,
                              trailer_size_mb=lambda _t: 1)
    proprietaire = mod.TrailerStore(manager, None)
    proprietaire.start([t])

elif CAS in ("ops_telechargement_erreur", "ops_installation"):
    mod, proprietaire, jeu = ops_et_jeu()
    if CAS == "ops_telechargement_erreur":
        mod.Downloader = lent(Downloader, "error", "hors ligne", Echec())
    else:
        # Fin de téléchargement → installation → fin d'installation : les deux
        # slots de fin réussie, enchaînés comme en vrai.
        archive = tmp / "cache" / "a.7z"
        mod.Downloader = lent(Downloader, "download_finished", str(archive))
        mod.Installer = lent(Installer, "install_finished", str(tmp / "jeux"))
    if MODE == "naif":
        naif(mod, lambda th: None)
    proprietaire.download(jeu, jeu.current_download)
    if CAS == "ops_installation":
        # Détruire après la FIN D'INSTALLATION, pas après le téléchargement.
        proprietaire.state_changed.connect(
            lambda: proprietaire._installer is None and proprietaire._active_game is None
            and detruire_bientot(proprietaire))
    else:
        detruire_bientot(proprietaire)

elif CAS in ("ops_installation_erreur",):
    mod, proprietaire, jeu = ops_et_jeu()
    mod.Installer = lent(Installer, "error", "archive corrompue")
    if MODE == "naif":
        naif(mod, lambda th: None)
    proprietaire.install(jeu, tmp / "cache" / "a.7z")
    detruire_bientot(proprietaire)

elif CAS in ("maj_fini", "maj_erreur"):
    from src.ui import update_dispatcher as mod
    mod.can_self_update = lambda: True
    mod.apply_update_and_restart = lambda _p: False
    mod.Downloader = (lent(Downloader, "download_finished", str(tmp / "maj.exe"))
                      if CAS == "maj_fini"
                      else lent(Downloader, "error", "hors ligne", Echec()))
    if MODE == "naif":
        naif(mod, lambda th: None)
    manager = SimpleNamespace(config=SimpleNamespace(cache_path=tmp))
    proprietaire = mod.UpdateDispatcher(manager)
    proprietaire.asset_url = "https://x/AccioLauncher.exe"
    proprietaire.download()
    detruire_bientot(proprietaire)

elif CAS == "preparation_wine":
    from src.ui import preparateur_wine as mod
    mod.compat = SimpleNamespace(lanceur=lambda: SimpleNamespace(famille="wine"),
                                 prefixe=lambda _f: tmp / "prefixe",
                                 dossier_journaux=lambda: tmp)
    mod.PreparationWine = lent(PreparationWine, "preparation_terminee", True, "")
    if MODE == "naif":
        naif(mod, lambda th: th.deleteLater())
    proprietaire = mod.PreparateurWine()
    assert proprietaire.demarrer(SimpleNamespace(id="hp1"), [], puis_jouer=False)
    detruire_bientot(proprietaire)

else:
    raise SystemExit(f"cas inconnu : {CAS}")

QTimer.singleShot(800, app.quit)
app.exec()
print("SORTIE PROPRE", flush=True)
'''

CAS = [
    "trailer_fini", "trailer_erreur",
    "ops_telechargement_erreur", "ops_installation", "ops_installation_erreur",
    "maj_fini", "maj_erreur",
    "preparation_wine",
]


def _executer(cas: str, mode: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-c", PROGRAMME % {"racine": str(RACINE)}, cas, mode],
        capture_output=True, text=True, timeout=120, cwd=str(RACINE), env=env,
    )


@pytest.mark.parametrize("cas", CAS)
def test_le_slot_de_fin_attend_le_thread(cas):
    r = _executer(cas, "corrige")
    assert r.returncode == 0 and "SORTIE PROPRE" in r.stdout, (
        f"sortie {r.returncode} — le processus a été abandonné.\n{r.stdout}\n{r.stderr}")
    assert "Destroyed while thread" not in r.stderr


@pytest.mark.parametrize("cas", CAS)
def test_l_ancien_code_plante_bien(cas):
    """Contre-épreuve : sans le correctif, le même scénario DOIT planter."""
    r = _executer(cas, "naif")
    assert r.returncode != 0 and "SORTIE PROPRE" not in r.stdout, (
        "l'ancien code ne plante plus : le scénario ne reproduit plus rien, "
        f"ce test ne garde donc plus rien.\n{r.stdout}\n{r.stderr}")
    assert "Destroyed while thread" in r.stderr

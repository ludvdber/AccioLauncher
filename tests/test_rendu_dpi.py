"""Rendu à une échelle d'affichage FRACTIONNAIRE (125 %, le réglage de Ludo).

Toute la suite tourne à l'échelle 1 : `QT_SCALE_FACTOR` doit être posé avant la
création de QApplication, or pytest-qt n'en crée qu'une pour toute la session.
Un défaut qui n'existe qu'à 125 % est donc structurellement invisible ici —
c'est exactement ce qui a laissé passer la couture d'un pixel au-dessus du
carrousel, signalée deux fois par l'utilisateur alors que la mesure à l'échelle
1 donnait « écart exactement 0 ».

D'où le sous-processus : c'est le seul moyen d'obtenir une vraie échelle
fractionnaire. Il coûte quelques secondes, à comparer au coût d'un défaut
visible en permanence sur l'écran principal du launcher.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

RACINE = Path(__file__).resolve().parent.parent

# Le programme tourne dans le sous-processus : il construit une vraie fenêtre,
# la capture, et compare la rangée du raccord à ses deux voisines.
PROGRAMME = r'''
import os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, %(racine)r)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

TMP = Path(tempfile.mkdtemp(prefix="accio_dpi_"))
import src.core.config as cfgmod
cfgmod.CONFIG_FILE_PATH = TMP / "config.json"
from src.core.config import Config
Config(install_path=TMP / "jeux", cache_path=TMP / "jeux" / ".cache",
       langue="fr", autoplay_videos=False).save()

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
import src.ui.main_window as mw
mw.MainWindow._start_update_check = lambda self: None
app = QApplication(sys.argv[:1])
w = mw.MainWindow()
w.resize(1270, 844)
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
w.show()
# Particules et étoiles sont aléatoires : elles contamineraient la mesure.
w._particles.hide()
w._carousel._stars = []
fin = time.time() + 2.0
while time.time() < fin:
    app.processEvents()
w.repaint(); app.processEvents()

img = w.grab().toImage()
dpr = img.width() / w.width()
assert dpr > 1.2, "l'echelle fractionnaire n'a pas ete appliquee (dpr=%%s)" %% dpr
frontiere = int(w._carousel.y() * dpr)

def moyenne(y):
    total = 0
    n = 0
    for x in range(0, img.width(), 4):
        c = img.pixelColor(x, y)
        total += c.red() + c.green() + c.blue()
        n += 3
    return total / n

haut, couture, bas = moyenne(frontiere - 2), moyenne(frontiere - 1), moyenne(frontiere)
ecart = couture - (haut + bas) / 2
print("DPR=%%.2f FRONTIERE=%%d ECART=%%.4f" %% (dpr, frontiere, ecart))
''' % {"racine": str(RACINE)}



def test_aucune_couture_au_raccord_du_carrousel_a_125_pourcent(tmp_path):
    """Un trait clair d'un pixel séparait la fiche du carrousel à 125 %.

    Cause : l'illustration est peinte en QRectF avec antialiasing et débordait
    d'une rangée physique sous le bord du widget, là où l'overlay opaque, posé
    depuis un pixmap à coordonnées entières, s'arrêtait. Invisible à 100 %,
    permanente à 125 %.
    """
    script = tmp_path / "mesure_dpi.py"
    script.write_text(PROGRAMME, encoding="utf-8")

    env = dict(os.environ)
    env["QT_SCALE_FACTOR"] = "1.25"
    env["PYTHONIOENCODING"] = "utf-8"
    resultat = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, env=env, cwd=str(RACINE), timeout=180,
    )
    assert resultat.returncode == 0, (
        "le sous-processus a échoué :\n%s\n%s" % (resultat.stdout, resultat.stderr))

    ligne = [x for x in resultat.stdout.splitlines() if x.startswith("DPR=")]
    assert ligne, "mesure absente :\n%s\n%s" % (resultat.stdout, resultat.stderr)
    ecart = float(ligne[-1].split("ECART=")[1])
    assert abs(ecart) < 1.0, (
        "couture d'un pixel au raccord fiche/carrousel : écart %.3f de "
        "luminance avec les rangées voisines (%s)" % (ecart, ligne[-1]))

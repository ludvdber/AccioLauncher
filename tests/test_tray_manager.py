"""Zone de notification : ce qui rouvre la fenêtre, et ce qui ne doit pas.

`TrayManager` n'avait aucun test, et il portait un défaut d'usage pur : seul
le DOUBLE-clic restaurait. Sous Windows, la convention de la zone de
notification est le clic gauche SIMPLE — Steam, Discord, Spotify et Teams
rouvrent tous au premier clic. Il fallait donc soit deviner qu'un double-clic
était exigé là où rien d'autre n'en demande, soit passer par « Restaurer » du
menu contextuel. Signalé par Ludo le 2026-08-30.

Le routage se teste en appelant `_on_activated` avec chaque raison : c'est la
seule logique du fichier, et la déclencher pour de vrai supposerait un vrai
clic dans une vraie zone de notification.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QWidget

from src.ui.tray_manager import TrayManager

RAISON = QSystemTrayIcon.ActivationReason


@pytest.fixture
def tray(qtbot):
    """`yield` et non `return` : le parent doit rester VIVANT.

    `TrayManager` a le QWidget pour parent Qt ; rendre le manager seul laisse
    Python ramasser le parent, Qt détruit l'enfant avec lui, et le test tombe
    sur « wrapped C/C++ object has been deleted » — mesuré, pas supposé.
    """
    parent = QWidget()
    qtbot.addWidget(parent)
    yield TrayManager(QIcon(), parent)


class TestCeQuiRouvreLaFenetre:
    def test_le_clic_gauche_simple_restaure(self, tray, qtbot):
        """LE test : il échoue sur le code d'avant, qui n'écoutait que
        `DoubleClick`."""
        with qtbot.waitSignal(tray.restore_requested, timeout=500):
            tray._on_activated(RAISON.Trigger)

    def test_le_double_clic_restaure_toujours(self, tray, qtbot):
        """Ne pas casser l'ancien geste en ajoutant le nouveau : quelqu'un qui
        a pris l'habitude du double-clic ne doit pas le voir cesser de
        marcher."""
        with qtbot.waitSignal(tray.restore_requested, timeout=500):
            tray._on_activated(RAISON.DoubleClick)


class TestCeQuiNeDoitPasRouvrir:
    def test_le_clic_droit_ne_restaure_pas(self, tray, qtbot):
        """Qt sert déjà le clic droit par `setContextMenu` : le faire restaurer
        ouvrirait la fenêtre EN MÊME TEMPS que le menu, donc un menu posé sur
        une fenêtre qui vient de surgir."""
        with qtbot.assertNotEmitted(tray.restore_requested):
            tray._on_activated(RAISON.Context)

    def test_le_clic_milieu_ne_restaure_pas(self, tray, qtbot):
        """Le clic du milieu n'a pas de sens établi dans une zone de
        notification : ne rien faire est plus honnête que deviner."""
        with qtbot.assertNotEmitted(tray.restore_requested):
            tray._on_activated(RAISON.MiddleClick)

    def test_un_survol_ne_restaure_pas(self, tray, qtbot):
        """`Unknown` couvre notamment le survol sur certaines plateformes — une
        fenêtre qui se rouvre au passage de la souris serait insupportable."""
        with qtbot.assertNotEmitted(tray.restore_requested):
            tray._on_activated(RAISON.Unknown)

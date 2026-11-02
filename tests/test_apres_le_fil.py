"""`ui.utils.apres_le_fil` : un travail sur un fil, sa fin dans le fil de l'interface.

Grand audit du 2026-11-02 : un signal émis d'un fil vers un objet en pleine
destruction levait « 'NoneType' object is not callable » dans la boucle de Qt
(une fois sur sept au démontage d'un test de la Médiathèque). La fin est
désormais guettée par un minuteur que possède l'objet.
"""
import threading

from PyQt6.QtCore import QObject

from src.ui.utils import apres_le_fil


def test_la_fin_arrive_dans_le_fil_de_l_interface(qtbot):
    proprietaire = QObject()
    fils, fins = [], []
    apres_le_fil(proprietaire, lambda: fils.append(threading.current_thread()) or 42,
                 lambda r: fins.append((threading.current_thread(), r)), "essai")
    qtbot.waitUntil(lambda: len(fins) == 1, timeout=5000)
    assert fils[0] is not threading.main_thread()
    assert fins == [(threading.main_thread(), 42)]


def test_proprietaire_detruit_plus_rien_n_arrive(qtbot):
    proprietaire = QObject()
    libre, fins = threading.Event(), []
    apres_le_fil(proprietaire, lambda: libre.wait(5) and 1, fins.append, "essai")
    proprietaire.deleteLater()
    qtbot.wait(50)                          # détruit pendant le travail
    libre.set()
    qtbot.wait(100)
    assert fins == []


def test_un_travail_qui_leve_n_appelle_pas_la_fin(qtbot):
    proprietaire = QObject()
    fins = []

    def casse():
        raise OSError("disque")
    apres_le_fil(proprietaire, casse, fins.append, "essai")
    qtbot.wait(150)
    assert fins == []

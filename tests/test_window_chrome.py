"""Bords saisissables d'une fenêtre sans cadre.

Ces 95 lignes ont vécu dans `main_window.py` sans un seul test : pour les
exercer il fallait construire la fenêtre entière, donc personne ne le faisait.
La géométrie étant maintenant PURE, on peut balayer les huit zones sans écran.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from src.ui.window_chrome import (  # noqa: E402
    MARGE_BORD, WindowChrome, bords_a, curseur_pour,
)

E = Qt.Edge
L, H = 1000, 800


class TestGeometrieDesBords:
    """`bords_a` est pure : ni fenêtre, ni écran, ni QApplication."""

    @pytest.mark.parametrize("x,y,attendu", [
        (500, 400, E(0)),                              # plein centre
        (2, 400, E.LeftEdge),
        (998, 400, E.RightEdge),
        (500, 2, E.TopEdge),
        (500, 798, E.BottomEdge),
        (2, 2, E.LeftEdge | E.TopEdge),
        (998, 2, E.RightEdge | E.TopEdge),
        (2, 798, E.LeftEdge | E.BottomEdge),
        (998, 798, E.RightEdge | E.BottomEdge),
    ])
    def test_les_huit_zones(self, x, y, attendu):
        assert bords_a(x, y, L, H) == attendu

    def test_la_marge_est_inclusive_des_deux_cotes(self):
        """Le pixel exactement à la marge appartient encore au bord.

        C'est l'erreur classique du `>=` devenu `>` : la zone perd un pixel
        de chaque côté, ce qui ne se voit jamais en test manuel mais rend le
        bord plus dur à attraper sur un écran à forte densité.
        """
        assert bords_a(MARGE_BORD, 400, L, H) == E.LeftEdge
        assert bords_a(MARGE_BORD + 1, 400, L, H) == E(0)
        assert bords_a(L - MARGE_BORD, 400, L, H) == E.RightEdge
        assert bords_a(L - MARGE_BORD - 1, 400, L, H) == E(0)

    def test_une_fenetre_plus_etroite_que_deux_marges_ne_rend_pas_deux_bords(self):
        """Gauche et droite ne peuvent jamais sortir ensemble.

        `startSystemResize(LeftEdge | RightEdge)` n'a aucun sens ; les `elif`
        de `bords_a` sont là pour ça, et non par style.
        """
        bords = bords_a(4, 4, 8, 8)
        assert not (bords & E.LeftEdge and bords & E.RightEdge)
        assert not (bords & E.TopEdge and bords & E.BottomEdge)


class TestFormeDuCurseur:
    def test_les_diagonales_suivent_le_sens_du_trait(self):
        assert curseur_pour(E.LeftEdge | E.TopEdge) == Qt.CursorShape.SizeFDiagCursor
        assert curseur_pour(E.RightEdge | E.BottomEdge) == Qt.CursorShape.SizeFDiagCursor
        assert curseur_pour(E.RightEdge | E.TopEdge) == Qt.CursorShape.SizeBDiagCursor
        assert curseur_pour(E.LeftEdge | E.BottomEdge) == Qt.CursorShape.SizeBDiagCursor

    def test_les_cotes(self):
        assert curseur_pour(E.LeftEdge) == Qt.CursorShape.SizeHorCursor
        assert curseur_pour(E.BottomEdge) == Qt.CursorShape.SizeVerCursor

    def test_aucun_bord_aucun_curseur(self):
        assert curseur_pour(E(0)) is None


class TestPileDeCurseurs:
    """`setOverrideCursor` EMPILE : le suivi doit être exact.

    Un empilement sans dépilement laisse un curseur de redimensionnement collé
    sur TOUTE l'application, dialogues compris ; un dépilement de trop retire
    le curseur d'attente de quelqu'un d'autre.
    """

    def _chrome(self, qtbot):
        w = QWidget()
        w.resize(L, H)
        qtbot.addWidget(w)
        return WindowChrome(w)

    def test_survoler_le_centre_ne_pose_rien(self, qtbot):
        c = self._chrome(qtbot)
        c.survol(QPoint(500, 400))
        assert not c.curseur_pose

    def test_pose_puis_relache_une_seule_fois(self, qtbot):
        c = self._chrome(qtbot)
        c.survol(QPoint(2, 400))
        assert c.curseur_pose
        c.survol(QPoint(500, 400))          # retour au centre
        assert not c.curseur_pose

    def test_glisser_le_long_du_bord_ne_reempile_pas(self, qtbot):
        """De gauche à haut-gauche : le curseur CHANGE, il ne s'empile pas.

        Sans ce chemin, longer un bord empilerait un curseur par pixel
        parcouru — et il en faudrait autant pour revenir.
        """
        c = self._chrome(qtbot)
        for y in (400, 300, 200, 100, 2):
            c.survol(QPoint(2, y))
            assert c.curseur_pose
        c.relacher_curseur()
        assert not c.curseur_pose

    def test_relacher_est_idempotent(self, qtbot):
        c = self._chrome(qtbot)
        c.relacher_curseur()
        c.relacher_curseur()
        assert not c.curseur_pose


class TestSaisie:
    def test_le_centre_ne_saisit_rien(self, qtbot):
        w = QWidget()
        w.resize(L, H)
        qtbot.addWidget(w)
        assert WindowChrome(w).saisir(QPoint(500, 400)) is False

    def test_sans_poignee_de_fenetre_on_ne_saisit_pas(self, qtbot):
        """Un widget jamais montré n'a pas de `windowHandle()`.

        Le code appelait `startSystemResize` dessus ; il était protégé par un
        `try` deux niveaux plus haut, donc l'échec était SILENCIEUX.
        """
        w = QWidget()
        w.resize(L, H)
        qtbot.addWidget(w)
        assert w.windowHandle() is None
        assert WindowChrome(w).saisir(QPoint(2, 2)) is False

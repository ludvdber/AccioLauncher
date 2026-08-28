"""Redimensionnement d'une fenêtre sans cadre par la saisie de ses bords.

Extrait de `main_window.py` le 2026-08-28. Ce n'est pas un découpage
cosmétique : c'était le seul bloc de la fenêtre à ne toucher AUCUN objet
métier — ni catalogue, ni jeu, ni configuration —, et c'était aussi le seul
sans le moindre test. Les deux vont ensemble : une logique noyée dans une
fenêtre de 965 lignes ne s'exerce qu'en construisant cette fenêtre, donc on ne
l'exerce pas.

La géométrie est une FONCTION PURE (`bords_a`), séparée du curseur : décider
quel bord est sous le pointeur ne demande ni fenêtre, ni écran, ni Qt vivant,
et c'est là que se cachent les erreurs de bord (le `>=` qui devient `>`, la
marge comptée deux fois dans un coin).
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QGuiApplication

# Zone de saisie des bords, en pixels. 6 px est un compromis mesuré à
# l'usage : en dessous le bord se rate à la souris, au-dessus il vole des
# clics aux boutons posés près du cadre.
MARGE_BORD = 6


def bords_a(x: int, y: int, largeur: int, hauteur: int,
            marge: int = MARGE_BORD) -> Qt.Edge:
    """Bords touchés par le point (x, y) dans une fenêtre `largeur`×`hauteur`.

    Fonction PURE — aucun widget, aucun état. Les tests peuvent donc balayer
    les quatre coins et les quatre côtés sans construire de fenêtre.

    Un coin rend DEUX bords (`LeftEdge | TopEdge`) : c'est ce que
    `startSystemResize` attend pour redimensionner en diagonale. Les `elif`
    sont voulus — sur une fenêtre plus étroite que deux fois la marge, gauche
    et droite se recouvriraient et le `|` rendrait un couple contradictoire.
    """
    bords = Qt.Edge(0)
    if x <= marge:
        bords |= Qt.Edge.LeftEdge
    elif x >= largeur - marge:
        bords |= Qt.Edge.RightEdge
    if y <= marge:
        bords |= Qt.Edge.TopEdge
    elif y >= hauteur - marge:
        bords |= Qt.Edge.BottomEdge
    return bords


def curseur_pour(bords: Qt.Edge) -> Qt.CursorShape | None:
    """Forme du curseur annonçant ce redimensionnement, None s'il n'y en a pas.

    Pure elle aussi. Les diagonales se lisent dans le sens du trait : `FDiag`
    descend vers la droite (haut-gauche ↔ bas-droite), `BDiag` monte.
    """
    E = Qt.Edge
    if (bords & E.LeftEdge and bords & E.TopEdge) or \
       (bords & E.RightEdge and bords & E.BottomEdge):
        return Qt.CursorShape.SizeFDiagCursor
    if (bords & E.RightEdge and bords & E.TopEdge) or \
       (bords & E.LeftEdge and bords & E.BottomEdge):
        return Qt.CursorShape.SizeBDiagCursor
    if bords & (E.LeftEdge | E.RightEdge):
        return Qt.CursorShape.SizeHorCursor
    if bords & (E.TopEdge | E.BottomEdge):
        return Qt.CursorShape.SizeVerCursor
    return None


class WindowChrome:
    """Curseur de bord et redimensionnement natif d'une fenêtre sans cadre.

    Porte le seul état du dispositif : `_curseur_pose`, qui dit si un
    override-cursor applicatif est actuellement empilé. Il doit être suivi
    exactement — `setOverrideCursor` EMPILE, et un empilement sans dépilement
    laisse un curseur de redimensionnement collé sur toute l'application,
    y compris par-dessus les dialogues.
    """

    def __init__(self, fenetre, marge: int = MARGE_BORD) -> None:
        self._fenetre = fenetre
        self._marge = marge
        self._curseur_pose = False

    @property
    def curseur_pose(self) -> bool:
        """Un override-cursor est-il empilé en ce moment ?"""
        return self._curseur_pose

    def bords_sous(self, local) -> Qt.Edge:
        """Bords sous un point en coordonnées locales de la fenêtre."""
        return bords_a(local.x(), local.y(),
                       self._fenetre.width(), self._fenetre.height(),
                       self._marge)

    def survol(self, local) -> None:
        """Pose, change ou retire le curseur selon le bord survolé."""
        forme = curseur_pour(self.bords_sous(local))
        if forme is None:
            self.relacher_curseur()
            return
        if self._curseur_pose:
            QGuiApplication.changeOverrideCursor(QCursor(forme))
        else:
            QGuiApplication.setOverrideCursor(QCursor(forme))
            self._curseur_pose = True

    def relacher_curseur(self) -> None:
        """Dépile le curseur s'il y en a un. Idempotent — un dépilement de
        trop retirerait le curseur de quelqu'un d'autre."""
        if self._curseur_pose:
            QGuiApplication.restoreOverrideCursor()
            self._curseur_pose = False

    def saisir(self, local) -> bool:
        """Démarre le redimensionnement natif. True = pris en charge.

        Passe la main au gestionnaire de fenêtres (`startSystemResize`) plutôt
        que de suivre la souris nous-mêmes : c'est lui qui connaît les
        accrochages, les bords d'écran et le retour haptique de la plateforme.
        """
        bords = self.bords_sous(local)
        poignee = self._fenetre.windowHandle()
        if not bords or poignee is None:
            return False
        poignee.startSystemResize(bords)
        return True

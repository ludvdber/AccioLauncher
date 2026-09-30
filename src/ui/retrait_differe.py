"""Sous Linux, la fenêtre se retire quand le jeu prend la main, pas au clic sur JOUER.

Proton met jusqu'à une minute à ouvrir la fenêtre du jeu (Ludo, Bazzite,
2026-09-30 : « il faut attendre plus d'une minute, on pense que ça a planté »).
Une fenêtre qui disparaît au clic laissait le bureau vide pendant tout ce
temps. Elle reste, la fenêtre dit ce qui se passe, et se retire quand elle
perd l'activation (le jeu vient devant), ou au bout de `ATTENTE_MS` au plus.
Sous Windows, où le jeu paraît en quelques secondes, rien ne change.
"""

import sys

from PyQt6.QtCore import QObject, QTimer

ATTENTE_MS = 120_000


class RetraitDiffere(QObject):
    def __init__(self, retirer, parent=None) -> None:
        super().__init__(parent)
        self._retirer = retirer
        self._nom = ""
        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.setInterval(ATTENTE_MS)
        self._minuteur.timeout.connect(self._finir)

    @property
    def attend(self) -> bool:
        return bool(self._nom)

    def differer(self, nom: str, fenetre_active: bool) -> bool:
        """True si le retrait attend le jeu ; False : l'appelant se retire tout de suite."""
        if sys.platform == "win32" or not fenetre_active:
            return False
        self._nom = nom
        self._minuteur.start()
        return True

    def desactivee(self) -> None:
        """La fenêtre vient de perdre l'activation : le jeu a pris la main."""
        if self._nom:
            self._finir()

    def oublier(self) -> None:
        """Le jeu s'est fermé avant d'avoir pris la main : plus rien à attendre."""
        self._nom = ""
        self._minuteur.stop()

    def _finir(self) -> None:
        if not self._nom:
            return
        self.oublier()
        self._retirer()

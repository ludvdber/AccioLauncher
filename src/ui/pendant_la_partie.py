"""Pendant une partie, le launcher se fait oublier (audit du 2026-11-13, règle 141).

Hors de `main_window.py` (plafond de lignes, `test_update_dispatcher`) : la fenêtre appelle `brancher` en
construisant sa session, et n'en sait pas plus.

- les fonds préchargés de la fiche (≈ 106 Mo pour les huit) sont rendus au jeu au lancement, et reviennent dès
  qu'on rouvre le launcher, ou au retour (Ludo, 2026-11-15) ;
- la question « Mise à jour disponible » ne s'ouvre pas par-dessus le jeu (`_propose_launcher_update` se tait tant
  qu'un jeu tourne) : elle est reposée au retour, sauf après un arrêt fatal, dont la boîte passe d'abord.

Au lancement, `GameSession.demarrer` appelle `liberer_les_caches` : paquets des jeux, folios, jaquettes
et fonds décodés lus par l'accueil, le Carnet et les Collections. Tout se relit à la demande au retour
(audit UI f113 : le launcher pesait 205 Mo pendant la partie au lieu de 144).
"""
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QObject, QTimer

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


def liberer_les_caches() -> None:
    """Ce qui ne sert qu'à l'accueil, au Carnet et aux Collections, rendu au jeu qui démarre."""
    from src.core import folio_hp3, folio_hp6, maillages_ue1, octets_gardes, textures_ue1
    from src.ui import background_widget, stats_releve
    textures_ue1.liberer()
    maillages_ue1.liberer()
    folio_hp3.liberer()
    folio_hp6.liberer()
    octets_gardes.liberer()
    stats_releve.liberer()
    background_widget.liberer_fonds_decodes()


class _LauncherRouvert(QObject):
    """La fenêtre reprend la main pendant la partie : ses fonds reviennent tout de suite,
    sans attendre la fin du jeu (sans partie, `fonds_pendant_la_partie` n'y fait rien)."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window

    def eventFilter(self, objet: QObject | None, event: QEvent | None) -> bool:  # noqa: N802 (Qt)
        if (event is not None and event.type() == QEvent.Type.ActivationChange
                and self._window.isActiveWindow() and not self._window.isMinimized()):
            self._window._detail.fonds_pendant_la_partie(False)
        return False


def brancher(window: MainWindow) -> None:
    window._session.demarree.connect(lambda _nom: window._detail.fonds_pendant_la_partie(True))
    window.installEventFilter(_LauncherRouvert(window))
    window._session.terminee.connect(lambda _nom, _partie, arret: au_retour(window, arret))


def au_retour(window: MainWindow, arret: bool) -> None:
    window._detail.fonds_pendant_la_partie(False)
    if window._updates.version and not arret:
        QTimer.singleShot(0, window._propose_launcher_update)

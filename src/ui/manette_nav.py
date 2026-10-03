"""Naviguer dans le launcher à la manette, depuis le canapé.

Demandé par Ludo (2026-10-03) : « évite de devoir se lever et utiliser la
souris ». Le launcher se pilotait déjà entièrement au clavier ; la manette
ne crée donc AUCUN chemin à elle : chaque appui devient la touche que le
clavier enverrait, et tout ce qui marche au clavier (carrousel, fiche,
dialogues, réglages, assistant) marche à la manette, sans un widget modifié.

| Manette                       | Touche     | Effet                                   |
|-------------------------------|------------|-----------------------------------------|
| croix directionnelle / stick  | ← →        | jeu précédent / suivant                 |
|                               | ↑ ↓        | bouton précédent / suivant (Maj+Tab, Tab), ou ↑ ↓ dans une liste |
| croix (PlayStation) / A       | Espace     | appuie sur le bouton qui a le focus     |
|                               | Entrée     | sans bouton sous le focus : JOUER ; dans une liste : choisir |
| rond / B                      | Échap      | ferme le dialogue, sort du plein écran  |
| L1 / R1                       | ← →        | jeu précédent / suivant, même dans une liste |
| stick droit                   | —          | fait défiler la page                    |

Lue seulement quand le launcher est l'application active : pendant une
partie, c'est le jeu qui a la manette, et le minuteur s'arrête (zéro
lecture). Au retour, ce qu'on tenait encore n'agit pas (`Repetition.reprendre`).
Réglage : `config.navigation_manette`, page Intégrations.
"""

from __future__ import annotations

import logging
import threading
import time

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QCursor, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QAbstractSpinBox, QApplication,
    QComboBox, QLineEdit, QSlider, QWidget,
)

from src.core import manette_lecture as lecture

log = logging.getLogger(__name__)

# Ces widgets gardent leurs flèches ↑ ↓ : elles y ont un sens (même liste
# que `clavier_global._EDITION`, plus les listes, dont les popups des combos).
_GARDENT_HAUT_BAS = (QLineEdit, QComboBox, QSlider, QAbstractSpinBox, QAbstractItemView)
# Espace y écrirait ou n'y ferait rien : on y valide par Entrée.
_VALIDENT_PAR_ENTREE = (QLineEdit, QAbstractSpinBox, QAbstractItemView)

PERIODE_MS = 16            # 60 lectures par seconde : un appui bref (≈ 60 ms) n'échappe pas
PERIODE_SANS_MANETTE_MS = 500
DEFILEMENT_PX = 22         # par lecture, stick droit à fond : ≈ 1 400 px/s


class NavigationManette(QObject):
    """Lit la manette et rejoue ses appuis comme des touches du clavier."""

    def __init__(self, app: QApplication, lecteur=None, horloge=time.monotonic) -> None:
        super().__init__(app)
        self._app = app
        self._lecteur = lecteur if lecteur is not None else lecture.lecteur()
        self._horloge = horloge
        self._repetition = lecture.Repetition()
        self._reprendre = True
        self._actif = False
        self._timer = QTimer(self)
        self._timer.setInterval(PERIODE_MS)
        self._timer.timeout.connect(self._lire)
        app.applicationStateChanged.connect(self._sur_etat_application)
        # Le premier appel à WinMM coûte 17 ms : payé sur un fil à part.
        threading.Thread(target=self._prechauffer, name="manette-nav", daemon=True).start()

    def _prechauffer(self) -> None:
        try:
            self._lecteur.prechauffer()
        except OSError as exc:            # jamais une erreur : au pire, pas de manette
            log.info("Manette (navigation) : %s", exc)

    # ── marche / arrêt ──

    def set_actif(self, actif: bool) -> None:
        self._actif = actif
        self._mettre_a_jour()

    @property
    def actif(self) -> bool:
        return self._actif

    def _sur_etat_application(self, _etat) -> None:
        self._mettre_a_jour()

    def _mettre_a_jour(self) -> None:
        en_marche = (self._actif
                     and self._app.applicationState() == Qt.ApplicationState.ApplicationActive)
        if en_marche and not self._timer.isActive():
            self._reprendre = True
            self._timer.start()
        elif not en_marche:
            self._timer.stop()

    # ── lecture ──

    def _lire(self) -> None:
        maintenant = self._horloge()
        try:
            etat = self._lecteur.lire(maintenant)
        except OSError as exc:
            log.info("Manette (navigation) : %s", exc)
            etat = lecture.Etat()
        # Pas de manette : on regarde deux fois par seconde si une arrive.
        self._timer.setInterval(PERIODE_MS if self._lecteur.nombre() else PERIODE_SANS_MANETTE_MS)
        if self._reprendre:
            self._repetition.reprendre(etat)
            self._reprendre = False
            return
        for action in self._repetition.actions(etat, maintenant):
            self.agir(action)
        vitesse = lecture.defilement_utile(etat.defilement)
        if vitesse:
            self._defiler(vitesse)

    # ── actions ──

    @staticmethod
    def _cible() -> QWidget | None:
        """Où va la touche : le menu ouvert, sinon le focus, sinon la fenêtre active."""
        return (QApplication.activePopupWidget() or QApplication.focusWidget()
                or QApplication.activeWindow())

    @staticmethod
    def _envoyer(cible: QWidget, touche: Qt.Key,
                 modificateurs=Qt.KeyboardModifier.NoModifier) -> None:
        # Par `sendEvent` : la touche passe par les filtres de QApplication
        # (←/→ du carrousel, anneau de focus) exactement comme une vraie.
        for type_ in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(cible, QKeyEvent(type_, touche, modificateurs))

    def agir(self, action: str) -> None:
        cible = self._cible()
        if cible is None:
            return
        focus = QApplication.focusWidget()
        dans_un_menu = QApplication.activePopupWidget() is not None
        match action:
            case lecture.GAUCHE | lecture.PRECEDENT:
                self._envoyer(cible, Qt.Key.Key_Left)
            case lecture.DROITE | lecture.SUIVANT:
                self._envoyer(cible, Qt.Key.Key_Right)
            case lecture.HAUT | lecture.BAS:
                if dans_un_menu or isinstance(focus, _GARDENT_HAUT_BAS):
                    self._envoyer(cible, Qt.Key.Key_Up if action == lecture.HAUT else Qt.Key.Key_Down)
                elif action == lecture.HAUT:
                    self._envoyer(cible, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
                else:
                    self._envoyer(cible, Qt.Key.Key_Tab)
            case lecture.VALIDER:
                if dans_un_menu or focus is None or focus.isWindow() \
                        or isinstance(focus, _VALIDENT_PAR_ENTREE):
                    self._envoyer(cible, Qt.Key.Key_Return)
                else:
                    self._envoyer(cible, Qt.Key.Key_Space)
            case lecture.RETOUR:
                self._envoyer(cible, Qt.Key.Key_Escape)

    @staticmethod
    def _zone_defilante() -> QAbstractScrollArea | None:
        """La zone qui défile : celle qui contient le focus, sinon celle sous la souris."""
        for depart in (QApplication.focusWidget(), QApplication.widgetAt(QCursor.pos())):
            widget = depart
            while widget is not None:
                if isinstance(widget, QAbstractScrollArea) \
                        and widget.verticalScrollBar().maximum() > 0:
                    return widget
                widget = widget.parentWidget()
        return None

    def _defiler(self, vitesse: float) -> None:
        zone = self._zone_defilante()
        if zone is not None:
            barre = zone.verticalScrollBar()
            barre.setValue(barre.value() + round(vitesse * DEFILEMENT_PX))


_navigation: NavigationManette | None = None


def install(app: QApplication, actif: bool) -> NavigationManette:
    """À appeler une fois, après QApplication : couvre aussi l'assistant de
    premier lancement, qui vit avant la fenêtre principale."""
    global _navigation
    if _navigation is None:
        _navigation = NavigationManette(app)
    _navigation.set_actif(actif)
    return _navigation


def navigation() -> NavigationManette | None:
    return _navigation

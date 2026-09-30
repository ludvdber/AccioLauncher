"""L'éditeur de touches de HP4 : chaque action du jeu, et la touche qu'on lui donne.

Un clic sur la touche d'une action, puis la touche (ou le bouton de souris)
voulue : elle est écrite AUSSITÔT dans `[Accio.Keys]` du `d3d9.ini`, comme tout
réglage du correctif. Échap annule. Le calcul (noms, conflits, écriture) vit
dans `core/touches_correctif` ; ici, seulement l'appui et ce qu'on en montre.

Pourquoi le dire à l'écran plutôt que le laisser découvrir en jeu : le
correctif RETIRE à une touche son rôle d'origine quand on la donne à une autre
action. Poser S sur Reculer (un AZERTY qui veut ZQSD) laisse Extremos sans
touche — le préréglage l'avait prévu en lui donnant R ; un joueur qui compose
les siennes doit le voir avant de lancer le jeu.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.core import touches_correctif as tc
from src.core.i18n import tr
from src.ui.fonts import body_font
from src.ui.theme import themed

log = logging.getLogger(__name__)

_LARGEUR_TOUCHE = 176

# Qt → nom lu par le correctif (keys.cpp, kNamedKeys).
_NOMMEES = {
    Qt.Key.Key_Space: "Space", Qt.Key.Key_Return: "Enter", Qt.Key.Key_Enter: "NumEnter",
    Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Backtab: "Tab", Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_CapsLock: "CapsLock", Qt.Key.Key_AltGr: "RAlt",
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down", Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "PageUp", Qt.Key.Key_PageDown: "PageDown",
    **{getattr(Qt.Key, f"Key_F{n}"): f"F{n}" for n in range(1, 13)},
}
# Pavé numérique verrouillage éteint : Qt dit « flèche », DirectInput « Num8 ».
_PAVE = {
    Qt.Key.Key_Insert: "Num0", Qt.Key.Key_End: "Num1", Qt.Key.Key_Down: "Num2",
    Qt.Key.Key_PageDown: "Num3", Qt.Key.Key_Left: "Num4", Qt.Key.Key_Clear: "Num5",
    Qt.Key.Key_Right: "Num6", Qt.Key.Key_Home: "Num7", Qt.Key.Key_Up: "Num8", Qt.Key.Key_PageUp: "Num9",
    **{getattr(Qt.Key, f"Key_{n}"): f"Num{n}" for n in range(10)},
}
# Gauche ou droite : le code de balayage natif. Windows (bit 0x100 = touche
# étendue) puis X11/Wayland (evdev + 8) ; les deux familles ne se recouvrent pas
# pour ces trois touches.
_DROITES = {
    Qt.Key.Key_Shift: ({0x36, 62}, "LShift", "RShift"),
    Qt.Key.Key_Control: ({0x11D, 105}, "LCtrl", "RCtrl"),
    Qt.Key.Key_Alt: ({0x138, 108}, "LAlt", "RAlt"),
}
_BOUTONS = {
    Qt.MouseButton.LeftButton: "MouseLeft", Qt.MouseButton.RightButton: "MouseRight",
    Qt.MouseButton.MiddleButton: "MouseMiddle", Qt.MouseButton.XButton1: "Mouse4",
    Qt.MouseButton.XButton2: "Mouse5",
}


def nom_de_touche(touche: int, texte: str, scan: int, pave: bool) -> str | None:
    """Le nom qu'écrit l'éditeur pour un appui, ou None si le correctif ne saurait pas le lire.

    Une lettre est nommée telle qu'IMPRIMÉE (le texte de l'appui suit la
    disposition active) : c'est ainsi que le correctif la retrouve.
    """
    if pave and touche in _PAVE:
        return _PAVE[touche]
    if touche in _NOMMEES:
        return _NOMMEES[touche]
    if touche in _DROITES:
        droites, gauche, droite = _DROITES[touche]
        return droite if scan in droites else gauche
    return texte.upper() if len(texte) == 1 and tc.nom_valide(texte) else None


class CaptureTouche(QPushButton):
    """Montre une touche ; cliqué, attend l'appui suivant et le rend par `choisie`."""

    choisie = pyqtSignal(str)
    refusee = pyqtSignal()
    annulee = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ecoute = False
        self.setFont(body_font(12))
        self.setFixedWidth(_LARGEUR_TOUCHE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Dans une QDialog, un bouton « par défaut » part sur Entrée d'où qu'elle
        # vienne : une capture lancée sans qu'on ait visé ce bouton.
        self.setAutoDefault(False)
        self.clicked.connect(self._ecouter)

    def ecoute(self) -> bool:
        return self._ecoute

    def _ecouter(self) -> None:
        if self._ecoute:
            return
        self._ecoute = True
        self.setText(tr("Appuyez sur une touche…"))
        # Tout va à ce bouton tant qu'il écoute : un clic ailleurs est un bouton
        # de souris qu'on choisit, Tab une touche et non un changement de focus.
        self.grabKeyboard()
        self.grabMouse()

    def arreter(self) -> None:
        if not self._ecoute:
            return
        self._ecoute = False
        self.releaseKeyboard()
        self.releaseMouse()

    def event(self, e) -> bool:
        if self._ecoute and e.type() == QEvent.Type.KeyPress:
            if not e.isAutoRepeat():
                self._appui(e)
            return True
        if self._ecoute and e.type() in (QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride):
            e.accept()
            return True
        return super().event(e)

    def _appui(self, e) -> None:
        self.arreter()
        if e.key() == Qt.Key.Key_Escape:
            self.annulee.emit()
            return
        nom = nom_de_touche(e.key(), e.text(), e.nativeScanCode(),
                            bool(e.modifiers() & Qt.KeyboardModifier.KeypadModifier))
        if nom is None:
            self.refusee.emit()
        else:
            self.choisie.emit(nom)

    def mousePressEvent(self, e) -> None:
        if not self._ecoute:
            super().mousePressEvent(e)
            return
        # Pas d'appel au parent : le relâchement ne fera pas un second clic.
        # Un bouton de souris ne compte que cliqué SUR la case : qui change
        # d'avis et clique ailleurs annule, au lieu de donner « Clic gauche » à
        # l'action sans l'avoir voulu.
        self.arreter()
        nom = _BOUTONS.get(e.button()) if self.rect().contains(e.position().toPoint()) else None
        if nom is None:
            self.annulee.emit()
        else:
            self.choisie.emit(nom)

    def focusOutEvent(self, e) -> None:
        if self._ecoute:
            self.arreter()
            self.annulee.emit()
        super().focusOutEvent(e)


_STYLE_TOUCHE = (
    "QPushButton { background: #16213e; color: %s; border: 1px solid #2c3e6b;"
    " border-radius: 6px; padding: 5px 10px; font-size: 13px; }"
    "QPushButton:hover { border: 1px solid #d6a72c; }"
)
_STYLE_LIEN = (
    "QPushButton { color: #d6a72c; background: transparent; border: none; padding: 4px 0px; }"
    "QPushButton:hover { color: #e8c547; text-decoration: underline; }"
    "QPushButton:disabled { color: #55556a; }"
)


class EditeurTouches(QWidget):
    """Une ligne par action de HP4. `modifie` après chaque écriture, `echec` si
    le fichier refuse (la fenêtre de réglages le dit, comme pour un réglage)."""

    modifie = pyqtSignal()
    echec = pyqtSignal()

    def __init__(self, ini: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ini = ini
        self._message = ""
        self._boutons: dict[str, CaptureTouche] = {}
        self._rendre: dict[str, QPushButton] = {}
        self.setStyleSheet("background: transparent;")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        for action in tc.ACTIONS:
            v.addWidget(self._ligne(action))
        self._avis = QLabel("")
        self._avis.setFont(body_font(10))
        self._avis.setWordWrap(True)
        self._avis.setTextFormat(Qt.TextFormat.PlainText)
        self._avis.setStyleSheet("color: #e8955a; background: transparent; padding-top: 4px;")
        self._avis.hide()
        v.addWidget(self._avis)
        self._tout = QPushButton(tr("Remettre toutes les touches du jeu"))
        self._tout.setFont(body_font(12))
        self._tout.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tout.setStyleSheet(themed(_STYLE_LIEN))
        self._tout.setAutoDefault(False)
        self._tout.clicked.connect(lambda: self._rendre_touches(None))
        ligne = QHBoxLayout()
        ligne.addWidget(self._tout)
        ligne.addStretch()
        v.addLayout(ligne)
        self.rafraichir()

    def _ligne(self, action: tc.Action) -> QWidget:
        ligne = QWidget()
        ligne.setStyleSheet("background: transparent;")
        h = QHBoxLayout(ligne)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        nom = QLabel(tc.libelle(action))
        nom.setTextFormat(Qt.TextFormat.PlainText)
        nom.setStyleSheet("color: #ffffff; font-size: 13px; background: transparent;")
        h.addWidget(nom, stretch=1)
        rendre = QPushButton(tr("D'origine"))
        rendre.setFont(body_font(10))
        rendre.setCursor(Qt.CursorShape.PointingHandCursor)
        rendre.setStyleSheet(themed(_STYLE_LIEN))
        rendre.setAutoDefault(False)
        rendre.setToolTip(tr("Rend à cette action la touche du jeu : {}.").format(tc.touche_d_origine(action)))
        rendre.clicked.connect(lambda _c=False, a=action.cle: self._rendre_touches((a,)))
        h.addWidget(rendre)
        bouton = CaptureTouche()
        bouton.choisie.connect(lambda nom_, a=action.cle: self._choisie(a, nom_))
        bouton.refusee.connect(self._refusee)
        bouton.annulee.connect(self.rafraichir)
        h.addWidget(bouton)
        self._boutons[action.cle] = bouton
        self._rendre[action.cle] = rendre
        return ligne

    def rafraichir(self) -> None:
        """Remet chaque ligne sur ce que porte le fichier."""
        try:
            choisies = tc.touches(self._ini)
        except OSError:
            log.warning("Touches : %s illisible", self._ini, exc_info=True)
            return
        perdues = tc.sans_touche(choisies)
        for action in tc.ACTIONS:
            bouton = self._boutons[action.cle]
            noms = choisies[action.cle]
            if noms:
                texte, couleur = ", ".join(tc.texte_touche(n) for n in noms), "#ffffff"
            elif action.cle in perdues:
                texte, couleur = tr("Aucune"), "#e8955a"
            else:
                texte, couleur = tc.touche_d_origine(action), "#8a8aaa"
            bouton.setText(bouton.fontMetrics().elidedText(
                texte, Qt.TextElideMode.ElideRight, _LARGEUR_TOUCHE - 24))
            if noms:
                bouton.setToolTip(texte)   # le texte du bouton a pu être élidé
            else:
                bouton.setToolTip("" if action.cle in perdues else tr("Touche d'origine du jeu"))
            bouton.setAccessibleName(f"{tc.libelle(action)} : {texte}")
            bouton.setStyleSheet(themed(_STYLE_TOUCHE % couleur))
            self._rendre[action.cle].setVisible(bool(noms))
        lignes = [self._message] if self._message else []
        for cle, prenant in perdues.items():
            action = tc.PAR_CLE[cle]
            lignes.append(tr("{} n'a plus de touche : {} sert maintenant à {}.").format(
                tc.libelle(action), tc.touche_d_origine(action), tc.libelle(tc.PAR_CLE[prenant])))
        self._avis.setText("\n".join(lignes))
        self._avis.setVisible(bool(lignes))
        self._tout.setEnabled(any(choisies.values()))

    # ── Réaction ──

    def _choisie(self, action: str, nom: str) -> None:
        try:
            perdues = tc.attribuer(self._ini, action, nom)
        except (OSError, ValueError):
            log.warning("Touches : %s non écrite pour %s", nom, action, exc_info=True)
            self._message = ""
            self.rafraichir()
            self.echec.emit()
            return
        self._message = "\n".join(
            tr("{} retirée de « {} ».").format(tc.texte_touche(nom), tc.libelle(tc.PAR_CLE[a]))
            for a in perdues)
        self.rafraichir()
        self.modifie.emit()

    def _refusee(self) -> None:
        self._message = tr("Cette touche ne peut pas être donnée au jeu : choisissez-en une autre.")
        self.rafraichir()

    def _rendre_touches(self, actions) -> None:
        try:
            tc.rendre(self._ini, actions)
        except OSError:
            log.warning("Touches : remise d'origine impossible", exc_info=True)
            self.echec.emit()
            return
        self._message = ""
        self.rafraichir()
        self.modifie.emit()

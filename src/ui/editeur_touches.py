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

from PyQt6.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from src.core import touches_correctif as tc
from src.core.i18n import tr
from src.ui.composants import Rangee, petit_titre
from src.ui.fonts import body_font
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, themed

log = logging.getLogger(__name__)

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
    """Une touche du clavier dessinée ; cliquée, attend l'appui suivant et le rend par `choisie`.

    `largeur` fixe la touche (la croix des déplacements) ; sinon elle suit son
    texte, coupé au-delà de `_LARGEUR_MAX`.
    """

    choisie = pyqtSignal(str)
    refusee = pyqtSignal()
    annulee = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, largeur: int = 0) -> None:
        super().__init__(parent)
        self._ecoute = False
        self._largeur = largeur
        self.setFont(body_font(11))
        self.setFixedHeight(36)
        if largeur:
            self.setFixedWidth(largeur)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Dans une QDialog, un bouton « par défaut » part sur Entrée d'où qu'elle
        # vienne : une capture lancée sans qu'on ait visé ce bouton.
        self.setAutoDefault(False)
        self.clicked.connect(self._ecouter)

    def ecoute(self) -> bool:
        return self._ecoute

    def montrer(self, texte: str, icone: str | None, couleur: str) -> None:
        """La touche telle que le fichier la porte : une flèche se DESSINE."""
        self.setProperty("ecoute", False)
        self.setStyleSheet(themed(_STYLE_TOUCHE % couleur))
        if icone is not None:
            self.setIcon(QIcon(pixmap_icone(icone, 18, QColor(couleur))))
            self.setIconSize(QSize(18, 18))
            self._poser_texte("")
        else:
            self.setIcon(QIcon())
            self._poser_texte(texte)

    def _poser_texte(self, texte: str) -> None:
        largeur = self._largeur or _LARGEUR_MAX
        coupe = self.fontMetrics().elidedText(texte, Qt.TextElideMode.ElideRight, largeur - 24)
        self.setText(coupe)
        if not self._largeur:
            self.setFixedWidth(max(_LARGEUR_MIN, min(_LARGEUR_MAX,
                                                     self.fontMetrics().horizontalAdvance(coupe) + 26)))

    def _ecouter(self) -> None:
        if self._ecoute:
            return
        self._ecoute = True
        self.setIcon(QIcon())
        self.setProperty("ecoute", True)
        self.style().unpolish(self)
        self.style().polish(self)
        # Dans la croix, la touche garde sa largeur : la phrase courte y tient.
        self.setText(tr("Appuyez sur une touche…") if not self._largeur else tr("Appuyez…"))
        if not self._largeur:
            self.setFixedWidth(min(_LARGEUR_MAX + 30, self.fontMetrics().horizontalAdvance(self.text()) + 26))
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


_LARGEUR_MIN, _LARGEUR_MAX = 46, 170
_STYLE_TOUCHE = (
    "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
    " stop:0 #1b1b33, stop:1 #141428); color: %s;"
    " border: 1px solid rgba(255,255,255,0.17); border-bottom: 3px solid rgba(255,255,255,0.17);"
    " border-radius: 7px; padding: 0px 10px; }"
    "QPushButton:hover { border-color: #d6a72c; }"
    "QPushButton[ecoute=\"true\"] { color: #f2e6c4; background: rgba(214,167,44,0.12);"
    " border-color: #d6a72c; font-style: italic; }"
    "QPushButton[focusClavier=\"true\"]:focus { border-color: #d6a72c; }"
)
_STYLE_LIEN = (
    "QPushButton { color: #d6a72c; background: transparent; border: none; padding: 4px 0px; }"
    "QPushButton:hover { color: #e8c547; text-decoration: underline; }"
    "QPushButton:disabled { color: #55556a; }"
)
_STYLE_RENDRE = (
    "QPushButton { background: transparent; border: none; padding: 0px; }"
    "QPushButton[focusClavier=\"true\"]:focus { border: 1px solid #d6a72c; border-radius: 4px; }"
)

# Les trois cartes de la maquette (2026-10-09) : on cherche une touche par ce
# qu'elle fait, pas dans une liste de onze lignes.
_DEPLACER = ("MoveUp", "MoveLeft", "MoveDown", "MoveRight")
_SORTS = ("Charm", "Jinx", "Accio", "Extremos")
_MENUS = ("Pause", "Confirm", "Back")
_LARGEUR_CROIX = 92
# Clé tr() du nom de la touche → son pictogramme : une flèche se reconnaît
# d'un coup d'œil, « Flèche gauche » se lit.
_FLECHES = {"Flèche haut": "fleche_haut", "Flèche bas": "fleche_bas",
            "Flèche gauche": "retour", "Flèche droite": "fleche_droite"}


class EditeurTouches(QWidget):
    """Les actions de HP4 en trois cartes. `modifie` après chaque écriture,
    `echec` si le fichier refuse (la fenêtre de réglages le dit, comme pour un
    réglage). `tout` (« Remettre les touches du jeu ») est posé par la
    fenêtre, au bout du titre de la rubrique."""

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
        v.setSpacing(12)
        cartes = [self._carte_deplacer(),
                  self._carte_liste(tr("Lancer un sort"), _SORTS),
                  self._carte_liste(tr("Menus"), _MENUS)]
        v.addWidget(Rangee(cartes, colonnes=3, seuil=_SEUIL_TROIS))
        self._avis = QLabel("")
        self._avis.setFont(body_font(10))
        self._avis.setWordWrap(True)
        self._avis.setTextFormat(Qt.TextFormat.PlainText)
        self._avis.setStyleSheet("color: #e8955a; background: transparent;")
        self._avis.hide()
        v.addWidget(self._avis)
        self._tout = QPushButton(tr("Remettre les touches du jeu"))
        self._tout.setFont(body_font(11))
        self._tout.setIcon(QIcon(pixmap_icone("replay", 18, accent_qcolor())))
        self._tout.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tout.setStyleSheet(themed(_STYLE_LIEN))
        self._tout.setAutoDefault(False)
        self._tout.clicked.connect(lambda: self._rendre_touches(None))
        self.rafraichir()

    @property
    def tout(self) -> QPushButton:
        return self._tout

    @staticmethod
    def _carte(titre: str) -> tuple[QFrame, QVBoxLayout]:
        carte = QFrame()
        carte.setObjectName("carte")
        v = QVBoxLayout(carte)
        v.setContentsMargins(18, 16, 18, 10)
        v.setSpacing(4)
        v.addWidget(petit_titre(titre))
        return carte, v

    def _capture(self, action: tc.Action, largeur: int = 0) -> CaptureTouche:
        bouton = CaptureTouche(largeur=largeur)
        bouton.choisie.connect(lambda nom_, a=action.cle: self._choisie(a, nom_))
        bouton.refusee.connect(self._refusee)
        bouton.annulee.connect(self.rafraichir)
        self._boutons[action.cle] = bouton
        return bouton

    def _carte_deplacer(self) -> QFrame:
        """Les quatre déplacements en croix, comme sur le clavier, chacun nommé."""
        carte, v = self._carte(tr("Se déplacer"))
        grille = QGridLayout()
        grille.setHorizontalSpacing(6)
        grille.setVerticalSpacing(4)
        # (ligne et colonne de la touche, ligne et colonne de son nom)
        places = {"MoveUp": (1, 1, 0, 1), "MoveLeft": (2, 0, 3, 0),
                  "MoveDown": (2, 1, 3, 1), "MoveRight": (2, 2, 3, 2)}
        for cle in _DEPLACER:
            action = tc.PAR_CLE[cle]
            ligne, col, ligne_nom, col_nom = places[cle]
            grille.addWidget(self._capture(action, _LARGEUR_CROIX), ligne, col)
            nom = QLabel(tc.libelle(action))
            nom.setTextFormat(Qt.TextFormat.PlainText)
            nom.setWordWrap(True)
            nom.setFixedWidth(_LARGEUR_CROIX)
            f = body_font(10)
            f.setItalic(True)
            nom.setFont(f)
            nom.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            nom.setStyleSheet("color: #8f8db0; background: transparent; border: none;")
            grille.addWidget(nom, ligne_nom, col_nom)
        v.addSpacing(6)
        h = QHBoxLayout()
        h.addStretch()
        h.addLayout(grille)
        h.addStretch()
        v.addLayout(h)
        v.addStretch()
        return carte

    def _carte_liste(self, titre: str, cles: tuple[str, ...]) -> QFrame:
        carte, v = self._carte(titre)
        for rang, cle in enumerate(cles):
            action = tc.PAR_CLE[cle]
            if rang:
                filet = QFrame()
                filet.setObjectName("separateur")
                filet.setFixedHeight(1)
                v.addWidget(filet)
            ligne = QWidget()
            ligne.setMinimumHeight(46)
            ligne.setStyleSheet("background: transparent;")
            h = QHBoxLayout(ligne)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            nom = QLabel(tc.libelle(action))
            nom.setTextFormat(Qt.TextFormat.PlainText)
            nom.setFont(body_font(12))
            nom.setMinimumWidth(1)
            nom.setStyleSheet("color: #ecebf3; background: transparent;")
            h.addWidget(nom, stretch=1)
            # Rendre UNE touche : visible seulement quand elle a été changée.
            rendre = QPushButton()
            rendre.setIcon(QIcon(pixmap_icone("replay", 18, accent_qcolor())))
            rendre.setIconSize(QSize(18, 18))
            rendre.setFixedSize(26, 26)
            rendre.setCursor(Qt.CursorShape.PointingHandCursor)
            rendre.setStyleSheet(themed(_STYLE_RENDRE))
            rendre.setAutoDefault(False)
            rendre.setToolTip(tr("Rend à cette action la touche du jeu : {}.").format(
                tc.touche_d_origine(action)))
            rendre.setAccessibleName(tr("D'origine"))
            rendre.clicked.connect(lambda _c=False, a=action.cle: self._rendre_touches((a,)))
            h.addWidget(rendre)
            self._rendre[action.cle] = rendre
            h.addWidget(self._capture(action))
            v.addWidget(ligne)
        v.addStretch()
        return carte

    def rafraichir(self) -> None:
        """Remet chaque touche sur ce que porte le fichier."""
        try:
            choisies = tc.touches(self._ini)
        except OSError:
            log.warning("Touches : %s illisible", self._ini, exc_info=True)
            return
        perdues = tc.sans_touche(choisies)
        fleches = {tr(nom): icone for nom, icone in _FLECHES.items()}
        for action in tc.ACTIONS:
            bouton = self._boutons[action.cle]
            noms = choisies[action.cle]
            if noms:
                texte, couleur = ", ".join(tc.texte_touche(n) for n in noms), "#ecebf3"
            elif action.cle in perdues:
                texte, couleur = tr("Aucune"), "#e8955a"
            else:
                texte, couleur = tc.touche_d_origine(action), "#a9a7c4"
            bouton.montrer(texte, fleches.get(texte), couleur)
            if noms:
                bouton.setToolTip(texte)   # le texte de la touche a pu être coupé
            else:
                bouton.setToolTip("" if action.cle in perdues else tr("Touche d'origine du jeu"))
            bouton.setAccessibleName(f"{tc.libelle(action)} : {texte}")
            rendre = self._rendre.get(action.cle)
            if rendre is not None:
                rendre.setVisible(bool(noms))
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


# Trois cartes côte à côte en dessous de cette largeur ne tiennent plus : la
# croix fait 3 × 92 px plus ses marges, une ligne de sort son nom et sa touche.
_SEUIL_TROIS = 900

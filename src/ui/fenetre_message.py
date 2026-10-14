"""La fenêtre de message du launcher : ce qui s'est passé, ce qui est conservé, le bouton qui répare.

Refonte du 2026-10-09. Les erreurs, les questions et les constats passaient par
`QMessageBox` : une boîte Windows grise, son icône système, ses boutons gris,
au milieu d'une application dorée sur bleu nuit. Elles parlent maintenant
comme les Paramètres et l'assistant (`composants.py`) :

- le TITRE dit ce qui s'est passé, en clair ;
- le texte explique, puis une ligne verte dit ce qui est CONSERVÉ (règle 112 :
  un échec qui ne dit pas ce qui reste fait craindre le pire) ;
- les boutons sont NOMMÉS (règle 116), le plus engageant à droite, en or.

**Même interface que `QMessageBox`** pour ce qui sert ici (`setText`,
`setInformativeText`, `addButton`, `clickedButton`…), et ses énumérations
`Icon` et `ButtonRole` : les appelants n'ont changé que de classe, et le texte
reste BRUT quoi qu'on demande (un nom de jeu vient du catalogue distant).
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from src.core.i18n import tr
from src.ui.composants import ENCRE_DOUCE, feuille_de_style, police, texte
from src.ui.fonts import cinzel
from src.ui.icon_button import pixmap_icone
from src.ui.theme import accent_qcolor, themed

_STYLE = """
QDialog#fenetreMessage { background: #0d0d1a; }
QPushButton#danger {
    min-height: 34px; max-height: 34px; padding: 0 16px; border-radius: 7px;
    color: #f6d2cd; background: rgba(224, 88, 79, 0.10);
    border: 1px solid rgba(224, 88, 79, 0.60);
}
QPushButton#danger:hover { background: rgba(224, 88, 79, 0.20); border-color: #e0584f; }
QPushButton#danger[focusClavier="true"]:focus { border: 2px solid #f39a8f; padding: 0 15px; }
"""
_VERT = "#5fbf86"
# Pictogramme et couleur de chaque nature de message. Une question n'a pas
# d'icône : c'est son titre qui la pose.
_ICONES = {
    QMessageBox.Icon.Warning: ("attention", "#e0a05a"),
    QMessageBox.Icon.Critical: ("attention", "#e0584f"),
    QMessageBox.Icon.Information: ("infos", ""),
}
_ROLES_PRINCIPAUX = (QMessageBox.ButtonRole.AcceptRole, QMessageBox.ButtonRole.YesRole,
                     QMessageBox.ButtonRole.ApplyRole)


class FenetreMessage(QDialog):
    """Un message à lire, avec un ou plusieurs boutons nommés."""

    Icon = QMessageBox.Icon
    ButtonRole = QMessageBox.ButtonRole

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("fenetreMessage")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(640)
        self.setStyleSheet(themed(_STYLE) + feuille_de_style())
        self._icone = QMessageBox.Icon.NoIcon
        self._texte = ""
        self._detail = ""
        self._conserve = ""
        self._boutons: list[tuple[QPushButton, QMessageBox.ButtonRole]] = []
        self._defaut: QPushButton | None = None
        self._echap: QPushButton | None = None
        self._clique: QPushButton | None = None
        self._construite = False

    # ── L'interface de QMessageBox ──

    def setIcon(self, icone) -> None:  # noqa: N802 (Qt)
        self._icone = icone

    def setTextFormat(self, _format) -> None:  # noqa: N802 (Qt)
        """Ignoré : le texte est TOUJOURS brut (il cite des noms venus du catalogue)."""

    def setText(self, contenu: str) -> None:  # noqa: N802 (Qt)
        self._texte = contenu

    def text(self) -> str:
        return self._texte

    def setInformativeText(self, contenu: str) -> None:  # noqa: N802 (Qt)
        self._detail = contenu

    def informativeText(self) -> str:  # noqa: N802 (Qt)
        return self._detail

    def setConserve(self, contenu: str) -> None:  # noqa: N802 (même style)
        """La ligne verte : ce que l'échec n'a PAS emporté."""
        self._conserve = contenu

    def conserve(self) -> str:
        return self._conserve

    def addButton(self, libelle: str, role) -> QPushButton:  # noqa: N802 (Qt)
        btn = QPushButton(libelle)
        btn.setFont(police(13, gras=True))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.clicked.connect(lambda _c=False, b=btn: self._cliquer(b))
        self._boutons.append((btn, role))
        return btn

    def buttons(self) -> list[QPushButton]:
        return [b for b, _ in self._boutons]

    def setDefaultButton(self, bouton: QPushButton) -> None:  # noqa: N802 (Qt)
        self._defaut = bouton

    def setEscapeButton(self, bouton: QPushButton) -> None:  # noqa: N802 (Qt)
        self._echap = bouton

    def clickedButton(self) -> QPushButton | None:  # noqa: N802 (Qt)
        return self._clique

    # ── Comportement ──

    def _cliquer(self, bouton: QPushButton) -> None:
        self._clique = bouton
        self.accept()

    def _bouton_d_echap(self) -> QPushButton | None:
        """Échap répond « non » : le bouton désigné, sinon le dernier qui se retire."""
        if self._echap is not None:
            return self._echap
        retraits = [b for b, r in self._boutons if r == QMessageBox.ButtonRole.RejectRole]
        return retraits[-1] if retraits else None

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.key() == Qt.Key.Key_Escape:
            bouton = self._bouton_d_echap()
            if bouton is not None:
                bouton.click()
                return
        super().keyPressEvent(event)

    def setVisible(self, visible: bool) -> None:  # noqa: N802 (Qt)
        if visible and not self._construite:
            self._construire()
        super().setVisible(visible)

    # ── Construction, au premier affichage ──

    def _construire(self) -> None:
        self._construite = True
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(0)

        tete = QHBoxLayout()
        tete.setSpacing(14)
        nom, couleur = _ICONES.get(self._icone, ("", ""))
        if nom:
            icone = QLabel()
            icone.setStyleSheet("background: transparent;")
            icone.setPixmap(pixmap_icone(nom, 26, QColor(couleur) if couleur else accent_qcolor()))
            tete.addWidget(icone, alignment=Qt.AlignmentFlag.AlignTop)
        titre = texte(self.windowTitle(), 17, "#f4f2f8", retour=True)
        titre.setFont(police(17, gras=True))
        tete.addWidget(titre, stretch=1)
        lay.addLayout(tete)

        for contenu, px, encre, ecart in ((self._texte, 14, "#d9d6e8", 14),
                                          (self._detail, 13, ENCRE_DOUCE, 10)):
            if contenu:
                lay.addSpacing(ecart)
                lbl = texte(contenu, px, encre, retour=True)
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                lay.addWidget(lbl)
        if self._conserve:
            lay.addSpacing(16)
            lay.addWidget(cadre_conserve(self._conserve))

        lay.addSpacing(22)
        rangee = QHBoxLayout()
        rangee.setSpacing(10)
        rangee.addStretch()
        # Du plus neutre au plus engageant : celui qui agit finit à droite.
        for bouton, role in reversed(self._boutons):
            if role == QMessageBox.ButtonRole.DestructiveRole:
                bouton.setObjectName("danger")
            elif role in _ROLES_PRINCIPAUX and bouton is self._boutons[0][0]:
                bouton.setObjectName("principal")
            else:
                bouton.setObjectName("secondaire")
            rangee.addWidget(bouton)
        lay.addLayout(rangee)
        cible = self._defaut or (self._boutons[0][0] if self._boutons else None)
        if cible is not None:
            cible.setDefault(True)
            cible.setFocus()


def cadre_conserve(contenu: str) -> QFrame:
    """La ligne verte « Ce qui est conservé », posable dans n'importe quelle fenêtre."""
    cadre = QFrame()
    cadre.setObjectName("conserve")
    cadre.setStyleSheet(
        "QFrame#conserve { background: rgba(95, 191, 134, 0.07);"
        " border: 1px solid rgba(95, 191, 134, 0.28); border-radius: 8px; }")
    h = QHBoxLayout(cadre)
    h.setContentsMargins(14, 11, 14, 12)
    h.setSpacing(12)
    coche = QLabel()
    coche.setStyleSheet("background: transparent; border: none;")
    coche.setPixmap(pixmap_icone("coche", 18, QColor(_VERT)))
    h.addWidget(coche, alignment=Qt.AlignmentFlag.AlignTop)
    colonne = QVBoxLayout()
    colonne.setSpacing(3)
    etiquette = QLabel(tr("Ce qui est conservé").upper())
    etiquette.setFont(cinzel(7, bold=True))
    etiquette.setStyleSheet(f"color: {_VERT}; background: transparent; border: none;")
    colonne.addWidget(etiquette)
    corps = texte(contenu, 13, "#b9d8c4", retour=True)
    corps.setStyleSheet(corps.styleSheet() + " border: none;")
    colonne.addWidget(corps)
    h.addLayout(colonne, stretch=1)
    return cadre


def message(parent, icone, titre: str, contenu: str, choix=(), defaut: int = 0,
            conserve: str = "") -> int:
    """Pose la fenêtre et rend l'INDEX du bouton cliqué, -1 si fermée autrement.

    `choix` va du plus engageant au plus neutre ; le dernier est le retrait,
    celui qu'Échap déclenche. Sans `choix`, un seul bouton « Fermer ».
    """
    boite = FenetreMessage(parent)
    boite.setIcon(icone)
    boite.setWindowTitle(titre)
    boite.setText(contenu)
    boite.setConserve(conserve)
    libelles = tuple(choix) or (tr("Fermer"),)
    boutons = [boite.addButton(libelle, QMessageBox.ButtonRole.AcceptRole if i == 0 and choix
                               else QMessageBox.ButtonRole.RejectRole)
               for i, libelle in enumerate(libelles)]
    boite.setDefaultButton(boutons[min(max(defaut, 0), len(boutons) - 1)])
    boite.exec()
    clique = boite.clickedButton()
    if not choix:
        return -1
    return next((i for i, b in enumerate(boutons) if b is clique), -1)

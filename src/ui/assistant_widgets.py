"""Les pièces de l'assistant de premier lancement (maquette validée le 2026-10-09).

Le rail des étapes, les cartes qui se choisissent (langue, réponse du
Choixpeau, couleurs), la barre du disque et la ligne d'un jeu retrouvé.
`onboarding.py` garde le parcours ; ce module, ce qu'on en voit.

Tout ce qui est doré se peint ou se colore AU MOMENT de l'affichage : au
verdict du Choixpeau, l'assistant prend les couleurs de la maison sans être
reconstruit (`OnboardingDialog._appliquer_theme`).
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from src.ui.composants import ENCRE, ENCRE_DISCRETE, ENCRE_DOUCE, Chemin, police
from src.ui.fonts import cinzel, cinzel_decorative
from src.ui.icon_button import pixmap_icone
from src.ui.reglages_widgets import _Jaquette
from src.ui.theme import THEMES, accent_qcolor

# Écrit dans la palette Poudlard : `themed()` le recolore à chaque changement.
STYLE = """
QDialog#assistant { background: #060611; }
QFrame#railAssistant {
    background: #0d0d1a; border: none;
    border-right: 1px solid rgba(214, 167, 44, 0.12);
}
QFrame#piedAssistant {
    background: transparent; border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}
QLabel#marque, QLabel#surtitreEtape { color: #d6a72c; background: transparent; }
QLabel#titreEtape { color: #f4f2f8; background: transparent; }
QPushButton#suivant {
    min-height: 40px; max-height: 40px; padding: 0 22px; border-radius: 7px;
    color: #f6ecd0; background: rgba(214, 167, 44, 0.16); border: 1px solid #d6a72c;
}
QPushButton#suivant:hover { background: rgba(214, 167, 44, 0.26); }
QPushButton#suivant:disabled {
    color: #6f6d8e; background: transparent; border-color: rgba(255, 255, 255, 0.10);
}
QPushButton#suivant[focusClavier="true"]:focus { border: 2px solid #f0d060; padding: 0 21px; }
QPushButton#lien {
    background: transparent; border: none; color: #a9a7c4;
    text-decoration: underline; padding: 6px 4px;
}
QPushButton#lien:hover { color: #f2f2f4; }
QPushButton#lien[focusClavier="true"]:focus { color: #e8c547; }
QPushButton#carteChoix {
    background: #0d0d1a; border: 2px solid rgba(255, 255, 255, 0.09);
    border-radius: 12px; text-align: left;
}
QPushButton#carteChoix:hover { border-color: rgba(214, 167, 44, 0.55); }
QPushButton#carteChoix:checked { border-color: #d6a72c; background: rgba(214, 167, 44, 0.10); }
QPushButton#carteChoix[focusClavier="true"]:focus { border-color: #f0d060; }
QPushButton#ligneJeu { background: transparent; border: none; text-align: left; }
QPushButton#ligneJeu:hover { background: rgba(255, 255, 255, 0.03); }
QPushButton#ligneJeu[focusClavier="true"]:focus { background: rgba(214, 167, 44, 0.10); }
"""

_JAQUETTE_LIGNE = QSize(30, 42)
_ENCRE_RAIL = "#a9a7c4"
_ENCRE_ICI = "#f2e6c4"


def titre_etape(contenu: str) -> QLabel:
    """Le titre d'un écran : Cinzel Decorative, comme le nom du launcher."""
    lbl = QLabel(contenu)
    lbl.setObjectName("titreEtape")
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    lbl.setWordWrap(True)
    lbl.setFont(cinzel_decorative(20, QFont.Weight.Bold))
    return lbl


def surtitre_etape(contenu: str) -> QLabel:
    """« ÉTAPE 2 SUR 5 » : doré, coloré par la feuille de la fenêtre."""
    lbl = QLabel(contenu.upper())
    lbl.setObjectName("surtitreEtape")
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    f = cinzel(8, bold=True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
    lbl.setFont(f)
    return lbl


def bouton_suivant(libelle: str) -> QPushButton:
    btn = QPushButton(libelle)
    btn.setObjectName("suivant")
    btn.setFont(police(14, gras=True))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAutoDefault(False)
    return btn


def lien(libelle: str) -> QPushButton:
    """Un choix discret du pied (« Je n'en ai pas, passer ») : souligné, sans cadre."""
    btn = QPushButton(libelle)
    btn.setObjectName("lien")
    btn.setFont(police(13))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAutoDefault(False)
    return btn


class _Pion(QWidget):
    """Le rond numéroté d'une étape : à venir, en cours ou faite (coche)."""

    A_VENIR, ICI, FAITE = range(3)

    def __init__(self, numero: int) -> None:
        super().__init__()
        self._numero = numero
        self.etat = self.A_VENIR
        self.setFixedSize(26, 26)

    def regler(self, etat: int) -> None:
        self.etat = etat
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1.5, 1.5, 23, 23)
        if self.etat == self.FAITE:
            p.setPen(QPen(accent_qcolor(130), 1.5))
            p.setBrush(accent_qcolor(36))
            p.drawEllipse(r)
            coche = pixmap_icone("coche", 18, accent_qcolor())
            p.drawPixmap(4, 4, coche)
        else:
            ici = self.etat == self.ICI
            p.setPen(QPen(accent_qcolor() if ici else QColor(255, 255, 255, 46), 2 if ici else 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r)
            p.setFont(cinzel(8, bold=True))
            p.setPen(accent_qcolor() if ici else QColor(ENCRE_DISCRETE))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._numero))
        p.end()


class _EtapeRail(QWidget):
    def __init__(self, numero: int, libelle: str) -> None:
        super().__init__()
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.pion = _Pion(numero)
        lay.addWidget(self.pion)
        self.libelle = QLabel(libelle)
        self.libelle.setTextFormat(Qt.TextFormat.PlainText)
        self.libelle.setFont(police(14))
        lay.addWidget(self.libelle, stretch=1)
        self.regler(_Pion.A_VENIR)

    def regler(self, etat: int) -> None:
        self.pion.regler(etat)
        encre = {_Pion.A_VENIR: ENCRE_DISCRETE, _Pion.ICI: _ENCRE_ICI}.get(etat, _ENCRE_RAIL)
        self.libelle.setStyleSheet(f"color: {encre}; background: transparent;")


class RailEtapes(QWidget):
    """La liste des étapes : on voit d'un coup ce qui vient et combien il en reste."""

    def __init__(self, libelles: list[str], premiere_faite: str = "") -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._faite = None
        if premiere_faite:
            # La langue : déjà choisie quand le rail apparaît, toujours cochée.
            self._faite = _EtapeRail(1, premiere_faite)
            self._faite.regler(_Pion.FAITE)
            lay.addWidget(self._faite)
        decalage = 2 if premiere_faite else 1
        self.etapes = [_EtapeRail(i + decalage, nom) for i, nom in enumerate(libelles)]
        for etape in self.etapes:
            lay.addWidget(etape)

    def regler(self, courante: int) -> None:
        for i, etape in enumerate(self.etapes):
            etape.regler(_Pion.FAITE if i < courante else _Pion.ICI if i == courante else _Pion.A_VENIR)

    def repeindre(self) -> None:
        for etape in ([self._faite] if self._faite else []) + self.etapes:
            etape.pion.update()


class CarteChoix(QPushButton):
    """Une carte qui se choisit, de la hauteur de ce qu'elle porte (règles 38 et 39)."""

    def __init__(self, nom_accessible: str) -> None:
        super().__init__()
        self.setObjectName("carteChoix")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(nom_accessible)
        politique = self.sizePolicy()
        politique.setHeightForWidth(True)
        politique.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        # Preferred et non Minimum (défaut d'un bouton) : sinon la largeur voulue
        # devient un MINIMUM, et cinq cartes de couleurs débordaient à 860 px.
        politique.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        self.setSizePolicy(politique)

    def _figer_enfants(self) -> None:
        for enfant in self.findChildren(QWidget):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt)
        return True

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802 (Qt)
        return self.layout().totalHeightForWidth(largeur)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(200, self.heightForWidth(max(self.width(), 200)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(150, self.heightForWidth(max(self.width(), 150)))


class CarteLangue(CarteChoix):
    """« FR / Français » : écrite dans sa propre langue, lisible sans la connaître."""

    def __init__(self, code: str, nom: str) -> None:
        super().__init__(nom)
        self.code = code
        self.setFixedSize(196, 132)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(6)
        lay.addStretch()
        self._code = QLabel(code.upper())
        f = cinzel(8, bold=True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        self._code.setFont(f)
        lay.addWidget(self._code)
        nom_lbl = QLabel(nom)
        nom_lbl.setTextFormat(Qt.TextFormat.PlainText)
        nom_lbl.setFont(police(22))
        nom_lbl.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        lay.addWidget(nom_lbl)
        self._figer_enfants()
        self.toggled.connect(self._teinter)
        self._teinter(False)

    def _teinter(self, coche: bool) -> None:
        encre = accent_qcolor().name() if coche else ENCRE_DOUCE
        self._code.setStyleSheet(f"color: {encre}; background: transparent;")


class _Rond(QWidget):
    """Le rond d'une réponse : plein quand elle est choisie."""

    def __init__(self, carte: QPushButton) -> None:
        super().__init__()
        self._carte = carte
        self.setFixedSize(18, 18)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        coche = self._carte.isChecked()
        p.setPen(QPen(accent_qcolor() if coche else QColor(255, 255, 255, 80), 2 if coche else 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(1, 1, 16, 16))
        if coche:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent_qcolor())
            p.drawEllipse(QRectF(5, 5, 8, 8))
        p.end()


class CarteReponse(CarteChoix):
    """Une réponse du Choixpeau ; son texte change d'une question à l'autre."""

    def __init__(self) -> None:
        super().__init__("")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 15, 16, 15)
        lay.setSpacing(12)
        self._rond = _Rond(self)
        lay.addWidget(self._rond, alignment=Qt.AlignmentFlag.AlignTop)
        self.texte = QLabel()
        self.texte.setTextFormat(Qt.TextFormat.PlainText)
        self.texte.setWordWrap(True)
        self.texte.setFont(police(14))
        self.texte.setStyleSheet("color: #e4e1ef; background: transparent;")
        self.texte.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.texte, stretch=1)
        self._figer_enfants()
        self.setMinimumHeight(74)
        self.toggled.connect(lambda _c: self._rond.update())

    def dire(self, contenu: str) -> None:
        self.texte.setText(contenu)
        self.setAccessibleName(contenu)
        self.updateGeometry()

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802 (Qt)
        return max(74, super().heightForWidth(largeur))


class _BarreCouleur(QWidget):
    def __init__(self, couleur: str) -> None:
        super().__init__()
        self._couleur = QColor(couleur)
        self.setFixedHeight(6)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        tiers = (self.width() - 4) / 3
        p.setBrush(self._couleur)
        p.drawRoundedRect(QRectF(0, 0, 2 * tiers, 6), 3, 3)
        p.setBrush(QColor(255, 255, 255, 46))
        p.drawRoundedRect(QRectF(2 * tiers + 4, 0, tiers, 6), 3, 3)
        p.end()


class CarteCouleur(CarteChoix):
    """Les couleurs d'une maison, posées sur SON fond : on choisit en voyant.

    Ses couleurs sont celles de sa palette, jamais celles du thème actif : elle
    ne passe donc pas par la feuille de la fenêtre (`themed()` les changerait).
    """

    def __init__(self, theme_id: str, nom: str) -> None:
        super().__init__(nom)
        self.setObjectName("carteCouleur")
        self.theme_id = theme_id
        palette = THEMES[theme_id]
        self.setStyleSheet(
            f"QPushButton {{ background: {palette.bg_dialog}; border: 2px solid rgba(255, 255, 255, 0.09);"
            " border-radius: 10px; text-align: left; }}"
            f"QPushButton:hover {{ border-color: {palette.accent}; }}"
            f"QPushButton:checked {{ border-color: {palette.accent_light}; }}"
            f"QPushButton[focusClavier=\"true\"]:focus {{ border-color: {palette.accent_light}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)
        lay.addWidget(_BarreCouleur(palette.accent))
        nom_lbl = QLabel(nom)
        nom_lbl.setTextFormat(Qt.TextFormat.PlainText)
        nom_lbl.setFont(police(14))
        nom_lbl.setStyleSheet(f"color: {ENCRE}; background: transparent; border: none;")
        lay.addWidget(nom_lbl)
        self.note = QLabel()
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setWordWrap(True)
        self.note.setFont(police(12))
        self.note.setStyleSheet(f"color: {palette.accent_light}; background: transparent; border: none;")
        lay.addWidget(self.note)
        lay.addStretch()
        self._figer_enfants()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(110, self.heightForWidth(max(self.width(), 110)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(96, self.heightForWidth(max(self.width(), 96)))

    def annoter(self, note: str) -> None:
        self.note.setText(note)


class BarreDisque(QWidget):
    """Le disque en une barre : ce qui est déjà pris en gris, la saga en or."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(8)
        self._pris = 0.0
        self._saga = 0.0

    def regler(self, pris: int, saga: int, total: int) -> None:
        if total <= 0:
            self._pris = self._saga = 0.0
        else:
            self._pris = max(0.0, min(1.0, pris / total))
            self._saga = max(0.0, min(1.0 - self._pris, saga / total))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        p.setBrush(QColor(255, 255, 255, 18))
        p.drawRoundedRect(rect, 4, 4)
        p.setClipRect(rect)
        largeur = rect.width()
        pris = largeur * self._pris
        p.setBrush(QColor(255, 255, 255, 56))
        p.drawRoundedRect(QRectF(0, 0, pris + 4, rect.height()), 4, 4)
        if self._saga > 0:
            p.setBrush(accent_qcolor())
            p.drawRect(QRectF(pris, 0, max(3.0, largeur * self._saga), rect.height()))
        p.end()


class _Case(QWidget):
    """La case d'un jeu à importer : pleine et cochée, ou vide."""

    def __init__(self, ligne: QPushButton) -> None:
        super().__init__()
        self._ligne = ligne
        self.setFixedSize(24, 24)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, 22, 22)
        if self._ligne.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent_qcolor())
            p.drawRoundedRect(r, 5, 5)
            p.drawPixmap(3, 3, pixmap_icone("coche", 18, QColor("#0b0b18")))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 80), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 5, 5)
        p.end()


class LigneJeu(QPushButton):
    """Un jeu retrouvé : jaquette, nom, dossier, et la case qui dit s'il est repris.

    Avec une `note`, il n'y a rien à cocher : le jeu est déjà dans le dossier du
    launcher (rien à déplacer), ou sur un autre disque (pas déplaçable d'ici).
    La ligne le dit, c'est tout.
    """

    def __init__(self, nom: str, jaquette: str, dossier: str, note: str = "",
                 encre_note: str = "#b9d8c4") -> None:
        super().__init__()
        self.setObjectName("ligneJeu")
        self.setAutoDefault(False)
        self.setCheckable(not note)
        self.setChecked(not note)
        self.setAccessibleName(nom)
        if note:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(16)
        lay.addWidget(_Jaquette(jaquette, _JAQUETTE_LIGNE))
        colonne = QVBoxLayout()
        colonne.setSpacing(1)
        nom_lbl = QLabel(nom)
        nom_lbl.setTextFormat(Qt.TextFormat.PlainText)
        nom_lbl.setFont(police(14))
        nom_lbl.setStyleSheet(f"color: {ENCRE}; background: transparent;")
        colonne.addWidget(nom_lbl)
        colonne.addWidget(Chemin(dossier, 12, ENCRE_DOUCE))
        lay.addLayout(colonne, stretch=1)
        if note:
            etat = QLabel(note)
            etat.setTextFormat(Qt.TextFormat.PlainText)
            etat.setFont(police(12))
            etat.setStyleSheet(f"color: {encre_note}; background: transparent;")
            lay.addWidget(etat)
        else:
            self._case = _Case(self)
            lay.addWidget(self._case)
            self.toggled.connect(lambda _c: self._case.update())
        for enfant in self.findChildren(QWidget):
            enfant.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


class Progression(QWidget):
    """Les points du Choixpeau : faits en or, l'actuel en long, le reste en gris."""

    def __init__(self, total: int) -> None:
        super().__init__()
        self._total = total
        self._courant = 0
        self.setFixedSize(total * 14 + 14, 8)

    def regler(self, courant: int) -> None:
        self._courant = courant
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        x = 0.0
        for i in range(self._total):
            largeur = 22.0 if i == self._courant else 8.0
            p.setBrush(accent_qcolor() if i <= self._courant else QColor(255, 255, 255, 40))
            p.drawRoundedRect(QRectF(x, 0, largeur, 8), 4, 4)
            x += largeur + 6
        p.end()

"""Où en est la partie, sur la fiche d'un jeu dont on sait lire les sauvegardes.

La description cède sa place dès qu'il y a mieux à montrer (Ludo, 2026-10-15) :
qui a déjà joué l'a lue, et veut savoir où il en était. Un jeu dont on ne lit
rien garde sa description (`folio.RESUMES` : HP1 et HP3 aujourd'hui).

Maquette H du canevas « fiche » : la ligne « Dernière partie » sous le titre,
puis le bouton, puis ce bloc (éventail des cartes, compte, barre, maisons et
temps de jeu). Le bloc entier ouvre le folio.
"""

from datetime import date, datetime
from html import escape
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core import folio, folio_hp3
from src.core.formatting import format_duree_compacte, format_relative_date
from src.core.i18n import get_language, tr
from src.ui.fonts import body_font
from src.ui.theme import accent_qcolor, themed

# Au-delà, le bloc s'étirerait sur toute la colonne pour trois lignes courtes.
LARGEUR_MAX = 380
_CARTE_H = 34          # hauteur d'une carte de l'éventail, px logiques
_EVENTAIL = ((0, 4, -10.0), (14, 1, -1.0), (28, 3, 9.0))   # x, y, angle

_STYLE = """
QFrame#blocFolio {
    background: rgba(255, 255, 255, 0.04); border: 1px solid transparent; border-radius: 8px;
}
QFrame#blocFolio:hover { background: rgba(255, 255, 255, 0.07); }
QFrame#blocFolio[focusClavier="true"]:focus { border-color: #d6a72c; }
"""


def phrase_derniere_partie(modifie: datetime, lieu: str, today: date | None = None) -> str:
    """« Dernière partie hier · Parc de Poudlard », en RichText échappé.

    La date est celle que le JEU a écrite (la sauvegarde), pas la dernière
    session du launcher : elle va avec le lieu, et une partie lancée hors du
    launcher compte aussi. Un point plutôt que « au » : le lieu vient du jeu,
    dans sa langue, et « au Bibliothèque » se lirait mal.
    """
    today = today or date.today()
    if (today - modifie.date()).days > 30:
        debut = tr("Dernière partie le {}").format(modifie.strftime("%d/%m/%Y"))
    else:
        debut = tr("Dernière partie {}").format(
            format_relative_date(modifie.isoformat(), today))
    texte = f'<span style="color:#b4b4d0;">{escape(debut, quote=False)}</span>'
    if lieu:
        texte += ('<span style="color:#b4b4d0;">&nbsp;·&nbsp;</span>'
                  + escape(lieu, quote=False))
    return texte


def maison_en_tete(releve: folio.Releve) -> str:
    """« Serpentard mène », « À égalité », ou rien sans points."""
    from src.ui.folio_page import nom_maison
    tete = releve.en_tete()
    if tete is None:
        return tr("À égalité") if releve.lu and any(releve.points.values()) else ""
    return tr("{} mène").format(nom_maison(tete[0]))


def phrase_cartes(trouvees: int, total: int = folio.CARTES_HP1) -> str:
    cle = "{} carte sur {}" if trouvees == 1 else "{} cartes sur {}"
    return tr(cle).format(trouvees, total)


class _Eventail(QWidget):
    """Trois cartes trouvées, en éventail, telles que le jeu les dessine."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(58, 42)
        self._cartes: list[QPixmap] = []

    def regler(self, cartes: list[QPixmap]) -> None:
        self._cartes = cartes[:len(_EVENTAIL)]
        self.setVisible(bool(self._cartes))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for pix, (x, y, angle) in zip(self._cartes, _EVENTAIL):
            ratio = pix.devicePixelRatio() or 1.0
            larg, haut = pix.width() / ratio, pix.height() / ratio
            p.save()
            p.translate(x + larg / 2, y + haut / 2)
            p.rotate(angle)
            p.drawPixmap(QRectF(-larg / 2, -haut / 2, larg, haut), pix, QRectF(pix.rect()))
            p.restore()
        p.end()


class _Barre(QWidget):
    """Cartes trouvées sur le total, en or sur un rail discret."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(3)
        self._part = 0.0

    def regler(self, part: float) -> None:
        self._part = max(0.0, min(1.0, part))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rail = QRectF(self.rect())
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawRoundedRect(rail, 1.5, 1.5)
        if self._part > 0:
            p.setBrush(accent_qcolor())
            p.drawRoundedRect(QRectF(0, 0, max(3.0, rail.width() * self._part),
                                     rail.height()), 1.5, 1.5)
        p.end()


class BlocFolio(QFrame):
    """Le bloc cliquable : il a l'air d'un bouton, il en est un (règle 119)."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("blocFolio")
        self.setStyleSheet(themed(_STYLE))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Atteint au clavier ET à la manette (règle 15).
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(tr("Ouvrir le folio"))
        self.setMaximumWidth(LARGEUR_MAX)

        rang = QHBoxLayout(self)
        rang.setContentsMargins(8, 8, 12, 8)
        rang.setSpacing(12)
        self._eventail = _Eventail()
        rang.addWidget(self._eventail, 0, Qt.AlignmentFlag.AlignVCenter)

        colonne = QVBoxLayout()
        colonne.setSpacing(6)
        haut = QHBoxLayout()
        haut.setSpacing(10)
        self._compte = QLabel()
        self._compte.setFont(body_font(14))
        self._compte.setStyleSheet("color: #f2f2f4; background: transparent;")
        lien = QLabel(tr("Folio") + " ›")
        lien.setFont(body_font(12))
        lien.setStyleSheet(themed("color: #d6a72c; background: transparent;"))
        haut.addWidget(self._compte)
        haut.addStretch(1)
        haut.addWidget(lien)
        colonne.addLayout(haut)
        self._barre = _Barre()
        colonne.addWidget(self._barre)
        self._detail = QLabel()
        self._detail.setFont(body_font(12))
        # Opaque (règle 65), même gris que la ligne méta.
        self._detail.setStyleSheet("color: #b4b4d0; background: transparent;")
        # Une seule ligne, courte (« Serpentard mène · 10 min en tout ») : en
        # deux, la hauteur du bloc ne suivait pas et la seconde était coupée.
        # L'écart de points est dans le folio.
        colonne.addWidget(self._detail)
        rang.addLayout(colonne, 1)

    def montrer(self, resume: folio.Resume, cartes: list[QPixmap], secondes: int) -> None:
        self._compte.setText(phrase_cartes(resume.trouvees, resume.total))
        self._barre.regler(resume.trouvees / resume.total if resume.total else 0.0)
        self._eventail.regler(cartes)
        # Les maisons : HP1 seulement (HP3 n'écrit pas leurs points).
        maisons = (maison_en_tete(resume.releve)
                   if isinstance(resume.releve, folio.Releve) else "")
        morceaux = [m for m in (maisons,
                                tr("{} en tout").format(format_duree_compacte(secondes))
                                if secondes > 0 else "") if m]
        self._detail.setText(" · ".join(morceaux))
        self._detail.setVisible(bool(morceaux))

    def heightForWidth(self, largeur: int) -> int:
        # Le panneau demande à SA largeur ; le bloc s'arrête à LARGEUR_MAX.
        return super().heightForWidth(min(largeur, self.maximumWidth()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def texte_detail(self) -> str:
        return self._detail.text() if self._detail.isVisibleTo(self) else ""

    def texte_compte(self) -> str:
        return self._compte.text()


def cartes_eventail(game_id: str, system: Path, releve, dpr: float) -> list[QPixmap]:
    """Les trois premières cartes trouvées, en petit ; vide sans le jeu installé."""
    from src.ui.folio_page import pixmap_texture
    if not system.is_dir():
        return []
    textures = []
    if game_id == "hp1":
        paquet = folio.paquet_menu(system)
        if paquet is None:
            return []
        textures = [folio.image_carte_hp1(paquet, n, grande=False)
                    for n in sorted(releve.cartes)[:len(_EVENTAIL)]]
    elif game_id == "hp3":
        cat = folio_hp3.catalogue(system, get_language())
        trouvees = [c for c in cat.cartes if c.classe in releve.cartes][:len(_EVENTAIL)]
        textures = [folio_hp3.image_carte(system, c.code, grande=False) for c in trouvees]
    return [pixmap_texture(t, _CARTE_H, dpr) for t in textures if t is not None]

"""Les choix des Paramètres montrés au lieu d'être listés (maquettes A « Voûte » et B « Almanach », Ludo,
2026-11-15) : la langue sur son drapeau, la maison sur son blason, l'ambiance sur son dessin, les effets animés
sur un aperçu.

`ChoixEnTuiles` parle comme une `QComboBox` (`addItem`, `currentIndex`, `setCurrentIndex`, `currentData`,
`findData`, `count`, `itemData`, `itemText`, `currentIndexChanged`) : la page qui l'emploie, ses slots et ses
tests n'ont pas à savoir qu'il n'y a plus de liste. Les tuiles sont des boutons cochables d'un groupe exclusif :
Tab entre sur le choix coché, ←/→ et la manette passent de l'une à l'autre comme dans tout groupe
(`focus_visible`, `manette_nav`). Une tuile peinte dit sa forme à l'anneau du clavier (`focus_visible.forme`),
ne dessine aucun anneau elle-même, et s'éclaire au survol (`composants.survol`).
"""

import random
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QGuiApplication, QIcon, QImage, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QButtonGroup, QGridLayout, QPushButton, QSizePolicy, QWidget

from src.core.config import ASSETS_DIR
from src.ui import focus_visible
from src.ui.composants import ENCRE, ENCRE_DOUCE, filtre, police, survol, transparent
from src.ui.fonts import cinzel
from src.ui.theme import RAYON_CARTE, accent_qcolor

# ── Le choix, à l'interface d'une liste déroulante ──


class ChoixEnTuiles(QWidget):
    """Un choix exclusif en tuiles, rangées en grille ; autant de colonnes que la largeur en laisse passer,
    `colonnes` au plus, chacune d'au moins `largeur_min` px."""

    currentIndexChanged = pyqtSignal(int)  # noqa: N815 (le nom de QComboBox)

    def __init__(self, fabrique: Callable[[str, object], QPushButton], colonnes: int,
                 largeur_min: int = 0, ecart: int = 10) -> None:
        super().__init__()
        transparent(self, "choixEnTuiles")
        self._fabrique = fabrique
        self._colonnes = colonnes
        self._largeur_min = largeur_min
        self._grille = QGridLayout(self)
        self._grille.setContentsMargins(0, 0, 0, 0)
        self._grille.setSpacing(ecart)
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self._tuiles: list[QPushButton] = []
        self._donnees: list[object] = []
        self._courant = -1
        self._n = 0

    # QComboBox
    def addItem(self, texte: str, donnee: object = None) -> None:  # noqa: N802
        tuile = self._fabrique(texte, donnee)
        tuile.setCheckable(True)
        tuile.setAccessibleName(texte)
        rang = len(self._tuiles)
        tuile.toggled.connect(lambda oui, r=rang: oui and self._choisi(r))
        self._groupe.addButton(tuile)
        self._tuiles.append(tuile)
        self._donnees.append(donnee)
        self._ranger(self._n or self._colonnes, force=True)

    def count(self) -> int:
        return len(self._tuiles)

    def currentIndex(self) -> int:  # noqa: N802
        return self._courant

    def setCurrentIndex(self, rang: int) -> None:  # noqa: N802
        if 0 <= rang < len(self._tuiles) and rang != self._courant:
            self._tuiles[rang].setChecked(True)

    def currentData(self) -> object:  # noqa: N802
        return self._donnees[self._courant] if self._courant >= 0 else None

    def itemData(self, rang: int) -> object:  # noqa: N802
        return self._donnees[rang]

    def itemText(self, rang: int) -> str:  # noqa: N802
        return self._tuiles[rang].accessibleName()

    def currentText(self) -> str:  # noqa: N802
        return self.itemText(self._courant) if self._courant >= 0 else ""

    def findData(self, donnee: object) -> int:  # noqa: N802
        return self._donnees.index(donnee) if donnee in self._donnees else -1

    @property
    def tuiles(self) -> tuple[QPushButton, ...]:
        return tuple(self._tuiles)

    def _choisi(self, rang: int) -> None:
        if rang != self._courant:
            self._courant = rang
            self.currentIndexChanged.emit(rang)

    # La grille
    def _ranger(self, n: int, force: bool = False) -> None:
        n = max(1, min(n, self._colonnes, len(self._tuiles) or 1))
        if n == self._n and not force:
            return
        self._n = n
        for tuile in self._tuiles:
            self._grille.removeWidget(tuile)
        for c in range(self._colonnes):
            self._grille.setColumnStretch(c, 1 if c < n else 0)
        for rang, tuile in enumerate(self._tuiles):
            ligne, col = divmod(rang, n)
            self._grille.addWidget(tuile, ligne, col)

    def _colonnes_pour(self, largeur: int) -> int:
        if not self._largeur_min:
            return self._colonnes
        ecart = self._grille.horizontalSpacing()
        return max(1, (largeur + ecart) // (self._largeur_min + ecart))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        """Le minimum d'UNE colonne : la grille se replie plutôt que de bloquer la page (`Rangee`)."""
        largeur = max((t.minimumSizeHint().width() for t in self._tuiles), default=0)
        return QSize(max(largeur, self._largeur_min), super().minimumSizeHint().height())

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt)
        return True

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802 (Qt)
        n = max(1, min(self._colonnes_pour(largeur), self._colonnes, len(self._tuiles) or 1))
        lignes = -(-len(self._tuiles) // n) if self._tuiles else 0
        haut = max((t.sizeHint().height() for t in self._tuiles), default=0)
        return lignes * haut + max(0, lignes - 1) * self._grille.verticalSpacing()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._ranger(self._colonnes_pour(event.size().width()))


# ── Les tuiles peintes ──


class Tuile(QPushButton):
    """Une tuile cochable peinte : un fond, un dessin, un nom, une ligne douce. Cochée : un trait d'or.

    `dessin(p, rect)` peint ce qui fait la tuile (blason, motif, aperçu) avant le texte."""

    def __init__(self, nom: str, sous: str, hauteur: int,
                 dessin: Callable[[QPainter, QRectF], None], *, fond: QLinearGradient | QColor | None = None,
                 texte_a: str = "bas", retrait_texte: int = 12) -> None:
        super().__init__()
        self.setObjectName("tuile")
        self._nom, self._sous = nom, sous
        self._dessin = dessin
        self._fond = fond
        self._texte_a = texte_a          # "bas" (sous le dessin) ou "droite" (à droite du blason)
        self._retrait = retrait_texte
        self.setFixedHeight(hauteur)
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip(nom if not sous else f"{nom} · {sous}")
        focus_visible.forme(self, RAYON_CARTE)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(120, self.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(96, self.height())

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        forme = QPainterPath()
        forme.addRoundedRect(r, RAYON_CARTE, RAYON_CARTE)
        p.setClipPath(forme)
        if isinstance(self._fond, QLinearGradient):
            fond = QLinearGradient(self._fond)
            fond.setStart(r.topLeft())
            fond.setFinalStop(r.bottomRight())
            p.fillRect(r, fond)
        else:
            p.fillRect(r, self._fond if isinstance(self._fond, QColor) else QColor("#0b0b16"))
        if self.isChecked():
            p.fillRect(r, accent_qcolor(22))
        self._dessin(p, r)
        p.setClipping(False)
        survol(p, self, RAYON_CARTE)
        self._texte(p, r)
        # Le cadre : un filet au repos, l'or de la maison une fois choisie.
        if self.isChecked():
            p.setPen(QPen(accent_qcolor(255), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), RAYON_CARTE - 1, RAYON_CARTE - 1)
        else:
            p.setPen(QPen(QColor(255, 255, 255, 26), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), RAYON_CARTE, RAYON_CARTE)
        p.end()

    def _texte(self, p: QPainter, r: QRectF) -> None:
        nom = police(13, gras=True)
        sous = police(11)
        hn = 18   # la hauteur de la ligne du nom, en 13 px
        if self._texte_a == "droite":
            zone = r.adjusted(self._retrait, 0, -8, 0)
            p.setFont(_capitales(9))
            p.setPen(QColor(ENCRE) if self.isEnabled() else QColor(ENCRE_DOUCE))
            texte = p.fontMetrics().elidedText(self._nom.upper(), Qt.TextElideMode.ElideRight, int(zone.width()))
            p.drawText(zone, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, texte)
            return
        bas = r.bottom() - 9
        largeur = int(r.width() - 2 * self._retrait)
        if self._sous:
            p.setFont(sous)
            p.setPen(QColor("#a9a7c4"))
            p.drawText(QRectF(r.left() + self._retrait, bas - 15, largeur, 15),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(self._sous, Qt.TextElideMode.ElideRight, largeur))
            bas -= 16
        p.setFont(nom)
        p.setPen(QColor(ENCRE))
        p.drawText(QRectF(r.left() + self._retrait, bas - hn, largeur, hn),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(self._nom, Qt.TextElideMode.ElideRight, largeur))


def _capitales(pt: int) -> QFont:
    f = cinzel(pt, bold=True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
    return f


def _rien(_p: QPainter, _r: QRectF) -> None:
    """Une tuile sans dessin (l'ambiance « Aucune », les effets coupés)."""


# ── La maison : son blason ──


def blason(p: QPainter, x: float, y: float, taille: float, haut: QColor, bas: QColor, lettre: str) -> None:
    """Un écu dégradé et l'initiale de la maison (dessiné ici : aucun blason officiel n'est reproduit)."""
    lg, h = taille, taille * 1.15
    ecu = QPainterPath()
    ecu.moveTo(x + lg * 0.5, y + h * 0.04)
    ecu.lineTo(x + lg * 0.93, y + h * 0.17)
    ecu.lineTo(x + lg * 0.93, y + h * 0.48)
    ecu.cubicTo(x + lg * 0.93, y + h * 0.72, x + lg * 0.73, y + h * 0.87, x + lg * 0.5, y + h * 0.96)
    ecu.cubicTo(x + lg * 0.27, y + h * 0.87, x + lg * 0.07, y + h * 0.72, x + lg * 0.07, y + h * 0.48)
    ecu.lineTo(x + lg * 0.07, y + h * 0.17)
    ecu.closeSubpath()
    degrade = QLinearGradient(x, y, x, y + h)
    degrade.setColorAt(0, haut)
    degrade.setColorAt(1, bas)
    p.setBrush(degrade)
    p.setPen(QPen(QColor(255, 255, 255, 90), 1))
    p.drawPath(ecu)
    p.setPen(QColor(255, 255, 255, 235))
    p.setFont(cinzel(max(7, round(taille * 0.3)), bold=True))
    p.drawText(QRectF(x, y + h * 0.12, lg, h * 0.7), Qt.AlignmentFlag.AlignCenter, lettre)


def tuile_maison(nom: str, haut: str, bas: str) -> Tuile:
    def dessin(p: QPainter, r: QRectF) -> None:
        blason(p, r.left() + 14, r.center().y() - 15, 26, QColor(haut), QColor(bas), nom[:1])
    return Tuile(nom, "", 54, dessin, texte_a="droite", retrait_texte=52)


# ── L'ambiance : son mois, son motif ──

# (début, fin du dégradé, signe, couleur du signe, places du signe en fractions de la tuile)
_AMBIANCES: dict[str, tuple[str, str, str, str, tuple[tuple[float, float], ...]]] = {
    "auto": ("#141a3a", "#06071a", "", "", ()),
    "aucune": ("#0b0b16", "#0b0b16", "", "", ()),
    "halloween": ("#3a2210", "#120a05", "❦", "#e8955a", ((0.10, 0.10), (0.52, 0.30), (0.82, 0.06))),
    "noel": ("#1b2350", "#090b1f", "✻", "#e6f0ff", ((0.09, 0.08), (0.45, 0.28), (0.76, 0.06), (0.92, 0.34))),
    "rentree": ("#2b1a14", "#0d0806", "✉", "#e6d3a8", ((0.13, 0.08), (0.70, 0.24))),
    "anniversaire": ("#3d3210", "#100d04", "✶", "#f0d060", ((0.38, 0.06), (0.80, 0.28), (0.14, 0.30))),
    "bataille": ("#2a1530", "#0b0610", "✦", "#c9a7f2", ((0.22, 0.08), (0.66, 0.26), (0.90, 0.04))),
}


def nom_et_date(libelle: str) -> tuple[str, str]:
    """« Halloween (octobre) » → (« Halloween », « octobre ») : les libellés de `season.SEASON_LABELS`, traduits,
    portent la date entre parenthèses ; la tuile la pose sous le nom."""
    if libelle.endswith(")") and " (" in libelle:
        nom, _, date = libelle[:-1].partition(" (")
        return nom, date
    return libelle, ""


def tuile_ambiance(saison: str, libelle: str) -> Tuile:
    debut, fin, signe, couleur, places = _AMBIANCES.get(saison, _AMBIANCES["aucune"])
    fond = QLinearGradient(0, 0, 1, 1)
    fond.setColorAt(0, QColor(debut))
    fond.setColorAt(1, QColor(fin))

    def dessin(p: QPainter, r: QRectF) -> None:
        if saison == "auto":
            _etoiles(p, r, 26, graine=7)
        if not signe:
            return
        encre = QColor(couleur)
        encre.setAlpha(215)
        p.setPen(encre)
        for rang, (fx, fy) in enumerate(places):
            p.setFont(police(15 - (rang % 2) * 4))
            # Le motif reste dans le haut de la tuile : le nom et la date vivent en bas.
            p.drawText(QPointF(r.left() + fx * r.width(), r.top() + 16 + fy * min(r.height() * 0.4, 30)), signe)

    nom, date = nom_et_date(libelle)
    return Tuile(nom, date, 78, dessin, fond=fond)


# ── Les effets animés : un aperçu ──


def _etoiles(p: QPainter, r: QRectF, n: int, graine: int) -> None:
    """Un ciel fixe (la graine le rend identique à chaque peinture) : quelques étoiles froides ou dorées."""
    tirage = random.Random(graine)
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(n):
        x, y = r.left() + tirage.random() * r.width(), r.top() + tirage.random() * r.height()
        c = QColor(255, 236, 190) if tirage.random() < 0.25 else QColor(220, 226, 255)
        c.setAlpha(tirage.randint(70, 230))
        p.setBrush(c)
        rayon = 1.3 if tirage.random() < 0.1 else 0.8
        p.drawEllipse(QPointF(x, y), rayon, rayon)


def tuile_effets(mode: str, nom: str, sous: str) -> Tuile:
    def dessin(p: QPainter, r: QRectF) -> None:
        apercu = QRectF(r.left() + 10, r.top() + 10, r.width() - 20, 34)
        chemin = QPainterPath()
        chemin.addRoundedRect(apercu, 6, 6)
        p.save()
        p.setClipPath(chemin, Qt.ClipOperation.IntersectClip)
        if mode == "non":
            p.fillRect(apercu, QColor("#0b0b16"))
        else:
            ciel = QLinearGradient(apercu.topLeft(), apercu.bottomRight())
            ciel.setColorAt(0, QColor("#141a3a"))
            ciel.setColorAt(1, QColor("#06071a"))
            p.fillRect(apercu, ciel)
            _etoiles(p, apercu, 22 if mode == "auto" else 40, graine=3 if mode == "auto" else 4)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(apercu, 6, 6)

    return Tuile(nom, sous, 96, dessin)


# ── La langue : son drapeau ──

# Le drapeau de chaque langue du launcher (flag-icons, MIT, `assets/icons/drapeaux/`). Un drapeau dit un pays,
# pas une langue : il accompagne TOUJOURS le nom de la langue écrit dans cette langue, jamais seul. Une langue
# ajoutée sans drapeau garde sa pastille, sans image.
_DRAPEAUX = {"fr": "fr", "en": "gb", "es": "es"}
_DOSSIER_DRAPEAUX = ASSETS_DIR / "icons" / "drapeaux"


@lru_cache(maxsize=16)
def _drapeau(fichier: Path, largeur: int, ratio: float) -> QImage:
    """Le drapeau rendu une fois, coins arrondis, un filet clair autour (les fonds sombres l'avalent sinon)."""
    hauteur = round(largeur * 3 / 4)
    img = QImage(round(largeur * ratio), round(hauteur * ratio), QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(ratio)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(0.5, 0.5, largeur - 1, hauteur - 1)
    forme = QPainterPath()
    forme.addRoundedRect(r, 2.5, 2.5)
    p.setClipPath(forme)
    QSvgRenderer(QByteArray(fichier.read_bytes())).render(p, r)
    p.setClipping(False)
    p.setPen(QPen(QColor(255, 255, 255, 60), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r, 2.5, 2.5)
    p.end()
    return img


def icone_drapeau(code: str, largeur: int = 20) -> QIcon | None:
    pays = _DRAPEAUX.get(code)
    if pays is None or not (_DOSSIER_DRAPEAUX / f"{pays}.svg").is_file():
        return None
    ecran = QGuiApplication.primaryScreen()
    ratio = ecran.devicePixelRatio() if ecran is not None else 1.0
    pm = QPixmap.fromImage(_drapeau(_DOSSIER_DRAPEAUX / f"{pays}.svg", largeur, ratio))
    pm.setDevicePixelRatio(ratio)
    return QIcon(pm)


def pastille_langue(nom: str, code: object) -> QPushButton:
    """Une langue en pastille, comme les rubriques : son drapeau, son nom dans sa langue."""
    b = filtre(nom, grand=True)
    icone = icone_drapeau(str(code))
    if icone is not None:
        b.setIcon(icone)
        b.setIconSize(QSize(20, 15))
    return b

"""Le cadran de défi de l'onglet « Difficulté » des réglages du jeu (`difficulte_panneau.py`).

Maquette de l'expert UI/UX validée par Ludo le 2026-10-31 (atelier,
`artefact_difficulte/index.html`) : un instrument d'astronome, cousin de
l'horloge des Weasley. 240 degrés, 48 écailles qui passent de la lueur de Lumos
à l'or, puis à la braise et au rouge ; une aiguille en baguette, une étincelle à
sa pointe ; les noms des presets gravés autour, cliquables. Sous le moyeu, le
nom du niveau et, pour du sur mesure, une ligne qui le situe. Aucun chiffre.

Tout se dessine dans le repère de la maquette (600 × 330, origine à x = -40),
mis à l'échelle du widget. Les noms gravés se cliquent à la souris ; au
clavier, les cartes de la page font le même choix (←/→).
"""

import math
from collections.abc import Callable

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from src.core.i18n import tr
from src.ui.composants import police
from src.ui.fonts import cinzel
from src.ui.theme import accent_qcolor, bg_qcolor
from src.ui.ticker import Ticker

# Le repère de la maquette.
_X0, _LARGEUR, _HAUTEUR = -40.0, 600.0, 330.0
_CX, _CY = 260.0, 205.0
_R_INT, _R_EXT = 128.0, 156.0
_HAUTEUR_MAX = 310
_NB_ECAILLES = 48
# Du bleu de Lumos (0) au rouge sang (100), en passant par l'or.
_TEINTES = ((0, (122, 172, 245)), (28, (196, 200, 170)), (45, (226, 179, 60)),
            (65, (232, 137, 46)), (84, (210, 69, 58)), (100, (163, 23, 47)))
# Part du chemin restant parcourue à chaque battement du Ticker (30 Hz) : pas
# fixe, un Ticker en pause reprend sans saut (règle 19).
_PAS = 0.16


def teinte(valeur: float) -> QColor:
    """La couleur d'un niveau de 0 à 100."""
    for (v0, c0), (v1, c1) in zip(_TEINTES, _TEINTES[1:], strict=False):
        if valeur <= v1:
            t = max(0.0, (valeur - v0) / (v1 - v0))
            return QColor(*(round(a + (b - a) * t) for a, b in zip(c0, c1, strict=True)))
    return QColor(*_TEINTES[-1][1])


def _angle(valeur: float) -> float:
    return math.radians(210 - 2.4 * valeur)


def _point(valeur: float, rayon: float) -> QPointF:
    a = _angle(valeur)
    return QPointF(_CX + rayon * math.cos(a), _CY - rayon * math.sin(a))


def _rect(rayon: float) -> QRectF:
    return QRectF(_CX - rayon, _CY - rayon, 2 * rayon, 2 * rayon)


def _arc(v0: float, v1: float, rayon: float) -> QPainterPath:
    chemin = QPainterPath(_point(v0, rayon))
    chemin.arcTo(_rect(rayon), 210 - 2.4 * v0, -2.4 * (v1 - v0))
    return chemin


def _secteur(v0: float, v1: float) -> QPainterPath:
    chemin = _arc(v0, v1, _R_EXT)
    chemin.arcTo(_rect(_R_INT), 210 - 2.4 * v1, 2.4 * (v1 - v0))
    chemin.closeSubpath()
    return chemin


def _etoiles() -> tuple[tuple[QPointF, float, float], ...]:
    """Le ciel du cadran : toujours le même (graine fixe, comme la maquette)."""
    graine = 7

    def hasard() -> float:
        nonlocal graine
        graine = (graine * 9301 + 49297) % 233280
        return graine / 233280

    etoiles = []
    for _ in range(34):
        v, r = hasard() * 100, 30 + hasard() * 80
        etoiles.append((_point(v, r), 0.5 + hasard() * 1.1, 0.15 + hasard() * 0.4))
    return tuple(etoiles)


_ETOILES = _etoiles()


class CadranDefi(QWidget):
    """Le niveau de défi d'un jeu, une aiguille sur un cadran."""

    def __init__(self, choisir: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._choisir = choisir
        self._crans: tuple[tuple[str, str, float], ...] = ()
        self._valeur = 40.0
        self._cible = 40.0
        self._anime = False
        self.nom = ""
        self.sous = ""
        self.actif = ""
        self._survole = ""
        self._zones: dict[str, QRectF] = {}
        self.setMouseTracking(True)
        politique = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        politique.setHeightForWidth(True)
        self.setSizePolicy(politique)
        self.setMinimumSize(320, round(320 * _HAUTEUR / _LARGEUR))
        self.setAccessibleName(tr("Niveau de défi"))

    # ── Mesure ────────────────────────────────────────────────────────────
    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt)
        return True

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802 (Qt)
        # Plafonnée : empilé sous l'en-tête, le cadran ne grandit plus et se
        # centre (une largeur maximale aurait aussi bridé la colonne de l'en-tête).
        return min(round(largeur * _HAUTEUR / _LARGEUR), _HAUTEUR_MAX)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(480, self.heightForWidth(480))

    def _echelle(self) -> tuple[float, float, float]:
        k = min(self.width() / _LARGEUR, self.height() / _HAUTEUR)
        dx = (self.width() - _LARGEUR * k) / 2 - _X0 * k
        dy = (self.height() - _HAUTEUR * k) / 2
        return k, dx, dy

    # ── État ──────────────────────────────────────────────────────────────
    def poser_crans(self, crans: tuple[tuple[str, str, float], ...]) -> None:
        """(identifiant, nom affiché, cran) de chaque preset du jeu."""
        self._crans = crans
        self.update()

    def viser(self, valeur: float, nom: str, sous: str = "", actif: str = "",
              anime: bool = True) -> None:
        """Pose l'aiguille sur `valeur` ; `actif` est le preset choisi (vide :
        sur mesure)."""
        self._cible = max(0.0, min(100.0, valeur))
        self.nom, self.sous, self.actif = nom, sous, actif
        self.setAccessibleDescription(f"{nom}, {sous}" if sous else nom)
        if not anime or not self.isVisible():
            self._arreter()
        elif not self._anime:
            self._anime = True
            Ticker.instance().tick.connect(self._battement)
        self.update()

    def valeur(self) -> float:
        return self._valeur

    def _battement(self) -> None:
        reste = self._cible - self._valeur
        if abs(reste) < 0.15:
            self._arreter()
        else:
            self._valeur += reste * _PAS
        self.update()

    def _arreter(self) -> None:
        self._valeur = self._cible
        if self._anime:
            self._anime = False
            Ticker.detach(self._battement)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._arreter()
        super().hideEvent(event)

    # ── Souris ────────────────────────────────────────────────────────────
    def _cran_sous(self, pos: QPointF) -> str:
        k, dx, dy = self._echelle()
        logique = QPointF((pos.x() - dx) / k, (pos.y() - dy) / k)
        return next((i for i, zone in self._zones.items() if zone.contains(logique)), "")

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        survole = self._cran_sous(event.position())
        if survole != self._survole:
            self._survole = survole
            self.setCursor(Qt.CursorShape.PointingHandCursor if survole else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self._survole:
            self._survole = ""
            self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            ident = self._cran_sous(event.position())
            if ident:
                self._choisir(ident)
                return
        super().mouseReleaseEvent(event)

    # ── Peinture : l'ordre des appels est l'ordre de profondeur ───────────
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        k, dx, dy = self._echelle()
        p.translate(dx, dy)
        p.scale(k, k)
        v = self._valeur
        self._fond(p)
        self._gravures(p)
        self._ecailles(p, v)
        self._reperes(p)
        self._aiguille(p, v)
        self._moyeu(p)
        self._textes(p)
        p.end()

    def _fond(self, p: QPainter) -> None:
        # S'éteint avant le bas du repère (125 sous le moyeu) : pas de bord net.
        halo = QRadialGradient(QPointF(_CX, _CY), 200)
        halo.setColorAt(0, QColor(27, 32, 71, 130))
        halo.setColorAt(0.45, QColor(27, 32, 71, 70))
        halo.setColorAt(0.62, bg_qcolor(0))
        halo.setColorAt(1, bg_qcolor(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(_CX, _CY), 200, 200)
        for centre, rayon, opacite in _ETOILES:
            p.setBrush(QColor(201, 198, 234, round(255 * opacite)))
            p.drawEllipse(centre, rayon, rayon)

    def _gravures(self, p: QPainter) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        for rayon, alpha, pointille in ((_R_EXT + 8, 115, False), (_R_INT - 7, 56, False),
                                        (_R_INT - 11, 26, True)):
            stylo = QPen(accent_qcolor(alpha), 1)
            if pointille:
                stylo.setDashPattern([1, 5])
            p.setPen(stylo)
            p.drawPath(_arc(0, 100, rayon))
        for t in range(0, 101, 5):
            majeur = t % 25 == 0
            p.setPen(QPen(accent_qcolor(140 if majeur else 64), 1))
            p.drawLine(_point(t, _R_EXT + 8), _point(t, _R_EXT + (15 if majeur else 12)))

    def _ecailles(self, p: QPainter, v: float) -> None:
        pas = 100 / _NB_ECAILLES
        for i in range(_NB_ECAILLES):
            milieu = (i + 0.5) * pas
            chemin = _secteur(i * pas + 0.35, (i + 1) * pas - 0.35)
            if milieu <= v:
                couleur = teinte(milieu)
                proche = max(0.0, 1 - (v - milieu) / 30)
                opacite = 0.55 + 0.45 * proche
                lueur = QColor(couleur)
                lueur.setAlphaF(0.22 * opacite)
                p.setPen(QPen(lueur, 5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(chemin)
                couleur.setAlphaF(opacite)
                p.setPen(QPen(QColor(255, 240, 200, 90), 0.8))
                p.setBrush(couleur)
            else:
                p.setPen(QPen(accent_qcolor(41), 0.8))
                p.setBrush(QColor(255, 255, 255, 9))
            p.drawPath(chemin)

    def _reperes(self, p: QPainter) -> None:
        """Un losange et un nom gravé par preset ; le nom se clique."""
        self._zones = {}
        f = cinzel(10, bold=True)
        f.setPixelSize(15)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
        p.setFont(f)
        mesure = QFontMetricsF(f)
        for ident, nom, cran in self._crans:
            actif = ident == self.actif
            centre = _point(cran, _R_EXT + 8)
            losange = QPolygonF([centre + QPointF(0, -4.5), centre + QPointF(4.5, 0),
                                 centre + QPointF(0, 4.5), centre + QPointF(-4.5, 0)])
            p.setPen(QPen(accent_qcolor(), 1.2))
            p.setBrush(QColor(240, 208, 96) if actif else bg_qcolor())
            p.drawPolygon(losange)
            ancre = _point(cran, _R_EXT + 26)
            ecart = ancre.x() - _CX
            # La place jusqu'au bord du repère : un nom plus long s'élide (règle 50).
            if abs(ecart) < 40:
                place = 2 * min(ancre.x() - _X0, _X0 + _LARGEUR - ancre.x())
            elif ecart < 0:
                place = ancre.x() - _X0 - 4
            else:
                place = _X0 + _LARGEUR - ancre.x() - 4
            texte = mesure.elidedText(nom, Qt.TextElideMode.ElideRight, place)
            largeur = mesure.horizontalAdvance(texte)
            x = ancre.x() - (largeur / 2 if abs(ecart) < 40 else (largeur if ecart < 0 else 0))
            y = ancre.y() + (-2 if ancre.y() < _CY - 120 else 5)
            zone = QRectF(x, y - mesure.ascent(), largeur, mesure.height()).adjusted(-6, -4, 6, 4)
            self._zones[ident] = zone
            if actif:
                p.setPen(QColor(240, 208, 96))
            elif ident == self._survole:
                p.setPen(QColor(242, 242, 244))
            else:
                p.setPen(QColor(108, 106, 136))
            p.drawText(QPointF(x, y), texte)

    def _aiguille(self, p: QPainter, v: float) -> None:
        a = _angle(v)
        pointe = _point(v, _R_INT - 4)
        normale = QPointF(-math.sin(a), -math.cos(a))
        base = QPointF(_CX - 22 * math.cos(a), _CY + 22 * math.sin(a))
        corps = QPolygonF([base + normale * 4.2, pointe + normale * 0.8,
                           pointe - normale * 0.8, base - normale * 4.2])
        bois = QLinearGradient(base + normale * 4.2, base - normale * 4.2)
        bois.setColorAt(0, QColor(58, 42, 18))
        bois.setColorAt(0.5, QColor(138, 106, 44))
        bois.setColorAt(1, QColor(58, 42, 18))
        # Le halo de la pointe, sous la baguette.
        halo = QRadialGradient(pointe, 16 + v / 6)
        couleur = teinte(v)
        couleur.setAlpha(150)
        halo.setColorAt(0, couleur)
        couleur.setAlpha(0)
        halo.setColorAt(1, couleur)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(pointe, 16 + v / 6, 16 + v / 6)
        p.setPen(QPen(accent_qcolor(180), 0.8))
        p.setBrush(QBrush(bois))
        p.drawPolygon(corps)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent_qcolor())
        p.drawEllipse(_point(v, 30), 4.2, 4.2)
        # L'étincelle : une étoile à quatre branches qui tourne avec l'aiguille.
        p.save()
        p.translate(pointe)
        p.rotate(v * 1.2)
        p.scale(0.8 + v / 250, 0.8 + v / 250)
        p.setBrush(QColor(255, 246, 216))
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in (
            (0, -9), (2, -2), (9, 0), (2, 2), (0, 9), (-2, 2), (-9, 0), (-2, -2))]))
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(0, 0), 2.6, 2.6)
        p.restore()

    def _moyeu(self, p: QPainter) -> None:
        centre = QPointF(_CX, _CY)
        laiton = QRadialGradient(QPointF(_CX - 3.4, _CY - 5), 24)
        laiton.setColorAt(0, QColor(246, 220, 132))
        laiton.setColorAt(0.55, QColor(184, 137, 42))
        laiton.setColorAt(1, QColor(94, 69, 18))
        p.setPen(QPen(QColor(240, 208, 96, 153), 1))
        p.setBrush(QBrush(laiton))
        p.drawEllipse(centre, 17, 17)
        p.setPen(QPen(QColor(59, 43, 14, 153), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(centre, 9, 9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(42, 31, 10))
        p.drawEllipse(centre, 3, 3)

    def _textes(self, p: QPainter) -> None:
        legende = cinzel(8, bold=True)
        legende.setPixelSize(12)
        legende.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.4)
        self._centre(p, tr("Niveau de défi").upper(), legende, 252, QColor(169, 167, 196))
        nom = cinzel(20, bold=True)
        nom.setPixelSize(34)
        self._centre(p, self.nom, nom, 290, QColor(242, 242, 244))
        if self.sous:
            sous = police(16)
            sous.setItalic(True)
            self._centre(p, self.sous, sous, 317, QColor(169, 167, 196))

    @staticmethod
    def _centre(p: QPainter, texte: str, f: QFont, y: float, couleur: QColor) -> None:
        """Centré sous le moyeu, dans la largeur du repère : réduit, puis élidé."""
        place = _LARGEUR - 40
        while QFontMetricsF(f).horizontalAdvance(texte) > place and f.pixelSize() > 11:
            f.setPixelSize(f.pixelSize() - 1)
        mesure = QFontMetricsF(f)
        texte = mesure.elidedText(texte, Qt.TextElideMode.ElideRight, place)
        p.setFont(f)
        p.setPen(couleur)
        p.drawText(QPointF(_CX - mesure.horizontalAdvance(texte) / 2, y), texte)

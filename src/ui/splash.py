"""Écran de démarrage : logo, ligne de progression qui nomme ses étapes, fait du jour.

Maquette « Démarrage A » validée par Ludo le 2026-10-14 : le logo, une ligne
d'or sous laquelle sont écrites les étapes (faites, en cours, à venir), une
phrase qui dit ce qui se fait, le fait de l'almanach en bas à gauche et la
version en bas à droite.

Le pack de marque impose une règle : « ne pas intégrer le statut dans une image
fixe : il doit pouvoir évoluer pendant le chargement » (règle 123). L'écran est
donc PEINT ; seul le logo horizontal est une image (32 Ko). Les étapes sont
annoncées par ceux qui les font (`src/core/demarrage.py`) : rien n'est simulé.

Les positions sont des fractions de la maquette 1280×720 ; les corps de texte,
eux, sont plus grands qu'une simple réduction : à 720 px de large, les 14 px de
la maquette en feraient 8, illisibles.
"""

import logging

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QColor, QFont, QFontMetricsF, QGuiApplication, QPainter,
    QPixmap, QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from src.core import demarrage
from src.core.config import APP_VERSION, ASSETS_DIR
from src.core.i18n import tr
from src.ui.utils import icone_application

log = logging.getLogger(__name__)

# ── Palette du pack de marque ──
_FOND = "#060611"          # bleu nuit, coins de la maquette
_HALO = "#141a33"          # voile plus clair derrière le logo
_OR = "#d6a72c"            # or principal du pack (le logo est peint dans cet or)
_ETAPE_FAITE = "#7d7b92"
_ETAPE_EN_COURS = "#f2e6c4"
_ETAPE_A_VENIR = "#4d4b62"
_PHRASE = "#a9a7c4"
_FAIT = "#8d8ba8"
_VERSION = "#5f5d74"

# ── Proportions relevées sur la maquette 1280×720 ──
_LOGO_LARGEUR = 0.40       # largeur du PNG rapportée à celle de l'écran
_LOGO_CENTRE_Y = 0.374     # centre vertical du logo
_LIGNE_Y = 0.583           # ligne de progression
_LIGNE_LARGEUR = 0.46
_LIGNE_EPAISSEUR = 0.0042  # rapportée à la hauteur (3 px sur 720)
_MARGE_BAS = 0.047         # fait du jour et version, au-dessus du bord
_MARGE_COTE = 0.031
_FAIT_LARGEUR = 0.50
_FAIT_LIGNES = 3           # au-delà, le fait est coupé net (aucun ne l'est)

# ── Corps, rapportés à la hauteur ──
_CORPS_ETAPES = 0.030
_CORPS_PHRASE = 0.036
_CORPS_FAIT = 0.033
_CORPS_VERSION = 0.029

# Le logo horizontal n'est pas centré dans son PNG : l'encre occupe x 52→912
# sur 1024, donc son milieu est 30 px à gauche du milieu de l'image. Centrer
# l'image telle quelle décalerait visiblement le logo vers la gauche.
_LOGO_DECALAGE = 30 / 1024


def libelle_etape(etape: str) -> str:
    """Le nom court d'une étape, sous la ligne."""
    return {
        demarrage.CATALOGUE: tr("Catalogue"),
        demarrage.JEUX: tr("Vos jeux"),
        demarrage.BIBLIOTHEQUE: tr("Bibliothèque"),
        demarrage.FENETRE: tr("Fenêtre"),
    }[etape]


def phrase_etape(etape: str | None) -> str:
    """Ce qui se fait pendant l'étape, sous les noms."""
    if etape is None:
        return tr("Démarrage…")
    return {
        demarrage.CATALOGUE: tr("Lecture du catalogue…"),
        demarrage.JEUX: tr("Recherche de vos jeux…"),
        demarrage.BIBLIOTHEQUE: tr("Préparation de la bibliothèque…"),
        demarrage.FENETRE: tr("Ouverture de la fenêtre…"),
    }[etape]


def _en_pixels(police: QFont, pixels: float) -> QFont:
    police.setPixelSize(max(9, round(pixels)))
    return police


class AccioSplash(QWidget):
    """Écran de démarrage dont l'étape se met à jour.

    **Pourquoi un `QWidget` et non un `QSplashScreen`**, qui serait pourtant la
    classe faite pour ça : `QSplashScreen.show()` coûte **≈ 1 018 ms** sur
    Windows 11 (7 mesures, 1 005 à 1 032 ms), plateforme déjà chaude et fenêtre
    réellement exposée. Une `QWidget` portant EXACTEMENT les mêmes drapeaux de
    fenêtre s'affiche en 2 à 19 ms. Ce n'est ni les polices (6 ms), ni le logo,
    ni l'icône : c'est la classe elle-même (règle 124).

    `pixmap()` est conservé parce que c'est par là que le rendu s'inspecte, ici
    comme dans `tests/test_splash.py`.
    """

    def __init__(self, largeur: int = 720, fait: str = "") -> None:
        hauteur = int(largeur * 9 / 16)   # la maquette est en 16:9
        # Les drapeaux que QSplashScreen posait pour nous. Sans eux, le splash
        # prendrait une barre de titre et passerait derrière la fenêtre.
        super().__init__(None, Qt.WindowType.SplashScreen
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._w = largeur
        self._h = hauteur
        self._etape: str | None = None
        self._fait = fait
        self._pix = QPixmap(largeur, hauteur)
        self._logo = QPixmap(str(ASSETS_DIR / "accio_logo_horizontal.png"))
        if self._logo.isNull():
            log.warning("Logo horizontal introuvable — écran de démarrage sans logo")
        self.setWindowIcon(icone_application())
        self.setFixedSize(largeur, hauteur)
        self._centrer()
        self._redessine()

    def _centrer(self) -> None:
        """QSplashScreen se centrait tout seul ; une QWidget, non.

        Sans ça le splash s'ouvre dans le coin haut-gauche — le genre de
        régression qu'aucun test de rendu ne voit, puisque le dessin est juste.
        """
        ecran = self.screen() or QGuiApplication.primaryScreen()
        if ecran is not None:
            centre = ecran.availableGeometry().center()
            self.move(centre.x() - self._w // 2, centre.y() - self._h // 2)

    # ── API ──

    def etape(self, etape: str) -> None:
        """`etape` commence (voir `demarrage.ETAPES`).

        Repeint immédiatement : l'appelant est dans une phase de démarrage
        synchrone, il n'y a pas de boucle d'événements pour le faire à sa place.
        """
        if etape not in demarrage.ETAPES:
            return
        self._etape = etape
        self._redessine()
        self.repaint()

    @property
    def progres(self) -> float:
        """La part de la ligne en or : le milieu de l'étape en cours."""
        if self._etape is None:
            return 0.0
        return (demarrage.ETAPES.index(self._etape) + 0.5) / len(demarrage.ETAPES)

    def finish(self, fenetre) -> None:
        """Referme le splash une fois la fenêtre prête.

        `main.py` l'appelle APRÈS `window.show()`, donc il n'y a plus rien à
        attendre. Le paramètre est gardé pour ne rien changer à l'appelant.
        """
        self.close()

    def pixmap(self) -> QPixmap:
        """Le rendu courant. C'est par là qu'on inspecte ce qui est peint."""
        return self._pix

    # ── Écoute des étapes : seulement tant qu'il est à l'écran ──

    def showEvent(self, event) -> None:
        demarrage.ecouter(self.etape)
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        # Fermé pour l'assistant ou à la fin : un auditeur resté branché
        # repeindrait un widget détruit au prochain `GameManager`.
        demarrage.ecouter(None)
        super().hideEvent(event)

    # ── Peinture ──

    def paintEvent(self, _event) -> None:
        """Le pixmap porte son `devicePixelRatio`, donc `drawPixmap` le repose à
        la bonne échelle : à 125 %, 900×506 physiques pour 720×405 logiques."""
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pix)
        p.end()

    def _redessine(self) -> None:
        # Peindre à la résolution PHYSIQUE : sur un écran à 125 % ou 200 %, un
        # pixmap créé aux dimensions logiques est agrandi par Qt et le logo
        # ressort flou.
        dpr = self.devicePixelRatioF() or 1.0
        pix = QPixmap(int(self._w * dpr), int(self._h * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(QColor(_FOND))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._peint_fond(p)
        self._peint_logo(p)
        self._peint_ligne(p)
        self._peint_etapes(p)
        self._peint_bas(p)
        p.end()
        self._pix = pix
        self.update()

    def _peint_fond(self, p: QPainter) -> None:
        """Bleu nuit, éclairci en halo derrière le logo (comme la maquette)."""
        halo = QRadialGradient(self._w * 0.5, self._h * 0.42, self._w * 0.62)
        halo.setColorAt(0.0, QColor(_HALO))
        halo.setColorAt(1.0, QColor(_FOND))
        p.fillRect(QRectF(0, 0, self._w, self._h), halo)

    def _peint_logo(self, p: QPainter) -> None:
        if self._logo.isNull():
            return
        larg = self._w * _LOGO_LARGEUR
        haut = larg * self._logo.height() / self._logo.width()
        x = (self._w - larg) / 2 + larg * _LOGO_DECALAGE
        y = self._h * _LOGO_CENTRE_Y - haut / 2
        p.drawPixmap(QRectF(x, y, larg, haut), self._logo,
                     QRectF(self._logo.rect()))

    def _ligne(self) -> QRectF:
        larg = self._w * _LIGNE_LARGEUR
        ep = max(2.0, self._h * _LIGNE_EPAISSEUR)
        return QRectF((self._w - larg) / 2, self._h * _LIGNE_Y, larg, ep)

    def _peint_ligne(self, p: QPainter) -> None:
        """Filet fin ; la part déjà parcourue en or plein, le reste éteint."""
        ligne = self._ligne()
        rayon = ligne.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(214, 167, 44, 41))
        p.drawRoundedRect(ligne, rayon, rayon)
        if self.progres > 0:
            faite = QRectF(ligne.x(), ligne.y(), ligne.width() * self.progres, ligne.height())
            p.setBrush(QColor(_OR))
            p.drawRoundedRect(faite, rayon, rayon)

    def police_etapes(self) -> QFont:
        """Le corps des noms d'étapes, réduit s'il le faut pour tenir sous la ligne.

        Quatre noms côte à côte sur 46 % de la largeur : en espagnol ou à
        480 px, ils ne tiennent pas toujours au corps de la maquette.
        """
        from src.ui.fonts import body_font

        largeur = self._ligne().width()
        pixels = self._h * _CORPS_ETAPES
        while True:
            police = _en_pixels(body_font(), pixels)
            fm = QFontMetricsF(police)
            besoin = sum(fm.horizontalAdvance(libelle_etape(e)) for e in demarrage.ETAPES)
            if besoin + 3 * fm.horizontalAdvance("  ") <= largeur or pixels <= 9:
                return police
            pixels -= 0.5

    def _peint_etapes(self, p: QPainter) -> None:
        """Les quatre noms répartis sous la ligne, puis la phrase de l'étape."""
        from src.ui.fonts import body_font

        ligne = self._ligne()
        police = self.police_etapes()
        fm = QFontMetricsF(police)
        p.setFont(police)
        largeurs = [fm.horizontalAdvance(libelle_etape(e)) for e in demarrage.ETAPES]
        # Réparties comme la maquette : la première au début de la ligne, la
        # dernière à sa fin, des écarts égaux entre elles.
        ecart = (ligne.width() - sum(largeurs)) / (len(largeurs) - 1)
        en_cours = demarrage.ETAPES.index(self._etape) if self._etape else -1
        y = ligne.bottom() + self._h * 0.019
        x = ligne.x()
        for i, (etape, larg) in enumerate(zip(demarrage.ETAPES, largeurs, strict=True)):
            couleur = (_ETAPE_EN_COURS if i == en_cours
                       else _ETAPE_FAITE if i < en_cours else _ETAPE_A_VENIR)
            p.setPen(QColor(couleur))
            p.drawText(QRectF(x, y, larg + 1, fm.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       libelle_etape(etape))
            x += larg + ecart

        phrase = _en_pixels(body_font(), self._h * _CORPS_PHRASE)
        fmp = QFontMetricsF(phrase)
        p.setFont(phrase)
        p.setPen(QColor(_PHRASE))
        y += fm.height() + self._h * 0.022
        marge = self._w * _MARGE_COTE
        texte = fmp.elidedText(phrase_etape(self._etape), Qt.TextElideMode.ElideRight,
                               self._w - 2 * marge)
        p.drawText(QRectF(marge, y, self._w - 2 * marge, fmp.height() + 2),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, texte)

    def zone_du_fait(self) -> QRectF:
        """Le cadre du fait du jour : en bas à gauche, trois lignes au plus."""
        fm = QFontMetricsF(self.police_du_fait())
        haut = fm.lineSpacing() * _FAIT_LIGNES
        marge = self._w * _MARGE_COTE
        return QRectF(marge, self._h * (1 - _MARGE_BAS) - haut,
                      self._w * _FAIT_LARGEUR, haut)

    def police_du_fait(self) -> QFont:
        from src.ui.fonts import body_font

        police = _en_pixels(body_font(), self._h * _CORPS_FAIT)
        police.setItalic(True)
        return police

    def _peint_bas(self, p: QPainter) -> None:
        """Le fait de l'almanach à gauche, la version à droite, sur la même base."""
        from src.ui.fonts import body_font

        bas = self._h * (1 - _MARGE_BAS)
        marge = self._w * _MARGE_COTE
        if self._fait:
            p.setFont(self.police_du_fait())
            p.setPen(QColor(_FAIT))
            p.save()
            zone = self.zone_du_fait()
            p.setClipRect(zone)
            p.drawText(zone, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
                       | Qt.TextFlag.TextWordWrap, self._fait)
            p.restore()

        version = _en_pixels(body_font(), self._h * _CORPS_VERSION)
        fmv = QFontMetricsF(version)
        p.setFont(version)
        p.setPen(QColor(_VERSION))
        p.drawText(QRectF(0, bas - fmv.height(), self._w - marge, fmv.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                   f"v{APP_VERSION}")

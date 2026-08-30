"""Écran de démarrage — logo de marque, ligne de progression, état vivant.

Le pack de marque impose une règle sur ce point : « ne pas intégrer le statut
dans une image fixe : il doit pouvoir évoluer pendant le chargement ». L'écran
est donc PEINT, pas affiché comme capture — seul le logo horizontal est une
image (32 Ko), le reste est du dessin. Ça permet aussi de ne pas embarquer le
splash de référence, qui pèse 1,1 Mo à lui seul.

Les proportions viennent de la maquette `splash-initialisation-1600x900.png`,
relevées au pixel puis exprimées en fractions — l'écran est donc identique à
n'importe quelle taille, et suit le DPI de l'utilisateur.
"""

import logging

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QFont, QGuiApplication, QIcon, QLinearGradient, QPainter, QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from src.core.config import APP_VERSION, ASSETS_DIR

log = logging.getLogger(__name__)

# ── Palette du pack de marque ──
_FOND = "#060611"          # bleu nuit, coins de la maquette
_HALO = "#141a33"          # voile plus clair derrière le logo (mesuré #13172e)
_OR = "#d6a72c"            # or principal du pack (le logo est peint dans cet or)
_TEXTE_2 = "#9b98a6"       # texte secondaire
_TEXTE_3 = "#6d6a7a"       # numéro de version, discret mais lisible

# ── Proportions relevées sur la maquette 1600×900 ──
_LOGO_LARGEUR = 0.50       # largeur du logo rapportée à celle de l'écran
_LOGO_CENTRE_Y = 0.46      # centre vertical du logo
_LIGNE_Y = 0.688           # ligne de progression
_LIGNE_LARGEUR = 0.46
_LIGNE_EPAISSEUR = 0.004   # rapportée à la hauteur (2 px sur 450, 4 sur 900)
_STATUT_Y = 0.733          # ligne de base du libellé d'état
_STATUT_CORPS = 0.030      # corps de police rapporté à la hauteur
_VERSION_MARGE = 0.028

# Le logo horizontal n'est pas centré dans son PNG : l'encre occupe x 52→912
# sur 1024, donc son milieu est 30 px à gauche du milieu de l'image. Centrer
# l'image telle quelle décalerait visiblement le logo vers la gauche.
_LOGO_DECALAGE = 30 / 1024


class AccioSplash(QWidget):
    """Écran de démarrage dont l'état et la progression se mettent à jour.

    **Pourquoi un `QWidget` et non un `QSplashScreen`**, qui serait pourtant la
    classe faite pour ça : `QSplashScreen.show()` coûte **≈ 1 018 ms** sur
    Windows 11 (7 mesures, 1 005 à 1 032 ms), plateforme déjà chaude et fenêtre
    réellement exposée. Une `QWidget` portant EXACTEMENT les mêmes drapeaux de
    fenêtre s'affiche en 2 à 19 ms. Ce n'est ni les polices (6 ms), ni le logo,
    ni l'icône : c'est la classe elle-même.

    Une seconde, donc — et c'est la pire de toutes, puisqu'elle précède le
    premier pixel : l'écran de marque existe POUR couvrir le chargement, et il
    arrivait après le poste le plus cher du démarrage. Mesuré de bout en bout :
    1 231 à 1 297 ms avant que quoi que ce soit n'apparaisse (4 relevés).

    Le dessin, lui, n'a pas bougé d'un pixel — vérifié en comparant les deux
    rendus image contre image : 0 différence sur 275 100 pixels. `pixmap()` est
    conservé parce que c'est par là que le rendu s'inspecte, ici comme dans
    `tests/test_splash.py`.
    """

    def __init__(self, largeur: int = 560) -> None:
        hauteur = int(largeur * 9 / 16)   # la maquette est en 16:9
        # Les drapeaux que QSplashScreen posait pour nous. Sans eux, le splash
        # prendrait une barre de titre et passerait derrière la fenêtre.
        super().__init__(None, Qt.WindowType.SplashScreen
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._w = largeur
        self._h = hauteur
        self._statut = ""
        self._progres = 0.0    # 0.0 → 1.0
        self._pix = QPixmap(largeur, hauteur)
        self._logo = QPixmap(str(ASSETS_DIR / "accio_logo_horizontal.png"))
        if self._logo.isNull():
            log.warning("Logo horizontal introuvable — écran de démarrage sans logo")
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "accio_launcher.ico")))
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

    def set_statut(self, texte: str, progres: float | None = None) -> None:
        """Change le libellé d'état, et éventuellement l'avancement (0 → 1).

        Repeint immédiatement : l'appelant est dans une phase de démarrage
        synchrone, il n'y a pas de boucle d'événements pour le faire à sa place.
        """
        self._statut = texte
        if progres is not None:
            self._progres = max(0.0, min(1.0, progres))
        self._redessine()
        self.repaint()

    def finish(self, fenetre) -> None:
        """Referme le splash une fois la fenêtre prête.

        `QSplashScreen.finish` attendait l'exposition de `fenetre` ; ici
        `main.py` l'appelle APRÈS `window.show()`, donc il n'y a plus rien à
        attendre. Le paramètre est gardé pour ne rien changer à l'appelant.
        """
        self.close()

    def pixmap(self) -> QPixmap:
        """Le rendu courant. C'est par là qu'on inspecte ce qui est peint."""
        return self._pix

    def setPixmap(self, pix: QPixmap) -> None:
        self._pix = pix
        self.update()

    # ── Peinture ──

    def paintEvent(self, _event) -> None:
        """QSplashScreen peignait son pixmap ; à nous de le faire.

        Le pixmap porte son `devicePixelRatio`, donc `drawPixmap` le repose à
        la bonne échelle : à 125 %, 700×394 physiques pour 560×315 logiques.
        """
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pix)
        p.end()

    def _redessine(self) -> None:
        # Peindre à la résolution PHYSIQUE : sur un écran à 125 % ou 200 %, un
        # pixmap créé aux dimensions logiques est agrandi par Qt et le logo
        # ressort flou. Le logo source fait 1024 px de large pour 280 px
        # logiques affichés — il y a donc de la matière jusqu'à 3,6×.
        dpr = self.devicePixelRatioF() or 1.0
        pix = QPixmap(int(self._w * dpr), int(self._h * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(QColor(_FOND))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._peint_fond(p)
        self._peint_logo(p)
        self._peint_ligne(p)
        self._peint_textes(p)
        p.end()
        self.setPixmap(pix)

    def _peint_fond(self, p: QPainter) -> None:
        """Bleu nuit, éclairci en halo derrière le logo (comme la maquette)."""
        # Rayon serré (0,45 W) : à 0,62 le voile débordait sur les bords, qui
        # mesuraient #090a19 là où la maquette est à #050614.
        halo = QRadialGradient(self._w * 0.5, self._h * _LOGO_CENTRE_Y,
                               self._w * 0.45)
        halo.setColorAt(0.0, QColor(_HALO))
        halo.setColorAt(0.45, QColor(13, 16, 34))
        halo.setColorAt(1.0, QColor(_FOND))
        p.fillRect(QRectF(0, 0, self._w, self._h), halo)
        # Assombrissement des bords : la maquette est nettement plus sombre en
        # haut et en bas qu'au centre.
        bord = QLinearGradient(0, 0, 0, self._h)
        bord.setColorAt(0.0, QColor(6, 6, 17, 190))
        bord.setColorAt(0.42, QColor(6, 6, 17, 0))
        bord.setColorAt(0.80, QColor(6, 6, 17, 90))
        bord.setColorAt(1.0, QColor(6, 6, 17, 210))
        p.fillRect(QRectF(0, 0, self._w, self._h), bord)

    def _peint_logo(self, p: QPainter) -> None:
        if self._logo.isNull():
            return
        larg = self._w * _LOGO_LARGEUR
        haut = larg * self._logo.height() / self._logo.width()
        x = (self._w - larg) / 2 + larg * _LOGO_DECALAGE
        y = self._h * _LOGO_CENTRE_Y - haut / 2
        p.drawPixmap(QRectF(x, y, larg, haut), self._logo,
                     QRectF(self._logo.rect()))

    def _peint_ligne(self, p: QPainter) -> None:
        """Filet fin ; la part déjà parcourue est en or plein, le reste éteint."""
        larg = self._w * _LIGNE_LARGEUR
        x = (self._w - larg) / 2
        y = self._h * _LIGNE_Y
        ep = max(1.0, self._h * _LIGNE_EPAISSEUR)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(214, 167, 44, 38))
        p.drawRect(QRectF(x, y, larg, ep))

        if self._progres > 0:
            faite = larg * self._progres
            grad = QLinearGradient(x, 0, x + faite, 0)
            grad.setColorAt(0.0, QColor(214, 167, 44, 120))
            grad.setColorAt(1.0, QColor(_OR))
            p.setBrush(grad)
            p.drawRect(QRectF(x, y, faite, ep))
            # Étincelle en tête de course, comme sur la maquette.
            etincelle = QRadialGradient(x + faite, y + ep / 2, ep * 3.5)
            etincelle.setColorAt(0.0, QColor(255, 232, 170, 220))
            etincelle.setColorAt(1.0, QColor(214, 167, 44, 0))
            p.setBrush(etincelle)
            p.drawEllipse(QRectF(x + faite - ep * 3.5, y + ep / 2 - ep * 3.5,
                                 ep * 7, ep * 7))

    def _peint_textes(self, p: QPainter) -> None:
        from src.ui.fonts import cinzel

        # État — capitales espacées, gris clair. Cinzel possède tous ces
        # caractères ; aucun pictogramme ici, volontairement.
        corps = max(8, int(self._h * _STATUT_CORPS))
        police = cinzel(corps)
        police.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 132)
        p.setFont(police)
        p.setPen(QColor(_TEXTE_2))
        zone = QRect(0, int(self._h * _STATUT_Y), self._w, corps * 2)
        p.drawText(zone, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   self._statut.upper())

        # Version — en bas à droite, discrète.
        petite = cinzel(max(7, int(corps * 0.72)))
        p.setFont(petite)
        p.setPen(QColor(_TEXTE_3))
        marge = int(self._w * _VERSION_MARGE)
        p.drawText(QRect(0, 0, self._w - marge, self._h - int(marge * 0.6)),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                   f"v{APP_VERSION}")

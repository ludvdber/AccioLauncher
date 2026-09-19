"""Boutons à pictogramme — commandes de la fenêtre, barre de bande-annonce, actions.

**Les pictogrammes sont de vrais dessins, plus des tracés maison** (2026-09-19).
Ludo : « le logo engrenage ou même discord sont dégueulasse, je veux pas du
fait maison je veux du vrai design ». Ils viennent de `assets/icons/`, sous
leur nom d'origine — mettre une icône à jour, c'est recopier celle du paquet :

· **Phosphor** (MIT) pour tout ce qui est à nous, en graisse **Bold** ; lecture
  et pause en version PLEINE, comme sur tout lecteur vidéo. Retenu sur planche
  contre Lucide et Tabler, rendus par ce même moteur, au repos, au survol et
  posés sur une vraie illustration. La graisse a été tranchée EN SITUATION, sur
  une illustration claire et à 125 % : la normale (trait de 1/16 de la boîte,
  1,1 px à 18 px) disparaissait dans la barre audio à côté d'une pause pleine,
  et paraissait maigre à côté du Clyde, qui est plein par nature.
· **Les logos OFFICIELS** pour les marques : le Clyde du kit de Discord, la
  tasse de Ko-fi (tracé publié par Simple Icons, relevé sur le kit de Ko-fi).
  Le Clyde tracé à la main avait demandé trois itérations et se lisait encore
  comme une tête d'ours : une marque se reproduit, elle ne se redessine pas.

**Discord ne se recolore pas** : ses règles l'interdisent, seuls le blanc, le
noir et son bleu « Blurple » sont permis. Il est donc blanc au repos et Blurple
au survol, jamais à l'or de la maison. Tout le reste suit l'accent du thème.

La couleur est posée PAR-DESSUS le rendu (`CompositionMode_SourceIn`) au lieu
de réécrire le SVG : un fichier Phosphor porte `currentColor`, celui de Simple
Icons rien du tout, et la teinte ne doit dépendre ni de l'un ni de l'autre.

Toujours valable, et vérifié par `tests/test_icon_button.py` : **aucun
pictogramme en caractère**. Le haut-parleur de la barre audio était l'emoji
U+1F50A, que Windows rendait bleu au milieu d'une interface or et blanche ; et
l'engrenage U+2699, pourtant `Emoji_Presentation=No`, sortait à 65 % en
couleur (mesuré le 2026-08-26). Une propriété Unicode dit ce que le caractère
demande, pas ce que la chaîne de repli de la plateforme lui donne.
"""

from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QAbstractButton, QWidget

from src.core.config import ASSETS_DIR
from src.ui import theme
from src.ui.focus_visible import PROPRIETE as _FOCUS_CLAVIER

_DOSSIER = ASSETS_DIR / "icons"

# Nom d'usage → fichier. La provenance se lit dans le chemin.
_FICHIERS = {
    "play": "phosphor/play-fill.svg",
    "pause": "phosphor/pause-fill.svg",
    "replay": "phosphor/arrow-counter-clockwise-bold.svg",
    "volume": "phosphor/speaker-high-bold.svg",
    "muet": "phosphor/speaker-x-bold.svg",
    "reglages": "phosphor/gear-six-bold.svg",
    "stats": "phosphor/chart-bar-bold.svg",
    "plein_ecran": "phosphor/corners-out-bold.svg",
    "quitter_plein_ecran": "phosphor/corners-in-bold.svg",
    "site": "phosphor/globe-bold.svg",
    "discord": "marques/Discord-Symbol-White.svg",
    "kofi": "marques/kofi.svg",
}
ICONES = tuple(_FICHIERS)

# Le second fichier officiel de Discord, et non une teinte : recolorer le blanc
# serait précisément ce que leurs règles interdisent.
_DISCORD_SURVOL = "marques/Discord-Symbol-Blurple.svg"
BLURPLE = QColor(0x58, 0x65, 0xF2)

# Un SVG Phosphor porte sa marge dans sa boîte (le globe va de 24 à 232 sur
# 256) ; un logo de marque, non, sa boîte colle à l'encre. Sans ce retrait,
# Clyde et la tasse paraîtraient d'un cran plus gros que leurs voisins.
_MARGE = {"discord": 0.10, "kofi": 0.10}

# Part du bouton occupée par la boîte du pictogramme : 24 px dans un galet de
# 36, 18 dans un bouton de 26 de la barre audio. Réglé à l'image, sur une
# vraie illustration et à 125 % — plus grand, le pictogramme mange son galet ;
# plus petit, le trait (3/32 de la boîte en Bold) passe sous le pixel et
# devient de la brume.
_PROPORTION = 0.68

_COULEUR = QColor(234, 234, 234)
_BLANC = QColor(255, 255, 255)


def _cadrage(boite: QRectF, taille: float, marge: float) -> QRectF:
    """La boîte du SVG posée dans un carré `taille`, proportions conservées."""
    utile = taille * (1.0 - 2.0 * marge)
    rapport = boite.width() / boite.height() if boite.height() else 1.0
    largeur, hauteur = ((utile, utile / rapport) if rapport >= 1.0
                        else (utile * rapport, utile))
    return QRectF((taille - largeur) / 2.0, (taille - hauteur) / 2.0, largeur, hauteur)


@lru_cache(maxsize=128)
def _dessin(fichier: str, marge: float, taille: int, ratio: float,
            teinte: int | None) -> QImage:
    """Le SVG rendu une fois pour toutes à cette taille, cette échelle, cette teinte.

    Mis en cache parce que la barre audio est posée SUR la bande-annonce : ses
    boutons sont repeints à chaque image de la vidéo, et re-parcourir un SVG
    trente fois par seconde pour trois pictogrammes identiques ne sert à rien.

    Une `QImage` et non une `QPixmap` : le cache vit aussi longtemps que le
    module, donc au-delà de la `QApplication`, et une `QImage` n'en dépend pas.
    """
    cote = max(1, round(taille * ratio))
    img = QImage(cote, cote, QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(ratio)
    img.fill(Qt.GlobalColor.transparent)

    rendu = QSvgRenderer(str(_DOSSIER / fichier))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rendu.render(p, _cadrage(rendu.viewBoxF(), cote / ratio, marge))
    if teinte is not None:
        # L'encre du SVG ne sert plus que de MASQUE : la couleur la remplace
        # en gardant son alpha, donc l'antialiasing est conservé tel quel.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(QRectF(0, 0, cote / ratio, cote / ratio), QColor.fromRgba(teinte))
    p.end()
    return img


def _image(icone: str, taille: int, couleur: QColor, ratio: float) -> QImage:
    marge = _MARGE.get(icone, 0.0)
    if icone == "discord":
        # Jamais teinté : l'un des deux fichiers officiels, tel quel.
        fichier = _DISCORD_SURVOL if couleur.rgb() == BLURPLE.rgb() else _FICHIERS[icone]
        return _dessin(fichier, marge, taille, ratio, None)
    return _dessin(_FICHIERS[icone], marge, taille, ratio, couleur.rgba())


class IconButton(QAbstractButton):
    """Bouton carré à pictogramme, accordé au thème.

    Survol : la couleur passe à l'accent de la maison et un disque très discret
    apparaît dessous — assez pour désigner la cible, pas assez pour faire une
    tache sur une bande-annonce.
    """

    def __init__(self, icone: str, taille: int = 26,
                 parent: QWidget | None = None, *,
                 cadre: str | None = None, galet: bool = False) -> None:
        """Trois habillages, selon ce qu'il y a derrière le bouton.

        `cadre` — couleur du contour, ou None pour un bouton nu. Encadré dans
        une rangée d'actions : à côté d'un DÉSINSTALLER de 160 × 36 en style
        « outline », un pictogramme sans cadre se détache de la rangée et
        paraît flotter. Le contour reprend la géométrie et les alphas de
        `GlowButton` outline (rayon 6, 1,5 px, 120 au repos, 180 au survol),
        pour que les deux boutons ne diffèrent que par leur contenu.

        `galet` — disque sombre PERMANENT sous le pictogramme, pour un bouton
        posé à même l'illustration ou la bande-annonce sans autre support :
        sans lui, un plan clair l'efface. Les boutons de la barre audio n'en
        ont pas besoin, `AudioBar` peint déjà le sien.

        Ni l'un ni l'autre — le bouton nu, sur un support qui le porte déjà.
        """
        super().__init__(parent)
        if icone not in ICONES:
            raise ValueError(f"icône inconnue : {icone!r}")
        self._icone = icone
        self._survol = False
        self._cadre = QColor(cadre) if cadre else None
        self._galet = galet
        self.setFixedSize(taille, taille)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def icone(self) -> str:
        return self._icone

    def set_icone(self, icone: str) -> None:
        if icone not in ICONES:
            raise ValueError(f"icône inconnue : {icone!r}")
        if icone != self._icone:
            self._icone = icone
            self.update()

    # ── Survol ──

    def enterEvent(self, event) -> None:
        self._survol = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._survol = False
        self.update()
        super().leaveEvent(event)

    # ── Peinture ──

    def _encre(self, actif: bool) -> QColor:
        if self._icone == "discord":
            return BLURPLE if actif else _BLANC
        if actif:
            return theme.accent_qcolor()
        if self._cadre is not None:
            # Encadré, le pictogramme prend la couleur de son cadre : c'est ce
            # que fait GlowButton en style outline (`text_color = glow_color`),
            # et deux boutons voisins de la même rangée ne doivent pas avoir
            # deux valeurs de gris différentes.
            return QColor(self._cadre)
        return _COULEUR

    def _halo(self, alpha: int) -> QColor:
        """Disque de survol : dans la couleur du pictogramme qu'il porte."""
        if self._icone == "discord":
            return QColor(BLURPLE.red(), BLURPLE.green(), BLURPLE.blue(), alpha)
        return theme.accent_qcolor(alpha)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        actif = self._survol or self.isDown()
        if self._galet:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 153 if actif else 102))
            p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

        if self._cadre is not None:
            cadre_rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 12) if self.isDown()
                       else QColor(self._cadre.red(), self._cadre.green(),
                                   self._cadre.blue(), 20) if self._survol
                       else QColor(255, 255, 255, 6))
            p.drawRoundedRect(cadre_rect, 6, 6)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(self._cadre.red(), self._cadre.green(),
                                 self._cadre.blue(), 180 if actif else 120), 1.5))
            p.drawRoundedRect(cadre_rect, 6, 6)
        elif actif:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._halo(30 if self._survol else 52))
            p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

        # L'anneau de focus reste réservé au CLAVIER (cf. focus_visible) : un
        # bouton peint n'est pas atteint par la règle `:focus` du stylesheet,
        # il doit donc le dessiner lui-même ou l'utilisateur au clavier perd
        # son seul repère.
        if self.property(_FOCUS_CLAVIER):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.accent_qcolor(210), 1.2))
            anneau = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            if self._cadre is not None:
                p.drawRoundedRect(anneau, 6, 6)
            else:
                p.drawEllipse(anneau)

        ratio = self.devicePixelRatioF()
        cote = round(min(self.width(), self.height()) * _PROPORTION)
        img = _image(self._icone, cote, self._encre(actif), ratio)
        # Origine calée sur la grille des pixels PHYSIQUES : posée sur un
        # demi-pixel, l'image serait rééchantillonnée, donc floue — à 125 %,
        # l'échelle de Ludo, un centrage logique tombe presque toujours entre
        # deux pixels.
        x = round((self.width() - cote) / 2.0 * ratio) / ratio
        y = round((self.height() - cote) / 2.0 * ratio) / ratio
        p.drawImage(QPointF(x, y), img)
        p.end()


def pixmap_icone(icone: str, taille: int,
                 couleur: QColor | None = None) -> QPixmap:
    """Le pictogramme SEUL, sur fond transparent — pour un `QPushButton`.

    Un bouton qui porte à la fois un pictogramme et un libellé n'est pas un
    `IconButton` : c'est un vrai bouton texte, et il lui faut une `QIcon`.

    Rendu à `devicePixelRatio` près : sur l'écran de Ludo (125 %) un pixmap à
    l'échelle 1 remonterait flou dans un bouton, ce qui se voit beaucoup plus
    qu'on ne le croit à 22 px. Le SVG est rendu DIRECTEMENT à la taille
    physique : aucun `scale` ne s'ajoute au `devicePixelRatio` (le double
    facteur rognait le tiers droit de chaque pictogramme à 125 %, cf.
    `tests/test_rendu_dpi.py`).

    Pour `discord`, la couleur ne s'applique pas : Blurple donne le logo
    Blurple, toute autre couleur le logo blanc — les deux seuls permis.
    """
    ecran = QGuiApplication.primaryScreen()
    ratio = ecran.devicePixelRatio() if ecran is not None else 1.0
    encre = QColor(couleur) if couleur is not None else QColor(_COULEUR)
    pm = QPixmap.fromImage(_image(icone, taille, encre, ratio))
    pm.setDevicePixelRatio(ratio)
    return pm

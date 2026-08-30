"""Boutons à pictogramme DESSINÉ — barre de bande-annonce, réglages, actions.

Pourquoi peindre plutôt qu'écrire un caractère : les boutons de la barre
étaient des glyphes posés dans des `QPushButton` — deux barres, un triangle, un
haut-parleur. Deux conséquences, toutes deux visibles à l'écran. D'abord le
haut-parleur est un EMOJI (U+1F50A) : Windows le rend en couleur via Segoe UI
Emoji, insensible au `setPen`, donc bleu au milieu d'une interface or et
blanche — c'est le piège déjà documenté dans CLAUDE.md, et il était ici depuis
le début. Ensuite un
glyphe dépend de la police qui finit par le servir : ni sa graisse, ni sa
taille optique, ni son centrage ne sont les nôtres, et rien ne garantit qu'ils
seront les mêmes d'un pictogramme à l'autre — d'où trois symboles qui ne
paraissaient pas de la même famille.

Dessinés, ils partagent une épaisseur de trait, une boîte et une couleur, ils
suivent l'accent du thème au survol, et ils restent nets à toutes les échelles
d'affichage (celle de Ludo est à 125 %).

**Le critère « pas de présentation emoji » ne suffit pas.** L'engrenage
U+2699 y répondait — `Emoji_Presentation=No` — et il partait quand même en
couleur : 65 % de pixels colorés, mesuré le 2026-08-26, contre 0 % pour une
lettre témoin et 21 % pour un vrai emoji. La propriété Unicode dit ce que le
CARACTÈRE demande ; la chaîne de repli de la plateforme fait ce qu'elle veut.
Vérifiés au rendu dans la foulée et RESTÉS monochromes : ◆ ✕ ✓ ❤ ❄ ↑ (0 %).
Le seul verdict qui vaille est une mesure, pas une table de propriétés.
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QAbstractButton, QWidget

from src.ui import theme
from src.ui.focus_visible import PROPRIETE as _FOCUS_CLAVIER

# Les tracés sont écrits dans une boîte de 24 × 24 puis mis à l'échelle du
# bouton : une seule géométrie à relire, quelle que soit la taille demandée.
_BOITE = 24.0
_TRAIT = 1.7
_COULEUR = QColor(234, 234, 234)


def _appliquer_encre(p: QPainter, couleur: QColor) -> None:
    """Pose le trait ET le remplissage d'un pictogramme.

    Les tracés se servent des deux — `play` est une forme pleine, `volume` un
    trait — et le réglage vit ici pour que le bouton (`paintEvent`) et le
    pixmap (`pixmap_icone`) ne puissent pas diverger : c'est la même famille de
    pictogrammes, une graisse ou un bout de trait changé d'un seul côté se
    verrait aussitôt dans une rangée qui mélange les deux.
    """
    stylo = QPen(couleur, _TRAIT)
    stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
    stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(stylo)
    p.setBrush(couleur)

ICONES = ("play", "pause", "replay", "volume", "muet", "reglages", "stats",
          "plein_ecran", "quitter_plein_ecran", "site", "discord", "kofi")


class IconButton(QAbstractButton):
    """Bouton carré au pictogramme peint, accordé au thème.

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
            p.setBrush(theme.accent_qcolor(30 if self._survol else 52))
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

        if actif:
            couleur = theme.accent_qcolor()
        elif self._cadre is not None:
            # Encadré, le pictogramme prend la couleur de son cadre : c'est ce
            # que fait GlowButton en style outline (`text_color = glow_color`),
            # et deux boutons voisins de la même rangée ne doivent pas avoir
            # deux valeurs de gris différentes.
            couleur = QColor(self._cadre)
        else:
            couleur = _COULEUR
        echelle = min(self.width(), self.height()) / _BOITE
        p.translate((self.width() - _BOITE * echelle) / 2.0,
                    (self.height() - _BOITE * echelle) / 2.0)
        p.scale(echelle, echelle)

        _appliquer_encre(p, couleur)
        getattr(self, "_peindre_" + self._icone)(p)
        p.end()

    # ── Tracés (boîte 24 × 24) ──

    @staticmethod
    def _peindre_play(p: QPainter) -> None:
        chemin = QPainterPath()
        chemin.moveTo(9.0, 5.6)
        chemin.lineTo(18.6, 12.0)
        chemin.lineTo(9.0, 18.4)
        chemin.closeSubpath()
        # Rempli ET tracé : le trait à bouts ronds arrondit les trois pointes,
        # qui piquent sinon dans une barre par ailleurs toute en courbes.
        p.drawPath(chemin)

    @staticmethod
    def _peindre_pause(p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(8.0, 6.0, 3.2, 12.0), 1.6, 1.6)
        p.drawRoundedRect(QRectF(12.8, 6.0, 3.2, 12.0), 1.6, 1.6)

    @staticmethod
    def _peindre_replay(p: QPainter) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        cercle = QRectF(5.4, 5.4, 13.2, 13.2)
        chemin = QPainterPath()
        # Ouverture en haut : c'est là que se pose la pointe, et une boucle
        # fermée ne dirait plus dans quel sens elle tourne.
        chemin.arcMoveTo(cercle, 62)
        chemin.arcTo(cercle, 62, -300)
        p.drawPath(chemin)

        # Pointe posée sur la TANGENTE de fin de course, calculée et non
        # devinée : un triangle placé à la main se voit tout de suite de
        # travers, et c'est ce qui rendait le pictogramme bancal.
        fin = chemin.pointAtPercent(1.0)
        angle = math.radians(chemin.angleAtPercent(1.0))
        dx, dy = math.cos(angle), -math.sin(angle)     # Qt : y vers le bas
        px, py = -dy, dx                               # perpendiculaire
        base = QPointF(fin.x() - dx * 1.1, fin.y() - dy * 1.1)
        pointe = QPainterPath()
        pointe.moveTo(base.x() + dx * 4.3, base.y() + dy * 4.3)
        pointe.lineTo(base.x() + px * 2.6, base.y() + py * 2.6)
        pointe.lineTo(base.x() - px * 2.6, base.y() - py * 2.6)
        pointe.closeSubpath()
        p.setBrush(p.pen().color())
        p.drawPath(pointe)

    @staticmethod
    def _corps_haut_parleur(p: QPainter) -> None:
        chemin = QPainterPath()
        chemin.moveTo(4.4, 9.4)
        chemin.lineTo(7.6, 9.4)
        chemin.lineTo(11.4, 5.6)
        chemin.lineTo(11.4, 18.4)
        chemin.lineTo(7.6, 14.6)
        chemin.lineTo(4.4, 14.6)
        chemin.closeSubpath()
        p.drawPath(chemin)

    @classmethod
    def _peindre_volume(cls, p: QPainter) -> None:
        cls._corps_haut_parleur(p)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for rayon in (4.2, 7.2) :
            arc = QRectF(11.0 - rayon, 12.0 - rayon, rayon * 2, rayon * 2)
            chemin = QPainterPath()
            chemin.arcMoveTo(arc, -50)
            chemin.arcTo(arc, -50, 100)
            p.drawPath(chemin)

    @staticmethod
    def _peindre_reglages(p: QPainter) -> None:
        """Roue dentée — remplaçante de U+2699.

        Ce caractère était réputé sûr : sa propriété Unicode est
        `Emoji_Presentation=No`, donc « repli monochrome, sensible au setPen ».
        C'était faux, et écrit sans jamais l'avoir rendu. Mesuré le 2026-08-26
        en peignant le glyphe dans une QImage en anti-crénelage NIVEAUX DE GRIS
        (sans quoi ClearType colore franchement TOUS les glyphes et la mesure ne
        vaut rien) : **65 % de pixels colorés**, contre 0 % pour une lettre
        ordinaire et 21 % pour U+1F50A, un vrai emoji pris comme témoin. Windows le
        sert donc en couleur, et plus franchement encore que l'emoji qui avait
        motivé ce fichier. La propriété Unicode dit ce que le caractère
        DEMANDE, pas ce que la chaîne de repli de la plateforme lui DONNE.

        Les dents sont posées par rotation autour du centre et non écrites une
        à une : à la main, la dernière ne retombe jamais sur la première.
        """
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx = cy = 12.0
        dents = 8
        r_creux, r_dent = 5.3, 8.0
        pas = 2 * math.pi / dents
        # Une dent occupe 40 % de la période au grand rayon, puis une rampe de
        # 10 %, puis 40 % au petit rayon, puis la rampe symétrique.
        profil = ((0.05, r_dent), (0.45, r_dent), (0.55, r_creux), (0.95, r_creux))

        chemin = QPainterPath()
        for i in range(dents):
            base = i * pas
            for fraction, rayon in profil:
                ang = base + fraction * pas
                pt = QPointF(cx + rayon * math.cos(ang), cy + rayon * math.sin(ang))
                if i == 0 and fraction == 0.05:
                    chemin.moveTo(pt)
                else:
                    chemin.lineTo(pt)
        chemin.closeSubpath()
        p.drawPath(chemin)

        # Moyeu : un simple cercle, tracé et non rempli — rempli, la roue
        # devient une pastille pleine dès qu'on descend sous 20 px.
        p.drawEllipse(QRectF(cx - 2.5, cy - 2.5, 5.0, 5.0))

    @staticmethod
    def _peindre_stats(p: QPainter) -> None:
        """Trois barres montantes — les statistiques de jeu.

        Barres PLEINES et non tracées, comme la pause : à 36 px un contour de
        1,7 px sur une barre de 3,4 de large laisse un filet d'un pixel au
        milieu, qui scintille dès que le bouton bouge d'un demi-pixel.

        Elles montent de gauche à droite plutôt que de dessiner un histogramme
        quelconque : c'est ce qui distingue un pictogramme de statistiques d'un
        pictogramme d'égaliseur, et le sens de lecture fait le reste.
        """
        p.setPen(Qt.PenStyle.NoPen)
        # Largeur 4,0 et non 3,4 : à graisse égale avec la roue d'à côté, avec
        # laquelle il partage la barre de titre — trois traits fins à côté d'un
        # engrenage plein faisaient deux familles.
        for x, haut in ((5.0, 13.6), (10.0, 9.4), (15.0, 5.6)):
            p.drawRoundedRect(QRectF(x, haut, 4.0, 19.0 - haut), 1.5, 1.5)

    @staticmethod
    def _peindre_site(p: QPainter) -> None:
        """Globe — le site du projet.

        Un cercle, l'équateur, un méridien : le globe canonique. La première
        version en avait DEUX, plus une corde horizontale traversante — quatre
        courbes qui se coupaient au centre, et le pictogramme se lisait comme
        un blason, pas comme une planète.

        Deux réglages tirés du rendu à l'image (2026-08-27), pas du tracé sur
        papier. **Le méridien fait 9 unités de large et non 7** : à 7 son
        intérieur est une fente, et le globe se lisait comme une amande. **Et
        le cercle occupe 18 unités sur 24 au lieu de 15,2** — c'est le seul
        pictogramme du jeu fait de trois courbes concentriques, donc celui qui
        se brouille le premier quand on le réduit, et il est justement servi
        à 16 px dans l'À propos. Lui rendre sa marge, c'est +18 % de diamètre
        là où ça compte.
        """
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(3.0, 3.0, 18.0, 18.0))          # le globe
        p.drawEllipse(QRectF(7.5, 3.0, 9.0, 18.0))           # le méridien
        p.drawLine(QPointF(3.4, 12.0), QPointF(20.6, 12.0))  # l'équateur

    @staticmethod
    def _peindre_discord(p: QPainter) -> None:
        """Silhouette de Clyde — reconnaissable au premier coup d'œil.

        Ludo, 2026-08-26 : « il y a pas de logo web ou discord dans le à propos
        donc c'est pas fou pour vite reconnaître sans lire ». Pour Discord seule
        la vraie forme fait le travail : un pictogramme générique (bulle,
        casque) ne dit pas « Discord ». Tracé à la main plutôt qu'importé,
        pour la même raison que tous les autres.

        **C'est le seul pictogramme PLEIN de la famille, et c'est délibéré.**
        La marque Discord est une silhouette pleine ; en contour elle ne dit
        plus rien — la première version, tracée au même stylo que les autres,
        se lisait comme une tête d'ours. On ne restyle pas la marque de
        quelqu'un d'autre pour l'accorder à son trait maison : on la reproduit.
        Les yeux sont PERCÉS (`OddEvenFill`) et non peints par-dessus, donc ils
        restent des trous quelle que soit la couleur du bouton ou du survol.

        Proportions relevées sur le tracé officiel (boîte 24 × 24), et non
        estimées — deux itérations s'y sont cassé les dents :

        · la forme est **plus large que haute** (20,8 × 15,5, soit 1,34) et
          s'évase vers le BAS : ses points les plus larges sont les pieds, pas
          les épaules. La version précédente arrondissait les coins bas et
          creusait une encoche au milieu — exactement l'inverse ;
        · **les yeux sont à 55 % de la hauteur**, pas en haut. Posés à 30 %
          comme au premier essai, la silhouette devient un casque ;
        · ils sont **gros** (4,1 × 4,6) et écartés d'une largeur d'œil.
        """
        corps = QPainterPath()
        corps.setFillRule(Qt.FillRule.OddEvenFill)
        corps.moveTo(12.0, 4.4)
        corps.cubicTo(15.2, 4.4, 17.6, 4.9, 19.4, 5.8)       # épaule droite
        corps.cubicTo(21.4, 9.0, 22.8, 13.6, 22.4, 18.6)     # flanc qui s'évase
        corps.cubicTo(22.3, 19.3, 21.9, 19.8, 21.2, 19.9)    # pointe du pied droit
        corps.cubicTo(18.6, 19.2, 15.4, 17.0, 12.0, 17.0)    # le bas remonte au centre
        corps.cubicTo(8.6, 17.0, 5.4, 19.2, 2.8, 19.9)
        corps.cubicTo(2.1, 19.8, 1.7, 19.3, 1.6, 18.6)       # pointe du pied gauche
        corps.cubicTo(1.2, 13.6, 2.6, 9.0, 4.6, 5.8)
        corps.cubicTo(6.4, 4.9, 8.8, 4.4, 12.0, 4.4)
        corps.closeSubpath()
        for cx in (8.2, 15.8):
            corps.addEllipse(QRectF(cx - 2.05, 10.5, 4.1, 4.6))

        encre = p.pen().color()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(encre)
        p.drawPath(corps)

    @staticmethod
    def _peindre_kofi(p: QPainter) -> None:
        """Tasse — le don Ko-fi.

        La tasse plutôt qu'un cœur : le cœur (U+2764) était déjà là en
        caractère, et il dit « j'aime » quand le bouton dit « offrir un café ».
        """
        p.setBrush(Qt.BrushStyle.NoBrush)
        tasse = QPainterPath()
        tasse.moveTo(4.6, 9.4)
        tasse.lineTo(15.4, 9.4)
        tasse.lineTo(15.4, 15.0)
        tasse.cubicTo(15.4, 17.8, 13.2, 19.4, 10.0, 19.4)
        tasse.cubicTo(6.8, 19.4, 4.6, 17.8, 4.6, 15.0)
        tasse.closeSubpath()
        p.drawPath(tasse)

        # Anse : deux tangentes HORIZONTALES aux points de jonction, sinon
        # elle repart en biais et la tasse gagne un coin pointu. Un demi-arc
        # d'ellipse ne marchait pas non plus — sa moitié gauche disparaît
        # derrière la tasse et il n'en dépassait qu'une pointe.
        anse = QPainterPath()
        anse.moveTo(15.4, 10.6)
        anse.cubicTo(19.9, 10.6, 19.9, 15.8, 15.4, 15.8)
        p.drawPath(anse)

        # Deux volutes de vapeur — sans elles la tasse se lit comme un seau.
        for x in (8.0, 11.6):
            vapeur = QPainterPath()
            vapeur.moveTo(x, 7.2)
            vapeur.cubicTo(x + 1.5, 5.8, x - 1.5, 5.0, x, 3.6)
            p.drawPath(vapeur)

    @staticmethod
    def _peindre_plein_ecran(p: QPainter) -> None:
        """Quatre équerres tournées vers l'extérieur."""
        p.setBrush(Qt.BrushStyle.NoBrush)
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x, y = 12.0 + sx * 7.2, 12.0 + sy * 7.2
            chemin = QPainterPath()
            chemin.moveTo(x - sx * 4.4, y)
            chemin.lineTo(x, y)
            chemin.lineTo(x, y - sy * 4.4)
            p.drawPath(chemin)

    @staticmethod
    def _peindre_quitter_plein_ecran(p: QPainter) -> None:
        """Les mêmes équerres, tournées vers l'intérieur."""
        p.setBrush(Qt.BrushStyle.NoBrush)
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x, y = 12.0 + sx * 3.0, 12.0 + sy * 3.0
            chemin = QPainterPath()
            chemin.moveTo(x + sx * 4.4, y)
            chemin.lineTo(x, y)
            chemin.lineTo(x, y + sy * 4.4)
            p.drawPath(chemin)

    @classmethod
    def _peindre_muet(cls, p: QPainter) -> None:
        cls._corps_haut_parleur(p)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Une croix plutôt qu'une barre en travers : la barre traverse le corps
        # du haut-parleur et le rend illisible à 26 px.
        p.drawLine(QPointF(14.6, 9.2), QPointF(20.0, 14.6))
        p.drawLine(QPointF(20.0, 9.2), QPointF(14.6, 14.6))


def pixmap_icone(icone: str, taille: int,
                 couleur: QColor | None = None) -> QPixmap:
    """Le pictogramme SEUL, sur fond transparent — pour un `QPushButton`.

    Un bouton qui porte à la fois un pictogramme et un libellé n'est pas un
    `IconButton` : c'est un vrai bouton texte, et il lui faut une `QIcon`. Sans
    ce passage, les seuls pictogrammes disponibles ailleurs seraient à nouveau
    des caractères — c'est-à-dire le défaut que tout ce fichier corrige.

    Le rendu se fait à `devicePixelRatio` près : sur l'écran de Ludo (125 %) un
    pixmap à l'échelle 1 remonterait flou dans un bouton, ce qui se voit
    beaucoup plus qu'on ne le croit à 18 px.

    **Ne PAS remettre un `p.scale(ratio, ratio)` ici.** Il y en avait un, et il
    rognait le pictogramme : un `QPainter` ouvert sur un `QPixmap` qui porte un
    `devicePixelRatio` applique DÉJÀ ce facteur, ses coordonnées étant logiques.
    L'échelle valait donc ratio² — 1,25 × 1,25 × 22/24 = 1,80 au lieu de 1,15 —
    et la boîte de 24 sortait à 43 px physiques dans un pixmap de 27 : le globe
    perdait sa moitié droite, Clyde un œil, la tasse son anse (mesuré le
    2026-08-30, l'encre atteignait le DERNIER pixel du pixmap au lieu de
    s'arrêter deux pixels avant).

    Le défaut ne pouvait pas se voir en test : à `devicePixelRatio` 1 — la suite
    offscreen, et tout écran non mis à l'échelle — `p.scale(1, 1)` ne fait rien.
    Il ne se manifestait que sur un écran à échelle fractionnaire, c'est-à-dire
    uniquement chez l'utilisateur. Même angle mort que le trait clair du
    carrousel (`tests/test_rendu_dpi.py`), et même remède : le vérifier dans un
    sous-processus qui force l'échelle.

    `round` et non `int` : `int(22 × 1,25)` rend 27 pour 27,5 attendus, soit un
    demi-pixel de tracé perdu sur le bord.
    """
    ecran = QGuiApplication.primaryScreen()
    ratio = ecran.devicePixelRatio() if ecran is not None else 1.0
    pm = QPixmap(round(taille * ratio), round(taille * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    encre = QColor(couleur) if couleur is not None else QColor(_COULEUR)
    p.scale(taille / _BOITE, taille / _BOITE)
    _appliquer_encre(p, encre)
    getattr(IconButton, "_peindre_" + icone)(p)
    p.end()
    return pm

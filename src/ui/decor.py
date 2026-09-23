"""Le décor de l'Almanach — une silhouette dans le coin, selon la saison.

Ludo, 2026-09-23 : « en l'état tu as juste changé les particules, je
m'attendais à plus, genre le Poudlard Express dans un coin, des citrouilles
Halloween ». Il a raison : des particules habillent l'air, elles ne racontent
rien. Une silhouette, si.

**Trois contraintes tiennent tout ce module.**

① **C'est PEINT, jamais un fichier livré.** Règle du projet, et trois raisons qui
tiennent toujours : le poids de l'exe (on a retiré un PNG de 1,27 Mo affiché
en 64×64), l'échelle fractionnaire (une image posée à coordonnées entières
rate le bord à 125 %, payé trois fois ici), et le thème — une silhouette
peinte prend l'accent de la maison, une image reste de la couleur qu'elle a.
Des assets CC0 existent (Kenney, OpenGameArt) ; ils n'auraient rien réglé de
tout ça.

② **Ça se pose dans un COIN et ça reste discret.** Le décor est peint SOUS les
particules, en bas à droite, à une opacité qui le laisse lire comme une ombre
portée sur l'illustration du jeu. Il dresse le CADRE, il ne couvre pas le
contenu : la moitié gauche de la fenêtre porte le titre, la description et les
boutons, et rien n'a le droit d'aller s'y poser.

③ **La silhouette est rendue UNE fois dans une `QImage`, puis blittée.**
`paintEvent` de l'overlay tourne à chaque image : y retracer les courbes
coûtait, mesuré à 1270×844, 137 ms/s pour Halloween contre 58 sans décor.
Avec l'image en cache : 73. Un décor STATIQUE ne se paie pas au prix d'une
animation.
"""

import math

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath

from src.ui import theme

# Taille du décor, en fraction de la LARGEUR de la fenêtre, bornée. Une taille
# fixe en pixels serait minuscule sur un 1440p et envahissante à 980×660 —
# c'est le défaut `THUMB_H` / `CAROUSEL_HEIGHT`, appliqué à un ornement.
_PART_LARGEUR = 0.16
_LARGEUR_MIN, _LARGEUR_MAX = 120, 230
_RAPPORT = 0.72                 # hauteur / largeur
# Marge au bord de la fenêtre, et hauteur réservée en bas (carrousel + barre
# de statut) : le décor se pose AU-DESSUS, jamais par-dessus les vignettes.
_MARGE = 26
_BAS_RESERVE = 196

_OPACITE = 0.20
# L'ombre est plus marquée que l'or : c'est elle qui porte le contraste
# sur une illustration claire, où l'or seul disparaît.
_OPACITE_OMBRE = 0.26
_DECALAGE_OMBRE = 2

# Cle : (saison, largeur, hauteur, accent). L'accent en fait partie
# parce qu'un changement de theme doit rendre une autre image — les
# tests changent de maison, meme si l'application demande un redemarrage.
_cache: dict[tuple[str, int, int, tuple[int, int, int]], QImage] = {}


def zone(largeur_fenetre: int, hauteur_fenetre: int) -> QRect:
    """Le rectangle du décor : en bas à droite, au-dessus du carrousel.

    **Non borné volontairement.** Une première version ramenait le haut à
    `_MARGE` par un `max()`, et ce `max()` rendait le garde-fou de `peindre`
    INOPÉRANT : sur une fenêtre trop courte, le rectangle était ramené dans le
    cadre au lieu d'en sortir, donc la condition « ça ne tient pas » n'était
    jamais vraie et le décor se posait sur le carrousel. Trouvé par son propre
    test. Ici on rend la position VRAIE ; c'est l'appelant qui décide quoi
    faire quand elle ne tient pas.
    """
    largeur = int(max(_LARGEUR_MIN,
                      min(_LARGEUR_MAX, largeur_fenetre * _PART_LARGEUR)))
    hauteur = int(largeur * _RAPPORT)
    return QRect(largeur_fenetre - largeur - _MARGE,
                 hauteur_fenetre - _BAS_RESERVE - hauteur, largeur, hauteur)


def peindre(p: QPainter, saison: str, largeur: int, hauteur: int) -> None:
    """Pose le décor de la saison, s'il y en a un.

    Ne fait RIEN si la fenêtre est trop courte pour que le décor tienne
    au-dessus du carrousel : mieux vaut pas de décor qu'un décor qui chevauche
    les vignettes. C'est le cas à 980×660, la taille minimale.
    """
    tracer = _TRACES.get(saison)
    if tracer is None:
        return
    rect = zone(largeur, hauteur)
    # Fenêtre trop courte pour que le décor tienne au-dessus du carrousel :
    # mieux vaut pas de décor qu'un décor posé sur les vignettes. C'est le cas
    # à 980×660, la taille minimale.
    if rect.top() < _MARGE or rect.height() < 60:
        return

    accent = theme.current().accent_rgb
    cle = (saison, rect.width(), rect.height(), accent)
    image = _cache.get(cle)
    if image is None:
        image = _rendre(tracer, rect.width(), rect.height(), accent)
        _cache[cle] = image
    p.drawImage(rect.topLeft(), image)


def _rendre(tracer, largeur: int, hauteur: int,
            accent: tuple[int, int, int]) -> QImage:
    """Peint la silhouette UNE fois dans une image, opacités comprises.

    **Mesuré avant de décider.** Peindre les deux passes de `QPainterPath` à
    chaque image coûtait, sur l'overlay complet à 1270×844 : Halloween 137 ms/s
    contre 58 sans décor, Noël 84 contre 60. La citrouille est le pire cas —
    cinq lobes unis, un visage soustrait, le tout tracé deux fois. Une image
    déjà composée se blitte ; le tracé, lui, se recalcule.

    `QImage` et non `QPixmap`, pour la même raison que `icon_button` : une
    `QImage` survit sans `QApplication`, ce qu'une `QPixmap` globale ne
    garantit pas.

    **DEUX passes, et c'est ce qui rend le décor lisible sur les huit jeux.**
    Une seule passe dorée a été essayée, rendue, et REGARDÉE sur une vraie
    illustration : sur le fond clair et verdâtre de HP5, l'or à 20 % ne se
    lisait plus comme une silhouette mais comme une salissure posée sur le
    visage d'un personnage. Sur les fonds sombres, il allait très bien. Un
    ornement ne peut pas dépendre de la clarté de l'image qu'il habille.
    L'ombre portée donne le contraste sur les fonds CLAIRS, l'or sur les fonds
    SOMBRES ; ensemble ils tiennent partout. C'est le procédé ordinaire du
    filigrane, il n'y avait pas de raison de le réinventer.
    """
    # La marge accueille le décalage de l'ombre sans rogner la silhouette.
    image = QImage(largeur + _DECALAGE_OMBRE, hauteur + _DECALAGE_OMBRE,
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    chemin = tracer(QRectF(0, 0, largeur, hauteur))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setOpacity(_OPACITE_OMBRE)
    p.setBrush(QColor(0, 0, 0))
    p.translate(_DECALAGE_OMBRE, _DECALAGE_OMBRE)
    p.drawPath(chemin)
    p.translate(-_DECALAGE_OMBRE, -_DECALAGE_OMBRE)
    p.setOpacity(_OPACITE)
    p.setBrush(QColor(*accent))
    p.drawPath(chemin)
    p.end()
    return image


# ── Les cinq silhouettes ─────────────────────────────────────────────────
# Chacune est tracée dans un rectangle de (0,0,la,h) et mise à l'échelle par
# le rectangle qu'on lui passe : aucune constante en pixels ici.


def _poudlard_express(r: QRectF) -> QPainterPath:
    """Une locomotive de profil, tournée vers la gauche, sur ses rails.

    Pas de détail inutile : à 150 px de large, une chaudière, une cabine, une
    cheminée, trois roues et trois bouffées de vapeur suffisent à ce qu'on
    reconnaisse un train. Un tracé plus fin ne se verrait pas et coûterait à
    peindre.
    """
    la, h = r.width(), r.height()
    chemin = QPainterPath()
    base = h * 0.80                                     # hauteur des rails
    # Chaudière (cylindre) + cabine (bloc plus haut, à droite)
    chemin.addRoundedRect(QRectF(la * 0.06, h * 0.46, la * 0.52, h * 0.24),
                          h * 0.06, h * 0.06)
    chemin.addRoundedRect(QRectF(la * 0.56, h * 0.30, la * 0.30, h * 0.40),
                          h * 0.05, h * 0.05)
    # Toit de cabine, débordant des deux côtés
    chemin.addRect(QRectF(la * 0.52, h * 0.26, la * 0.38, h * 0.06))
    # Cheminée, évasée vers le haut
    cheminee = QPainterPath()
    cheminee.moveTo(la * 0.11, h * 0.46)
    cheminee.lineTo(la * 0.14, h * 0.26)
    cheminee.lineTo(la * 0.24, h * 0.26)
    cheminee.lineTo(la * 0.24, h * 0.22)
    cheminee.lineTo(la * 0.09, h * 0.22)
    cheminee.lineTo(la * 0.09, h * 0.26)
    cheminee.lineTo(la * 0.05, h * 0.46)
    cheminee.closeSubpath()
    chemin.addPath(cheminee)
    # Roues : deux petites sous la chaudière, une grande sous la cabine
    for cx, rayon in ((0.18, 0.055), (0.34, 0.055), (0.66, 0.085)):
        c = QPointF(la * cx, base - h * rayon)
        chemin.addEllipse(c, la * rayon, la * rayon)
    # Rails
    chemin.addRect(QRectF(0.0, base, la, h * 0.035))
    # Vapeur : trois bouffées qui montent en s'élargissant. La dernière
    # débordait de 5 px au-dessus de la boîte (mesuré) — une silhouette
    # qui sort de son cadre salit ce qu'il y a autour.
    for i, (dx, dy, rayon) in enumerate(
            ((0.20, 0.185, 0.045), (0.31, 0.140, 0.060),
             (0.45, 0.100, 0.075))):
        chemin.addEllipse(QPointF(la * dx, h * dy), la * rayon, la * rayon * 0.78)
    return chemin.simplified()


def _citrouilles(r: QRectF) -> QPainterPath:
    """Une citrouille taillée, et une plus petite derrière.

    **Premier essai jeté après l'avoir REGARDÉ** : trois ellipses empilées et
    un visage soustrait donnaient une masse ronde barrée d'un trait vertical,
    que personne n'aurait appelée une citrouille. Deux corrections. ① Les côtes
    se voient par la DIFFÉRENCE de largeur des lobes, pas par leur nombre :
    cinq ellipses de rayons décroissants du centre vers les bords. ② Le visage
    est fait de polygones FERMÉS et anguleux, soustraits d'un coup — un tracé
    en zigzag refermé sur lui-même produit une forme que Qt remplit de travers.

    Les découpes sont RETIRÉES du tracé (`subtracted`) et non peintes par-
    dessus : le décor est monochrome à l'accent du thème, donc une découpe
    peinte en fond serait de la mauvaise couleur chez Serpentard.
    """
    la, h = r.width(), r.height()

    def corps(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
        """Cinq lobes : le central le plus large, les extrêmes les plus étroits."""
        forme = QPainterPath()
        for decalage, largeur in ((0.0, 1.00), (-0.42, 0.74), (0.42, 0.74),
                                  (-0.72, 0.46), (0.72, 0.46)):
            forme.addEllipse(QPointF(cx + rx * decalage, cy),
                             rx * largeur, ry)
        return forme.simplified()

    def triangle(*points) -> QPainterPath:
        tri = QPainterPath()
        tri.moveTo(*points[0])
        for pt in points[1:]:
            tri.lineTo(*pt)
        tri.closeSubpath()
        return tri

    chemin = QPainterPath()

    # ── La petite, en retrait à gauche : pas de visage, elle fait la masse ──
    pcx, pcy = la * 0.20, h * 0.74
    prx, pry = la * 0.145, h * 0.175
    petite = corps(pcx, pcy, prx, pry)
    petite.addRect(QRectF(pcx - prx * 0.08, pcy - pry * 1.45,
                          prx * 0.16, pry * 0.50))
    chemin.addPath(petite)

    # ── La grande, taillée ──
    cx, cy = la * 0.60, h * 0.60
    rx, ry = la * 0.285, h * 0.305
    grande = corps(cx, cy, rx, ry)

    visage = QPainterPath()
    for signe in (-1, 1):
        visage.addPath(triangle(
            (cx + signe * rx * 0.50, cy - ry * 0.42),
            (cx + signe * rx * 0.16, cy - ry * 0.08),
            (cx + signe * rx * 0.66, cy - ry * 0.02)))
    visage.addPath(triangle(                       # nez
        (cx, cy - ry * 0.02),
        (cx - rx * 0.13, cy + ry * 0.22),
        (cx + rx * 0.13, cy + ry * 0.22)))
    # Bouche : un bandeau, moins deux dents. Deux polygones explicites, pas
    # une ligne brisée refermée — c'est ce qui clochait au premier essai.
    bouche = QPainterPath()
    bouche.addRect(QRectF(cx - rx * 0.62, cy + ry * 0.36,
                          rx * 1.24, ry * 0.26))
    for decalage in (-0.26, 0.26):
        bouche = bouche.subtracted(triangle(
            (cx + rx * decalage - rx * 0.13, cy + ry * 0.36),
            (cx + rx * decalage + rx * 0.13, cy + ry * 0.36),
            (cx + rx * decalage, cy + ry * 0.62)))
    visage.addPath(bouche)
    grande = grande.subtracted(visage)

    # Queue, ajoutée APRÈS la découpe : elle ne se fait pas tailler.
    queue = QPainterPath()
    queue.moveTo(cx - rx * 0.09, cy - ry * 0.98)
    queue.lineTo(cx - rx * 0.05, cy - ry * 1.42)
    queue.lineTo(cx + rx * 0.16, cy - ry * 1.36)
    queue.lineTo(cx + rx * 0.09, cy - ry * 0.98)
    queue.closeSubpath()
    grande.addPath(queue)
    chemin.addPath(grande)
    return chemin


def _sapin(r: QRectF) -> QPainterPath:
    """Un sapin à trois étages, son étoile, et une congère au pied."""
    la, h = r.width(), r.height()
    chemin = QPainterPath()
    cx = la * 0.52
    for i, (sommet, base, demi) in enumerate(
            ((0.18, 0.42, 0.17), (0.34, 0.60, 0.24), (0.50, 0.80, 0.31))):
        etage = QPainterPath()
        etage.moveTo(cx, h * sommet)
        etage.lineTo(cx - la * demi, h * base)
        etage.lineTo(cx + la * demi, h * base)
        etage.closeSubpath()
        chemin.addPath(etage)
    chemin.addRect(QRectF(cx - la * 0.045, h * 0.78, la * 0.09, h * 0.10))
    # Étoile à cinq branches
    etoile = QPainterPath()
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        rayon = la * (0.075 if i % 2 == 0 else 0.032)
        pt = QPointF(cx + math.cos(angle) * rayon, h * 0.15 - math.sin(angle) * rayon)
        etoile.moveTo(pt) if i == 0 else etoile.lineTo(pt)
    etoile.closeSubpath()
    chemin.addPath(etoile)
    # Congère
    congere = QPainterPath()
    congere.moveTo(0.0, h)
    congere.quadTo(la * 0.30, h * 0.84, la * 0.62, h * 0.93)
    congere.quadTo(la * 0.82, h * 0.99, la, h * 0.90)
    congere.lineTo(la, h)
    congere.closeSubpath()
    chemin.addPath(congere)
    return chemin.simplified()


def _gateau(r: QRectF) -> QPainterPath:
    """Un gâteau à deux étages et ses bougies — « un peu écrasé », comme
    celui que Hagrid apporte pour les onze ans de Harry."""
    la, h = r.width(), r.height()
    chemin = QPainterPath()
    chemin.addRoundedRect(QRectF(la * 0.14, h * 0.60, la * 0.72, h * 0.28),
                          h * 0.05, h * 0.05)
    chemin.addRoundedRect(QRectF(la * 0.24, h * 0.42, la * 0.52, h * 0.20),
                          h * 0.05, h * 0.05)
    # Glaçage : une coulure au bord de l'étage du haut
    coulure = QPainterPath()
    coulure.moveTo(la * 0.24, h * 0.46)
    for i in range(5):
        x = la * (0.24 + 0.52 * i / 4)
        coulure.quadTo(x + la * 0.065, h * 0.56, x + la * 0.13, h * 0.46)
    coulure.lineTo(la * 0.76, h * 0.42)
    coulure.lineTo(la * 0.24, h * 0.42)
    coulure.closeSubpath()
    chemin.addPath(coulure)
    # Trois bougies, avec leur flamme
    for cx in (0.35, 0.50, 0.65):
        chemin.addRect(QRectF(la * cx - la * 0.018, h * 0.24, la * 0.036, h * 0.18))
        flamme = QPainterPath()
        flamme.moveTo(la * cx, h * 0.12)
        flamme.quadTo(la * cx + la * 0.032, h * 0.20, la * cx, h * 0.24)
        flamme.quadTo(la * cx - la * 0.032, h * 0.20, la * cx, h * 0.12)
        chemin.addPath(flamme)
    # Assiette
    chemin.addRoundedRect(QRectF(la * 0.06, h * 0.88, la * 0.88, h * 0.055),
                          h * 0.025, h * 0.025)
    return chemin.simplified()


def _baguette_brisee(r: QRectF) -> QPainterPath:
    """Une baguette brisée en deux, et quelques éclats.

    **La tour en ruine du premier essai a été jetée** : à 150 px, elle se
    lisait comme une maison, pas comme une tour, et encore moins comme une
    ruine. Une baguette cassée, elle, se reconnaît à sa silhouette seule — et
    c'est le geste par lequel la bataille se termine.

    Sobre, et c'est voulu : le 2 mai est une commémoration. Rien n'y brille,
    rien n'y sourit ; c'est la seule silhouette de la série qui soit posée de
    travers, et la seule qui soit en deux morceaux.
    """
    la, h = r.width(), r.height()

    def segment(x0: float, y0: float, x1: float, y1: float,
                ep0: float, ep1: float) -> QPainterPath:
        """Un tronçon fuselé : épais en (x0,y0), fin en (x1,y1)."""
        dx, dy = x1 - x0, y1 - y0
        longueur = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        nx, ny = -dy / longueur, dx / longueur      # normale unitaire
        forme = QPainterPath()
        forme.moveTo(x0 + nx * ep0, y0 + ny * ep0)
        forme.lineTo(x1 + nx * ep1, y1 + ny * ep1)
        forme.lineTo(x1 - nx * ep1, y1 - ny * ep1)
        forme.lineTo(x0 - nx * ep0, y0 - ny * ep0)
        forme.closeSubpath()
        return forme

    chemin = QPainterPath()
    ep = h * 0.045                       # demi-épaisseur au manche

    # Morceau du manche, en bas à gauche, avec son pommeau.
    chemin.addPath(segment(la * 0.10, h * 0.74, la * 0.46, h * 0.44,
                           ep, ep * 0.55))
    chemin.addEllipse(QPointF(la * 0.10, h * 0.74), ep * 1.7, ep * 1.7)
    # Deux bagues sur le manche : ce qui fait lire « baguette » et non
    # « branche ».
    for t in (0.22, 0.34):
        cx = la * (0.10 + (0.46 - 0.10) * t)
        cy = h * (0.74 + (0.44 - 0.74) * t)
        chemin.addPath(segment(cx, cy, cx + la * 0.028, cy - h * 0.023,
                               ep * 1.45, ep * 1.45))

    # Morceau de la pointe, décalé et pivoté : la cassure se voit à l'ANGLE,
    # pas seulement à l'écart.
    chemin.addPath(segment(la * 0.56, h * 0.50, la * 0.90, h * 0.30,
                           ep * 0.52, ep * 0.16))

    # Éclats, entre les deux morceaux.
    for x, y, taille in ((0.49, 0.40, 0.020), (0.53, 0.58, 0.014),
                         (0.45, 0.60, 0.011)):
        eclat = QPainterPath()
        eclat.moveTo(la * x, h * y)
        eclat.lineTo(la * (x + taille * 1.8), h * (y - taille * 1.2))
        eclat.lineTo(la * (x + taille * 0.9), h * (y + taille * 1.6))
        eclat.closeSubpath()
        chemin.addPath(eclat)

    # Le sol, comme pour les autres silhouettes : elles se posent toutes sur
    # la même ligne, sinon l'une a l'air de flotter.
    chemin.addRect(QRectF(0.0, h * 0.93, la, h * 0.035))
    return chemin.simplified()


_TRACES = {
    "rentree": _poudlard_express,
    "halloween": _citrouilles,
    "noel": _sapin,
    "anniversaire": _gateau,
    "bataille": _baguette_brisee,
}


def vider_cache() -> None:
    """Oublie les images rendues — utile aux tests et aux mesures."""
    _cache.clear()

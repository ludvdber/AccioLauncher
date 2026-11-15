"""Mesurer un rendu à l'image (audit UI f20) : un widget peint sur du noir, son fond exclu.

Une feuille de style peut dire vrai et l'écran montrer autre chose : ces aides lisent les pixels.
"""
from collections import Counter

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QColor, QImage, QRegion


def sur_noir(widget) -> QImage:
    """Le widget peint sur une image noire, à l'échelle 1, sans le fond de sa fenêtre."""
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0))
    widget.render(image, QPoint(0, 0), QRegion(QRect(QPoint(0, 0), widget.size())),
                  widget.RenderFlag.DrawChildren)
    return image


def encre(widget) -> QColor:
    """La couleur la plus claire peinte : celle du texte, sur un libellé sans fond."""
    image = sur_noir(widget)
    meilleure, lum = QColor(0, 0, 0), -1
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            v = c.red() * 299 + c.green() * 587 + c.blue() * 114
            if v > lum:
                meilleure, lum = c, v
    return meilleure


def cadre_de_l_encre(widget, seuil: int = 40) -> QRect:
    """Le rectangle des pixels qui s'écartent de plus de `seuil` (sur un canal) de la couleur
    la plus fréquente : le noir autour d'un rond, le fond peint d'un bouton."""
    image = sur_noir(widget)
    comptes = Counter(image.pixel(x, y) for y in range(image.height()) for x in range(image.width()))
    fond = QColor.fromRgba(comptes.most_common(1)[0][0])
    xs, ys = [], []
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if max(abs(c.red() - fond.red()), abs(c.green() - fond.green()), abs(c.blue() - fond.blue())) > seuil:
                xs.append(x)
                ys.append(y)
    if not xs:
        return QRect()
    return QRect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def cadre_du_texte(bouton) -> QRect:
    """Où le texte d'un bouton est peint : les pixels qui changent quand on le retire (le
    fond, le cadre et le dégradé du style restent les mêmes et s'annulent)."""
    avec = sur_noir(bouton)
    texte = bouton.text()
    bouton.setText("")
    try:
        sans = sur_noir(bouton)
    finally:
        bouton.setText(texte)
    xs = [x for y in range(avec.height()) for x in range(avec.width()) if avec.pixel(x, y) != sans.pixel(x, y)]
    ys = [y for y in range(avec.height()) for x in range(avec.width()) if avec.pixel(x, y) != sans.pixel(x, y)]
    if not xs:
        return QRect()
    return QRect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def proche(a: QColor, b: QColor, ecart: int = 24) -> bool:
    return max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) <= ecart

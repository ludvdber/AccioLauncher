"""Des jaquettes qui ne sont pas faites pour le launcher : jamais étirées. Trop
loin du portrait 18:25 de la vignette (HP2, les Reliques, carrées), la
jaquette est posée entière, centrée, entre deux aplats assombris de la couleur
de ses propres bords.
"""

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from src.core.images_a_refaire import ECART_PROPORTIONS

# Part de la couleur du bord gardée dans l'aplat (ACC15, planche du 2026-11-09).
_ASSOMBRI = 0.55


def _aplat(image: QImage, bord: QRect) -> QColor:
    """La couleur moyenne d'une bande de bord, assombrie."""
    moyenne = image.copy(bord).scaled(1, 1, Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation).pixelColor(0, 0)
    return QColor(int(moyenne.red() * _ASSOMBRI), int(moyenne.green() * _ASSOMBRI),
                  int(moyenne.blue() * _ASSOMBRI))


def jaquette(image: QImage, largeur: int, hauteur: int) -> QImage:
    """La jaquette aux proportions de la vignette, sans jamais la déformer.

    Proportions proches : recadrée au centre, comme avant. Trop éloignées
    (une jaquette carrée) : posée entière entre deux aplats tirés de ses bords.
    """
    cible = QSize(largeur, hauteur)
    rapport_cible = largeur / hauteur
    rapport = image.width() / max(1, image.height())
    pleine = image.scaled(cible, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    recadree = pleine.copy((pleine.width() - largeur) // 2, (pleine.height() - hauteur) // 2,
                           largeur, hauteur)
    if abs(rapport - rapport_cible) / rapport_cible <= ECART_PROPORTIONS:
        return recadree
    resultat = QImage(cible, QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(resultat)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    entiere = image.scaled(cible, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    large, h = entiere.width(), entiere.height()
    if rapport > rapport_cible:  # Plus large que la vignette : bandes en haut et en bas.
        bande = max(1, h // 40)
        premier, second = QRect(0, 0, large, bande), QRect(0, h - bande, large, bande)
        moitie = QRect(0, 0, largeur, hauteur // 2)
    else:                        # Plus étroite : bandes à gauche et à droite.
        bande = max(1, large // 40)
        premier, second = QRect(0, 0, bande, h), QRect(large - bande, 0, bande, h)
        moitie = QRect(0, 0, largeur // 2, hauteur)
    p.fillRect(resultat.rect(), _aplat(entiere, second))
    p.fillRect(moitie, _aplat(entiere, premier))
    p.drawImage(QRectF((largeur - entiere.width()) / 2, (hauteur - entiere.height()) / 2,
                       entiere.width(), entiere.height()), entiere)
    p.end()
    return resultat

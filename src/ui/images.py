"""Rendre au mieux des jaquettes qui ne sont pas faites pour le launcher (2026-10-09).

**Les jaquettes carrées** (HP2, les deux parties des Reliques) : la vignette
du carrousel est en portrait 18:25, et la jaquette y était ÉTIRÉE
(`drawPixmap` dans un rectangle d'autres proportions), visages allongés
compris. Elle est désormais posée entière, centrée, sur un fond tiré
d'elle-même, flouté et assombri : l'illustration garde ses proportions et la
vignette reste pleine.

Les fonds trop petits (HP3, HP4, HP5), eux, n'ont pas de remède ici : un flou
avant agrandissement a été essayé (avant/après du 2026-10-09) et rendait
l'image plus floue sans rien gagner. Le vrai remède est une illustration
faite pour le launcher : `src/core/images_a_refaire.py` et l'appel aux
artistes d'À propos.
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from src.core.images_a_refaire import ECART_PROPORTIONS

def _flou(image: QImage, force: int) -> QImage:
    """Flou par réduction puis agrandissement lissés : rapide, sans effet graphique."""
    petite = image.scaled(max(1, image.width() // force), max(1, image.height() // force),
                          Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    return petite.scaled(image.width(), image.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


def jaquette(image: QImage, largeur: int, hauteur: int) -> QImage:
    """La jaquette aux proportions de la vignette, sans jamais la déformer.

    Proportions proches : recadrée au centre, comme avant. Trop éloignées
    (une jaquette carrée) : posée entière sur un fond flouté tiré d'elle-même.
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
    p.drawImage(0, 0, _flou(recadree, 12))
    p.fillRect(resultat.rect(), QColor(0, 0, 0, 120))
    entiere = image.scaled(cible, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    p.drawImage(QRectF((largeur - entiere.width()) / 2, (hauteur - entiere.height()) / 2,
                       entiere.width(), entiere.height()), entiere)
    p.end()
    return resultat

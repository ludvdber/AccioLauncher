"""Le choix du jeu en haut du Carnet et des Collections : jaquette et année.

Les noms complets prenaient deux lignes au-dessus d'un folio qui redit déjà le
nom du jeu : une pastille porte la jaquette et l'année en chiffre romain, comme
le Relevé ; le nom complet est dans l'infobulle et le nom accessible. Les deux
parties des Reliques partagent la septième année : « VII · 1 » et « VII · 2 ».
"""

from html import escape

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QPushButton

from src.ui.composants import police
from src.ui.stats_releve import _ROMAINS, _jaquette

_ICONE = QSize(18, 24)
_ECART = 7


def espacee(pixmap: QPixmap, taille: QSize, ecart: int = _ECART) -> tuple[QIcon, QSize]:
    """L'icône et sa taille, avec `ecart` px de blanc à DROITE (règle 30 : Qt
    colle le libellé à l'icône, et des espaces en tête de libellé seraient
    traduits). Peinte en pixels logiques sur un pixmap au ratio de la source
    (règle 46 : pas de `scale` sur un QPainter ouvert sur un pixmap à ratio).
    La jaquette garde ses proportions, centrée : étirée dans la case 3:4, une
    jaquette carrée perdait un quart de sa largeur (audit du 2026-11-02)."""
    ratio = max(pixmap.devicePixelRatio(), 2.0)      # net aussi sur un écran à 200 %
    large = QSize(taille.width() + ecart, taille.height())
    toile = QPixmap(round(large.width() * ratio), round(large.height() * ratio))
    toile.setDevicePixelRatio(ratio)
    toile.fill(Qt.GlobalColor.transparent)
    p = QPainter(toile)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    ajustee = pixmap.size().scaled(taille, Qt.AspectRatioMode.KeepAspectRatio)
    if not ajustee.isEmpty():
        x, y = (taille.width() - ajustee.width()) / 2, (taille.height() - ajustee.height()) / 2
        p.drawPixmap(QRectF(x, y, ajustee.width(), ajustee.height()), pixmap, QRectF(pixmap.rect()))
    p.end()
    return QIcon(toile), large


def numeros(jeux) -> dict[str, str]:
    """id → « III », ou « VII · 2 » quand deux jeux partagent l'année ; le
    nom du jeu pour un jeu hors des sept années."""
    par_annee: dict[int, list[str]] = {}
    for game in jeux:
        if 1 <= game.annee <= len(_ROMAINS):
            par_annee.setdefault(game.annee, []).append(game.id)
    sortie: dict[str, str] = {}
    for game in jeux:
        ids = par_annee.get(game.annee)
        if not ids:
            sortie[game.id] = game.name
            continue
        romain = _ROMAINS[game.annee - 1]
        sortie[game.id] = romain if len(ids) == 1 else f"{romain} · {ids.index(game.id) + 1}"
    return sortie


def pastille(game, etiquette: str) -> QPushButton:
    """Une pastille cochable (`objectName` « filtre », le style des pages)."""
    b = QPushButton(etiquette)
    b.setObjectName("filtre")
    b.setCheckable(True)
    b.setAutoDefault(False)
    b.setFont(police(13))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    jaquette = _jaquette(game.cover_image)
    if jaquette is not None:
        icone, taille = espacee(jaquette, _ICONE)
        b.setIcon(icone)
        b.setIconSize(taille)
    # Le nom vient du CATALOGUE : échappé, une infobulle se lit en texte riche.
    b.setToolTip(f"<qt>{escape(game.name, quote=False)}</qt>")
    b.setAccessibleName(game.name)
    return b

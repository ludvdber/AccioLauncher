"""Les médailles des défis : un fond de métal et un emblème, composés à la volée.

Les images vivent dans `assets/medailles/` (2026-10-26) : trois fonds (bronze,
argent, or) avec ruban, un fond « verrouillé » sans ruban, et dix emblèmes. Le
disque est au même endroit sur les quatre fonds (mesuré : 180 px de diamètre
centré en (128, 157,5) sur 256) ; l'emblème en couvre la moitié.

Le choix de l'emblème et du métal est un choix d'AFFICHAGE : il vit ici, pas
dans `succes.py`, qui ne dit que ce que la sauvegarde prouve.
"""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap

from src.core.config import ASSETS_DIR

_DOSSIER = ASSETS_DIR / "medailles"
_COTE = 256
_CENTRE = (128.0, 157.5)
_EMBLEME = 90.0             # la moitié du disque

BRONZE, ARGENT, OR = "bronze", "argent", "or"

# Le reflet du métal posé sur l'emblème (argenté d'origine) : il appartient à
# sa médaille au lieu d'y paraître collé. L'argent garde l'emblème tel quel.
_TEINTE = {BRONZE: QColor(168, 102, 58, 90), OR: QColor(214, 167, 44, 80)}

# (emblème, métal) par jeu et par succès.
MEDAILLES: dict[str, dict[str, tuple[str, str]]] = {
    "hp1": {
        "carte": ("cartes-sorcier", BRONZE), "cartes_13": ("cartes-sorcier", ARGENT),
        "cartes_25": ("cartes-sorcier", OR), "points_100": ("points-maison", ARGENT),
        "gryffondor_tete": ("coupe-quatre-maisons", OR),
    },
    "hp2": {
        "carte": ("cartes-sorcier", BRONZE), "cartes_50": ("cartes-sorcier", ARGENT),
        "cartes_101": ("cartes-sorcier", OR), "sorts": ("sorts", OR),
    },
    "hp3": {
        "carte": ("cartes-sorcier", BRONZE), "cartes_40": ("cartes-sorcier", ARGENT),
        "cartes_80": ("cartes-sorcier", OR), "etoiles": ("sans-faute", ARGENT),
        "secrets": ("secrets", ARGENT),
    },
    "hp4": {
        "carte": ("cartes-sorcier", BRONZE), "bouclier": ("coupe-quatre-maisons", BRONZE),
        "boucliers_19": ("coupe-quatre-maisons", ARGENT), "boucliers_38": ("coupe-quatre-maisons", OR),
    },
    "hp5": {
        "moitie": ("avancement", ARGENT), "cent": ("avancement", OR), "decouverte": ("decouverte", ARGENT),
    },
    "hp6": {
        "ecusson": ("ecussons", BRONZE), "ecussons_63": ("ecussons", ARGENT),
        "ecussons_125": ("ecussons", OR), "mini_25": ("ecussons", OR), "sorts": ("sorts", OR),
        "badge": ("badges-club", BRONZE), "badges": ("badges-club", OR),
    },
}
# Les lignes pleines de l'écran « Informations sur le jeu » de HP5 (`complet_<n>`).
_PAR_PREFIXE = {("hp5", "complet_"): ("decouverte", ARGENT)}

_cache: dict[tuple[str, str, bool, int], QPixmap] = {}


def medaille(jeu: str, ident: str) -> tuple[str, str]:
    """(emblème, métal) d'un succès ; un succès sans entrée prend le bronze des cartes."""
    trouve = MEDAILLES.get(jeu, {}).get(ident)
    if trouve is not None:
        return trouve
    for (j, prefixe), valeur in _PAR_PREFIXE.items():
        if j == jeu and ident.startswith(prefixe):
            return valeur
    return ("cartes-sorcier", BRONZE)


def pixmap_medaille(jeu: str, ident: str, obtenue: bool, taille: int, ratio: float = 1.0) -> QPixmap:
    """La médaille composée, carrée, `taille` px logiques. Non obtenue : le fond
    verrouillé et l'emblème en creux, pour qu'on sache ce qu'on vise."""
    physique = max(1, round(taille * ratio))
    cle = (jeu, ident, obtenue, physique)
    if cle in _cache:
        return _cache[cle]
    embleme, sorte = medaille(jeu, ident)
    toile = QPixmap(_COTE, _COTE)
    toile.fill(Qt.GlobalColor.transparent)
    p = QPainter(toile)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawPixmap(0, 0, QPixmap(str(_DOSSIER / f"medaille-{sorte if obtenue else 'verrouillee'}.png")))
    dessin = _embleme(embleme, None if not obtenue else _TEINTE.get(sorte))
    cible = QRectF(_CENTRE[0] - _EMBLEME / 2, _CENTRE[1] - _EMBLEME / 2, _EMBLEME, _EMBLEME)
    p.setOpacity(1.0 if obtenue else 0.4)
    p.drawPixmap(cible, dessin, QRectF(dessin.rect()))
    p.end()
    rendu = toile.scaled(physique, physique, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    rendu.setDevicePixelRatio(ratio)
    _cache[cle] = rendu
    return rendu


def _embleme(nom: str, teinte: QColor | None) -> QPixmap:
    dessin = QPixmap(str(_DOSSIER / f"embleme-{nom}.png"))
    if teinte is None or dessin.isNull():
        return dessin
    p = QPainter(dessin)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    p.fillRect(dessin.rect(), teinte)
    p.end()
    return dessin

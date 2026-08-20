"""Chargement des polices embarquées et helpers typographiques.

Les TROIS polices de l'interface sont embarquées : Cinzel (titres secondaires,
boutons, méta), Cinzel Decorative (titre principal) et **Gelasio** (texte
courant). Gelasio remplace Georgia, qui était appelée par son nom : une police
Microsoft, présente sous Windows mais **absente sous Linux** et jamais garantie
nulle part. Gelasio est sous licence OFL et **métriquement compatible avec
Georgia** — largeurs identiques au pixel près, mesurées de 10 à 15 px — donc
son adoption ne déplace aucun retour à la ligne.

Effet secondaire précieux : sous `offscreen`, `QFontDatabase.families()` est
vide et Qt substituait Cinzel à Georgia (+22 % de largeur). La suite de tests
mesurait donc une autre police que l'utilisateur. Avec une police de corps
embarquée, elle mesure enfin la bonne.
"""

import logging

from PyQt6.QtGui import QFont, QFontDatabase

from src.core.config import ASSETS_DIR

log = logging.getLogger(__name__)

FONTS_DIR = ASSETS_DIR / "fonts"

_cinzel_family: str | None = None
_cinzel_deco_family: str | None = None
_body_family: str | None = None
_loaded = False

# Repli si le fichier embarqué manque : Georgia (Windows/macOS), puis n'importe
# quelle serif. `StyleHint.Serif` évite qu'un Linux sans Georgia tombe sur une
# sans-serif, ce qui changerait complètement l'allure des descriptions.
_REPLI_CORPS = "Georgia"


def load_fonts() -> None:
    """Charge les polices Cinzel et Cinzel Decorative depuis assets/fonts/."""
    global _cinzel_family, _cinzel_deco_family, _body_family, _loaded
    if _loaded:
        return
    _loaded = True

    # Cinzel (variable font — supporte Regular à Black)
    for name in ("Cinzel-Variable.ttf", "Cinzel-Regular.ttf", "Cinzel-Bold.ttf"):
        path = FONTS_DIR / name
        if path.exists():
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families and _cinzel_family is None:
                    _cinzel_family = families[0]
                    log.info("Police Cinzel chargée : %s", _cinzel_family)

    # Cinzel Decorative
    for name in ("CinzelDecorative-Black.ttf", "CinzelDecorative-Bold.ttf",
                 "CinzelDecorative-Regular.ttf"):
        path = FONTS_DIR / name
        if path.exists():
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families and _cinzel_deco_family is None:
                    _cinzel_deco_family = families[0]
                    log.info("Police Cinzel Decorative chargée : %s", _cinzel_deco_family)

    # Gelasio — police de corps (variable : Regular → Bold)
    path = FONTS_DIR / "Gelasio-Variable.ttf"
    if path.exists():
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid >= 0:
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                _body_family = families[0]
                log.info("Police de corps chargée : %s", _body_family)

    if not _cinzel_family:
        log.warning("Cinzel non trouvée, repli sur %s", _REPLI_CORPS)
    if not _cinzel_deco_family:
        log.warning("Cinzel Decorative non trouvée, repli sur %s", _REPLI_CORPS)
    if not _body_family:
        log.warning("Gelasio non trouvée, repli sur %s (absente sous Linux)",
                    _REPLI_CORPS)


def cinzel(size: int, bold: bool = False) -> QFont:
    """Police Cinzel pour sous-titres, méta, boutons, tags."""
    family = _cinzel_family or _body_family or _REPLI_CORPS
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    return QFont(family, size, weight)


def cinzel_decorative(size: int, weight: QFont.Weight = QFont.Weight.Black) -> QFont:
    """Police Cinzel Decorative pour titres principaux."""
    family = _cinzel_deco_family or _body_family or _REPLI_CORPS
    return QFont(family, size, weight)


def body_font(size: int = 14) -> QFont:
    """Police de corps (descriptions, notes, toasts) — embarquée."""
    police = QFont(_body_family or _REPLI_CORPS, size)
    police.setStyleHint(QFont.StyleHint.Serif)
    return police

"""Chargement des polices Cinzel / Cinzel Decorative et helpers typographiques."""

import logging
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase

log = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).parent.parent.parent / "assets" / "fonts"

_cinzel_family: str | None = None
_cinzel_deco_family: str | None = None
_loaded = False


def load_fonts() -> None:
    """Charge les polices Cinzel et Cinzel Decorative depuis assets/fonts/."""
    global _cinzel_family, _cinzel_deco_family, _loaded
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

    if not _cinzel_family:
        log.warning("Cinzel non trouvée, fallback Georgia")
    if not _cinzel_deco_family:
        log.warning("Cinzel Decorative non trouvée, fallback Georgia")


def cinzel(size: int, bold: bool = False) -> QFont:
    """Police Cinzel pour sous-titres, méta, boutons, tags."""
    family = _cinzel_family or "Georgia"
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    return QFont(family, size, weight)


def cinzel_decorative(size: int, weight: QFont.Weight = QFont.Weight.Black) -> QFont:
    """Police Cinzel Decorative pour titres principaux."""
    family = _cinzel_deco_family or "Georgia"
    return QFont(family, size, weight)


def body_font(size: int = 14) -> QFont:
    """Police de corps pour descriptions."""
    return QFont("Georgia", size)


# Rétrocompatibilité
def load_harry_font() -> None:
    load_fonts()


def harry_font(size: int, bold: bool = False) -> QFont:
    return cinzel_decorative(size)

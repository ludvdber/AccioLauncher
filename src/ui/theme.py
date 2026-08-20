"""Thèmes maisons — palette d'accent ET de surfaces appliquée au démarrage.

`set_theme(config.theme)` est appelé par MainWindow AVANT la construction des
widgets (même contrat que `i18n.set_language` : changement = redémarrage).

Les feuilles de style du projet restent écrites avec la palette Poudlard (or
sur bleu nuit) ; `themed(qss)` substitue au moment du `setStyleSheet` :
- les hexs or par l'accent du thème actif ;
- les surfaces sombres bleu nuit (#060611, #0d0d1a, #16213e…) par leurs
  équivalents teintés maison (v2 — même luminosité, teinte de la maison),
  pour que TOUTE l'ambiance change, pas seulement les liserés.

Les paintEvent peints à la main passent par `accent_qcolor()` /
`current().accent_rgb` pour l'accent, et `bg_qcolor(alpha)` pour les voiles
sombres (carrousel, veil gauche, title bar). Le bouton JOUER reste vert
(couleur universelle d'action positive), le bouton Ko-fi et le splash gardent
l'or de la marque.
"""

from dataclasses import dataclass


def _rgb(hexa: str) -> tuple[int, int, int]:
    h = hexa.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


@dataclass(frozen=True)
class Palette:
    id: str
    nom: str  # clé tr() affichée dans Paramètres
    accent: str
    accent_light: str
    accent_dark: str
    # Surfaces sombres teintées maison (v2) — dans l'ordre :
    # fond principal, fond dialogues, cartes/menus, contrôles, bordure, bordure forte.
    bg: str
    bg_dialog: str
    bg_card: str
    bg_control: str
    border: str
    border_strong: str

    @property
    def accent_rgb(self) -> tuple[int, int, int]:
        return _rgb(self.accent)

    @property
    def bg_rgb(self) -> tuple[int, int, int]:
        return _rgb(self.bg)


THEMES: dict[str, Palette] = {
    # Poudlard = les couleurs telles qu'écrites dans les sources (aucune substitution).
    "poudlard": Palette(
        "poudlard", "Poudlard (or)", "#d6a72c", "#f0d060", "#9a7209",
        "#060611", "#0d0d1a", "#0f1528", "#16213e", "#1a2744", "#2c3e6b",
    ),
    "gryffondor": Palette(
        "gryffondor", "Gryffondor", "#b22222", "#e05a50", "#7a1414",
        "#110607", "#1a0d0e", "#281013", "#3e161c", "#441a20", "#6b2c36",
    ),
    "serpentard": Palette(
        "serpentard", "Serpentard", "#2e8b57", "#4cbf7e", "#1d5c39",
        "#061109", "#0d1a11", "#0f2817", "#163e25", "#1a4429", "#2c6b42",
    ),
    "serdaigle": Palette(
        "serdaigle", "Serdaigle", "#4a7fd4", "#7da7e8", "#2d5191",
        "#060a16", "#0d1226", "#0f1c3a", "#162a52", "#1a3058", "#2c4a80",
    ),
    "poufsouffle": Palette(
        "poufsouffle", "Poufsouffle", "#e8c200", "#f5dd55", "#a98c00",
        "#100f06", "#19160d", "#26200f", "#3b3216", "#423a1a", "#685a2c",
    ),
}

_current: Palette = THEMES["poudlard"]


def set_theme(theme_id: str) -> None:
    """Active une palette (id inconnu → Poudlard). À appeler avant les widgets."""
    global _current
    _current = THEMES.get(theme_id, THEMES["poudlard"])


def current() -> Palette:
    return _current


# Hexs or tels qu'écrits dans les feuilles de style et paintEvent du projet.
_GOLD = "#d6a72c"
_GOLD_LIGHTS = ("#f0d060", "#e8c547", "#e6b422")
_GOLD_DARK = "#9a7209"
_GOLD_RGBS = ("214, 167, 44", "214,167,44")
# Surfaces bleu nuit telles qu'écrites dans les sources → attribut de Palette.
_SURFACES = ("bg", "bg_dialog", "bg_card", "bg_control", "border", "border_strong")
_BG_RGBS = ("6, 6, 17", "6,6,17")  # forme rgba(...) du fond principal


def themed(qss: str) -> str:
    """Substitue la palette Poudlard (or + bleu nuit) par le thème actif."""
    p = _current
    if p.id == "poudlard":
        return qss
    base = THEMES["poudlard"]
    out = qss.replace(_GOLD, p.accent).replace(_GOLD_DARK, p.accent_dark)
    for v in _GOLD_LIGHTS:
        out = out.replace(v, p.accent_light)
    r, g, b = p.accent_rgb
    for v in _GOLD_RGBS:
        out = out.replace(v, f"{r}, {g}, {b}")
    for attr in _SURFACES:
        out = out.replace(getattr(base, attr), getattr(p, attr))
    br, bg_, bb = p.bg_rgb
    for v in _BG_RGBS:
        out = out.replace(v, f"{br}, {bg_}, {bb}")
    return out


def accent_qcolor(alpha: int = 255):
    """QColor de l'accent du thème actif (pour les paintEvent)."""
    from PyQt6.QtGui import QColor

    r, g, b = _current.accent_rgb
    return QColor(r, g, b, alpha)


def bg_qcolor(alpha: int = 255):
    """QColor du fond sombre du thème actif (voiles peints à la main)."""
    from PyQt6.QtGui import QColor

    r, g, b = _current.bg_rgb
    return QColor(r, g, b, alpha)

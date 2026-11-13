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

import re
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
    # Gryffondor et Serpentard revus le 2026-09-27 (planches 11 C et 12 C, choix de
    # Ludo) : l'ancien rouge `#b22222` faisait 2,99 de contraste sur son fond et 2,35
    # sur un bouton — illisible, et « agressif » parce que sombre ET saturé. Un
    # écarlate plus clair (5,3) sur des fonds bordeaux garde la maison et se lit ;
    # même remède pour le vert (4,5 → émeraude plus clair). `test_contraste` tient
    # le seuil pour chaque thème.
    "gryffondor": Palette(
        "gryffondor", "Gryffondor", "#e0584f", "#f39a8f", "#962b2b",
        "#1a0709", "#240b10", "#330f17", "#4a1422", "#5a1a2a", "#8c2a3e",
    ),
    "serpentard": Palette(
        "serpentard", "Serpentard", "#3fbf7f", "#7fdcaa", "#23784d",
        "#061209", "#0c1d13", "#0f2c1b", "#16432a", "#1b4c31", "#2e7550",
    ),
    "serdaigle": Palette(
        "serdaigle", "Serdaigle", "#4a7fd4", "#7da7e8", "#2d5191",
        "#060a16", "#0d1226", "#0f1c3a", "#162a52", "#1a3058", "#2c4a80",
    ),
    # Jaune adouci (planche 14 B, 2026-09-27) : `#e8c200` était saturé à 100 %,
    # « bizarre » ; surfaces presque noires — l'autre couleur de la maison.
    "poufsouffle": Palette(
        "poufsouffle", "Poufsouffle", "#e3bf45", "#f2d97e", "#9a7d1c",
        "#0c0b08", "#15130e", "#1f1c12", "#2e2918", "#37311c", "#5c522e",
    ),
}

_current: Palette = THEMES["poudlard"]


def set_theme(theme_id: str) -> None:
    """Active une palette (id inconnu → Poudlard). À appeler avant les widgets."""
    global _current
    _current = THEMES.get(theme_id, THEMES["poudlard"])


def current() -> Palette:
    return _current


# L'échelle des rayons (2026-11-12, constat tra12) : treize rayons différents
# sur les boutons (4 à 25 px) pour trois formes. Une commande (bouton, liste,
# rubrique ou rangée d'un rail), une carte (bloc bordé, carte cliquable), une pastille
# (ronde aux deux bouts : la moitié de sa hauteur, qui doit donc être FIXE —
# un rayon plus grand que la demi-hauteur, Qt ne le peint pas).
RAYON_CONTROLE = 6
RAYON_CARTE = 10


def rayon_pastille(hauteur: int) -> int:
    """Le rayon d'une pastille de `hauteur` px : ronde aux deux bouts."""
    return hauteur // 2


# Hexs or tels qu'écrits dans les feuilles de style et paintEvent du projet → attribut de Palette.
_OR = {"#d6a72c": "accent", "#9a7209": "accent_dark",
       **dict.fromkeys(("#f0d060", "#e8c547", "#e6b422", "#e8bd4a", "#f4e2a8"), "accent_light")}
# Surfaces bleu nuit de Poudlard → attribut de Palette.
_SURFACES = ("bg", "bg_dialog", "bg_card", "bg_control", "border", "border_strong")
# Surfaces bleu nuit écrites HORS palette (audit du 2026-11-13) : sans elles, Réglages du jeu,
# Carnet, Collections et leurs listes restaient bleu nuit entre deux bandes de la maison. Chacune
# suit la surface de Poudlard la plus proche, décalée du même écart.
_VOISINES = ("#070712", "#08081a", "#0a0a14", "#0a0a16", "#0b0b18", "#10101d", "#11111f", "#12121f",
             "#121226", "#141428", "#15152a", "#16162c", "#16172c", "#1b1b33", "#222f5b", "#2a2a48")
# Un hex, ou les trois premiers nombres d'un rgb()/rgba() : une seule passe, rien n'est substitué deux fois.
_COULEUR = re.compile(r"#[0-9a-fA-F]{6}\b|(?<=rgb\()[^)]*|(?<=rgba\()[^)]*")
_TRIPLET = re.compile(r"\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?=\s*(?:,|$))")
type _Rgb = tuple[int, int, int]
_tables: dict[str, dict[_Rgb, _Rgb]] = {}


def _table(p: Palette) -> dict[_Rgb, _Rgb]:
    """Couleur de Poudlard → couleur du thème `p`, calculée une fois par thème."""
    table = _tables.get(p.id)
    if table is None:
        base = THEMES["poudlard"]
        table = {_rgb(h): _rgb(getattr(p, attr)) for h, attr in _OR.items()}
        roles = {_rgb(getattr(base, a)): _rgb(getattr(p, a)) for a in _SURFACES}
        table.update(roles)
        for h in _VOISINES:
            source = _rgb(h)
            proche = min(roles, key=lambda c: sum((x - y) ** 2 for x, y in zip(c, source, strict=True)))
            (tr, tg, tb), (sr, sg, sb), (cr, cg, cb) = roles[proche], source, proche
            table[source] = (_borne(tr + sr - cr), _borne(tg + sg - cg), _borne(tb + sb - cb))
        _tables[p.id] = table
    return table


def _borne(v: int) -> int:
    return max(0, min(255, v))


def _substituer(m: re.Match[str], table: dict[_Rgb, _Rgb]) -> str:
    texte = m.group(0)
    if texte.startswith("#"):
        neuf = table.get(_rgb(texte))
        return "#{:02x}{:02x}{:02x}".format(*neuf) if neuf else texte
    t = _TRIPLET.match(texte)
    if t is None:
        return texte
    neuf = table.get((int(t.group(1)), int(t.group(2)), int(t.group(3))))
    return "{}, {}, {}".format(*neuf) + texte[t.end():] if neuf else texte


def themed(qss: str) -> str:
    """Substitue la palette Poudlard (or + bleu nuit) par le thème actif."""
    p = _current
    if p.id == "poudlard":
        return qss
    table = _table(p)
    return _COULEUR.sub(lambda m: _substituer(m, table), qss)


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

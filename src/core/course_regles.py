"""Les règles de course d'un jeu, lues dans le catalogue (bloc `race`, catalogue 0.63, 1.5).

Ce qui change d'un jeu à l'autre vit dans `games.json`, pas dans le code : les catégories (celles de
speedrun.com pour CE jeu : Glitchless n'existe que pour HP1 et HP2), le temps qui classe (réel pour HP4 à HP6,
sans chargements pour HP1 à HP3, comme speedrun.com), le départ et l'arrivée dits en clair, et la version du
correctif qui sait chronométrer. Une règle lue un mardi s'ouvre le mardi, traduite, sans republier l'exe.

    "race": {
      "fix_min": "2.5.0", "timing": "real", "speedrun": "hp4",
      "start": "…", "end": "…",
      "categories": [{"id": "Any%", "rule": "…"},
                     {"id": "All Shields", "name": "Tous les boucliers", "rule": "…", "note": "…"}],
      "i18n": {"en": {"start": "…", "end": "…"}}
    }

`id` est écrit TEL QUEL dans la ligne ACCIO que le correctif dessine (ASCII, `course.ligne_id`) et nomme la
catégorie dans `classement.json` ; `name` est ce que l'interface montre (l'`id` à défaut) ; `note` dit, quand il
y en a un, l'écart entre le chrono d'Accio et celui de speedrun.com pour cette catégorie. Chaque catégorie porte
son propre bloc `i18n`. `speedrun` est l'identifiant de la page du jeu sur speedrun.com (`hp1pc`, `hp4`…) : le
Carnet y renvoie pour les records du jeu d'origine ; absent ou mal formé, pas de lien. Le catalogue est DISTANT : tout est contrôlé, une catégorie mal formée est sautée, un
bloc sans catégorie valable n'existe pas (le jeu n'a pas de course).
"""

import re
from dataclasses import dataclass
from typing import Any

from src.core.catalogue_blocs import _loc

REEL = "reel"                           # temps réel, chargements compris
SANS_CHARGEMENTS = "sans_chargements"
# L'identifiant d'une page de speedrun.com : il finit dans une adresse, rien d'autre n'y passe.
_PAGE = re.compile(r"[a-z0-9_]{1,40}")
_TEMPS = {"real": REEL, "loadless": SANS_CHARGEMENTS}
# Un nom de catégorie de la ligne ACCIO : 23 signes au plus (la ligne en fait 63, `race::IsRaceId`), sans
# point-virgule ni tabulation (l'ini et le journal du correctif les liraient comme des séparateurs).
_CATEGORIE = re.compile(r"[A-Za-z0-9%+](?:[A-Za-z0-9%+ .-]{0,21}[A-Za-z0-9%+.])?")
_VERSION = re.compile(r"\d{1,3}(?:\.\d{1,3}){1,3}")
_TEXTE_MAX = 400
CATEGORIES_MAX = 8


def categorie_valide(texte: object) -> bool:
    """La forme d'un nom de catégorie que la ligne ACCIO et le classement acceptent."""
    return isinstance(texte, str) and _CATEGORIE.fullmatch(texte) is not None


def version(texte: object) -> tuple[int, ...] | None:
    """« 2.5.0 » → (2, 5, 0) ; None pour tout le reste."""
    if not isinstance(texte, str) or _VERSION.fullmatch(texte.strip()) is None:
        return None
    return tuple(int(x) for x in texte.strip().split("."))


@dataclass(frozen=True, slots=True)
class Categorie:
    ident: str          # écrit dans la ligne ACCIO et dans `classement.json`
    nom: str            # ce que l'interface montre
    regle: str          # ce que la catégorie demande, en une phrase ; le launcher ne le vérifie pas
    note: str = ""      # l'écart au chrono de speedrun.com, s'il y en a un


@dataclass(frozen=True, slots=True)
class Regles:
    correctif_min: tuple[int, ...]
    temps: str                          # REEL ou SANS_CHARGEMENTS : le temps qui classe
    depart: str
    arrivee: str
    categories: tuple[Categorie, ...]
    speedrun: str = ""                  # la page du jeu sur speedrun.com (`hp1pc`) ; vide : pas de lien

    def categorie(self, ident: str) -> Categorie | None:
        return next((c for c in self.categories if c.ident == ident), None)

    @property
    def idents(self) -> tuple[str, ...]:
        return tuple(c.ident for c in self.categories)


def _texte(data: dict[str, Any], cle: str) -> str:
    valeur = _loc(data, cle, "")
    return valeur.strip() if isinstance(valeur, str) and len(valeur) <= _TEXTE_MAX else ""


def _categorie(brut: object) -> Categorie | None:
    if not isinstance(brut, dict) or not categorie_valide(brut.get("id")):
        return None
    ident = str(brut["id"])
    regle = _texte(brut, "rule")
    if not regle:
        return None
    return Categorie(ident, _texte(brut, "name") or ident, regle, _texte(brut, "note"))


def lire(brut: object) -> Regles | None:
    """Le bloc `race` d'un jeu ; None s'il manque, ou s'il lui manque la version, le temps, le départ, l'arrivée
    ou toute catégorie valable. Deux catégories du même nom : la seconde est sautée."""
    if not isinstance(brut, dict):
        return None
    correctif_min = version(brut.get("fix_min"))
    timing = brut.get("timing")
    temps = _TEMPS.get(timing) if isinstance(timing, str) else None
    depart, arrivee = _texte(brut, "start"), _texte(brut, "end")
    liste = brut.get("categories")
    if correctif_min is None or temps is None or not depart or not arrivee or not isinstance(liste, list):
        return None
    categories: list[Categorie] = []
    for c in map(_categorie, liste[:CATEGORIES_MAX]):
        if c is not None and all(c.ident != d.ident for d in categories):
            categories.append(c)
    page = brut.get("speedrun")
    speedrun = page if isinstance(page, str) and _PAGE.fullmatch(page) else ""
    return Regles(correctif_min, temps, depart, arrivee, tuple(categories), speedrun) if categories else None

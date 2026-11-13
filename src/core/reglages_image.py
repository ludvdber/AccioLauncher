"""L'onglet Image des réglages d'un jeu, rangé en six catégories (maquette « Curseurs gradués »,
2026-11-12, choisie par Ludo) : Écran, Qualité, Éclairage et ombres, Distance d'affichage, Couleurs,
Ciel et ambiance. Pure donnée et règles, sans Qt : `ui/page_image.py` les montre.

Ce qui est tranché (la maquette, « Déjà tranché ») :

- une catégorie par onglet en haut, comme dans un jeu, avec une pastille qui compte les réglages
  qui s'écartent de la valeur Accio ;
- chaque réglage montre deux repères : le jeu d'origine (argent) et la valeur Accio (or) ;
- des boutons pour 2 à 5 choix courts, un curseur pour les nombres (`CURSEURS`), une liste
  seulement pour ce qui a trop de choix ou de trop longs noms (la résolution, le mode d'affichage).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from src.core.reglages_correctif import curseur, libelle_choix
from src.core.reglages_table import Reglage

# (identifiant, nom) dans l'ordre des onglets.
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("ecran", "Écran"),
    ("qualite", "Qualité"),
    ("lumiere", "Éclairage et ombres"),
    ("distance", "Distance d'affichage"),
    ("couleurs", "Couleurs"),
    ("ciel", "Ciel et ambiance"),
)

# Où va chaque réglage : (catégorie, groupe). L'ordre de la table fait l'ordre des lignes.
_PLACES: dict[str, tuple[str, str]] = {
    "resolution": ("ecran", "Affichage"),
    "mode_fenetre": ("ecran", "Affichage"),
    "format_image": ("ecran", "Affichage"),
    "champ_vision": ("ecran", "Affichage"),
    "ecran_principal": ("ecran", "Fenêtre"),
    "premier_plan": ("ecran", "Fenêtre"),
    "surechantillonnage": ("qualite", "Contours"),
    "anticrenelage": ("qualite", "Contours"),
    "anticrenelage_transparence": ("qualite", "Contours"),
    "lissage": ("qualite", "Contours"),
    "nettete": ("qualite", "Contours"),
    "filtrage": ("qualite", "Textures"),
    "textures_lointaines": ("qualite", "Textures"),
    "mipmaps_fins": ("qualite", "Textures"),
    "textures_hd": ("qualite", "Textures"),
    "occlusion": ("lumiere", "Ombres de contact"),
    "ombres_nettes": ("lumiere", "Ombres portées"),
    "ombres_douces": ("lumiere", "Ombres portées"),
    "halo": ("lumiere", "Halo et rayons"),
    "force_halo": ("lumiere", "Halo et rayons"),
    "rayons": ("lumiere", "Halo et rayons"),
    "decor_entier": ("distance", "Décor"),
    "particules_lointaines": ("distance", "Effets"),
    "feuillage_lointain": ("distance", "Végétation"),
    "couleurs": ("couleurs", "Couleurs"),
    "vivacite": ("couleurs", "Couleurs"),
    "contraste": ("couleurs", "Couleurs"),
    "vignette": ("couleurs", "Couleurs"),
    "vert_relief": ("couleurs", "Couleurs"),
    "ciel": ("ciel", "Ciel"),
    "ciel_heure": ("ciel", "Ciel"),
    "ciel_couleur": ("ciel", "Ciel"),
    "brouillard": ("ciel", "Atmosphère"),
}
# L'ordre des lignes dans leur groupe : celui de la maquette (le suréchantillonnage, qui se voit le
# plus, en tête des contours), puis celui de la table pour un réglage qu'elle ne nomme pas.
_ORDRE = tuple(_PLACES)
# Un réglage d'image qu'aucune place ne nomme n'est jamais perdu.
_AILLEURS = ("qualite", "Autres")

# Au-delà, des boutons côte à côte ne tiennent plus dans la ligne : une liste.
_MAX_BOUTONS = 5
_MAX_CARACTERES = 40

type Controle = Literal["inter", "boutons", "curseur", "teinte", "liste"]


@dataclass(frozen=True, slots=True)
class Groupe:
    nom: str
    reglages: tuple[Reglage, ...]


@dataclass(frozen=True, slots=True)
class Categorie:
    ident: str
    nom: str
    groupes: tuple[Groupe, ...]

    @property
    def reglages(self) -> tuple[Reglage, ...]:
        return tuple(r for g in self.groupes for r in g.reglages)


def place(reglage: Reglage) -> tuple[str, str]:
    """(catégorie, groupe) d'un réglage de l'onglet Image."""
    return _PLACES.get(reglage.ident, _AILLEURS)


def ranger(reglages: Iterable[Reglage]) -> tuple[Categorie, ...]:
    """Les réglages en catégories, puis en groupes ; les catégories vides n'existent pas."""
    tous = sorted(reglages, key=lambda r: _ORDRE.index(r.ident) if r.ident in _ORDRE else len(_ORDRE))
    categories = []
    for ident, nom in CATEGORIES:
        groupes: dict[str, list[Reglage]] = {}
        for r in tous:
            cat, groupe = place(r)
            if cat == ident:
                groupes.setdefault(groupe, []).append(r)
        if groupes:
            categories.append(Categorie(ident, nom, tuple(Groupe(n, tuple(m)) for n, m in groupes.items())))
    return tuple(categories)


def controle(reglage: Reglage) -> Controle:
    """Le contrôle qui montre ce réglage."""
    if not reglage.choix:
        return "inter"
    if curseur(reglage) is not None:
        return "curseur"
    if reglage.ident == "ciel_couleur":
        return "teinte"
    noms = [libelle_choix(reglage, v) for v in reglage.choix]
    if len(noms) <= _MAX_BOUTONS and sum(len(n) for n in noms) <= _MAX_CARACTERES:
        return "boutons"
    return "liste"


def correspond(reglage: Reglage, libelle: str, aide: str, recherche: str) -> bool:
    """La recherche trouve-t-elle ce réglage ? Dans son nom ou sa description, sans casse ni accents."""
    voulu = _plat(recherche)
    return bool(voulu) and voulu in _plat(f"{libelle} {aide}")


def _plat(texte: str) -> str:
    import unicodedata
    decompose = unicodedata.normalize("NFKD", texte.casefold())
    return "".join(c for c in decompose if not unicodedata.combining(c)).strip()

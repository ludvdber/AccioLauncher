"""L'onglet Image des réglages d'un jeu, rangé en six catégories (maquette « Curseurs gradués »,
2026-11-12, choisie par Ludo) : Écran, Qualité, Éclairage et ombres, Distance d'affichage, Couleurs,
Ciel et ambiance. Pure donnée et règles, sans Qt : `ui/page_image.py` les montre.

Ce qui est tranché (la maquette, « Déjà tranché ») :

- une catégorie par onglet en haut, comme dans un jeu, avec une pastille qui compte les réglages
  qui s'écartent de la valeur Accio ;
- chaque réglage montre deux repères : le jeu d'origine (argent) et la valeur Accio (or) ;
- des boutons pour 2 à 5 choix courts, un curseur pour les nombres (`CURSEURS`), une liste
  seulement pour ce qui a trop de choix ou de trop longs noms (la résolution, le mode d'affichage).

Les dosages qu'on ne touche presque jamais (Ludo, 2026-11-20 : « Avancé, repliée ») vont dans le
groupe `GROUPE_FIN` de leur catégorie, le dernier, que la page montre replié.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from src.core import reglages_correctif as rc
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
    # L'ancienne page Performances (audit UI reg21) : ce qui règle le rythme des images.
    ("fluidite", "Fluidité"),
)

# Le groupe replié d'une catégorie : ses dosages fins.
GROUPE_FIN = "Réglages fins"

# Où va chaque réglage : (catégorie, groupe). L'ordre de la table fait l'ordre des lignes.
_PLACES: dict[str, tuple[str, str]] = {
    "resolution": ("ecran", "Affichage"),
    "mode_fenetre": ("ecran", "Affichage"),
    "plein_ecran": ("ecran", "Affichage"),
    "format_image": ("ecran", "Affichage"),
    "champ_vision": ("ecran", "Affichage"),
    "fov_course": ("ecran", "Affichage"),
    "ecran_principal": ("ecran", "Fenêtre"),
    "premier_plan": ("ecran", "Fenêtre"),
    "surechantillonnage": ("qualite", "Contours"),
    "anticrenelage": ("qualite", "Contours"),
    "anticrenelage_transparence": ("qualite", "Contours"),
    "lissage": ("qualite", "Contours"),
    "nettete": ("qualite", "Contours"),
    "filtrage": ("qualite", "Textures"),
    "textures_lointaines": ("qualite", "Textures"),
    "textures_hd": ("qualite", "Textures"),
    "occlusion": ("lumiere", "Ombres de contact"),
    "force_occlusion": ("lumiere", "Ombres de contact"),
    "ombres_nettes": ("lumiere", "Ombres portées"),
    "ombres_douces": ("lumiere", "Ombres portées"),
    "ombres_fines": ("lumiere", "Ombres portées"),
    "ombres_floutees": ("lumiere", "Ombres portées"),
    "halo": ("lumiere", "Halo et rayons"),
    "intensite_halo": ("lumiere", "Halo et rayons"),
    "force_halo": ("lumiere", "Halo et rayons"),
    "halo_fin": ("lumiere", "Halo et rayons"),
    "rayons": ("lumiere", "Halo et rayons"),
    "force_rayons": ("lumiere", "Halo et rayons"),
    "portee_occlusion": ("lumiere", GROUPE_FIN),
    "seuil_halo": ("lumiere", GROUPE_FIN),
    "longueur_rayons": ("lumiere", GROUPE_FIN),
    "decor_entier": ("distance", "Décor"),
    "petits_objets_lointains": ("distance", "Décor"),
    "horizon": ("distance", "Décor"),
    "particules_lointaines": ("distance", "Effets"),
    "feuillage_lointain": ("distance", "Végétation"),
    # À côté du feuillage dense : rangés dans deux catégories, les deux réglages d'arbres
    # lointains ne se trouvaient jamais ensemble (audit UI f67).
    "mipmaps_fins": ("distance", "Végétation"),
    "couleurs": ("couleurs", "Couleurs"),
    "vivacite": ("couleurs", "Couleurs"),
    "contraste": ("couleurs", "Couleurs"),
    "vignette": ("couleurs", "Couleurs"),
    "tons_moyens": ("couleurs", "Couleurs"),
    "temperature": ("couleurs", "Couleurs"),
    "retenue_vert": ("couleurs", "Couleurs"),
    "vert_relief": ("couleurs", "Couleurs"),
    "noirs_releves": ("couleurs", GROUPE_FIN),
    "exposition": ("couleurs", GROUPE_FIN),
    "teinte": ("couleurs", GROUPE_FIN),
    "virage": ("couleurs", GROUPE_FIN),
    "retenue_jaune": ("couleurs", GROUPE_FIN),
    "ciel": ("ciel", "Ciel"),
    "ciel_heure": ("ciel", "Ciel"),
    "ciel_couleur": ("ciel", "Ciel"),
    "brouillard": ("ciel", "Atmosphère"),
    # Le rendu D3D11 de HP1/HP2 (`qualite_rendu`) et les réglages graphiques de HP3
    # (`reglages_graphiques`), aux places de leurs pareils du correctif.
    "graph_resolution": ("qualite", "Contours"),
    "rendu_anticrenelage": ("qualite", "Contours"),
    "graph_antialiasing": ("qualite", "Contours"),
    "rendu_feuillage": ("qualite", "Contours"),
    "graph_textures_rendu": ("qualite", "Contours"),
    "rendu_filtrage": ("qualite", "Textures"),
    "graph_filtrage": ("qualite", "Textures"),
    "rendu_textures_lointaines": ("qualite", "Textures"),
    "rendu_relief": ("qualite", "Relief des surfaces"),
    "rendu_parallaxe": ("qualite", "Relief des surfaces"),
    "rendu_occlusion": ("lumiere", "Ombres de contact"),
    "rendu_hdr": ("lumiere", "Lumière"),
    "rendu_volumetrique": ("lumiere", "Lumière"),
    "rendu_reflets": ("lumiere", "Reflets"),
    "rendu_reflets_force": ("lumiere", "Reflets"),
    "rendu_distance": ("distance", "Décor"),
    "rendu_limite": ("fluidite", "Images par seconde"),
    "graph_limite": ("fluidite", "Images par seconde"),
    "rendu_vsync": ("fluidite", "Images par seconde"),
    "graph_vsync": ("fluidite", "Images par seconde"),
    "limite_fps": ("fluidite", "Images par seconde"),
    "limite_fps_60": ("fluidite", "Images par seconde"),
    "synchro_verticale": ("fluidite", "Images par seconde"),
    "images_a_l_heure": ("fluidite", "Images par seconde"),
    "camera_fluide": ("fluidite", "Images par seconde"),
    "fermeture_sans_plantage": ("fluidite", "Stabilité"),
    "compteur_fps": ("fluidite", "Compteurs"),
    "compteur_fps_hp3": ("fluidite", "Compteurs"),
    "panneau_perfs": ("fluidite", "Compteurs"),
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


class Magasin(Protocol):
    """Où la page Image lit et écrit un réglage : l'ini du correctif (`MagasinCorrectif`), le rendu D3D11
    de HP1/HP2 (`qualite_rendu.MagasinRendu`), les réglages graphiques de HP3
    (`reglages_graphiques.MagasinGraphique`). `lire` lève OSError, `ecrire` OSError ou ValueError."""

    def lire(self, reglage: Reglage) -> object: ...

    def lire_tout(self, reglages: Iterable[Reglage]) -> dict[str, object]:
        """Plusieurs réglages, par identifiant : leur fichier lu une fois. Lève OSError."""
        ...

    def ecrire(self, reglage: Reglage, valeur: object) -> None: ...

    def ecrire_tout(self, valeurs: Sequence[tuple[Reglage, object]]) -> dict[str, object]:
        """Plusieurs réglages d'un coup (un préréglage), et ce que porte ensuite le magasin, par identifiant :
        la page n'a rien à relire."""
        ...

    def accio(self, reglage: Reglage) -> object: ...

    def jeu(self, reglage: Reglage) -> object: ...


class MagasinCorrectif:
    """L'ini du correctif (`d3d9.ini`, `winmm.ini`, `dinput8.ini`)."""

    def __init__(self, ini: Path) -> None:
        self.ini = ini

    def lire(self, reglage: Reglage) -> object:
        return rc.lire(self.ini, reglage).valeur

    def lire_tout(self, reglages: Iterable[Reglage]) -> dict[str, object]:
        # `rc.lire` passe par `lecture_ini` : l'ini n'est relu que s'il vient d'être écrit.
        return {r.ident: self.lire(r) for r in reglages}

    def ecrire(self, reglage: Reglage, valeur: object) -> None:
        rc.ecrire(self.ini, reglage, valeur)

    def ecrire_tout(self, valeurs: Sequence[tuple[Reglage, object]]) -> dict[str, object]:
        """Un réglage après l'autre (`rc.ecrire` connaît les réglages à plusieurs clés) : ce qui précède
        un refus reste écrit, et la page relit alors tout le lot."""
        for reglage, valeur in valeurs:
            rc.ecrire(self.ini, reglage, valeur)
        return {r.ident: self.lire(r) for r, _v in valeurs}

    def accio(self, reglage: Reglage) -> object:
        return rc.valeur_accio(self.ini, reglage)

    def jeu(self, reglage: Reglage) -> object:
        return rc.valeur_du_jeu(reglage)


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
            # Le groupe replié ferme toujours sa catégorie, où que tombe son premier réglage.
            ordre = sorted(groupes.items(), key=lambda g: g[0] == GROUPE_FIN)
            categories.append(Categorie(ident, nom, tuple(Groupe(n, tuple(m)) for n, m in ordre)))
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


def correspond(libelle: str, aide: str, recherche: str) -> bool:
    """La recherche trouve-t-elle ce réglage ? Dans son nom ou sa description, sans casse ni accents."""
    voulu = _plat(recherche)
    return bool(voulu) and voulu in _plat(f"{libelle} {aide}")


def _plat(texte: str) -> str:
    import unicodedata
    decompose = unicodedata.normalize("NFKD", texte.casefold())
    return "".join(c for c in decompose if not unicodedata.combining(c)).strip()

"""L'Almanach de Poudlard — quelle ambiance, à quelle date, et à quoi elle ressemble.

`config.season` vaut "auto" (selon la date) ou l'identifiant d'une ambiance.
Le changement depuis Paramètres est appliqué EN DIRECT (les particules sont
re-semées), contrairement au thème qui demande un redémarrage.

**Ce module ne peint rien et n'importe pas Qt.** Il porte DEUX choses, toutes
deux pures : le calendrier (quelle ambiance un jour donné) et le `Profil` de
chaque ambiance — c'est-à-dire tous les nombres qui la distinguent. C'est
`particles.py` qui sait les peindre.

Le partage est délibéré. Avant l'Almanach, ces nombres vivaient dans une
cascade de `if season == …` au milieu du constructeur des particules : deux
ambiances y tenaient, cinq en auraient fait un mur illisible, et rien de tout
ça n'était testable sans construire un widget. En données, ajouter un jour de
l'Almanach est une ligne de table — et la table s'exerce sans `QApplication`.

**Les quatre dates de l'Almanach** ne sont pas décoratives : ce sont celles que
tout lecteur reconnaît sans qu'on les lui explique — le 1ᵉʳ septembre (le
Poudlard Express part à 11 h de la voie 9¾), le 31 juillet, le 2 mai (la
bataille de Poudlard, 1998), et la nuit du 31 octobre, que le launcher fêtait
déjà sans le dire.
"""

from dataclasses import dataclass, field
from datetime import date

# `None` dans une palette = l'accent du THÈME en cours. C'est ce qui fait que
# les particules de base restent vertes chez Serpentard et or chez Poudlard :
# une couleur figée ici casserait le thème de maison.
Couleur = tuple[int, int, int] | None
Palette = tuple[tuple[Couleur, float], ...]


@dataclass(frozen=True)
class Profil:
    """Tout ce qui distingue une ambiance, en NOMBRES.

    Les intervalles sont des `(min, max)` tirés au hasard par particule. Les
    valeurs par défaut décrivent l'ambiance ordinaire — une ambiance
    saisonnière ne redéclare que ce qu'elle change, ce qui rend la table
    lisible d'un coup d'œil et empêche un oubli de se transformer en zéro.
    """

    nombre: int = 35
    forme: str = "point"
    # Part des particules qui portent la forme ; le reste reste en points.
    # C'est ce qui donne la « poudreuse » derrière les flocons.
    part_forme: float = 1.0
    palette: Palette = field(
        default_factory=lambda: ((None, 0.7), ((200, 200, 230), 0.3)))
    taille: tuple[float, float] = (1.5, 4.0)
    # Négatif = monte (braises, poussière), positif = tombe (flocons, cendres).
    vitesse_y: tuple[float, float] = (-0.5, -0.2)
    derive_x: tuple[float, float] = (-0.2, 0.2)
    oscillation: float = 0.15
    vitesse_phase: float = 0.008
    scintillement: tuple[float, float] = (1.5, 1.5)
    opacite: tuple[float, float] = (0.10, 0.35)
    variation: tuple[float, float] = (0.05, 0.15)
    proba_halo: float = 0.15
    halo: tuple[float, float] = (8.0, 14.0)
    vitesse_rotation: tuple[float, float] = (0.0, 0.0)
    # Taille des particules qui N'ONT PAS la forme (poudreuse de fond).
    taille_fond: tuple[float, float] | None = None


_ORDINAIRE = Profil()

PROFILS: dict[str, Profil] = {
    "aucune": _ORDINAIRE,

    # ── 31 octobre · Halloween ──────────────────────────────────────────
    # Braises de feu de sorcière : orange et violet, halo large et fréquent,
    # scintillement rapide, montée plus vive.
    "halloween": Profil(
        nombre=45,
        palette=(((255, 140, 0), 0.60), ((150, 90, 220), 0.25),
                 ((200, 200, 230), 0.15)),
        taille=(1.5, 3.5),
        vitesse_y=(-0.75, -0.35),
        oscillation=0.30,
        scintillement=(3.0, 5.0),
        opacite=(0.15, 0.40),
        variation=(0.12, 0.28),
        proba_halo=0.55,
        halo=(10.0, 18.0),
    ),

    # ── Décembre · Noël ─────────────────────────────────────────────────
    # Vrais flocons à six branches qui TOMBENT en tournoyant, sur un fond de
    # poudreuse plus fine.
    "noel": Profil(
        nombre=55,
        forme="flocon",
        part_forme=0.75,
        palette=(((235, 240, 255), 0.8), ((200, 210, 240), 0.2)),
        taille=(2.5, 5.0),
        taille_fond=(1.2, 2.5),
        vitesse_y=(0.25, 0.6),
        oscillation=0.50,
        vitesse_phase=0.012,
        opacite=(0.20, 0.45),
        proba_halo=0.10,
        vitesse_rotation=(-0.8, 0.8),
    ),

    # ── 1ᵉʳ septembre · La rentrée ──────────────────────────────────────
    # Les lettres de Poudlard. Elles DESCENDENT en tournoyant lentement, comme
    # celles qui inondent le salon des Dursley, et leur cachet de cire prend
    # l'accent du thème — donc la couleur de la maison de l'utilisateur.
    # Quelques escarbilles dorées montent derrière : la vapeur du Poudlard
    # Express. Deux sens de déplacement dans la même scène, ce qu'aucune autre
    # ambiance ne fait : c'est ce qui la rend reconnaissable en un regard.
    # La taille des lettres n'est PAS un réglage d'ambiance : c'est un seuil
    # de lisibilité. Premier essai à 3–5,5 px, rendu et regardé : les
    # enveloppes sortaient à 5–8 px de large et se lisaient comme des grains
    # de poussière — la forme était là, personne ne l'aurait reconnue. Une
    # lettre demande une douzaine de pixels pour que son rabat se voie ; en
    # contrepartie on en met MOINS, sinon la scène devient une tempête de
    # papier.
    "rentree": Profil(
        nombre=30,
        forme="enveloppe",
        part_forme=0.5,
        palette=(((244, 236, 214), 0.75), ((214, 196, 150), 0.25)),
        taille=(6.5, 11.0),
        taille_fond=(1.2, 2.4),
        vitesse_y=(0.18, 0.45),
        derive_x=(-0.25, 0.25),
        oscillation=0.55,
        vitesse_phase=0.010,
        opacite=(0.18, 0.42),
        variation=(0.06, 0.14),
        proba_halo=0.12,
        halo=(8.0, 13.0),
        vitesse_rotation=(-0.45, 0.45),
    ),

    # ── 31 juillet · L'anniversaire ─────────────────────────────────────
    # Les bougies de la Grande Salle : des flammes qui flottent presque sur
    # place, très lentement, avec un halo chaud sur PRESQUE toutes — c'est le
    # halo qui fait la scène, pas la flamme.
    "anniversaire": Profil(
        nombre=28,
        forme="flamme",
        part_forme=0.8,
        palette=(((255, 205, 110), 0.6), ((255, 170, 60), 0.3),
                 ((255, 240, 200), 0.1)),
        # Même leçon que les lettres : à 2,2 px la goutte sortait en filament
        # d'un pixel de large, donc en trait et non en flamme.
        taille=(3.2, 5.6),
        taille_fond=(1.0, 2.0),
        vitesse_y=(-0.16, -0.05),
        derive_x=(-0.06, 0.06),
        oscillation=0.08,
        vitesse_phase=0.014,
        scintillement=(2.0, 3.4),
        opacite=(0.22, 0.48),
        variation=(0.10, 0.20),
        proba_halo=0.85,
        halo=(12.0, 22.0),
    ),

    # ── 2 mai · La bataille de Poudlard ─────────────────────────────────
    # Des cendres. Grises, froides, qui tombent lentement et dérivent
    # beaucoup ; quelques braises mourantes, rares et sourdes. C'est une
    # commémoration : rien n'y brille, et c'est le contraire exact d'Halloween
    # — là des braises vives qui montent, ici des cendres éteintes qui
    # retombent.
    "bataille": Profil(
        nombre=50,
        palette=(((168, 172, 186), 0.55), ((120, 126, 142), 0.30),
                 ((196, 110, 70), 0.15)),
        taille=(1.2, 3.0),
        vitesse_y=(0.10, 0.35),
        derive_x=(-0.35, 0.35),
        oscillation=0.42,
        vitesse_phase=0.006,
        scintillement=(0.8, 1.6),
        opacite=(0.12, 0.30),
        variation=(0.04, 0.10),
        proba_halo=0.08,
        halo=(6.0, 11.0),
    ),
}

# Ordre d'affichage dans Paramètres. "auto" est résolu via `current_season()`.
# SOURCE UNIQUE : le sélecteur des Paramètres le lit au lieu de tenir sa
# propre liste — il en tenait une, et deux listes qu'aucun calcul ne relie
# finissent par diverger (c'est le défaut `THUMB_H` / `CAROUSEL_HEIGHT`).
SEASONS = ("auto", "aucune", "halloween", "noel",
           "rentree", "anniversaire", "bataille")

# Libellés du sélecteur. Ils portent la DATE, pas seulement le nom : « 2 mai »
# ne dit rien à qui n'a pas la référence, « 2 mai — la bataille de Poudlard »
# se comprend sans l'avoir. Résolus par `tr()` À L'APPEL, comme les noms de
# maison — ces clés doivent donc exister dans chaque `src/data/i18n/*.json`.
SEASON_LABELS: dict[str, str] = {
    "auto": "Automatique (selon la date)",
    "aucune": "Aucune",
    "halloween": "Octobre — Halloween",
    "noel": "Décembre — Noël",
    "rentree": "1ᵉʳ septembre — la rentrée",
    "anniversaire": "31 juillet — l'anniversaire",
    "bataille": "2 mai — la bataille de Poudlard",
}

# ── L'Almanach : un MOIS, une ambiance ───────────────────────────────────
# Chaque ambiance tient tout son mois (décision de Ludo, 2026-09-23). La
# première version les limitait à leur jour exact — le 31 juillet, le 2 mai —
# et c'était une erreur de conception : une ambiance qu'on ne voit qu'un jour
# par an n'existe pas pour la plupart des gens, et celui qui la manque n'a
# aucun moyen de savoir qu'elle a existé. Le JOUR reste ce qui compte pour le
# fait du jour (`almanach.py`), qui lui change tous les jours ; l'ambiance,
# elle, habille la saison.
_MOIS: dict[int, str] = {
    5: "bataille",       # mai — la bataille de Poudlard (2 mai 1998)
    7: "anniversaire",   # juillet — l'anniversaire de Harry (31 juillet)
    9: "rentree",        # septembre — le Poudlard Express (1ᵉʳ septembre)
    10: "halloween",     # octobre
    12: "noel",          # décembre
}
# Les douze jours de Noël débordent sur janvier : le launcher reste en tenue
# de fête pendant les vacances scolaires, pas seulement en décembre.
_NOEL_JANVIER = 6


def profil(season: str) -> Profil:
    """Le `Profil` d'une ambiance ; l'ordinaire si elle est inconnue.

    Inconnue arrive pour de vrai : une `config.json` écrite par une version
    plus récente du launcher peut nommer une ambiance que celui-ci n'a pas.
    """
    return PROFILS.get(season, _ORDINAIRE)


def current_season(today: date | None = None) -> str:
    """L'ambiance du jour selon l'Almanach."""
    today = today or date.today()
    if today.month == 1 and today.day <= _NOEL_JANVIER:
        return "noel"
    return _MOIS.get(today.month, "aucune")


def resolve(config_value: str, today: date | None = None) -> str:
    """Traduit la valeur de config en ambiance effective ("auto" → date du jour)."""
    if config_value == "auto":
        return current_season(today)
    return config_value if config_value in SEASONS else "aucune"

"""Les presets de difficulté de la 1.4 : Récit (accessibilité, Harry invincible),
Détendu, Normal, Difficile, Hardcore, et deux presets à une seule vie, Réaliste
et Impardonnable.

Tranché par Ludo le 2026-10-30 (atelier, `notes/DIFFICULTE_1.4.md` § 4) : des
presets aux noms clairs, et « Sur mesure » dans des réglages à dérouler. Un
preset n'est qu'un jeu de valeurs pour des réglages qui existent déjà : ceux du
correctif (`[Accio.Hardcore]`, le Quidditch de HP1/HP2) et la difficulté
propre du jeu (`difficulte_jeu`, HP2). Rien de neuf n'est écrit ailleurs.

Les valeurs sont COMMUNES à tous les jeux, comme les préréglages d'image :
chaque jeu n'en garde que les réglages qu'il déclare. Un preset qui ne change
rien dans un jeu n'y est pas proposé.

AUCUN preset ne retire de sort (Ludo, 2026-10-30) : un sort retiré peut bloquer
la partie (une leçon, un défi qui le demande). `sorts_retires` reste un réglage
à part, dans « Sur mesure ».

Une seule vie (Ludo, 2026-10-30) : Réaliste = le jeu de base, Impardonnable =
Hardcore, et dans les deux la première mort termine la partie. Ce mécanisme
n'existe encore dans aucun jeu : ces presets se montrent « bientôt » tant que
`UNE_VIE_POSSIBLE` est vide.

Ce que dit un preset pour un jeu se CALCULE depuis les réglages (libellé et
choix affichés) : une phrase écrite à la main finirait par mentir.

Le niveau de défi (cadran de la page, maquette validée par Ludo le 2026-10-31)
va de 0 à 100. Chaque preset a son cran fixe (`NIVEAUX`), le même dans tous les
jeux ; du sur mesure se place entre les crans des presets du jeu, d'après la
« rigueur » de ses réglages, et le plus dur que le jeu permet vaut 100. Aucun
chiffre ne s'affiche : seulement l'aiguille et « Entre Difficile et Hardcore ».
"""

import itertools
import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.core import difficulte_jeu
from src.core import reglages_correctif as rc
from src.core.reglages_table import REGLAGES
from src.core.config import Config
from src.core.game_data import GameData
from src.core.i18n import tr

log = logging.getLogger(__name__)

# La difficulté propre du jeu (bloc `difficulty` du catalogue) : un rang 0..2.
NATIVE = "difficulte_native"
SUR_MESURE = "sur_mesure"

# Les jeux où « une seule vie » existe vraiment (aucun en 1.4.0).
UNE_VIE_POSSIBLE: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Preset:
    ident: str
    nom: str            # clé tr()
    phrase: str         # clé tr() : ce que le preset veut dire, tous jeux confondus
    valeurs: Mapping[str, object]
    une_vie: bool = False   # la première mort termine la partie
    # Le réglage sans lequel le preset n'a pas de sens (Récit sans invincibilité
    # ne serait qu'un Détendu mal nommé).
    exige: str = ""


# Pas de `sorts_retires` : aucun preset n'y touche, le choix du joueur reste.
_NORMAL: dict[str, object] = {
    "degats_recus": 1, "degats_infliges": 1, "reaction_ennemis": 1,
    "vie_joueur": 1, "regeneration": 1, "invincible": False, "quidditch": 0, NATIVE: 0,
}
# Difficile (Ludo, 2026-10-30) : un cran entre la difficulté d'origine la plus
# haute et Hardcore.
_DIFFICILE: dict[str, object] = {
    **_NORMAL, "degats_recus": 1.5, "degats_infliges": 0.75, "reaction_ennemis": 1.5,
    "regeneration": 0.5, "quidditch": 1, NATIVE: 2,
}
# Hardcore (Ludo, 2026-10-30) : bien au-delà. Réaction ×5 = attentes des ennemis
# divisées par 5 (0,4 s entre deux attaques au lieu de 2 s) : il reste une marge,
# minime, pour attaquer. Le sur mesure va encore plus loin (×10, ×5 de dégâts).
_HARDCORE: dict[str, object] = {
    **_NORMAL, "degats_recus": 3, "degats_infliges": 0.5, "reaction_ennemis": 5,
    "regeneration": 0, "quidditch": 2, NATIVE: 2,
}

# Du plus doux au plus dur, de gauche à droite.
PRESETS = (
    # Récit (Ludo, 2026-10-30) : le preset d'accessibilité, nommé positivement.
    Preset("recit", "Récit",
           "Pour vivre l'histoire sans échouer : les ennemis ne blessent plus Harry.",
           {**_NORMAL, "invincible": True, "degats_infliges": 1.5}, exige="invincible"),
    Preset("detendu", "Détendu",
           "Pour profiter de l'histoire : Harry encaisse mieux et ses sorts portent plus.",
           {**_NORMAL, "degats_recus": 0.5, "degats_infliges": 1.5, "vie_joueur": 1.5}),
    Preset("normal", "Normal", "Le jeu tel qu'il est sorti.", _NORMAL),
    Preset("difficile", "Difficile", "Un vrai défi, pour qui a déjà fini le jeu.", _DIFFICILE),
    Preset("hardcore", "Hardcore",
           "Pour qui connaît le jeu par cœur : le plus dur qui reste jouable.", _HARDCORE),
    Preset("realiste", "Réaliste",
           "Le jeu tel qu'il est sorti, mais la première mort termine la partie.",
           _NORMAL, une_vie=True),
    Preset("impardonnable", "Impardonnable",
           "Hardcore, et la première mort termine la partie.", _HARDCORE, une_vie=True),
)
PAR_IDENT = {p.ident: p for p in PRESETS}


def idents_du_jeu(game: GameData, ini: Path | None = None) -> frozenset[str]:
    """Les réglages de difficulté que CE jeu sait régler : déclarés au catalogue,
    portés par l'ini installé (une section absente ne s'écrirait pas), plus sa
    difficulté propre s'il en a une."""
    connus = {k for k in _NORMAL if k != NATIVE}
    reglages = rc.portes_par(ini, rc.reglages_du_jeu(i for i in game.fix_settings if i in connus))
    idents = {r.ident for r in reglages}
    if game.difficulte is not None:
        idents.add(NATIVE)
    return frozenset(idents)


def valeurs_pour(preset: Preset, idents: Iterable[str]) -> dict[str, object]:
    voulus = set(idents)
    return {k: v for k, v in preset.valeurs.items() if k in voulus}


def disponible(preset: Preset, game_id: str, idents: Iterable[str]) -> bool:
    """Normal toujours ; un autre preset seulement s'il change quelque chose ici
    (et une seule vie seulement là où son mécanisme existe : Réaliste n'y change
    alors que cela)."""
    if preset.ident == "normal":
        return True
    if preset.une_vie and game_id not in UNE_VIE_POSSIBLE:
        return False
    idents = frozenset(idents)
    if preset.exige and preset.exige not in idents:
        return False
    if preset.une_vie and preset.valeurs == PAR_IDENT["normal"].valeurs:
        return True
    return valeurs_pour(preset, idents) != valeurs_pour(PAR_IDENT["normal"], idents)


def courant(valeurs: Mapping[str, object], idents: Iterable[str]) -> str:
    """Le preset que portent `valeurs` (identifiant → valeur lue), ou SUR_MESURE.

    Les presets à une seule vie ont les valeurs de Normal ou de Hardcore : ils se
    reconnaîtront à leur partie à part, pas aux réglages. Normal passe en premier :
    là où Détendu ne change rien (HP2), il a les mêmes valeurs que lui."""
    idents = frozenset(idents)
    normal = PAR_IDENT["normal"]
    for preset in (normal, *(p for p in PRESETS if p is not normal)):
        if preset.une_vie or (preset.exige and preset.exige not in idents):
            continue
        voulues = valeurs_pour(preset, idents)
        if voulues and all(valeurs.get(k) == v for k, v in voulues.items()):
            return preset.ident
    return SUR_MESURE


def changements(preset: Preset, idents: Iterable[str]) -> tuple[tuple[str, str], ...]:
    """Ce que `preset` change dans ce jeu par rapport à Normal : (réglage, choix),
    en mots affichables, dans l'ordre des réglages ; celui qu'il `exige` en tête
    (« Harry invincible » pour Récit : c'est ce qui le définit)."""
    idents = frozenset(idents)
    normal = valeurs_pour(PAR_IDENT["normal"], idents)
    lignes = []
    voulues = sorted(valeurs_pour(preset, idents).items(), key=lambda kv: kv[0] != preset.exige)
    for ident, valeur in voulues:
        if normal.get(ident) == valeur:
            continue
        if ident == NATIVE:
            lignes.append((tr("Difficulté du jeu"), tr(difficulte_jeu.NIVEAUX[int(str(valeur))])))
            continue
        reglage = REGLAGES[ident]
        if not reglage.choix:
            # Un interrupteur allumé se dit par son nom seul (« Harry invincible »).
            lignes.append((rc.textes(reglage)[0], ""))
            continue
        lignes.append((rc.textes(reglage)[0], rc.libelle_choix(reglage, valeur)))
    return tuple(lignes)


# Le cran de chaque preset sur le cadran, le même dans tous les jeux. Les
# presets à une seule vie n'y ont pas de cran : ils ont les valeurs de Normal ou
# de Hardcore.
NIVEAUX: Mapping[str, float] = {"recit": 3, "detendu": 25, "normal": 40, "difficile": 60,
                                "hardcore": 82}
# Le plus doux et le plus dur que les réglages du jeu permettent (Harry
# invincible mis à part : c'est le cran de Récit).
_PLANCHER = 10.0
_PLAFOND = 100.0


def _nombre(valeur: object, defaut: float) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, int | float):
        return defaut
    return float(valeur)


def _terme(ident: str, valeur: object) -> float:
    """Ce que pèse UN réglage dans la rigueur : 0 au jeu tel que livré, positif
    plus dur. Les multiplicateurs comptent en doublements (×2 et ×0,5 pèsent
    autant, en sens contraires)."""
    if ident == NATIVE or ident == "quidditch":
        return (0.5 if ident == NATIVE else 0.6) * _nombre(valeur, 0)
    if ident == "regeneration":
        return 1.2 * (1 - _nombre(valeur, 1))
    poids = {"degats_recus": 1.0, "degats_infliges": -1.0, "reaction_ennemis": 0.6,
             "vie_joueur": -1.0}.get(ident)
    if poids is None:
        return 0.0
    return poids * math.log2(max(_nombre(valeur, 1), 0.01))


def rigueur(valeurs: Mapping[str, object]) -> float:
    """La difficulté brute de ces réglages, sans échelle : seul l'ordre compte."""
    return sum(_terme(ident, valeur) for ident, valeur in valeurs.items())


def _extremes(idents: Iterable[str]) -> tuple[float, float]:
    """La rigueur du plus doux et du plus dur que ces réglages permettent."""
    doux = dur = 0.0
    for ident in idents:
        if ident == NATIVE:
            choix: Iterable[object] = range(len(difficulte_jeu.NIVEAUX))
        elif ident in REGLAGES and REGLAGES[ident].choix:
            choix = REGLAGES[ident].choix
        else:
            continue
        termes = [_terme(ident, c) for c in choix]
        doux += min(termes)
        dur += max(termes)
    return doux, dur


def sur_mesure_utile(idents: Iterable[str]) -> bool:
    """Faux quand chaque combinaison que ces réglages permettent est déjà un
    preset : HP1, son Quidditch seul et ses trois crans (Normal, Difficile,
    Hardcore). « Sur mesure » n'y redirait que les cartes (Ludo, 2026-10-31)."""
    idents = frozenset(idents)
    listes: list[list[tuple[str, object]]] = []
    for ident in sorted(idents):
        choix: Iterable[object]
        if ident == NATIVE:
            choix = range(len(difficulte_jeu.NIVEAUX))
        elif REGLAGES[ident].choix:
            choix = REGLAGES[ident].choix
        else:
            choix = (False, True)
        listes.append([(ident, c) for c in choix])
    if math.prod(len(liste) for liste in listes) > 512:
        return True
    return any(courant(dict(combo), idents) == SUR_MESURE for combo in itertools.product(*listes))


def reperes(game_id: str, idents: Iterable[str]) -> tuple[tuple[Preset, float], ...]:
    """Les presets proposés dans ce jeu qui ont un cran sur le cadran, du plus
    doux au plus dur, avec leur cran."""
    idents = frozenset(idents)
    return tuple((p, NIVEAUX[p.ident]) for p in PRESETS
                 if p.ident in NIVEAUX and disponible(p, game_id, idents))


def niveau(valeurs: Mapping[str, object], game_id: str, idents: Iterable[str]) -> float:
    """Le niveau de défi de ces réglages, de 0 à 100 : le cran d'un preset quand
    ce sont ses valeurs, sinon une place entre les crans des presets du jeu."""
    idents = frozenset(idents)
    voulues = {k: v for k, v in valeurs.items() if k in idents}
    if "invincible" in idents and voulues.get("invincible") is True:
        return NIVEAUX["recit"]
    # Normal d'abord : un preset qui a sa rigueur ne le remplace pas.
    points: dict[float, float] = {}
    for preset, cran in sorted(reperes(game_id, idents), key=lambda pc: pc[0].ident != "normal"):
        if preset.exige != "invincible":
            points.setdefault(round(rigueur(valeurs_pour(preset, idents)), 6), cran)
    doux, dur = _extremes(idents)
    if doux < min(points) - 1e-6:
        points[doux] = _PLANCHER
    if dur > max(points) + 1e-6:
        points[dur] = _PLAFOND
    courbe = sorted(points.items())
    # Arrondie comme les points : les valeurs d'un preset tombent PILE sur son cran.
    r = round(rigueur(voulues), 6)
    if r <= courbe[0][0]:
        return courbe[0][1]
    for (r0, n0), (r1, n1) in itertools.pairwise(courbe):
        if r <= r1:
            return n0 + (n1 - n0) * (r - r0) / (r1 - r0)
    return courbe[-1][1]


def situer(valeur: float, crans: Sequence[tuple[Preset, float]]) -> str:
    """Une ligne qui place un niveau sur mesure parmi les presets du jeu
    (« Entre Difficile et Hardcore ») : jamais de chiffre."""
    if not crans:
        return ""
    for preset, cran in crans:
        if abs(valeur - cran) < 0.5:
            return tr("Au niveau de {}").format(tr(preset.nom))
    if valeur > crans[-1][1]:
        return tr("Au-delà de {}").format(tr(crans[-1][0].nom))
    if valeur < crans[0][1]:
        return tr("En deçà de {}").format(tr(crans[0][0].nom))
    for (doux, c0), (dur, c1) in itertools.pairwise(crans):
        if c0 < valeur < c1:
            return tr("Entre {} et {}").format(tr(doux.nom), tr(dur.nom))
    return ""


def lire(game: GameData, config: Config, ini: Path | None, idents: Iterable[str]) -> dict[str, object]:
    """Les valeurs actuelles des réglages de difficulté de ce jeu ; un réglage
    illisible est absent (le preset courant devient alors « Sur mesure »)."""
    valeurs: dict[str, object] = {}
    for ident in idents:
        if ident == NATIVE:
            rang = difficulte_jeu.lire(game, config)
            if rang is not None:
                valeurs[NATIVE] = rang
            continue
        if ini is None:
            continue
        try:
            valeurs[ident] = rc.lire(ini, REGLAGES[ident]).valeur
        except (OSError, ValueError) as exc:
            log.warning("Difficulté : %s illisible (%s)", ident, exc)
    return valeurs


def appliquer(preset: Preset, game: GameData, config: Config, ini: Path | None,
              idents: Iterable[str]) -> list[str]:
    """Écrit les valeurs du preset ; rend les réglages qui n'ont PAS pu l'être
    (liste vide : tout est écrit). Rien n'est écrit au lancement du jeu."""
    rates = []
    for ident, valeur in valeurs_pour(preset, idents).items():
        if ident == NATIVE:
            if not difficulte_jeu.ecrire(game, config, int(str(valeur))):
                rates.append(ident)
            continue
        if ini is None:
            rates.append(ident)
            continue
        try:
            rc.ecrire(ini, REGLAGES[ident], valeur)
        except (OSError, ValueError) as exc:
            log.warning("Difficulté : %s non écrit (%s)", ident, exc)
            rates.append(ident)
    return rates

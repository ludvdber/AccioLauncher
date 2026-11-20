"""Les presets de difficulté de la 1.4 : Récit (accessibilité, Harry invincible),
Détendu, Normal, Difficile, Hardcore, et trois presets à une seule vie, Réaliste,
Impardonnable et Avada Kedavra.

Tranché par Ludo le 2026-10-30 (atelier, `notes/DIFFICULTE_1.4.md` § 4) : des
presets aux noms clairs, et « Sur mesure » (les réglages un par un sous les presets). Un
preset n'est qu'un jeu de valeurs pour des réglages qui existent déjà : ceux du
correctif (`[Accio.Hardcore]`, le Quidditch de HP1/HP2) et la difficulté
propre du jeu (`difficulte_jeu`, HP2). Rien de neuf n'est écrit ailleurs.

Les valeurs sont COMMUNES à tous les jeux, comme les préréglages d'image :
chaque jeu n'en garde que les réglages qu'il déclare. Un preset qui ne change
rien dans un jeu n'y est pas proposé.

AUCUN preset ne retire de sort (Ludo, 2026-10-30) : un sort retiré peut bloquer
la partie (une leçon, un défi qui le demande). `sorts_retires` reste un réglage
à part, dans « Sur mesure ».

Une seule vie (Ludo, 2026-10-30, refaite le 2026-11-20) : dans les trois, la
première mort termine la partie (`une_vie` : la partie se joue dans un dossier à
part, ses sauvegardes sont effacées par la DLL à la première mort, C4) ;
sauvegarder et revenir reste permis.
- Réaliste n'écrit AUCUNE valeur : la difficulté que le joueur a réglée, et la vie
  de Harry telle quelle ; seule la vie unique s'ajoute.
- Impardonnable = Hardcore, et le premier coup reçu par le héros joué est fatal
  (`OneHit` du correctif : le ×10 des dégâts reçus ne tuait pas d'un coup, HP2
  allant jusqu'à 600 de vie et buvant sa potion seul).
- Avada Kedavra, « pour le fun et le délire du tryharder » : chaque réglage au plus
  dur (réaction des ennemis au maximum là où elle existe), et un coup fatal.
`UNE_VIE_POSSIBLE` ne nomme que les jeux où la mort a été VUE finir la vie ; le
mode n'est proposé que si le correctif installé le connaît (`une_vie_proposee`),
et un coup fatal seulement s'il porte `OneHit` (`un_coup_propose`). Le mode ne se
lit pas aux valeurs mais aux clés posées (`courant(une_vie=…, un_coup=…)`).

Ce que dit un preset pour un jeu se CALCULE depuis les réglages (libellé et
choix affichés) : une phrase écrite à la main finirait par mentir.

Le niveau de défi (cadran de l'onglet Difficulté, maquette validée par Ludo le 2026-10-31)
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

from src.core import difficulte_jeu, une_vie
from src.core import reglages_correctif as rc
from src.core.reglages_table import REGLAGES
from src.core.config import Config
from src.core.game_data import GameData
from src.core.i18n import tr

log = logging.getLogger(__name__)

# La difficulté propre du jeu (bloc `difficulty` du catalogue) : un rang 0..2.
NATIVE = "difficulte_native"
SUR_MESURE = "sur_mesure"

# Les jeux où la première mort a été VUE finir la vie (atelier,
# `notes/IDEES_A_VOIR_EN_JEU.md` et `DIFFICULTE_1.4.md` § 8) : HP1, HP2, HP3
# (2026-11-14 ; héros joué le 2026-11-18), HP4 (Harry choisi, 2026-11-18),
# HP5 (KO forgé, 2026-11-14 ; `une_vie.MODES` le dit au joueur), HP6
# (2026-11-14, relance et nouvelle vie le 2026-11-18).
UNE_VIE_POSSIBLE: frozenset[str] = frozenset(une_vie.MODES)


@dataclass(frozen=True)
class Preset:
    ident: str
    nom: str            # clé tr()
    phrase: str         # clé tr() : ce que le preset veut dire, tous jeux confondus
    valeurs: Mapping[str, object]
    une_vie: bool = False   # la première mort termine la partie
    un_coup: bool = False   # et le premier coup reçu par le héros joué est fatal (`OneHit`)
    # Le réglage sans lequel le preset n'a pas de sens (Récit sans invincibilité
    # ne serait qu'un Détendu mal nommé).
    exige: str = ""


# Pas de `sorts_retires` : aucun preset n'y touche, le choix du joueur reste.
_NORMAL: dict[str, object] = {
    "degats_recus": 1, "degats_infliges": 1, "reaction_ennemis": 1,
    "vie_joueur": 1, "regeneration": 1, "invincible": False, "quidditch": 0, NATIVE: 0,
    "sorts_par_creature": 1, "jauge_creature": 1,
}
# Difficile (Ludo, 2026-10-30) : un cran entre la difficulté d'origine la plus
# haute et Hardcore.
_DIFFICILE: dict[str, object] = {
    **_NORMAL, "degats_recus": 1.5, "degats_infliges": 0.75, "reaction_ennemis": 1.5,
    "regeneration": 0.5, "quidditch": 1, NATIVE: 2, "sorts_par_creature": 1.5, "jauge_creature": 0.7,
}
# Hardcore (Ludo, 2026-10-30) : bien au-delà. Réaction ×5 = attentes des ennemis
# divisées par 5 (0,4 s entre deux attaques au lieu de 2 s) : il reste une marge,
# minime, pour attaquer. Le sur mesure va encore plus loin (×10, ×5 de dégâts).
_HARDCORE: dict[str, object] = {
    **_NORMAL, "degats_recus": 3, "degats_infliges": 0.5, "reaction_ennemis": 5,
    "regeneration": 0, "quidditch": 2, NATIVE: 2, "sorts_par_creature": 2, "jauge_creature": 0.5,
}
# Avada Kedavra (Ludo, 2026-11-20) : chaque réglage à son choix le plus dur (`REGLAGES`). Les dégâts
# reçus et la vie de Harry n'y changent plus rien (un coup est fatal), ils restent au plus dur pour que
# la carte dise la même chose que le cadran.
_AVADA: dict[str, object] = {
    **_HARDCORE, "degats_recus": 5, "degats_infliges": 0.25, "reaction_ennemis": 10, "vie_joueur": 0.25,
    "sorts_par_creature": 3,
}

# Du plus doux au plus dur, de gauche à droite.
PRESETS = (
    # Récit (Ludo, 2026-10-30) : le preset d'accessibilité, nommé positivement.
    Preset("recit", "Récit",
           "Pour vivre l'histoire sans échouer : les ennemis ne blessent plus Harry.",
           {**_NORMAL, "invincible": True, "degats_infliges": 1.5}, exige="invincible"),
    Preset("detendu", "Détendu",
           "Pour profiter de l'histoire : Harry encaisse mieux et ses sorts portent plus.",
           {**_NORMAL, "degats_recus": 0.5, "degats_infliges": 1.5, "vie_joueur": 1.5,
            "sorts_par_creature": 0.6, "jauge_creature": 1.5}),
    Preset("normal", "Normal", "Le jeu tel qu'il est sorti.", _NORMAL),
    Preset("difficile", "Difficile", "Un vrai défi, pour qui a déjà fini le jeu.", _DIFFICILE),
    Preset("hardcore", "Hardcore",
           "Pour qui connaît le jeu par cœur : le plus dur qui reste jouable.", _HARDCORE),
    Preset("realiste", "Réaliste",
           "Votre difficulté, et une seule vie : Harry garde toute sa santé, mais la partie s'arrête "
           "quand elle tombe à zéro.", {}, une_vie=True),
    Preset("impardonnable", "Impardonnable",
           "Hardcore, et le premier coup reçu est fatal.", _HARDCORE, une_vie=True, un_coup=True),
    Preset("avada_kedavra", "Avada Kedavra",
           "Pour les acharnés : chaque réglage au plus dur, et le premier coup reçu est fatal.",
           _AVADA, une_vie=True, un_coup=True),
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
    """Les valeurs du preset que ce jeu sait régler. Là où le facteur de dégâts
    reçus s'applique, la difficulté propre du jeu reste Facile (rang 0) : les deux
    se multiplient (HP2 : 7,5 fois le jeu livré en Hardcore), Ludo 2026-11-19."""
    voulus = set(idents)
    valeurs = {k: v for k, v in preset.valeurs.items() if k in voulus}
    if NATIVE in valeurs and "degats_recus" in voulus:
        valeurs[NATIVE] = 0
    return valeurs


def disponible(preset: Preset, game_id: str, idents: Iterable[str]) -> bool:
    """Normal toujours ; un autre preset seulement s'il change quelque chose ici
    (et une seule vie seulement là où son mécanisme existe : Réaliste n'y change
    alors que cela)."""
    if preset.ident == "normal":
        return True
    idents = frozenset(idents)
    if preset.une_vie:
        # Réaliste partout où le mode existe ; un preset à un coup, sauf s'il n'écrit ici que ce
        # qu'écrit déjà un autre avant lui (Avada Kedavra là où rien ne va au-delà de Hardcore).
        if game_id not in UNE_VIE_POSSIBLE:
            return False
        avant = PRESETS[:PRESETS.index(preset)]
        return all(valeurs_pour(p, idents) != valeurs_pour(preset, idents)
                   for p in avant if p.une_vie and p.un_coup == preset.un_coup)
    if preset.exige and preset.exige not in idents:
        return False
    return valeurs_pour(preset, idents) != valeurs_pour(PAR_IDENT["normal"], idents)


# Le preset dont le cran colore chaque carte à une seule vie (Réaliste n'a pas de valeurs à lui).
BASE_UNE_VIE: Mapping[str, str] = {"realiste": "normal", "impardonnable": "hardcore", "avada_kedavra": "hardcore"}


def courant(valeurs: Mapping[str, object], idents: Iterable[str], une_vie: bool = False,
            un_coup: bool = False) -> str:
    """Le preset que portent `valeurs` (identifiant → valeur lue), ou SUR_MESURE.

    Les presets à une seule vie se reconnaissent à leur partie à part (`une_vie` :
    les clés du mode sont posées). Sans coup fatal, c'est Réaliste quelles que soient
    les valeurs (il garde celles du joueur) ; avec, Impardonnable ou Avada Kedavra à
    leurs valeurs, « Sur mesure » sinon (le mode reste actif). Normal passe en
    premier : là où Détendu ne change rien (HP2), il a les mêmes valeurs que lui.
    Sans aucun réglage (HP3), le jeu est tel qu'il est sorti : Normal."""
    idents = frozenset(idents)
    if une_vie:
        if not un_coup:
            return "realiste"
        for preset in PRESETS:
            if preset.un_coup and all(valeurs.get(k) == v for k, v in valeurs_pour(preset, idents).items()):
                return preset.ident
        return SUR_MESURE
    if not idents:
        return "normal"
    normal = PAR_IDENT["normal"]
    for preset in (normal, *(p for p in PRESETS if p is not normal)):
        if preset.une_vie or (preset.exige and preset.exige not in idents):
            continue
        voulues = valeurs_pour(preset, idents)
        if voulues and all(valeurs.get(k) == v for k, v in voulues.items()):
            return preset.ident
    return SUR_MESURE


_SANS_EFFET_A_UN_COUP = frozenset({"degats_recus", "vie_joueur"})


def changements(preset: Preset, idents: Iterable[str]) -> tuple[tuple[str, str], ...]:
    """Ce que `preset` change dans ce jeu par rapport à Normal : (réglage, choix),
    en mots affichables, dans l'ordre où la page montre les réglages (la
    difficulté propre du jeu d'abord) ; celui qu'il `exige` en tête (« Harry
    invincible » pour Récit : c'est ce qui le définit). Un preset à un coup fatal le
    dit en tête, et ne dit ni les dégâts reçus ni la vie de Harry : ils n'y comptent plus."""
    idents = frozenset(idents)
    normal = valeurs_pour(PAR_IDENT["normal"], idents)
    lignes = [(tr("Un coup reçu est fatal"), "")] if preset.un_coup else []
    if preset.un_coup:
        normal = {**normal, **{k: v for k, v in valeurs_pour(preset, idents).items() if k in _SANS_EFFET_A_UN_COUP}}
    rangs = {ident: rang for rang, ident in enumerate(REGLAGES)}
    voulues = sorted(valeurs_pour(preset, idents).items(),
                     key=lambda kv: (kv[0] != preset.exige, kv[0] != NATIVE, rangs.get(kv[0], 0)))
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
             "vie_joueur": -1.0, "sorts_par_creature": 0.6, "jauge_creature": -0.4}.get(ident)
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


def une_vie_proposee(game: GameData, config: Config) -> bool:
    """Les presets à une seule vie se proposent dans ce jeu : sa mort est VUE, et
    le correctif installé porte les clés du mode dans un dossier qu'il accepte."""
    return game.id in UNE_VIE_POSSIBLE and une_vie.possible(game, une_vie.ini(game, config.install_path))


def un_coup_propose(game: GameData, config: Config) -> bool:
    """Impardonnable et Avada Kedavra : le mode est proposé, et le correctif installé porte `OneHit`
    (les archives d'avant le 2026-11-20 ne l'ont pas : un coup n'y tuerait pas)."""
    return une_vie_proposee(game, config) and une_vie.un_coup_possible(une_vie.ini(game, config.install_path))


def une_vie_active(game: GameData, config: Config) -> bool:
    return game.id in UNE_VIE_POSSIBLE and une_vie.actif(une_vie.ini(game, config.install_path))


def un_coup_actif(game: GameData, config: Config) -> bool:
    return game.id in UNE_VIE_POSSIBLE and une_vie.un_coup_actif(une_vie.ini(game, config.install_path))


def proposes(game: GameData, config: Config, idents: Iterable[str]) -> tuple[Preset, ...]:
    """Les presets que ce jeu propose, dans l'ordre de `PRESETS`."""
    idents = frozenset(idents)
    vie = une_vie_proposee(game, config)
    coup = vie and un_coup_propose(game, config)
    return tuple(p for p in PRESETS if disponible(p, game.id, idents)
                 and (vie or not p.une_vie) and (coup or not p.un_coup))


def au_lancement(game: GameData, config: Config) -> str:
    """Le preset que tient le jeu qu'on lance, "" si aucun (sur mesure,
    réglages illisibles) : noté avec la partie (`sauvegardes.attribuer`), il
    décide des médailles « Terminé en … » (`succes`)."""
    dossier_exe = Path(config.install_path) / Path(game.executable).parent
    ini = rc.ini_du_correctif(dossier_exe) if game.fix_settings else None
    idents = idents_du_jeu(game, ini)
    ident = courant(lire(game, config, ini, idents), idents, une_vie_active(game, config),
                    un_coup_actif(game, config))
    return "" if ident == SUR_MESURE else ident


def appliquer(preset: Preset, game: GameData, config: Config, ini: Path | None,
              idents: Iterable[str]) -> list[str]:
    """Écrit les valeurs du preset, et entre dans le mode à une seule vie ou en
    sort ; rend les réglages qui n'ont PAS pu l'être (liste vide : tout est
    écrit, `"une_vie"` pour les clés du mode). Rien n'est écrit au lancement du jeu."""
    rates = []
    vie = une_vie.ini(game, config.install_path) if game.id in UNE_VIE_POSSIBLE else None
    if vie is not None:
        if preset.une_vie:
            if not une_vie.entrer(game, vie, un_coup=preset.un_coup):
                rates.append("une_vie")
        elif une_vie.actif(vie) and not une_vie.sortir(vie):
            rates.append("une_vie")
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

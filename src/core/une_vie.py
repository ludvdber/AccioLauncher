r"""Une seule vie (Réaliste, Impardonnable) : ce que le launcher pose pour que le
correctif joue la partie dans un dossier à part (atelier, `notes/DIFFICULTE_1.4.md`
§ 6, § 8 et § 9, points 1 et 1 bis ; décisions C4 et C5 de Ludo).

**Le launcher ne pose que trois clés**, `[Accio.Game]` de l'ini du correctif
(`winmm.ini` de HP1/HP2, `dinput8.ini` de HP3, `d3d9.ini` de HP4 à HP6) :
`OneLife` (1 = la fin rend le jeu à son menu, 2 = il se ferme), `DeathCounter=1`
(une ligne par mort dans `accio_morts.tsv`, `compteur_morts`) et `OneLifeSaves`,
le dossier de la partie. C'est la DLL qui le donne au moteur, en mémoire :
**aucun ini du JEU n'est touché** (VU le 2026-11-14 : `SavePath` changé dans
`HP.ini` ne décidait rien). Les parties du joueur ne sont ni lues ni écrites.

**Le launcher n'efface jamais rien.** À la première mort, la DLL vide le
dossier et y pose la marque `une_vie_finie` ; une partie lancée ensuite est
une nouvelle vie, gardée dans le même dossier (C4). La DLL ne vide qu'un
dossier nommé `Save_UneVie` ou rangé dedans : tout autre chemin laisse le mode
coupé. Elle ne lit pas non plus un chemin que la page de codes de Windows ne
sait pas écrire, ni, pour HP4 à HP6 qui composent le leur en octets, plus long
que 150 caractères : le launcher ne propose alors pas le mode.

**Où** (un dossier par jeu, jamais à côté de celui du joueur sous le même nom :
`sauvegardes.json` range les parties par chemin relatif, celles du mode ne s'y
mêlent pas). Un chemin FIXE : celui qui est posé dans l'ini est celui où le
launcher relit la vie ; un dossier qui suivrait celui du joueur changerait de
place le jour où le jeu crée le sien (HP3, nom selon la langue) :

    HP1        <Documents>\Harry Potter\Save_UneVie
    HP3        <Documents>\Harry Potter et le prisonnier d'Azkaban\Save_UneVie
    HP2        <Documents>\Harry Potter II\Save_UneVie\Slot7, lancé avec -SAVESLOT=7
               (ses emplacements vont de 1 à 6 ; la DLL remet à la fermeture
               l'emplacement que `Game.ini` nommait avant, VU le 2026-11-18)
    HP4 à HP6  <AppData\Local>\Save_UneVie\HP4 (HP5, HP6) : le jeu y crée
               `Electronic Arts\<titre>\` comme sous AppData\Local

**Ce qui finit la vie, VU en jeu** (fiches de l'atelier, `IDEES_A_VOIR_EN_JEU.md`) :
la mort de Harry (HP1, HP2, le 2026-11-14), celle du héros JOUÉ (HP3, Harry
VU le 2026-11-18 ; un compagnon que personne ne joue tombe en `chute_equipier`
et la vie continue, C5), la chute du personnage choisi (HP4, Harry choisi VU
le 2026-11-18 ; un équipier tombe en `chute_equipier`), le KO (HP6 le
2026-11-14 et le 2026-11-18 ; HP5 sur un KO forgé seulement, d'où sa note).
Ce que le jeu fait ENSUITE est dit au joueur (`Mode.apres`) : HP2 n'a pas de
menu en jeu et HP4 pas de retour à la pensine, ils se ferment ; HP5 se ferme
aussi (`OneLife=2`, la voie sûre tant qu'un vrai duel perdu n'est pas vu : le
même KO forgé trop tôt après un chargement fermait le jeu pendant le retour au
menu) ; le menu de HP6 rouvert ne répond plus à « Continuer » ni à « Profils ».
"""

import logging
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from src.core import reglages_correctif as rc
from src.core import sauvegardes
from src.core.catalogue_blocs import Sauvegardes
from src.core.game_data import GameData

log = logging.getLogger(__name__)

SECTION = "Accio.Game"
CLE_MODE = "OneLife"
CLE_COMPTEUR = "DeathCounter"
CLE_DOSSIER = "OneLifeSaves"
NOM = "Save_UneVie"
MARQUE = "une_vie_finie"
_LONGUEUR_MAX = 150     # HP4 à HP6 (`SHGetFolderPathA` détourné, chemin en octets)
# Ce qu'un chemin ne peut pas porter dans l'ini : le correctif coupe la valeur
# à un commentaire de fin de ligne (`reglages_correctif._valeur`).
_INTERDITS = (";", "//", "\r", "\n", "\x00")
# HP2 : l'emplacement du mode, hors des six du jeu ; la reprise et la nouvelle partie.
_EMPLACEMENT_HP2 = 7
REPRISE_HP2 = ("-LOADGAME=0", f"-SAVESLOT={_EMPLACEMENT_HP2}")
NOUVELLE_HP2 = ("PrivetDr.unr", f"-SAVESLOT={_EMPLACEMENT_HP2}")


@dataclass(frozen=True)
class Mode:
    valeur: int     # OneLife
    apres: str      # clé tr() : ce que le joueur voit après la première mort
    note: str = ""  # clé tr() : ce qui finit la vie quand ce n'est pas « Harry »
    # Le dossier du jeu sous Documents quand le catalogue le nomme par un motif
    # (HP3 : un nom par langue) : le mode en prend un, toujours le même.
    parent: str = ""


# Les libellés du JEU ne sont pas cités, sauf « Continuer » de HP6 (sa traduction suit
# celle du jeu) : ils changent avec la langue du jeu, pas avec celle du launcher.
_AU_MENU = "Le jeu revient à son menu, où une nouvelle partie ouvre une nouvelle vie."
_SE_FERME = "Le jeu se ferme ; la partie suivante commence une nouvelle vie."
MODES: dict[str, Mode] = {
    "hp1": Mode(1, _AU_MENU),
    "hp2": Mode(1, _SE_FERME),
    "hp3": Mode(1, _AU_MENU,
                "Seule la mort du héros que vous jouez compte : un compagnon qui tombe se relève.",
                parent="Harry Potter et le prisonnier d'Azkaban"),
    "hp4": Mode(1, _SE_FERME,
                "Seule la chute du personnage choisi compte : un équipier qui tombe se relève."),
    "hp5": Mode(2, _SE_FERME,
                "Encore en essai sur un vrai duel perdu : ce qui ne va pas se signale sur le Discord "
                "du projet."),
    "hp6": Mode(1, "Le jeu revient à son menu, où « Continuer » ne répond plus : une nouvelle partie "
                   "ouvre une nouvelle vie."),
}


# ── Où ──

def dossier(game: GameData) -> Path | None:
    """`OneLifeSaves` pour ce jeu, ou None s'il n'a pas le mode ou pas de racine."""
    spec = game.sauvegardes
    if spec is None or game.id not in MODES:
        return None
    base = sauvegardes.racines().get(spec.racine)
    if base is None:
        return None
    if spec.racine == "localappdata":
        return base / NOM / game.id.upper()
    parent = _parent(game, spec)
    if parent is None:
        return None
    mode = base / parent / NOM
    return mode / f"Slot{_EMPLACEMENT_HP2}" if game.id == "hp2" else mode


def _parent(game: GameData, spec: Sauvegardes) -> str | None:
    """Le dossier du jeu sous Documents : celui que le catalogue nomme, ou
    `Mode.parent` quand il le nomme par un motif. Jamais celui qu'on trouve sur
    le disque : il dépend de la langue jouée (en-tête du module)."""
    nomme = Path(spec.dossiers[0]).parent.as_posix() if spec.dossiers else ""
    if nomme not in ("", ".") and not any(c in nomme for c in "*?["):
        return nomme
    return MODES[game.id].parent or None


def spec_du_mode(game: GameData) -> Sauvegardes | None:
    """Les sauvegardes de la partie à une seule vie, avec des chemins relatifs
    qui ne peuvent pas être ceux du joueur (`Save_UneVie/…`, `Electronic Arts/…`)."""
    spec, ou = game.sauvegardes, dossier(game)
    if spec is None or ou is None:      # `dossier` : jeu sans mode, ou racine inconnue
        return None
    if spec.racine == "localappdata":
        return replace(spec, dossiers=(f"{NOM}/{game.id.upper()}",),
                       fichiers=f"{spec.dossiers[0]}/{spec.fichiers}")
    parent = _parent(game, spec)
    if parent is None:
        return None
    return replace(spec, dossiers=(parent,), fichiers=f"{NOM}/{spec.fichiers}")


def pour_le_jeu(chemin: Path, plafond: bool = False) -> str | None:
    """Le chemin tel que le JEU le lira, ou None si le correctif le refuserait ;
    `plafond` : 150 caractères au plus (HP4 à HP6)."""
    if sys.platform == "win32":
        texte, codage = str(chemin), "mbcs"
    else:
        from src.core import compat
        texte, codage = compat.chemin_windows(chemin), compat.encodage_ansi()
    if (plafond and len(texte) > _LONGUEUR_MAX) or any(c in texte for c in _INTERDITS):
        return None
    try:
        texte.encode(codage)
    except (UnicodeEncodeError, LookupError):
        return None
    return texte


# ── Ce que porte l'ini ──

def ini(game: GameData, install_path: Path) -> Path | None:
    """L'ini du correctif de ce jeu, s'il porte les clés du mode."""
    if game.id not in MODES:
        return None
    chemin = rc.ini_du_correctif(Path(install_path) / Path(game.executable).parent)
    return chemin if rc.valeur_posee(chemin, SECTION, CLE_MODE) is not None else None


def possible(game: GameData, chemin_ini: Path | None) -> bool:
    """Le jeu a le mode, son correctif le connaît, et son dossier s'écrit."""
    if chemin_ini is None or game.id not in MODES:
        return False
    ou = dossier(game)
    return ou is not None and _pour(game, ou) is not None


def _pour(game: GameData, ou: Path) -> str | None:
    return pour_le_jeu(ou, plafond=game.sauvegardes is not None and game.sauvegardes.racine == "localappdata")


def actif(chemin_ini: Path | None) -> bool:
    """La DLL jouera la prochaine partie en une seule vie."""
    if chemin_ini is None:
        return False
    mode = rc.valeur_posee(chemin_ini, SECTION, CLE_MODE)
    return mode not in (None, "", "0") and bool(rc.valeur_posee(chemin_ini, SECTION, CLE_DOSSIER))


@dataclass(frozen=True)
class Etat:
    en_cours: bool = False   # une partie du mode est gardée dans son dossier
    finie: bool = False      # la dernière vie s'est terminée (marque de la DLL)


def etat(game: GameData) -> Etat:
    """Marque présente = aucune vie en cours (la DLL retire ce que le jeu
    réécrit en sortant au lancement suivant) ; marque absente et des
    sauvegardes = une vie en cours."""
    ou = dossier(game)
    if ou is None:
        return Etat()
    if (ou / MARQUE).is_file():
        return Etat(finie=True)
    return Etat(en_cours=bool(sauvegardes.fichiers(spec_du_mode(game))))


# ── Entrer, sortir ──

def entrer(game: GameData, chemin_ini: Path) -> bool:
    """Pose les trois clés ; `OneLife` en DERNIER : un échec en route laisse le
    mode coupé. Le dossier est créé ici pour que la page le lise aussitôt
    (la DLL sait aussi le créer)."""
    ou = dossier(game)
    texte = _pour(game, ou) if ou is not None else None
    if ou is None or texte is None:
        return False
    try:
        ou.mkdir(parents=True, exist_ok=True)
        rc.poser_valeur(chemin_ini, SECTION, CLE_DOSSIER, texte)
        rc.poser_valeur(chemin_ini, SECTION, CLE_COMPTEUR, "1")
        rc.poser_valeur(chemin_ini, SECTION, CLE_MODE, str(MODES[game.id].valeur))
    except (OSError, ValueError):
        log.warning("Une seule vie : clés non posées dans %s", chemin_ini, exc_info=True)
        return False
    return True


def sortir(chemin_ini: Path) -> bool:
    """Remet ce que l'ini livré porte (pas une valeur retenue) ; `OneLife` en
    PREMIER. Rien n'est effacé : la partie du mode reste dans son dossier."""
    origine = rc.chemin_origine(chemin_ini)
    try:
        for cle, defaut in ((CLE_MODE, "0"), (CLE_COMPTEUR, "0"), (CLE_DOSSIER, "")):
            if rc.valeur_posee(chemin_ini, SECTION, cle) is None:
                continue
            livree = rc.valeur_posee(origine, SECTION, cle) if origine.is_file() else None
            rc.poser_valeur(chemin_ini, SECTION, cle, livree if livree is not None else defaut)
    except (OSError, ValueError):
        log.warning("Une seule vie : clés non rendues dans %s", chemin_ini, exc_info=True)
        return False
    return True


# ── Au lancement ──

def pour_la_partie(game: GameData, install_path: Path) -> GameData:
    """Le jeu tel que la partie le joue : avec les sauvegardes du mode quand il
    est actif (reprise, relevé avant et après la partie), sinon tel quel."""
    if not actif(ini(game, install_path)):
        return game
    spec = spec_du_mode(game)
    return game if spec is None else replace(game, sauvegardes=spec)


def arguments(game: GameData) -> tuple[str, ...] | None:
    """Ce que le mode impose à la ligne de commande (`game` vu par
    `pour_la_partie`), None s'il n'impose rien. HP2 : toujours son emplacement
    7, reprise s'il y a une partie (VU, essai 22b), sinon nouvelle partie à
    Privet Drive (VU, essai 44) ; sans eux, le menu de son lanceur choisirait un
    emplacement du joueur."""
    if game.id != "hp2" or game.sauvegardes is None or NOM not in game.sauvegardes.fichiers:
        return None
    return REPRISE_HP2 if sauvegardes.fichiers(game.sauvegardes) else NOUVELLE_HP2

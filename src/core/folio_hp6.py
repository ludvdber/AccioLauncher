"""Le folio de HP6 : ce que `HPHBP0` dit de la partie du Prince de sang-mêlé.

Relevé le 2026-10-15 sur la sauvegarde de Ludo, en LECTURE seule, et VU contre
le menu de pause du jeu (« écussons 7 / 125 », « mini-écussons 3 / 25 (372) ») :
`Harry-Potter-PC-Fix/notes/HP6.md`, « Mission d'analyse ».

    0x00   « 20CM », taille, 0x38, taille du corps
    0x20   année, mois, jour de la semaine, jour, heure, minute, seconde
           (entiers 32 bits petit-boutistes), écrits par le jeu
    0x54   corps « HPHB2.00WN32 », entiers GROS-boutistes
    0x60   nombre de sections, puis (clé, décalage, nombre) par section
    corps + décalage : `nombre` paires (clé, valeur) de 8 octets

Les décalages partent du DÉBUT DU CORPS (0x54) : c'est la seule base où toutes
les sections se lisent en paires (clé, valeur), celles d'une seule entrée
comprises (`Minicrestometer` = (« MiniCrestsCollected », 372)). Lu depuis
0x58, chaque paire chevauchait la suivante, d'où les deux appariements
possibles notés le 2026-10-15 ; tranché le même soir par cette structure, et
c'est l'appariement vraisemblable (prologue fini, chapitre 2 en cours).

Une clé est le hachage ELF (PJW) du nom en minuscules (« spellunlock_lumos »),
une valeur d'état vaut 15 (fini), 5 (en cours ou acquis) ou 0. Dans
`CrestsCollected`, la clé est le rang de l'écusson (0 à 124) et la valeur
son identifiant d'objet, 0 s'il reste à trouver. Une seule partie par fichier.
"""

import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from src.core import folio, images_ea

log = logging.getLogger(__name__)

ECUSSONS = 125            # le « / 125 » du menu de pause
FINI, EN_COURS = 15, 5
_CORPS = 0x54
_TAILLE_MAX = 1024 * 1024  # 20 Ko chez Ludo

# Les sorts du jeu, dans l'ordre du folio (noms de `hp6.exe`,
# `SpellUnlock_<nom>`) ; les améliorations (Stupefy1 à 4, ChargedStupefy,
# LeviosaThrow) ne sont pas des sorts à part.
SORTS = ("Expelliarmus", "Stupefy", "Lumos", "Reparo", "Leviosa", "Accio", "Incendio",
         "Protego", "Petrificus", "LeviCorpus", "Depulso")

# Les paliers du « Minicrestometer », LUS dans `hp6.exe` (table à 0x8748F0,
# 2026-10-15) : le jeu affiche le nombre de seuils atteints sur 25 (« 3 / 25 »
# pour 372 chez Ludo, VU) et remplit sa barre du palier atteint au suivant
# (fonction à 0x45AD20).
PALIERS = (100, 200, 300, 450, 600, 800, 1000, 1250, 1500, 2000, 2500, 3250, 4000, 5000,
           6250, 7500, 9000, 10500, 12250, 14000, 16000, 18000, 20250, 22500, 25000)


# Où sont les 125 écussons, lieu par lieu (2026-10-16, lecture des archives du
# jeu, notes HP6 « Les 125 écussons nommés »). L'identifiant que la sauvegarde
# range dans `CrestsCollected` est le hachage ELF du nom de l'ENTITÉ de
# l'écusson : vérifié sur les 93 écussons posés dans les niveaux (instances de
# la même classe, chacune suivie de son nom) et sur les 7 de la partie de Ludo.
# Les 22 écussons de défi (potions, feux d'artifice, brutes, grilles) portent
# « .CrestMain » et les 10 à reconstituer leur nom nu : même règle, pas encore
# vue dans une sauvegarde. 93 + 22 + 10 = 125, le total du menu de pause.
# Les libellés sont ceux du château (« Volière », « Pont suspendu », « Couloir
# des cachots » sont les mots du jeu) ; ils passent par `tr()` à l'affichage.
LIEUX: tuple[tuple[str, str], ...] = (
    ("Escalier et couloir de Slughorn",
     "Armour_Crest_01.CrestMain Slughorn_Stairs_Crest_01 Slughorns_Corridor_Crest_01"),
    ("Entrée de la tour d'astronomie",
     "Astronomy_Entrance_Crest_01.CrestMain Astronomy_Entrance_Crest_Behind_Grate_01.CrestMain"),
    ("Marches du hangar à bateaux",
     "Boathouse_Steps_Crest_01 Boathouse_Steps_Crest_02 Boathouse_Steps_Crest_03"),
    ("Chemin du hangar à bateaux",
     "Boathouse_Path_Crest_01.CrestMain Boathouse_Path_Crest_BurnablePlant_01.CrestMain "
     "Boathouse_Path_Firework_Crest_01.CrestMain"),
    ("Hangar à bateaux", "Boathouse_Crest_01.CrestMain Boathouse_Crest_02.CrestMain"),
    ("Dortoir des garçons", "Boys_Dorm_Crest_01"),
    ("Chemin de la grotte", "Cave_Path_Crest_01.CrestMain Cave_Path_Crest_02"),
    ("Salle d'enchantements", "Charms_Class_Crest_01 Charms_Class_Crest_02.CrestMain"),
    ("Cour de la tour de l'horloge",
     "Clocktower_Courtyard_Crest_01 Clocktower_Courtyard_Crest_02 "
     "Clocktower_Courtyard_Crest_BurnablePlant_01.CrestMain Clocktower_Courtyard_Firework_Crest_01.CrestMain"),
    ("Tour de l'horloge", "Clocktower_Pendulum_Crest_01.CrestMain Clocktower_Potions_01.CrestMain"),
    ("Salle commune de Gryffondor", "Common_Room_Crest_01.CrestMain Common_Room_Crest_02.CrestMain"),
    ("Pont couvert", "Covered_Bridge_Crest_2"),
    ("Escalier de défense contre les forces du Mal", "DADA_Staircase_Crest01"),
    ("Couloir de défense contre les forces du Mal",
     "DADA_CorridorA_Mounted_Crest01.CrestMain DADA_Corridor_B_Crest_01.CrestMain "
     "DADA_Corridor_Potions_01.CrestMain"),
    ("Tunnel des cachots", "Dungeon_Tunnel_Crest_01.CrestMain Dungeon_Tunnel_Crest_02"),
    ("Cachots",
     "Dungeon_Corridor_Crest_01 Dungeon_Corridor_Crest_02.CrestMain "
     "Dungeon_Corridor_Crest_Behind_Grate_01.CrestMain Dungeon_Corridor_Crest_Cobweb_01.Crest "
     "Entrance_Dungeon_Crest_01.CrestMain"),
    ("Cour d'entrée",
     "Entrance_Courtyard_Bully_01.CrestMain Entrance_Courtyard_Crest_01.CrestMain "
     "Entrance_Courtyard_Crest_02.CrestMain"),
    ("Passerelle extérieure",
     "Exterior_Walkway_Crest_01 Exterior_Walkway_Crest_02 Exterior_Walkway_Crest_BurnablePlant_01.CrestMain"),
    ("Couloir du 1er étage", "Floor1_Corridor_Crest_01.CrestMain HW_Corridor_Armour_Crest_01.CrestMain"),
    ("Couloir et escalier du 2e étage",
     "Floor2_Corridor_Crest_01 Floor2_Corridor_Mounted_Crest_01.CrestMain Floor2_Stairs_Crest_01.CrestMain"),
    ("Escalier du 3e étage", "Floor3_Staircase_Crest_Behind_Grate_01.CrestMain"),
    ("Couloir du 5e étage", "Floor5_Corridor_Crest_01.CrestMain"),
    ("Chemin de la forêt", "Forest_Path_Crest_01 Forest_Path_Crest_02 Forest_Path_Crest_03"),
    ("Grand escalier",
     "Grand_Staircase_Crest_01.CrestMain Grand_Staircase_Crest_02 Grand_Staircase_Crest_03 "
     "Grand_Staircase_Crest_04"),
    ("Cabane de Hagrid",
     "Hagrids_Hut_Bully_01.CrestMain Hagrids_Hut_Crest_01.CrestMain Hagrids_Hut_Crest_02 "
     "Hagrids_Hut_Crest_03 Hagrids_Hut_Crest_BurnableBush_01.CrestMain"),
    ("Couloir de botanique",
     "Herbology_Corridor_Crest_01 Herbology_Corridor_Crest_02 Herbology_Corridor_Crest_03 "
     "Herbology_Corridor_Potions_01.CrestMain"),
    ("Serres de botanique",
     "Herbology_Crest_01 Herbology_Crest_02 Herbology_Crest_03.CrestMain Herbology_Crest_04"),
    ("Couloir de l'infirmerie", "Hospital_Corridor_Bully_01.CrestMain Hospital_Corridor_Crest_01.CrestMain"),
    ("Bibliothèque",
     "Library_Crest_01 Library_Crest_Behind_Grate_01.CrestMain Library_Potions_01.CrestMain"),
    ("Couloir de Mimi Geignarde", "Moaning_Myrtles_Corridor_Crest_01.CrestMain"),
    ("Volière",
     "Owlery_Crest_01 Owlery_Crest_02.CrestMain Owlery_Crest_03.CrestMain "
     "Owlery_Crest_Behind_Grate_01.CrestMain Owlery_Crest_Crest_01 Owlery_Crest_Crest_02 "
     "Owlery_Firework_Crest_01.CrestMain"),
    ("Cour pavée",
     "Paved_Courtyard_Crest_01 Paved_Courtyard_Crest_BurnablePlant_01.CrestMain "
     "Paved_Courtyard_Firework_Crest_01.CrestMain"),
    ("Couloir des préfets", "Prefects_Corridor_Crest_01 Prefects_Corridor_Crest_02"),
    ("Porte du terrain de Quidditch", "Quidditch_Gate_Crest_01"),
    ("Couloir de la Salle sur Demande",
     "ROR_CorridorA_Crest_02.CrestMain ROR_CorridorA_Crest_04 ROR_Corridor_Crest_01.CrestMain "
     "ROR_Corridor_Crest_03"),
    ("Pont de pierre", "Stone_Bridge_Crest_01.CrestMain Stone_Bridge_Crest_02"),
    ("Cercle de pierres", "Stone_Circle_Crest_02.CrestMain Stone_Circle_Crest_BurnableBush_01.CrestMain"),
    ("Pont suspendu", "Suspension_Bridge_Bully_01.CrestMain Suspension_Bridge_Crest_01.CrestMain"),
    ("Couloir de la tapisserie",
     "Tapestry_Corridor_Crest_01.CrestMain Tapestry_Corridor_Crest_02 Tapestry_Corridor_Crest_Cobweb_02.Crest"),
    ("Terrain d'entraînement",
     "Training_Ground_A_Bully_01.CrestMain Training_Ground_A_Crest_Behind_Grate_01.CrestMain "
     "Training_Ground_A_Crest_Behind_Grate_02.CrestMain Training_Ground_A_Crest_Cobweb_01.Crest "
     "Training_Ground_Crest_01.CrestMain Training_Ground_Crest_02.CrestMain Training_Ground_Crest_03 "
     "Training_Ground_Crest_04 Training_Ground_Crest_05.CrestMain Training_Ground_Crest_06 "
     "Training_Ground_Crest_BurnableBush_01.CrestMain Training_Ground_Crest_BurnablePlant_01.CrestMain "
     "Training_Ground_Firework_Crest_01.CrestMain"),
    ("Salle de métamorphose", "Transfig_Class_Crest_01.CrestMain"),
    ("Cour de métamorphose",
     "Transfig_Courtyard_Crest_01.CrestMain Transfig_Courtyard_Crest_02.CrestMain "
     "Transfig_Courtyard_Crest_03 Transfig_Courtyard_Crest_04 Transfig_Courtyard_Potions_01.CrestMain"),
    ("Entrée du viaduc",
     "Viaduct_Entrance_Crest_01.CrestMain Viaduct_Entrance_Crest_02 Viaduct_Entrance_Crest_03.CrestMain"),
)


# Les 30 badges, dans l'ordre de l'écran « Badges » du jeu : potions, Quidditch,
# duel (table `EG_PRE_BADGE_01` à `_30` de `chapters/frontend.str`, relevée le
# 2026-10-17). Par badge : sa clé dans la section `Badges` de la sauvegarde,
# puis les clés de son NOM et de la façon de l'OBTENIR dans les textes du jeu
# (`hp6.exe` les range par paires, l'explication puis le nom, dans l'ordre
# des clés de sauvegarde). L'image est `PT_BDG_<clé>_CM`, sauf une : le jeu
# montre `COM_BORNSURVIVOR` pour `COM_KEENDUELLIST` (case 27 de la table).
BADGES: tuple[tuple[str, str, str], ...] = tuple(
    (f"{cle}_{badge}", f"GUI_{gui}_BADGES_{nom}", f"GUI_{gui}_BADGES_{comment}")
    for cle, gui, serie in (
        ("POT", "POTIONS", (
            ("BEGINNERSLUCK", "BEGINNERS_LUCK", "FIRST_POTION"),
            ("ENDURANCE", "ENDURANCE", "SUCCESSFUL_POTIONS"),
            ("SMOKEYBREW", "SMOKY_BREWER", "SMOKY_POTIONS"),
            ("MESSIEST", "MESSIEST_MIXER", "LIQUID_ON_TABLE"),
            ("LASTGASP", "LAST_GASP", "RECOVER"),
            ("SPEEDBREW", "SPEEDY_BREWER", "SECONDS"),
            ("CLUBSTAR", "CLUB_STAR", "TOP_GRADE"),
            ("CLUBVET", "CLUB_VETERAN", "ALL_POTIONS"),
            ("CLUBMEMBER", "CLUB_MEMBER", "JOINED"),
            ("MASTERPOTIONEER", "MASTER_POTIONEER", "TOP_GRADE_ALL"))),
        ("QUID", "QUIDDITCH", (
            ("BEGINNERSLUCK", "BEGINNERS_LUCK", "CAUGHT_SNITCH"),
            ("ENDURANCE", "ENDURANCE", "FLOWN"),
            ("PRECISIONFLYER", "PRECISION", "HIT_GATES"),
            ("GROUNDED", "GROUNDED", "HARD_COLLISIONS"),
            ("BROOMRAGE", "BROOM_RAGE", "BUMPED_RIVAL"),
            ("PERSISTENCE", "PERSISTENCE", "REPLAYS"),
            ("DODGER", "DODGER", "NO_HARD_COLLISIONS"),
            ("COMBOFLYER", "COMBO_FLYER", "COMPLETE_CHAIN"),
            ("KEENFLYER", "KEEN_FLYER", "ALL_CLUBS"),
            ("MASTEROFFLYING", "MASTER_FLYING", "TOP_GRADE"))),
        ("COM", "COMBAT", (
            ("BEGINNERSLUCK", "BEGINNERS_LUCK", "JOINED_GRYFFINDOR"),
            ("NINELIVES", "NIVE_LIVES", "SUCCESSFULLY_RESIST"),
            ("REFLEX", "REFLEX_BADGE", "NO_HIT"),
            ("CROSSFIRE", "CROSSFIRE", "DESTROY_COVER"),
            ("PERSISTENCE", "PERSISTENCE", "LOST"),
            ("CLUBCHAMPION", "CLUB_CHAMPION", "BECOME_CHAMPION"),
            ("KEENDUELLIST", "KEEN_DUELLIST", "DUELLING_CLUBS"),
            ("DUELLINGVETERAN", "VETERAN_BADGE", "TOP_GRADE"),
            ("PACIFIST", "PACIFIST", "WON_DUEL"),
            ("MASTERDUELLIST", "MASTER_DUELLIST", "CHAMPION"))))
    for badge, nom, comment in serie)
SERIES = (("POT_", "Potions"), ("QUID_", "Quidditch"), ("COM_", "Duel"))
_IMAGE_A_PART = {"COM_KEENDUELLIST": "COM_BORNSURVIVOR"}
_LANGUES = {"fr": "fr-fr", "en": "en-gb", "es": "es-es", "de": "de-de", "it": "it-it",
            "nl": "nl-nl", "pl": "pl-pl", "pt": "pt-pt", "ru": "ru-ru"}
_ARCHIVES = ("data.big", "data2.big", "data3.big", "data4.big")


def palier(mini_ecussons: int) -> tuple[int, float]:
    """(paliers atteints, part du chemin vers le suivant ; 1.0 une fois tout atteint)."""
    atteints = sum(1 for s in PALIERS if mini_ecussons >= s)
    if atteints == len(PALIERS):
        return atteints, 1.0
    bas = PALIERS[atteints - 1] if atteints else 0
    return atteints, (mini_ecussons - bas) / (PALIERS[atteints] - bas)


def hachage(nom: str) -> int:
    """Le hachage ELF (PJW) du nom en minuscules, comme le jeu l'écrit."""
    h = 0
    for c in nom.lower().encode("ascii"):
        h = ((h << 4) + c) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xFFFFFFFF
    return h


# identifiant d'écusson → rang du lieu dans LIEUX
_LIEU_DE: dict[int, int] = {hachage(nom): k for k, (_, noms) in enumerate(LIEUX)
                            for nom in noms.split()}


@dataclass(frozen=True)
class Lieu:
    libelle: str      # en français : `tr()` à l'affichage
    trouves: int
    total: int


def par_lieu(trouves: frozenset[int]) -> list[Lieu]:
    """Écussons trouvés sur le total, lieu par lieu, dans l'ordre de LIEUX.

    On compte, on ne nomme pas l'écusson qui manque : le folio dit OÙ chercher,
    pas quoi, comme celui de HP3 ne montre pas une carte pas encore trouvée."""
    comptes = [0] * len(LIEUX)
    for ident in trouves:
        k = _LIEU_DE.get(ident)
        if k is not None:
            comptes[k] += 1
    return [Lieu(libelle, n, len(noms.split()))
            for (libelle, noms), n in zip(LIEUX, comptes, strict=True)]


@dataclass(frozen=True)
class Partie:
    ecrite: datetime | None
    ecussons: int                 # écussons trouvés, sur ECUSSONS
    mini_ecussons: int            # le « (372) » du menu de pause
    chapitre: int = 0             # `CurrentChapterId`, 1 = le prologue au Terrier
    sorts: tuple[str, ...] = ()   # appris, dans l'ordre de SORTS
    badges: int = 0
    badges_total: int = 0
    trouves: frozenset[int] = frozenset()   # identifiants des écussons trouvés
    acquis: frozenset[str] = frozenset()    # clés des badges remportés (BADGES)

    @property
    def emplacement(self) -> int:
        return 1    # une seule partie par fichier


def _sections(d: bytes) -> dict[int, dict[int, int]]:
    """clé de section → {clé : valeur}."""
    nombre = struct.unpack_from(">I", d, 0x60)[0]
    if not 0 < nombre <= 64 or 0x64 + 12 * nombre > len(d):
        raise ValueError("répertoire de sections illisible")
    sections = {}
    for k in range(nombre):
        cle, decalage, compte = struct.unpack_from(">III", d, 0x64 + 12 * k)
        position = _CORPS + decalage
        if compte > 4096 or position + 8 * compte > len(d):
            raise ValueError("section hors du fichier")
        sections[cle] = dict(struct.unpack_from(">II", d, position + 8 * i) for i in range(compte))
    return sections


def _date(d: bytes) -> datetime | None:
    annee, mois, _, jour, heure, minute, seconde = struct.unpack_from("<7I", d, 0x20)
    try:
        ecrite = datetime(annee, mois, jour, heure, minute, seconde)
    except (ValueError, OverflowError):
        return None
    return ecrite if 2000 <= annee <= 2100 else None


def lire(contenu: bytes) -> Partie | None:
    """La partie ; None si ce n'est pas une sauvegarde de HP6 telle que relevée."""
    if len(contenu) < 0x130 or contenu[:4] != b"20CM" or contenu[0x54:0x60] != b"HPHB2.00WN32":
        return None
    try:
        sections = _sections(contenu)
    except (ValueError, struct.error):
        log.warning("Folio HP6 : sauvegarde illisible", exc_info=True)
        return None
    ecussons = sections.get(hachage("CrestsCollected"))
    jauge = sections.get(hachage("Minicrestometer"))
    if ecussons is None or jauge is None:
        return None
    missions = sections.get(hachage("MissionId"), {})
    chapitre = sections.get(hachage("CurrentChapterId"), {})
    badges = sections.get(hachage("Badges"), {})
    # 31 clés pour 30 badges : `NOT_ACQUIRED` est un témoin, absent de l'écran
    # « Badges » du jeu (6 séries de 5, VU le 2026-10-16).
    badges.pop(hachage("NOT_ACQUIRED"), None)
    acquis = frozenset(cle for cle, _, _ in BADGES if badges.get(hachage(cle)))
    sorts = tuple(s for s in SORTS if missions.get(hachage(f"SpellUnlock_{s}")))
    return Partie(
        _date(contenu),
        min(sum(1 for v in ecussons.values() if v), ECUSSONS),
        jauge.get(hachage("MiniCrestsCollected"), 0),
        next(iter(chapitre.values()), 0),
        sorts,
        sum(1 for v in badges.values() if v), len(badges),
        frozenset(v for v in ecussons.values() if v), acquis)


def releve(chemin: Path) -> Partie | None:
    try:
        if chemin.stat().st_size > _TAILLE_MAX:
            return None
        return lire(chemin.read_bytes())
    except OSError:
        log.warning("Folio HP6 : %s illisible", chemin, exc_info=True)
        return None


# ── Ce que le jeu installé montre des badges ──

def fnv1(nom: str) -> int:
    """Le hachage FNV-1 du nom en minuscules : clés des textes du jeu
    (« GUI_POTIONS_BADGES_CLUB_STAR »), relevé le 2026-10-17."""
    h = 0x811C9DC5
    for c in nom.lower().encode("ascii"):
        h = ((h * 0x01000193) & 0xFFFFFFFF) ^ c
    return h


def table_textes(flux: bytes) -> dict[int, str]:
    """Les tables « TX » d'un flux de textes : clé → texte.

    Une table : « TX  », version 1, puis par texte sa clé, sa taille en octets,
    le texte UTF-16 LE terminé par un zéro (complété à 4 octets), et deux
    entiers que le folio n'emploie pas."""
    textes: dict[int, str] = {}
    p = flux.find(b"TX  \x01\x00\x00\x00")
    while p >= 0:
        q = p + 8
        while q + 8 <= len(flux):
            cle, taille = struct.unpack_from("<II", flux, q)
            if not (2 <= taille <= 8192 and taille % 2 == 0) or q + 8 + taille > len(flux):
                break
            brut = flux[q + 8:q + 8 + taille]
            fin = next((i for i in range(0, taille - 1, 2) if brut[i:i + 2] == b"\0\0"), taille)
            textes[cle] = brut[:fin].decode("utf-16-le", "replace")
            q += 16 + taille
        p = flux.find(b"TX  \x01\x00\x00\x00", p + 8)
    return textes


def _archive(system: Path, nom: str) -> bytes:
    """Une entrée des archives du jeu, cherchée dans chacune ; b"" sinon."""
    for archive in _ARCHIVES:
        chemin = system / archive
        if chemin.is_file():
            flux = images_ea.entree_big(chemin, nom)
            if flux:
                return flux
    return b""


def textes_badges(system: Path, langue: str) -> dict[str, tuple[str, str]]:
    """Clé de badge → (nom, façon de l'obtenir), dans la langue du launcher
    (l'anglais du jeu sinon) ; vide sans le jeu."""
    return _textes_badges(str(system), _LANGUES.get(langue, "en-gb"))


@lru_cache(maxsize=4)
def _textes_badges(system_txt: str, code: str) -> dict[str, tuple[str, str]]:
    try:
        flux = _archive(Path(system_txt), f"game/localised/{code}.str")
        textes = table_textes(flux)
    except (OSError, struct.error):
        log.warning("Folio HP6 : textes du jeu illisibles", exc_info=True)
        return {}
    return {cle: (textes[fnv1(nom)], textes.get(fnv1(comment), ""))
            for cle, nom, comment in BADGES if fnv1(nom) in textes}


def images_badges(system: Path) -> dict[str, tuple[int, int, bytes]]:
    """Clé de badge → son image du jeu (128 × 128, B V R A) ; vide sans le jeu.

    Décodées une fois par session : 0,3 s pour les trente."""
    return _images_badges(str(system))


@lru_cache(maxsize=2)
def _images_badges(system_txt: str) -> dict[str, tuple[int, int, bytes]]:
    try:
        flux = _archive(Path(system_txt), "chapters/frontend.str")
        positions = images_ea.images_nommees(flux)
        images = {}
        for cle, _, _ in BADGES:
            q = positions.get(f"PT_BDG_{_IMAGE_A_PART.get(cle, cle)}_CM")
            image = images_ea.image(flux, q) if q is not None else None
            if image is not None:
                images[cle] = image
        return images
    except (OSError, struct.error):
        log.warning("Folio HP6 : images des badges illisibles", exc_info=True)
        return {}


# Les écussons du menu de pause (DXT 64 × 64 dans `game.str`, relevés le 2026-10-17).
ICONES = {"ecussons": "PT_Crest_ALL", "mini": "PT_Mini_Crest_ALL"}


def image_menu(system: Path, cle: str) -> tuple[int, int, bytes] | None:
    """Une icône `ICONES` du jeu installé (B V R A), ou None."""
    return _images_menu(str(system)).get(cle)


@lru_cache(maxsize=2)
def _images_menu(system_txt: str) -> dict[str, tuple[int, int, bytes]]:
    images: dict[str, tuple[int, int, bytes]] = {}
    try:
        flux = _archive(Path(system_txt), "game.str")
        positions = images_ea.images_nommees(flux)
        for cle, nom in ICONES.items():
            q = positions.get(nom)
            image = images_ea.image(flux, q) if q is not None else None
            if image is not None:
                images[cle] = image
    except (OSError, struct.error):
        log.warning("Folio HP6 : icônes du menu illisibles", exc_info=True)
    return images


def resume(fichiers: dict[str, Path]) -> folio.Resume | None:
    """L'unique partie écrite en dernier : ses écussons sur 125. Rien tant
    qu'aucun n'est trouvé : la description dit mieux le début du jeu."""
    parties = [(p, chemin) for chemin in fichiers.values()
               if (p := releve(chemin)) is not None]
    if not parties:
        return None
    partie, chemin = max(parties, key=lambda pc: pc[0].ecrite or datetime.min)
    if partie.ecussons <= 0:
        return None
    quand = partie.ecrite or datetime.fromtimestamp(chemin.stat().st_mtime)
    return folio.Resume(partie, "", partie.ecussons, ECUSSONS, quand, "ecussons")

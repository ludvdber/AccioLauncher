"""Le folio : ce qu'une sauvegarde dit de la partie (cartes, dragées, points des maisons).

Maquette « Folio HP1, quatre maisons » validée par Ludo le 2026-10-14. Premier
jeu lu : HP1 ; les huit le sont depuis le 2026-10-16, chacun avec son module
(`folio_hp2` … `folio_hp7`, ce dernier pour les deux Reliques de la Mort).

**HP1** (relevé le 2026-10-14 sur les sauvegardes de Ludo, en LECTURE seule) :
`Documents/Harry Potter/Save/SaveN.usa` est un paquet Unreal. L'acteur Harry
(classe `Harry`) y porte ses propriétés binaires : c'est l'état au moment de
la sauvegarde, et c'est lui qu'on lit (`textures_ue1.Paquet.proprietes`).

Le même fichier porte aussi, en texte clair, un bloc d'Harry :

    Class=HarryPotter.Harry Name=Harry0
    {
    numHousePointsHarry=155
    numHousePointsGryffindor=155
    numHousePointsSlytherin=173
    …
    numBeans=112
    WizardCards[0]=(bHasCard=True)
    …
    }

Mais ce bloc est la « chaîne de voyage » d'Unreal, écrite au DERNIER
CHANGEMENT DE NIVEAU : sur la partie de Ludo, 112 dragées quand l'acteur et
le jeu en comptent 126 (relevé le 2026-10-15). Il ne sert plus qu'en repli,
si l'acteur ne se lit pas.

Unreal n'écrit que les propriétés qui diffèrent de leur valeur par défaut :
une propriété absente vaut 0. Au tout début du jeu, Harry n'a encore rien
(ni bloc, ni propriété) ; le folio dit alors qu'il n'y a rien encore à lire,
il n'invente pas de zéros. `GameSaveInfoN` donne le niveau où l'on a sauvegardé.

`Save9.usa` est la sauvegarde rapide (F5), que le menu du jeu ne range dans
aucun emplacement (`sauvegardes.est_rapide`).

Les noms des cartes et des lieux viennent du JEU INSTALLÉ (`HPMenu.int`,
`HPmenu.fre`…), dans sa langue : aucun texte du jeu n'est recopié ici.
"""

from __future__ import annotations

import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

if TYPE_CHECKING:
    from src.core import textures_ue1

log = logging.getLogger(__name__)

GRYFFONDOR, SERPENTARD, SERDAIGLE, POUFSOUFFLE = (
    "gryffondor", "serpentard", "serdaigle", "poufsouffle")
MAISONS = (GRYFFONDOR, SERPENTARD, SERDAIGLE, POUFSOUFFLE)

# Les jeux dont le folio sait lire les sauvegardes, par id du catalogue : ils
# ont leur PAGE (`ui/folio_jeux.page_folio`). Ceux de `RESUMES` montrent en
# plus la partie sur leur fiche, à la place de la description (cartes : HP1,
# HP3) ; HP4, HP5 et HP6 gardent la leur (pas d'éventail de cartes à montrer).
JEUX = ("hp1", "hp2", "hp3", "hp4", "hp5", "hp6", "hp7a", "hp7b")
RESUMES = ("hp1", "hp2", "hp3")

# Le folio du jeu, emplacement par emplacement : `WizardCards[i]` de la
# sauvegarde est la carte i + 1 de cette liste. Relevé le 2026-10-14 dans le
# jeu installé, pas déduit des textes :
# - l'ordre vient des propriétés par défaut de `baseHarry` (`HPBase.u`), où
#   chaque `WizardCards[i]` porte l'`ID` de collection de sa carte ;
# - l'ID mène au texte par `FEFolioPage.GetWizardText` et à l'image par
#   `GetBigTexture` / `GetSmallTexture` (`HPMenu.u`).
# 25 cartes : le fichier de textes en a 28, mais Merwyn (06), Archibald (13)
# et Grogan (16) n'y sont jamais appelés. Le numéro PEINT sur la carte (96 pour
# Hengist) est l'ID de collection, pas l'emplacement.
# (nom de la texture dans `HPMenu.u`, numéro de `wizard_card_new_NN`)
_FOLIO_HP1 = (
    ("Dumbledore", 4), ("Merlin", 1), ("Tilly", 12), ("Burdock", 2),
    ("Adalbert", 11), ("Uric", 8), ("Derwent", 25), ("Cornelius", 10),
    ("Newt", 9), ("Edgar", 18), ("Bowman", 14), ("Godric", 17),
    ("Morgan", 7), ("Bertie", 23), ("Salizar", 19), ("Cassandra", 15),
    ("Ignatia", 22), ("Gifford", 21), ("Elladora", 20), ("Hengist", 28),
    ("Helga", 24), ("Rowena", 26), ("Roderic", 27), ("Herpo", 5),
    ("Harry", 3),
)
CARTES_HP1 = len(_FOLIO_HP1)
_PROPRIETES_HP1 = {
    GRYFFONDOR: "numHousePointsGryffindor",
    SERPENTARD: "numHousePointsSlytherin",
    SERDAIGLE: "numHousePointsRavenclaw",
    POUFSOUFFLE: "numHousePointsHufflepuff",
}
_BLOC_HARRY = re.compile(rb"Class=HarryPotter\.Harry Name=\w+\r?\n\{\r?\n(.*?)\r?\n\}", re.S)
_CARTE = re.compile(r"WizardCards\[(\d+)\]=\(bHasCard=True\)")
_LUES = {*_PROPRIETES_HP1.values(), "numHousePointsHarry", "numBeans"}
# `Save9.usa`, rangé après les emplacements du menu.
_EMPLACEMENT_RAPIDE = 10
# Plafond de lecture : une sauvegarde HP1 pèse 1,5 à 2,4 Mo.
_TAILLE_MAX = 16 * 1024 * 1024

# Extension des fichiers de texte du jeu par langue du launcher ; `int`,
# l'anglais, existe toujours.
_EXTENSIONS = {"fr": "fre", "es": "esp", "de": "det", "it": "itt", "en": "int"}


@dataclass(frozen=True)
class Carte:
    numero: int        # emplacement du folio, 1 à 25, dans l'ordre du jeu
    nom: str
    dates: str
    texte: str


@dataclass(frozen=True)
class Releve:
    """Ce qu'un emplacement de sauvegarde dit de la partie."""
    emplacement: int              # 1, 2, 3 : comme le menu du jeu
    chemin: Path
    modifie: datetime
    niveau: str = ""              # code du niveau (« LEV2_HOGFRONT »)
    lu: bool = False              # False : aucun bloc d'Harry (tout début du jeu)
    cartes: frozenset[int] = field(default_factory=frozenset)   # emplacements 1 à 25
    dragees: int = 0
    points: dict[str, int] = field(default_factory=dict)        # par maison
    points_harry: int = 0

    @property
    def rapide(self) -> bool:
        """La sauvegarde rapide (F5), hors des emplacements du menu."""
        return self.emplacement == _EMPLACEMENT_RAPIDE

    @property
    def avancement(self) -> tuple[int, int, int]:
        return (len(self.cartes), self.points_harry, self.dragees)

    def en_tete(self) -> tuple[str, int] | None:
        """(maison, avance sur la deuxième) ; None sans relevé ou à égalité."""
        if not self.lu:
            return None
        classement = sorted(self.points.items(), key=lambda m: m[1], reverse=True)
        if len(classement) < 2 or classement[0][1] == classement[1][1]:
            return None
        return classement[0][0], classement[0][1] - classement[1][1]


# ── Lecture d'une sauvegarde ──

def lire_harry_hp1(contenu: bytes) -> dict[str, Any] | None:
    """Les valeurs de l'acteur Harry, au moment de la sauvegarde ; None sans
    acteur lisible ou sans rien d'écrit (tout début du jeu)."""
    from src.core import textures_ue1
    try:
        props = textures_ue1.Paquet(contenu).proprietes("Harry")
    except (ValueError, IndexError, struct.error):
        log.warning("Folio : acteur d'Harry illisible", exc_info=True)
        return None
    if props is None:
        return None
    valeurs: dict[str, int] = {}
    cartes: set[int] = set()
    for nom, indice, valeur in props:
        if not isinstance(valeur, bytes):
            continue
        if nom == "WizardCards":
            # Structure `WizardList` : l'ID de collection (4 octets), puis bHasCard.
            if len(valeur) == 5 and valeur[4] and 0 <= indice < CARTES_HP1:
                cartes.add(indice + 1)
        elif indice == 0 and len(valeur) == 4:
            valeurs.setdefault(nom, struct.unpack("<i", valeur)[0])
    if not cartes and not valeurs.keys() & _LUES:
        return None
    return _valeurs(valeurs, frozenset(cartes))


def lire_bloc_hp1(contenu: bytes) -> dict[str, Any] | None:
    """Les valeurs du bloc texte d'Harry ; None s'il n'y en a pas. EN RETARD
    sur la sauvegarde (voir l'en-tête) : en repli seulement."""
    trouve = _BLOC_HARRY.search(contenu)
    if trouve is None:
        return None
    texte = trouve.group(1).decode("latin-1")
    valeurs: dict[str, int] = {}
    for ligne in texte.splitlines():
        cle, egal, valeur = ligne.strip().partition("=")
        if egal and re.fullmatch(r"-?\d+", valeur):
            valeurs[cle] = int(valeur)
    cartes = frozenset(int(n) + 1 for n in _CARTE.findall(texte)
                       if 0 <= int(n) < CARTES_HP1)
    return _valeurs(valeurs, cartes)


def _valeurs(valeurs: dict[str, int], cartes: frozenset[int]) -> dict[str, Any]:
    return {
        "points": {m: max(0, valeurs.get(p, 0)) for m, p in _PROPRIETES_HP1.items()},
        "points_harry": max(0, valeurs.get("numHousePointsHarry", 0)),
        "dragees": max(0, valeurs.get("numBeans", 0)),
        "cartes": cartes,
    }


def info_hp1(info: Path) -> tuple[str, int]:
    """(code du niveau, point de sauvegarde) de `GameSaveInfoN` ; ("", -1) illisible.

    `GameSaveInfo.uc` : dragées, étoiles, points (3 × 4 octets), `savePointID`
    (4), puis le niveau en chaîne Unreal (longueur sur un octet). Le point vaut
    -1 hors d'un point de sauvegarde : l'ancienne lecture prenait ses quatre
    `FF` pour un marqueur, et perdait le niveau dès qu'il valait autre chose.
    """
    try:
        brut = info.read_bytes()[:512]
    except OSError:
        return "", -1
    if len(brut) < 18:
        return "", -1
    point = struct.unpack_from("<i", brut, 12)[0]
    taille = brut[16]
    chaine = brut[17:17 + taille].rstrip(b"\x00")
    if not 1 < taille < 64 or not re.fullmatch(rb"[A-Za-z0-9_]+", chaine):
        return "", -1
    return chaine.decode("ascii"), point


def niveau_hp1(info: Path) -> str:
    """Le code du niveau dans `GameSaveInfoN` (`info_hp1`)."""
    return info_hp1(info)[0]


# Les niveaux de l'histoire dans l'ordre où le jeu les enchaîne : chaque
# carte nomme la suivante (relevé le 2026-10-17 dans `Maps/*.unr`). Après
# `Lev3_Intro`, tout le reste (Lev3 à Lev5, bureau de Rogue, matchs) vient plus tard.
_ORDRE_HP1 = ("lev_tut1", "lev_tut1b", "lev_tut2", "lev_tut3", "lev_tut3b",
              "lev2_hogfront", "lev2_inc_a", "lev2_inc_b", "lev2_hogfront_2",
              "lev2_remchase", "lev2_hogfront_3", "lev2_fire2", "lev2_fire1",
              "lev2_quid1", "lev3_intro")
_APRES_HP1 = re.compile(r"lev[345]_\w+|snapes_office|quid_\w+")

# Chaque sort et le niveau de sa leçon (`SpellLearnTrigger.Spell` des cartes).
SORTS_HP1 = (("Flipendo", "lev_tut1"), ("Alohomora", "lev_tut3"),
             ("Wingardium Leviosa", "lev_tut3"), ("Incendio", "lev2_inc_a"),
             ("Lumos", "lev3_intro"))


def _rang_hp1(niveau: str) -> int | None:
    n = niveau.lower()
    if n in _ORDRE_HP1:
        return _ORDRE_HP1.index(n)
    return len(_ORDRE_HP1) if _APRES_HP1.fullmatch(n) else None


def sorts_hp1(niveau: str) -> list[tuple[str, bool]] | None:
    """Les cinq sorts et s'ils sont appris, au niveau `niveau` ; None si le
    niveau est inconnu.

    La sauvegarde ne les écrit pas (la baguette y est vide, relevé sur les
    trois de Ludo) : le jeu les rend selon l'avancée dans l'histoire. Un sort
    compte comme appris APRÈS le niveau de sa leçon : sauvegardé pendant la
    leçon, on ne sait pas si elle est réussie, et on ne l'affirme pas.
    """
    rang = _rang_hp1(niveau)
    if rang is None:
        return None
    return [(nom, rang > _ORDRE_HP1.index(lecon)) for nom, lecon in SORTS_HP1]


def image_sauvegarde_hp1(system: Path, sauvegarde: Path) -> Path | None:
    """L'image que le menu de chargement du jeu montre pour `SaveN.usa`.

    `FESlotPage.uc` : `save/SGS <niveau><point>.bmp`, sinon `SGS <niveau>.bmp`,
    sinon `DefaultGameSnap.bmp`, dans le dossier `save` du jeu INSTALLÉ (des
    images livrées avec le jeu, 128 px, une par niveau). Le système de fichiers
    du jeu ignore la casse (« SGS lev2_hogfront.bmp » pour LEV2_HOGFRONT).
    """
    numero = re.fullmatch(r"Save(\d+)\.usa", sauvegarde.name, re.I)
    if numero is None:
        return None
    niveau, point = info_hp1(sauvegarde.with_name(f"GameSaveInfo{numero.group(1)}"))
    try:
        dossier = next((d for d in system.parent.iterdir()
                        if d.is_dir() and d.name.lower() == "save"), None)
        images = {f.name.lower(): f for f in dossier.iterdir()} if dossier else {}
    except OSError:
        return None
    noms = ([f"sgs {niveau}{point}.bmp"] if niveau and point >= 0 else []) + \
        ([f"sgs {niveau}.bmp"] if niveau else []) + ["defaultgamesnap.bmp"]
    return next((images[n.lower()] for n in noms if n.lower() in images), None)


def releve_hp1(chemin: Path) -> Releve | None:
    """Le relevé de `SaveN.usa` ; None si le fichier ne se lit pas."""
    numero = re.fullmatch(r"Save(\d+)\.usa", chemin.name, re.I)
    if numero is None:
        return None
    try:
        infos = chemin.stat()
        if infos.st_size > _TAILLE_MAX:
            return None
        modifie = datetime.fromtimestamp(infos.st_mtime)
        bloc = _valeurs_hp1(str(chemin), infos.st_mtime_ns, infos.st_size)
    except OSError:
        log.warning("Folio : %s illisible", chemin, exc_info=True)
        return None
    n = int(numero.group(1))
    niveau = niveau_hp1(chemin.with_name(f"GameSaveInfo{n}"))
    if bloc is None:
        return Releve(n + 1, chemin, modifie, niveau)
    return Releve(n + 1, chemin, modifie, niveau, True, **bloc)


@lru_cache(maxsize=16)
def _valeurs_hp1(chemin: str, _mtime_ns: int, _taille: int) -> dict[str, Any] | None:
    """Lu une fois tant que le fichier ne change pas : la fiche relit les
    sauvegardes à chaque retour, et l'acteur coûte 6 à 12 ms par fichier."""
    contenu = Path(chemin).read_bytes()
    return lire_harry_hp1(contenu) or lire_bloc_hp1(contenu)


def emplacements_hp1(fichiers: dict[str, Path]) -> list[Releve]:
    """Les emplacements dans l'ordre du menu du jeu (`sauvegardes.fichiers`)."""
    releves = [r for r in (releve_hp1(p) for p in fichiers.values()) if r is not None]
    return sorted(releves, key=lambda r: r.emplacement)


def le_plus_avance(releves: list[Releve]) -> Releve | None:
    """Celui qui a le plus de cartes, puis de points, puis de dragées ; None si
    un seul est lu, ou aucun (rien à départager)."""
    lus = [r for r in releves if r.lu]
    if len(releves) < 2 or not lus:
        return None
    return max(lus, key=lambda r: r.avancement)


class PartieLue(Protocol):
    """Ce qu'ont en commun les relevés de tous les jeux (HP1, HP3…)."""

    @property
    def emplacement(self) -> int: ...
    @property
    def modifie(self) -> datetime: ...
    @property
    def lu(self) -> bool: ...


_P = TypeVar("_P", bound=PartieLue)


def la_derniere_jouee(releves: Sequence[_P]) -> _P | None:
    """Celui que le jeu a écrit en dernier : la partie qu'on reprend. Parmi les
    lisibles d'abord, sinon un emplacement illisible ouvrirait sur du vide."""
    candidats = [r for r in releves if r.lu] or list(releves)
    return max(candidats, key=lambda r: r.modifie, default=None)


@dataclass(frozen=True)
class Resume:
    """Ce que la fiche du jeu montre à la place de sa description."""
    releve: PartieLue   # `Releve` pour HP1, `folio_hp3.Releve` pour HP3
    lieu: str        # vide si le jeu n'est pas installé ou ne nomme pas le niveau
    trouvees: int = 0     # cartes trouvées…
    total: int = 0        # … sur tant


def resume_hp1(fichiers: dict[str, Path], system: Path, langue: str) -> Resume | None:
    """La partie à reprendre, ou None : la fiche garde alors sa description.

    Les LISIBLES seulement, contrairement au folio : un emplacement du tout
    début du jeu n'a rien à montrer de plus que la description (Ludo,
    2026-10-15 : « tant qu'on a rien on laisse la description »).
    """
    lisibles = [r for r in emplacements_hp1(fichiers) if r.lu]
    releve = la_derniere_jouee(lisibles)
    if releve is None:
        return None
    _, titres = textes_hp1(fichier_textes(system, langue))
    return Resume(releve, lieu(titres, releve.niveau), len(releve.cartes), CARTES_HP1)


# ── Les textes du jeu installé ──

def _decoder(brut: bytes) -> str:
    """Les fichiers de texte d'Unreal : UTF-16 avec BOM, sinon Windows-1252 (règle 81)."""
    if brut[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return brut.decode("utf-16", "replace")
    try:
        return brut.decode("utf-8")
    except UnicodeDecodeError:
        return brut.decode("cp1252", "replace")


def fichier_textes(system: Path, langue: str) -> Path | None:
    """`HPMenu.<ext>` dans la langue du launcher, sinon l'anglais."""
    if not system.is_dir():
        return None
    try:
        noms = {p.name.lower(): p for p in system.iterdir() if p.is_file()}
    except OSError:
        return None
    for ext in (_EXTENSIONS.get(langue, "int"), "int"):
        trouve = noms.get(f"hpmenu.{ext}")
        if trouve is not None:
            return trouve
    return None


def textes_hp1(fichier: Path | None) -> tuple[dict[int, Carte], dict[str, str]]:
    """(cartes par emplacement du folio, titres des niveaux par code en minuscules)."""
    if fichier is None:
        return {}, {}
    try:
        texte = _decoder(fichier.read_bytes())
    except OSError:
        return {}, {}
    brutes: dict[str, str] = {}
    titres: dict[str, str] = {}
    for ligne in texte.splitlines():
        cle, egal, valeur = ligne.partition("=")
        cle = cle.strip().lower()
        if not egal:
            continue
        # Le fichier a une seconde section aux mêmes clés, VIDES : la première
        # valeur non vide l'emporte.
        if not valeur.strip():
            continue
        if cle.startswith("wizard_card_new_"):
            brutes.setdefault(cle[len("wizard_card_new_"):], valeur.strip())
        elif cle.startswith("title_"):
            titres.setdefault(cle[len("title_"):], valeur.strip())
    cartes: dict[int, Carte] = {}
    for numero, (_texture, texte_jeu) in enumerate(_FOLIO_HP1, start=1):
        # La variante « b » est la version corrigée du jeu (28 : « Ecosse. fondant »).
        brut = brutes.get(f"{texte_jeu:02d}b") or brutes.get(f"{texte_jeu:02d}")
        if not brut:
            continue
        morceaux = re.split(r"\.\s+", brut, maxsplit=2)
        nom = morceaux[0].strip()
        dates = morceaux[1].strip() if len(morceaux) > 1 else ""
        corps = morceaux[2].strip() if len(morceaux) > 2 else ""
        cartes[numero] = Carte(numero, nom, dates, corps)
    return cartes, titres


def lieu(titres: dict[str, str], niveau: str) -> str:
    return titres.get(niveau.lower(), "") if niveau else ""


# ── Les images des cartes, dans le jeu installé ──

def paquet_menu(system: Path) -> Path | None:
    """`HPMenu.u`, quelle que soit sa casse."""
    try:
        return next((p for p in system.iterdir() if p.name.lower() == "hpmenu.u"), None)
    except OSError:
        return None


# Les blasons de la Coupe, dans `HPMenu.u` (128 px, relevés le 2026-10-16).
BLASONS_HP1 = {GRYFFONDOR: "FEGrifLogoMed", SERPENTARD: "FESlytLogoMed",
               SERDAIGLE: "FERaveLogoMed", POUFSOUFFLE: "FEHuffLogoMed"}
# Les icônes des tuiles (relevées le 2026-10-17) : la petite carte de Dumbledore,
# la première du folio, et les trois dragées du compteur du jeu. Les insignes
# du rapport de fin d'année (`CardBadgeTexture`) posent l'objet sur un ruban :
# rognés, ils restaient plats et petits.
ICONES_HP1 = {"cartes": "WizCardDumbledoreSmallTexture", "dragees": "beans1"}


def image_menu_hp1(paquet: Path | None, nom: str) -> textures_ue1.TexturePaletee | None:
    """Une image du menu du jeu (`BLASONS_HP1`), ou None sans le jeu."""
    if paquet is None:
        return None
    from src.core import textures_ue1
    return textures_ue1.texture(paquet, nom)


def image_carte_hp1(paquet: Path | None, numero: int,
                    grande: bool = True) -> textures_ue1.TexturePaletee | None:
    """La carte de l'emplacement `numero` telle que le jeu la dessine
    (`textures_ue1.TexturePaletee`), ou None. Noms de texture du jeu,
    orthographe comprise (« Salizar », « Uric »)."""
    if paquet is None or not 1 <= numero <= CARTES_HP1:
        return None
    nom = _FOLIO_HP1[numero - 1][0]
    from src.core import textures_ue1
    return textures_ue1.texture(paquet, f"WizCard{nom}{'Big' if grande else 'Small'}Texture")

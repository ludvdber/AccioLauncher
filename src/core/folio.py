"""Le folio : ce qu'une sauvegarde dit de la partie (cartes, dragées, points des maisons).

Maquette « Folio HP1, quatre maisons » validée par Ludo le 2026-10-14. Premier
jeu lu : HP1. Les autres arriveront jeu par jeu, chacun avec son lecteur
(`LECTEURS`), quand leur format aura été relevé.

**HP1** (relevé le 2026-10-14 sur les sauvegardes de Ludo, en LECTURE seule) :
`Documents/Harry Potter/Save/SaveN.usa` porte, en texte clair, le bloc
d'Harry tel qu'Unreal l'exporte :

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

Unreal n'écrit que les propriétés qui diffèrent de leur valeur par défaut :
une propriété absente vaut 0. Une sauvegarde du tout début du jeu n'a pas de
bloc du tout ; le folio dit alors qu'il n'y a rien encore à lire, il n'invente
pas de zéros. `GameSaveInfoN` donne le niveau où l'on a sauvegardé.

Les noms des cartes et des lieux viennent du JEU INSTALLÉ (`HPMenu.int`,
`HPmenu.fre`…), dans sa langue : aucun texte du jeu n'est recopié ici.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

GRYFFONDOR, SERPENTARD, SERDAIGLE, POUFSOUFFLE = (
    "gryffondor", "serpentard", "serdaigle", "poufsouffle")
MAISONS = (GRYFFONDOR, SERPENTARD, SERDAIGLE, POUFSOUFFLE)

# Les jeux dont le folio sait lire les sauvegardes, par id du catalogue.
JEUX = ("hp1",)

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

def lire_bloc_hp1(contenu: bytes) -> dict | None:
    """Les valeurs du bloc d'Harry ; None s'il n'y en a pas."""
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
    return {
        "points": {m: max(0, valeurs.get(p, 0)) for m, p in _PROPRIETES_HP1.items()},
        "points_harry": max(0, valeurs.get("numHousePointsHarry", 0)),
        "dragees": max(0, valeurs.get("numBeans", 0)),
        "cartes": cartes,
    }


def niveau_hp1(info: Path) -> str:
    """Le code du niveau dans `GameSaveInfoN` : une chaîne Unreal après le marqueur -1."""
    try:
        brut = info.read_bytes()[:512]
    except OSError:
        return ""
    debut = brut.find(b"\xff\xff\xff\xff")
    if debut < 0 or debut + 5 > len(brut):
        return ""
    taille = brut[debut + 4]
    if not 1 < taille < 64:
        return ""
    chaine = brut[debut + 5:debut + 5 + taille].rstrip(b"\x00")
    return chaine.decode("ascii", "ignore") if re.fullmatch(rb"[A-Za-z0-9_]+", chaine) else ""


def releve_hp1(chemin: Path) -> Releve | None:
    """Le relevé de `SaveN.usa` ; None si le fichier ne se lit pas."""
    numero = re.fullmatch(r"Save(\d+)\.usa", chemin.name, re.I)
    if numero is None:
        return None
    try:
        if chemin.stat().st_size > _TAILLE_MAX:
            return None
        contenu = chemin.read_bytes()
        modifie = datetime.fromtimestamp(chemin.stat().st_mtime)
    except OSError:
        log.warning("Folio : %s illisible", chemin, exc_info=True)
        return None
    n = int(numero.group(1))
    niveau = niveau_hp1(chemin.with_name(f"GameSaveInfo{n}"))
    bloc = lire_bloc_hp1(contenu)
    if bloc is None:
        return Releve(n + 1, chemin, modifie, niveau)
    return Releve(n + 1, chemin, modifie, niveau, True, **bloc)


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


def image_carte_hp1(paquet: Path | None, numero: int, grande: bool = True):
    """La carte de l'emplacement `numero` telle que le jeu la dessine
    (`textures_ue1.TexturePaletee`), ou None. Noms de texture du jeu,
    orthographe comprise (« Salizar », « Uric »)."""
    if paquet is None or not 1 <= numero <= CARTES_HP1:
        return None
    nom = _FOLIO_HP1[numero - 1][0]
    from src.core import textures_ue1
    return textures_ue1.texture(paquet, f"WizCard{nom}{'Big' if grande else 'Small'}Texture")

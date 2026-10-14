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

CARTES_HP1 = 28
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
    numero: int        # 1 à 28, comme le jeu
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
    cartes: frozenset[int] = field(default_factory=frozenset)   # numéros 1 à 28
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
    """(cartes par numéro, titres des niveaux par code en minuscules)."""
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
    for numero in range(1, CARTES_HP1 + 1):
        # La variante « b » est la version corrigée du jeu (28 : « Ecosse. fondant »).
        brut = brutes.get(f"{numero:02d}b") or brutes.get(f"{numero:02d}")
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

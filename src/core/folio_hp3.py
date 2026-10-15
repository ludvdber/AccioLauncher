"""Le folio de HP3 : ce qu'une sauvegarde du Prisonnier d'Azkaban dit de la partie.

Relevé le 2026-10-15 sur les sauvegardes de Ludo, en LECTURE seule
(`Harry-Potter-PC-Fix/notes/HP3.md`, « Mission d'analyse ») : `SaveN.usa` est
un paquet Unreal 2 (version 129) dont quelques objets portent la partie :

    JellybeanCollection.iNumItems        dragées (813)
    PumpkinPastyCollection.iNumItems     pasties du chaudron… (23)
    CauldronCakeCollection.iNumItems     gâteaux du chaudron (5)
    WizardCardManager.Cards[80]          CardClass (WC_…), Status (5 = possédée)
    ChallengeStarManager.FoundStatus[]   LevelID, NumInLevel, Found[0..9]
    SecretManager.FoundStatus[]          LevelID, NumFound, NumInLevel
    hgame.CurrentGameState               avancement de l'histoire (GState010)
    LevelInfo.LevelEnterText             niveau (HP3_INSIDEHUB)

Unreal n'écrit que ce qui diffère du défaut : un objet absent vaut zéro. Une
sauvegarde du tout début (Save1 de Ludo, `HP3_Adv1Express`) n'a ni cartes ni
collections : elle n'a rien à montrer, le folio le dit au lieu d'inventer.

Les noms des cartes viennent du JEU INSTALLÉ : la classe `WC_ZouYen` porte son
numéro dans ses propriétés par défaut (`dialogId`, `HGame.u`), et ce numéro
mène au nom (`WizardName_142=Dzou Yen`, `HpMenu.<langue>`, UTF-16). Rien n'est
deviné d'après le nom de la classe : il ne correspond pas toujours (« Dzou »).
"""

from __future__ import annotations

import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from src.core import textures_ue1

log = logging.getLogger(__name__)

POSSEDEE = 5         # EWizardCardStatus.WCS_OwnedByPlayer (lu dans HGame.u)
_TAILLE_MAX = 32 * 1024 * 1024      # une sauvegarde HP3 pèse 4 à 9 Mo
_EMPLACEMENT_RAPIDE = 10            # Save9.usa, la sauvegarde rapide (F5)
_EXTENSIONS = {"fr": "fre", "es": "esp", "de": "det", "it": "itt", "en": "int"}


@dataclass(frozen=True)
class Niveau:
    ident: str          # « CR », tel que le jeu le range (pas encore nommé)
    trouves: int
    total: int


@dataclass(frozen=True)
class Releve:
    emplacement: int
    chemin: Path
    modifie: datetime
    lu: bool = False
    histoire: str = ""                       # « GState010 »
    niveau: str = ""                         # « HP3_INSIDEHUB »
    dragees: int = 0
    pasties: int = 0
    gateaux: int = 0
    cartes: frozenset[str] = field(default_factory=frozenset)   # classes possédées
    total_cartes: int = 0
    etoiles: tuple[Niveau, ...] = ()
    secrets: tuple[Niveau, ...] = ()

    @property
    def rapide(self) -> bool:
        return self.emplacement == _EMPLACEMENT_RAPIDE


def _champs(props: list[textures_ue1.ProprieteLue] | None) -> dict[str, object]:
    """Premier élément de chaque propriété, par nom."""
    sortie: dict[str, object] = {}
    for nom, _, valeur in props or ():
        sortie.setdefault(nom, valeur)
    return sortie


def _entier(valeur: object) -> int:
    return max(0, valeur) if isinstance(valeur, int) and not isinstance(valeur, bool) else 0


def _niveaux(props: list[textures_ue1.ProprieteLue] | None, etoiles: bool) -> tuple[Niveau, ...]:
    niveaux = []
    for nom, _, valeur in props or ():
        if nom != "FoundStatus" or not isinstance(valeur, list):
            continue
        champs = _champs(valeur)
        ident = champs.get("LevelID")
        total = _entier(champs.get("NumInLevel"))
        if not isinstance(ident, str) or not ident:
            continue
        if etoiles:
            trouves = sum(1 for n, i, v in valeur if n == "Found" and i < total and v)
        else:
            trouves = _entier(champs.get("NumFound"))
        niveaux.append(Niveau(ident, min(trouves, total) if total else trouves, total))
    return tuple(niveaux)


@dataclass(frozen=True)
class _Partie:
    """Ce que `lire` rend : la partie sans son fichier."""
    dragees: int
    pasties: int
    gateaux: int
    cartes: frozenset[str]
    total_cartes: int
    etoiles: tuple[Niveau, ...]
    secrets: tuple[Niveau, ...]
    histoire: str
    niveau: str


def lire(contenu: bytes) -> _Partie | None:
    """Les valeurs de la partie ; None si rien n'est encore écrit (tout début)."""
    try:
        p = textures_ue1.Paquet(contenu)
        objets = {c: p.lues(c) for c in (
            "JellybeanCollection", "PumpkinPastyCollection", "CauldronCakeCollection",
            "hgame", "LevelInfo", "WizardCardManager", "ChallengeStarManager", "SecretManager")}
    except (ValueError, IndexError, struct.error):
        log.warning("Folio HP3 : sauvegarde illisible", exc_info=True)
        return None
    cartes = _champs(objets["WizardCardManager"]).get("Cards")
    liste = cartes if isinstance(cartes, list) else []
    possedees = set()
    classes = set()
    for carte in liste:
        if not isinstance(carte, list):
            continue
        champs = _champs(carte)
        classe = champs.get("CardClass")
        if isinstance(classe, str) and classe:
            classes.add(classe.lower())
            if champs.get("Status") == POSSEDEE:
                possedees.add(classe.lower())
    dragees = _entier(_champs(objets["JellybeanCollection"]).get("iNumItems"))
    pasties = _entier(_champs(objets["PumpkinPastyCollection"]).get("iNumItems"))
    gateaux = _entier(_champs(objets["CauldronCakeCollection"]).get("iNumItems"))
    if not classes and not (dragees or pasties or gateaux):
        return None
    histoire = _champs(objets["hgame"]).get("CurrentGameState")
    niveau = _champs(objets["LevelInfo"]).get("LevelEnterText")
    return _Partie(
        dragees, pasties, gateaux, frozenset(possedees),
        # Les classes, sans la casse : `wc_ThaddeusThurkell` et ses 79 sœurs en
        # `WC_` font les 80 cartes du jeu.
        len(classes),
        _niveaux(objets["ChallengeStarManager"], etoiles=True),
        _niveaux(objets["SecretManager"], etoiles=False),
        histoire if isinstance(histoire, str) else "",
        niveau if isinstance(niveau, str) else "")


@lru_cache(maxsize=8)
def _valeurs(chemin: str, _mtime_ns: int, _taille: int) -> _Partie | None:
    """Lu une fois tant que le fichier ne change pas (25 à 60 ms par fichier)."""
    return lire(Path(chemin).read_bytes())


def releve(chemin: Path) -> Releve | None:
    numero = re.fullmatch(r"Save(\d+)\.usa", chemin.name, re.I)
    if numero is None:
        return None
    try:
        infos = chemin.stat()
        if infos.st_size > _TAILLE_MAX:
            return None
        modifie = datetime.fromtimestamp(infos.st_mtime)
        valeurs = _valeurs(str(chemin), infos.st_mtime_ns, infos.st_size)
    except OSError:
        log.warning("Folio HP3 : %s illisible", chemin, exc_info=True)
        return None
    n = int(numero.group(1))
    if valeurs is None:
        return Releve(n + 1, chemin, modifie)
    v = valeurs
    return Releve(n + 1, chemin, modifie, True, v.histoire, v.niveau, v.dragees, v.pasties,
                  v.gateaux, v.cartes, v.total_cartes, v.etoiles, v.secrets)


def emplacements(fichiers: dict[str, Path]) -> list[Releve]:
    """Dans l'ordre du menu du jeu (`sauvegardes.fichiers`, miroirs exclus)."""
    releves = [r for r in (releve(p) for p in fichiers.values()) if r is not None]
    return sorted(releves, key=lambda r: r.emplacement)


# ── Les noms des cartes, dans le jeu installé ──

def _fichier(system: Path, base: str, langue: str) -> Path | None:
    """`HpMenu.Fre`, `HpMenu.int`… quelle que soit la casse ; l'anglais en repli."""
    try:
        presents = {p.name.lower(): p for p in system.iterdir()}
    except OSError:
        return None
    for ext in (_EXTENSIONS.get(langue, "int"), "int"):
        trouve = presents.get(f"{base}.{ext}".lower())
        if trouve is not None:
            return trouve
    return None


def numeros_cartes(hgame: Path) -> dict[str, int]:
    """Classe `WC_…` → son numéro de texte (`dialogId` dans ses propriétés par
    défaut). Le motif cherché est l'étiquette entière : index du nom
    `dialogId` dans CE paquet, octet « entier sur 4 octets », valeur."""
    try:
        p = textures_ue1.Paquet(hgame.read_bytes())
    except (OSError, ValueError, IndexError, struct.error):
        log.warning("Folio HP3 : %s illisible", hgame, exc_info=True)
        return {}
    indice = p.indice_nom("dialogId")
    if indice is None:
        return {}
    etiquette = re.escape(_compact(indice) + b"\x22")
    motif = re.compile(etiquette + b"(....)", re.S)
    numeros = {}
    for classe, octets in p.classes("WC_").items():
        trouve = motif.search(octets)
        if trouve is not None:
            numeros[classe] = int.from_bytes(trouve.group(1), "little")
    return numeros


def _compact(v: int) -> bytes:
    a = abs(v)
    octets = bytearray([(0x80 if v < 0 else 0) | (a & 0x3F)])
    a >>= 6
    if a:
        octets[0] |= 0x40
    while a:
        b = a & 0x7F
        a >>= 7
        octets.append(b | (0x80 if a else 0))
    return bytes(octets)


def noms_cartes(system: Path, langue: str) -> dict[str, str]:
    """Classe `WC_…` EN MINUSCULES → nom de la carte dans la langue du jeu ;
    vide sans le jeu."""
    hgame = next((p for p in _lister(system) if p.name.lower() == "hgame.u"), None)
    menu = _fichier(system, "HpMenu", langue)
    if hgame is None or menu is None:
        return {}
    try:
        texte = menu.read_bytes().decode("utf-16")
    except (OSError, UnicodeDecodeError):
        log.warning("Folio HP3 : %s illisible", menu, exc_info=True)
        return {}
    noms = {int(n): nom.strip() for n, nom in
            re.findall(r"^WizardName_(\d+)=(.*?)\r?$", texte, re.M | re.I) if nom.strip()}
    # Clés en minuscules : la sauvegarde et le paquet n'écrivent pas toujours
    # une classe avec la même casse (`wc_ThaddeusThurkell`), Unreal l'ignore.
    return {classe.lower(): noms[n] for classe, n in numeros_cartes(hgame).items() if n in noms}


def _lister(system: Path) -> list[Path]:
    try:
        return list(system.iterdir())
    except OSError:
        return []

"""Le folio de HP3 : ce qu'une sauvegarde du Prisonnier d'Azkaban dit de la partie.

Relevé le 2026-10-15 sur les sauvegardes de Ludo, en LECTURE seule
(`Harry-Potter-PC-Fix/notes/HP3.md`, « Mission d'analyse ») : `SaveN.usa` est
un paquet Unreal 2 (version 129) dont quelques objets portent la partie :

    JellybeanCollection.iNumItems        dragées (813)
    PumpkinPastyCollection.iNumItems     patacitrouilles (23)
    CauldronCakeCollection.iNumItems     fondants du chaudron (5)
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
Son code (`CardID` « VP05 ») donne sa série et son image (`LVP05`,
`textures/HP3_Menu.utx`, 256 couleurs, lue par `textures_ue1`).
"""

import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from src.core import folio, textures_ue1

log = logging.getLogger(__name__)

CARTES = 80          # les classes `WC_` du jeu, toutes séries
POSSEDEE = 5         # EWizardCardStatus.WCS_OwnedByPlayer (lu dans HGame.u)
_TAILLE_MAX = 32 * 1024 * 1024      # une sauvegarde HP3 pèse 4 à 9 Mo
_EMPLACEMENT_RAPIDE = 10            # Save9.usa, la sauvegarde rapide (F5)
_EXTENSIONS = {"fr": "fre", "es": "esp", "de": "det", "it": "itt", "en": "int"}


@dataclass(frozen=True)
class Niveau:
    ident: str          # « CR » : l'`ID` du LevelInfo de la carte (nommé par `defis`)
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
    numero = re.fullmatch(r"Save(\d+)\.usa", chemin.name, re.IGNORECASE)
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
    défaut)."""
    return _proprietes_cartes(hgame)[0]


def _proprietes_cartes(hgame: Path) -> tuple[dict[str, int], dict[str, str]]:
    """Classe `WC_…` → (numéro de texte, code de carte), lus dans les
    propriétés par défaut de chaque classe. Le motif cherché est l'étiquette
    entière : index du nom dans CE paquet, octet de type, valeur ; `dialogId`
    est un entier sur 4 octets, `CardID` une chaîne de 5 (« VP05 » et son zéro)."""
    try:
        p = textures_ue1.Paquet(hgame.read_bytes())
    except (OSError, ValueError, IndexError, struct.error):
        log.warning("Folio HP3 : %s illisible", hgame, exc_info=True)
        return {}, {}
    dialog, carte = p.indice_nom("dialogId"), p.indice_nom("CardID")
    if dialog is None:
        return {}, {}
    motif = re.compile(re.escape(_compact(dialog) + b"\x22") + b"(....)", re.DOTALL)
    motif_code = (re.compile(re.escape(_compact(carte)) + rb"\x5d\x06\x05([A-Z]{2}[0-9]{2})\x00")
                  if carte is not None else None)
    numeros, codes = {}, {}
    for classe, octets in p.classes("WC_").items():
        trouve = motif.search(octets)
        if trouve is not None:
            numeros[classe] = int.from_bytes(trouve.group(1), "little")
        code = motif_code.search(octets) if motif_code is not None else None
        if code is not None:
            codes[classe] = code.group(1).decode("ascii")
    return numeros, codes


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
    return {c.classe: c.nom for c in catalogue(system, langue).cartes}


def _menu(system: Path, langue: str) -> dict[str, str]:
    """`HpMenu.<langue>` (UTF-16) : clé EN MINUSCULES → texte (la casse des clés
    varie dans le fichier : `WizardDesc_1`, `wizarddesc_12`)."""
    menu = _fichier(system, "HpMenu", langue)
    if menu is None:
        return {}
    try:
        texte = menu.read_bytes().decode("utf-16")
    except (OSError, UnicodeDecodeError):
        log.warning("Folio HP3 : %s illisible", menu, exc_info=True)
        return {}
    return {cle.lower(): valeur.strip() for cle, valeur in
            re.findall(r"^([A-Za-z_]+_\d+)=(.*?)\r?$", texte, re.MULTILINE) if valeur.strip()}


# Les séries du folio du jeu, dans l'ordre de son menu : le code de série
# d'une carte (`CardID` « VP05 » → « VP ») → la clé de son titre dans
# `HpMenu` (« Cartes des vampires célèbres »). Relevé le 2026-10-15 : VP05 est
# Vlad Dracula, QU04 Roderick Plumpton, et chaque série compte 5 ou 15 cartes.
_SERIES = (("WZ", 104), ("WI", 105), ("QU", 106), ("VP", 107), ("GB", 108),
           ("HG", 109), ("DR", 110), ("GI", 111), ("BE", 112), ("BO", 113))

# Les trois défis de sortilège : le `LevelID` de leurs deux cartes (`ID` du
# `LevelInfo` de HP3_Ch1CarpeRetractum.unr = « cr », de …B.unr = « crb »)
# → la clé de leur nom dans `HpMenu` (« Défi du Carpe Retractum »).
_DEFIS = (("cr", 2), ("dl", 3), ("gl", 4))


@dataclass(frozen=True)
class CarteHP3:
    classe: str          # en minuscules, comme `Releve.cartes`
    code: str            # « VP05 » : série et rang, nom de son image (`LVP05`)
    serie: str           # « VP »
    nom: str
    dates: str           # « 1812 - 1904 », vide si le texte n'en porte pas
    texte: str


@dataclass(frozen=True)
class Serie:
    code: str
    titre: str
    cartes: tuple[CarteHP3, ...]


@dataclass(frozen=True)
class Catalogue:
    cartes: tuple[CarteHP3, ...] = ()
    series: tuple[Serie, ...] = ()
    defis: dict[str, str] = field(default_factory=dict)   # « cr » → « Défi du Carpe Retractum »


def _description(brut: str, nom: str) -> tuple[str, str]:
    """« Comte Vlad Dracula (apparu en 1390) - Célèbre vampire… » → (dates, texte)."""
    trouve = re.match(r"^(.*?)\s*\(([^)]*)\)\s*-\s*(.*)$", brut, re.DOTALL)
    if trouve is None:
        return "", brut
    return trouve.group(2).strip(), trouve.group(3).strip()


def catalogue(system: Path, langue: str) -> Catalogue:
    """Les 80 cartes rangées par série, et les noms des défis ; vide sans le jeu."""
    return _catalogue(str(system), langue)


@lru_cache(maxsize=4)
def _catalogue(system_txt: str, langue: str) -> Catalogue:
    system = Path(system_txt)
    hgame = next((p for p in _lister(system) if p.name.lower() == "hgame.u"), None)
    textes = _menu(system, langue)
    if hgame is None or not textes:
        return Catalogue()
    numeros, codes = _proprietes_cartes(hgame)
    cartes = []
    for classe, numero in numeros.items():
        nom = textes.get(f"wizardname_{numero}")
        if not nom:
            continue
        code = codes.get(classe, "")
        dates, texte = _description(textes.get(f"wizarddesc_{numero}", ""), nom)
        cartes.append(CarteHP3(classe.lower(), code, code[:2].upper(), nom, dates, texte))
    rang = {code: i for i, (code, _) in enumerate(_SERIES)}
    cartes.sort(key=lambda c: (rang.get(c.serie, len(rang)), c.code, c.nom))
    series = []
    for code, cle in _SERIES:
        membres = tuple(c for c in cartes if c.serie == code)
        if membres:
            series.append(Serie(code, textes.get(f"wizardmenu_{cle}", code), membres))
    defis = {ident: textes[f"achievemntsmenu_{cle}"] for ident, cle in _DEFIS
             if f"achievemntsmenu_{cle}" in textes}
    return Catalogue(tuple(cartes), tuple(series), defis)


def image_carte(system: Path, code: str,
                grande: bool = True) -> textures_ue1.TexturePaletee | None:
    """La carte telle que le jeu la dessine : `LVP05` (256 px) ou `SVP05`
    (128 px) dans `textures/HP3_Menu.utx`. None sans le jeu ou sans code."""
    if not re.fullmatch(r"[A-Z]{2}\d{2}", code):
        return None
    paquet = next((p for p in _lister(system.parent / "textures")
                   if p.name.lower() == "hp3_menu.utx"), None)
    if paquet is None:
        return None
    return textures_ue1.texture(paquet, ("L" if grande else "S") + code)


# ── Les défis, nommés ──

# Le bouclier de chaque défi dans `textures/HP3_Menu.utx` (32 bits, 128 × 128,
# relevé le 2026-10-17) : écusson aux quatre couleurs des maisons et motif du
# sort. Le « DR » de Draconifors ; `ShieldLP` existe aussi, sans défi relevé.
_BOUCLIERS = {"cr": "ShieldCR", "dl": "ShieldDR", "gl": "ShieldGL"}


def image_bouclier(system: Path, ident: str) -> tuple[int, int, bytes] | None:
    """Le bouclier du défi (B V R A) dans le jeu installé, ou None."""
    nom = _BOUCLIERS.get(ident)
    return image_menu(system, nom) if nom is not None else None


# Les icônes du menu (relevées le 2026-10-17) : les friandises en DXT5 128 px,
# le pentagone étoilé des cartes, et celui de chaque série (`Card` + son code).
ICONES = {"cartes": "CardTiny_In", "dragees": "Beans", "pasties": "PumpkinPasties",
          "gateaux": "CauldronCakes"}


def image_menu(system: Path, nom: str) -> tuple[int, int, bytes] | None:
    """Une image de `textures/HP3_Menu.utx` (B V R A), ou None sans le jeu."""
    paquet = next((p for p in _lister(system.parent / "textures")
                   if p.name.lower() == "hp3_menu.utx"), None)
    try:
        date = paquet.stat().st_mtime_ns if paquet is not None else None
    except OSError:
        date = None
    return _image_menu(str(paquet), date, nom) if paquet is not None and date else None


@lru_cache(maxsize=32)
def _image_menu(paquet: str, _date: int, nom: str) -> tuple[int, int, bytes] | None:
    # Gardée tant que le fichier ne change pas : le DXT5 se décode en Python,
    # sinon à chaque partie choisie dans le rail. Les pentagones des séries
    # (`CardWZ`…) sont en 256 couleurs : rendus ici en B V R A comme les autres.
    image = textures_ue1.texture_32(Path(paquet), nom)
    if image is not None:
        return image
    tex = textures_ue1.texture(Path(paquet), nom)
    if tex is None:
        return None
    teintes = [bytes((b, v, r, 0 if tex.masquee and i == 0 else 255))
               for i, (r, v, b, _a) in enumerate(tex.palette)]
    if max(tex.indices, default=0) >= len(teintes):
        return None
    return tex.largeur, tex.hauteur, b"".join(teintes[i] for i in tex.indices)

@dataclass(frozen=True)
class Defi:
    nom: str
    boucliers: int
    boucliers_total: int
    secrets: int
    secrets_total: int
    ident: str = ""     # « cr », « dl », « gl »


def defis(releve: Releve, noms: dict[str, str]) -> list[Defi]:
    """Les défis de sortilège vus dans la partie, leurs deux cartes réunies
    (« cr » + « crb » : 6 + 4 = les 10 boucliers que le jeu annonce)."""
    def defi(ident: str) -> str:
        ident = ident.lower()
        return ident[:-1] if len(ident) == 3 and ident.endswith("b") else ident

    sortie = []
    for ident, nom in noms.items():
        b = [n for n in releve.etoiles if defi(n.ident) == ident]
        s = [n for n in releve.secrets if defi(n.ident) == ident]
        if b or s:
            sortie.append(Defi(nom, sum(n.trouves for n in b), sum(n.total for n in b),
                               sum(n.trouves for n in s), sum(n.total for n in s), ident))
    return sortie


def resume(fichiers: dict[str, Path], system: Path, langue: str) -> folio.Resume | None:
    """La partie à reprendre pour la fiche (`folio.resume_hp1`, même règle)."""
    releve = folio.la_derniere_jouee([r for r in emplacements(fichiers) if r.lu])
    if releve is None:
        return None
    return folio.Resume(releve, "", len(releve.cartes), releve.total_cartes or CARTES)


def _lister(system: Path) -> list[Path]:
    try:
        return list(system.iterdir())
    except OSError:
        return []

"""Le folio de HP2 : ce qu'une sauvegarde de la Chambre des Secrets dit de la partie.

Relevé le 2026-10-16 sur la sauvegarde de Ludo (`Slot1/Save0.usa`, tout début
du jeu), en LECTURE seule (`Harry-Potter-PC-Fix/notes/HP2.md`). Le fichier est
un paquet Unreal 1 ; l'acteur `harry` porte la partie :

    StatusSave[0..n]      StatusSaveData : classe du groupe, classe de l'objet,
                          puis trois entiers (nCount, nCurrCountPotential,
                          nMaxCount). `StatusItemJellybeans` = dragées,
                          `StatusItemGryffindorPts` = points de Gryffondor…
    BronzeCardSave[i]     WCardSaveData : Id de la carte, propriétaire
    SilverCardSave[i]     (ECardOwner, lu dans hgame.u : 0 personne,
    GoldCardSave[i]       1 Harry, 2 un marchand)
    CurrentGameState      avancement de l'histoire (GSTATE010)

et `LevelInfo0.Title` nomme le niveau, en anglais (« Whomping Willow »).

Le catalogue vient du JEU INSTALLÉ, `system/hgame.u` : 101 classes `WC…`
(`WCStarkey`), chacune avec son `Id` (1 à 101, le numéro peint sur la carte),
son texte (`strDescriptionId` = « WizCard_0045 », dans `HPMenu.<langue>`) et
son image (`textureBig`, 256 px, dans le même paquet). Sa catégorie est sa
classe PARENTE : `BronzeCards` (50), `SilverCards` (40), `Goldcards` (11),
le compte que le jeu annonce (`nMaxCount` 50 / 40 / 11).

Unreal n'écrit que ce qui diffère du défaut : une carte absente des listes
n'est à personne, un compteur absent vaut zéro.
"""

from __future__ import annotations

import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from src.core import folio, textures_ue1
from src.core.catalogue_blocs import Sauvegardes

log = logging.getLogger(__name__)

CARTES = 101
BRONZE, ARGENT, OR = "bronze", "argent", "or"
CATEGORIES = (BRONZE, ARGENT, OR)
_PARENTS = {"bronzecards": BRONZE, "silvercards": ARGENT, "goldcards": OR}
_LISTES = {"BronzeCardSave": BRONZE, "SilverCardSave": ARGENT, "GoldCardSave": OR}
HARRY = 1            # ECardOwner.CardOwner_Harry
_TAILLE_MAX = 16 * 1024 * 1024     # une sauvegarde HP2 pèse 1,4 Mo

# L'objet de `StatusSave` → ce qu'il compte.
_MAISONS = {
    "StatusItemGryffindorPts": folio.GRYFFONDOR,
    "StatusItemSlytherinPts": folio.SERPENTARD,
    "StatusItemRavenclawPts": folio.SERDAIGLE,
    "StatusItemHufflePuffPts": folio.POUFSOUFFLE,
}
_DRAGEES = "StatusItemJellybeans"
_ETOILES = "StatusItemStars"

# Le nom, les dates, puis le texte. Français : « Dorcas Bienaimée (1812 - 1904).
# Fonda… » ; anglais : « Dorcas Wellbeloved 1812-1904 Founder… ».
_AVEC_PARENTHESES = re.compile(r"^(.*?)\s*\(([^)]*)\)\s*[.,]?\s*(.*)$", re.S)
_DATES_ANGLAISES = re.compile(
    r"^(.*?)\s+((?:\d{3,4}|\?{4})\s*-\s*(?:\d{3,4}|present|unknown)"
    r"|Medieval, dates unknown|Ancient Greek|[\w-]+ [Cc]entury)\.?\s+(.*)$", re.S)
_SANS_DATES = re.compile(r"^([^.]{2,60})\.\s+(.*)$", re.S)     # « Harry Potter. Le Survivant. »


@dataclass(frozen=True)
class CarteHP2:
    numero: int          # l'`Id` du jeu, 1 à 101 : le numéro peint sur la carte
    classe: str          # `WCStarkey`
    categorie: str       # BRONZE, ARGENT ou OR
    nom: str
    dates: str
    texte: str
    image: str           # nom de la texture 256 px dans hgame.u


@dataclass(frozen=True)
class Releve(folio.Releve):
    """Les champs de HP1 (coupe, dragées, cartes par numéro), et ceux de HP2."""
    histoire: str = ""                    # « GSTATE010 »
    titre: str = ""                       # « Whomping Willow », tel qu'écrit
    etoiles: int | None = None            # None : le jeu n'en a rien écrit
    marchands: frozenset[int] = field(default_factory=frozenset)   # en vente

    @property
    def avancement(self) -> tuple[int, int, int]:
        return (len(self.cartes), self.points.get(folio.GRYFFONDOR, 0), self.dragees)


@dataclass(frozen=True)
class _Partie:
    cartes: frozenset[int]
    marchands: frozenset[int]
    dragees: int
    points: dict[str, int]
    etoiles: int | None
    histoire: str
    titre: str


def lire(contenu: bytes) -> _Partie | None:
    """Les valeurs de la partie ; None si rien n'est encore écrit (tout début)."""
    try:
        p = textures_ue1.Paquet(contenu)
        harry = p.proprietes("harry")
        niveau = p.lues("LevelInfo")
    except (ValueError, IndexError, struct.error):
        log.warning("Folio HP2 : sauvegarde illisible", exc_info=True)
        return None
    if harry is None:
        return None
    compteurs: dict[str, int] = {}
    cartes: set[int] = set()
    marchands: set[int] = set()
    histoire = ""
    for nom, _, valeur in harry:
        if not isinstance(valeur, bytes):
            continue
        if nom == "StatusSave":
            lec = textures_ue1._Lecteur(valeur)
            try:
                lec.index()
                objet = p._classe(lec.index())
            except (IndexError, ValueError):
                continue
            if len(valeur) - lec.p >= 4:
                compteurs.setdefault(objet, max(0, struct.unpack_from("<i", valeur, lec.p)[0]))
        elif nom in _LISTES and len(valeur) == 8:
            ident, proprietaire = struct.unpack("<ii", valeur)
            if 1 <= ident <= CARTES:
                if proprietaire == HARRY:
                    cartes.add(ident)
                elif proprietaire == 2:
                    marchands.add(ident)
        elif nom == "CurrentGameState":
            histoire = _chaine(p, valeur)
    if not compteurs and not cartes:
        return None
    titre = next((v for n, _, v in niveau or () if n == "Title" and isinstance(v, str)), "")
    return _Partie(
        frozenset(cartes), frozenset(marchands), compteurs.get(_DRAGEES, 0),
        {m: compteurs.get(item, 0) for item, m in _MAISONS.items()},
        compteurs.get(_ETOILES), histoire, titre)


def _chaine(p: textures_ue1.Paquet, brut: bytes) -> str:
    valeur = p._valeur(textures_ue1._CHAINE, brut, 0)
    return valeur if isinstance(valeur, str) else ""


@lru_cache(maxsize=8)
def _valeurs(chemin: str, _mtime_ns: int, _taille: int) -> _Partie | None:
    """Lu une fois tant que le fichier ne change pas."""
    return lire(Path(chemin).read_bytes())


def releve(chemin: Path, emplacement: int) -> Releve | None:
    try:
        infos = chemin.stat()
        if infos.st_size > _TAILLE_MAX:
            return None
        modifie = datetime.fromtimestamp(infos.st_mtime)
        v = _valeurs(str(chemin), infos.st_mtime_ns, infos.st_size)
    except OSError:
        log.warning("Folio HP2 : %s illisible", chemin, exc_info=True)
        return None
    if v is None:
        return Releve(emplacement, chemin, modifie)
    return Releve(emplacement, chemin, modifie, "", True, v.cartes, v.dragees, v.points, 0,
                  v.histoire, v.titre, v.etoiles, v.marchands)


def emplacements(spec: Sauvegardes | None) -> list[Releve]:
    """`Slot1/Save0.usa` → emplacement 1, dans l'ordre du menu du jeu."""
    from src.core import sauvegardes
    if spec is None:
        return []
    fichiers = sauvegardes.fichiers(spec)
    releves = []
    for rel, chemin in fichiers.items():
        numero = sauvegardes.numero(rel, spec, len(fichiers))
        r = releve(chemin, numero or 1)
        if r is not None:
            releves.append(r)
    return sorted(releves, key=lambda r: r.emplacement)


def resume(spec: Sauvegardes | None, system: Path, langue: str) -> folio.Resume | None:
    """La partie à reprendre pour la fiche (`folio.resume_hp1`, même règle)."""
    releve_ = folio.la_derniere_jouee([r for r in emplacements(spec) if r.lu])
    if releve_ is None:
        return None
    return folio.Resume(releve_, lieu(system, langue, releve_.titre), len(releve_.cartes), CARTES)


# ── Le catalogue, dans le jeu installé ──

def _hgame(system: Path) -> Path | None:
    try:
        return next((p for p in system.iterdir() if p.name.lower() == "hgame.u"), None)
    except OSError:
        return None


def _textes(system: Path, langue: str) -> dict[str, str]:
    """`HPMenu.<langue>` : clé EN MINUSCULES → texte ; l'anglais en repli."""
    fichier = folio.fichier_textes(system, langue)
    if fichier is None:
        return {}
    try:
        brut = fichier.read_bytes()
    except OSError:
        return {}
    return {cle.lower(): valeur.strip() for cle, valeur in
            re.findall(r"^([A-Za-z_0-9]+)=(.*?)\r?$", folio._decoder(brut), re.M)}


def decouper(brut: str, classe: str) -> tuple[str, str, str]:
    """« Nom (dates). Texte » ou « Nom dates Texte » → (nom, dates, texte)."""
    for motif in (_AVEC_PARENTHESES, _DATES_ANGLAISES):
        trouve = motif.match(brut)
        if trouve is not None:
            return trouve.group(1).strip(" ."), trouve.group(2).strip(), trouve.group(3).strip()
    trouve = _SANS_DATES.match(brut)
    if trouve is not None:
        return trouve.group(1).strip(), "", trouve.group(2).strip()
    # Anglais sans dates ni point : « Queen Maeve Legendary witch… ». Le nom
    # finit sur celui de la classe (`WCMaeve`).
    fin = re.search(rf"\b{re.escape(classe[2:])}\b", brut, re.I)
    if fin is not None and fin.end() < len(brut):
        return brut[:fin.end()].strip(), "", brut[fin.end():].strip()
    return brut, "", ""


def _propriete(p: textures_ue1.Paquet, octets: bytes, nom: str, genre: int) -> bytes | None:
    """La valeur de la propriété `nom` dans les propriétés par défaut d'une
    classe : on essaie la lecture à chaque endroit où son étiquette apparaît,
    et seule une étiquette du bon TYPE compte (l'index d'un nom, un octet,
    se retrouve aussi dans le code de la classe)."""
    indice = p.indice_nom(nom)
    if indice is None:
        return None
    etiquette = _compact(indice)
    debut = octets.find(etiquette)
    while debut >= 0:
        try:
            lues = p._brutes(textures_ue1._Lecteur(octets, debut), len(octets))
        except (ValueError, IndexError, struct.error):
            lues = []
        if lues and lues[0][0] == nom and lues[0][2] == genre and isinstance(lues[0][3], bytes):
            return lues[0][3]
        debut = octets.find(etiquette, debut + 1)
    return None


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


def catalogue(system: Path, langue: str) -> dict[int, CarteHP2]:
    """Les cartes par numéro ; vide sans le jeu."""
    return _catalogue(str(system), langue)


@lru_cache(maxsize=4)
def _catalogue(system_txt: str, langue: str) -> dict[int, CarteHP2]:
    system = Path(system_txt)
    hgame = _hgame(system)
    if hgame is None:
        return {}
    p = textures_ue1.paquet(hgame)
    if p is None:
        return {}
    textes = _textes(system, langue)
    cartes: dict[int, CarteHP2] = {}
    try:
        for classe, octets in p.classes("WC").items():
            categorie = _PARENTS.get(p.parent(classe).lower())
            ident = _propriete(p, octets, "Id", textures_ue1._ENTIER)
            if categorie is None or not isinstance(ident, bytes) or len(ident) != 4:
                continue
            numero = int.from_bytes(ident, "little", signed=True)
            if not 1 <= numero <= CARTES:
                continue
            cle = _propriete(p, octets, "strDescriptionId", textures_ue1._CHAINE)
            cle_txt = cle[1:].split(b"\0")[0].decode("latin-1") if isinstance(cle, bytes) else ""
            image = _propriete(p, octets, "textureBig", textures_ue1._OBJET)
            nom_image = (p._classe(textures_ue1._Lecteur(image).index())
                         if isinstance(image, bytes) and image else "")
            if not nom_image.lower().startswith("wizcard"):
                # Relevé : `WCVablatsky` n'écrit pas sa texture, et l'étiquette
                # de `WCKetteridge` mène ailleurs. Le nom du jeu suit sa classe.
                nom_image = f"WizCard{classe[2:]}BigTexture"
            nom, dates, texte = decouper(textes.get(cle_txt.lower(), ""), classe)
            cartes[numero] = CarteHP2(numero, classe, categorie, nom or classe[2:], dates,
                                      texte, nom_image)
    except (ValueError, IndexError, struct.error):
        log.warning("Folio HP2 : %s illisible", hgame, exc_info=True)
        return {}
    return cartes


def image_carte(system: Path, carte: CarteHP2) -> textures_ue1.TexturePaletee | None:
    """La carte telle que le jeu la dessine (256 px), ou None."""
    hgame = _hgame(system)
    if hgame is None or not carte.image:
        return None
    return textures_ue1.texture(hgame, carte.image)


# Les images du menu du jeu, dans `Textures/HP2_Menu.utx` (relevées le 2026-10-16).
BLASONS = {folio.GRYFFONDOR: "HP2GriffindorCrest", folio.SERPENTARD: "HP2SlytherinCrest",
           folio.SERDAIGLE: "HP2RavenclawCrest", folio.POUFSOUFFLE: "HP2HufflepuffCrest"}
ICONES = {"cartes": "HP2CardFolio", "dragees": "HP2MenuJellybeans", "etoiles": "HP2starcounter",
          BRONZE: "HP2FolioBronzeNormal", ARGENT: "HP2FolioSilverNormal", OR: "HP2FolioGoldNormal"}


def image_menu(system: Path, nom: str) -> textures_ue1.TexturePaletee | None:
    """Une image de `HP2_Menu.utx` (`BLASONS`, `ICONES`), ou None sans le jeu."""
    try:
        dossier = next((p for p in system.parent.iterdir() if p.name.lower() == "textures"), None)
        menu = (next((p for p in dossier.iterdir() if p.name.lower() == "hp2_menu.utx"), None)
                if dossier is not None else None)
    except OSError:
        return None
    return textures_ue1.texture(menu, nom) if menu is not None else None


def lieu(system: Path, langue: str, titre: str) -> str:
    """« Whomping Willow » (écrit en anglais dans la sauvegarde) → « Saule
    cogneur » : la clé dont c'est la valeur dans `HPMenu.int`, puis la même
    clé dans la langue du launcher. Le titre tel quel sinon."""
    if not titre:
        return ""
    anglais = _textes(system, "en")
    cle = next((c for c, v in anglais.items() if c.startswith("maps_") and v == titre), None)
    if cle is None:
        return titre
    return _textes(system, langue).get(cle, titre)

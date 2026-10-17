"""Le folio de HP4 : ce que `HPGOF` dit des parties de la Coupe de feu.

Relevé le 2026-10-16 sur la sauvegarde de Ludo, en LECTURE seule, et VU contre
les écrans de la pensine (touche I : classement, sortilèges, sorts, quêtes ;
`Harry-Potter-PC-Fix/notes/HP4.md`, « La sauvegarde relue contre les écrans ») :

    0x000  « 20CM », taille du fichier, 0x204, 0x7800
    0x010  trois fiches de 0xAC (empreinte, niveau à +0x0C, date à +0x6C, heure à +0x8C),
           puis à +0xAC de chacune : rang, boucliers (-1, -1 si vide)
    0x220  trois corps de 0x2800, un par emplacement

Un corps est une suite de morceaux RenderWare (type, taille, version). Une
entité (type 0x705) est une suite d'enregistrements [longueur][indice][charge] :
0x40000000 = GUID, 0x80000000 = nom sur 32 octets (bourrage NON nettoyé), puis
les attributs. `MagicMastery` porte les 16 jauges de maîtrise, `GlobalData`
la table des quêtes (attributs 0x63 à 0xC6, cinq par quête) et les dragées
(attribut 0x52 : 501, le compteur des pages de cartes, VU le 2026-10-16).
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from src.core.images_ea import entree_big as _entree_big
from src.core.images_ea import images_nommees

log = logging.getLogger(__name__)

_TAILLE = 0x220 + 3 * 0x2800
_ENTITE = 0x705
_DRAGEES = 0x52           # attribut de `GlobalData`
BOUCLIERS = 38            # l'armoire à trophées de la pensine : « 3/38 », VU

# Un nom : (indice dans la table de textes du jeu, nom français). La table du
# front-end (`<Langue>/{1025472C-…}.str` de `data.big`) est triée par clé,
# donc un même indice donne le même texte dans les cinq langues du jeu (VU :
# 149 = « Wingardium Leviosa » partout, 140 = « Bullitor » / « Ebublio »).
# Le nom français sert de repli, par `tr()`, quand la langue du launcher n'est
# pas dans le jeu (l'anglais n'y a pas de table) ou que le jeu n'est pas là.
Nom = tuple[int, str]

# Les rangs VUS sur les deux emplacements de Ludo (fiche d'en-tête +0xAC) ; les
# onze autres existent (13 seuils de maîtrise, code de `RATING` à 0x534930)
# mais leur ordre n'est pas établi : on n'en invente pas le nom.
RANGS: dict[int, Nom] = {0: (108, "Débutant(e)"), 4: (110, "Compétent(e)")}

# Les 16 jauges de `MagicMastery`, dans l'ordre du code de l'écran
# (`GetMagicMasteryStats`, 0x4FC2F0) : (indice de jauge, nom, maximum) ;
# maxima de l'entité de `RWS_GlobalFolder.str`. Accio et Flipendo (4, 5) n'ont
# pas de maximum et n'apparaissent pas à l'écran.
SORTILEGES: tuple[tuple[int, Nom, float], ...] = (
    (0, (149, "Wingardium Leviosa"), 250.0), (1, (137, "Carpe Retractum"), 150.0),
    (2, (135, "Aqua Eructo"), 400.0), (3, (141, "Herbivicus"), 150.0))
SORTS: tuple[tuple[int, Nom, float], ...] = (
    (6, (145, "Orbis"), 100.0), (7, (136, "Avifors"), 100.0), (8, (146, "Orchideus"), 100.0),
    (9, (144, "Citrouillétafors"), 75.0), (10, (148, "Veracrassus"), 100.0),
    (11, (147, "Volatilors"), 100.0), (12, (143, "Lièvrétafor"), 50.0),
    (13, (140, "Bullitor"), 20.0), (14, (139, "Kanarpalmus"), 5.0), (15, (142, "Gonflus"), 50.0))
TITRES: dict[str, Nom] = {"sortileges": (77, "Sortilèges"), "sorts": (101, "Sorts"),
                          "quetes": (102, "Quêtes"), "classement": (105, "Classement"),
                          "boucliers": (97, "Boucliers des Trois Sorciers")}

# Les types de quête (table 0x725F80 de l'exe, 1 à 20) qu'on sait nommer, par
# famille : plusieurs niveaux ont leurs statues de dragon ou leurs champignons,
# le folio additionne. Les défis de Maugrey (4-7, 9, 10) sont des scores, pas
# des objets à ramasser : laissés de côté. Les feux d'artifice n'ont pas de
# nom dans la table : indice -1, le nom français passe par `tr()`.
QUETES: tuple[tuple[Nom, tuple[int, ...]], ...] = (
    ((81, "Détecteurs de magie noire"), (8,)),
    ((83, "Statues de dragon"), (2, 16, 17, 18, 19, 20)),
    ((93, "Champignons"), (1, 12)),
    ((95, "Robinets"), (13,)),
    ((86, "Pelles"), (14,)),
    ((89, "Gargouilles"), (15,)),
    ((99, "Carte éphémère"), (3,)),
    ((-1, "Feux d'artifice du Dr Flibuste"), (11,)))


# Les cartes de collection (Folio Universitas). L'exe range ses 203 cartes dans
# une table de noms (0x725950 : 0 NONE, 1 HARRY_STAMINA_PLUS10_1…) ; la
# sauvegarde garde un bit par carte POSSÉDÉE dans les attributs 0x22 à 0x28 de
# `GlobalData` (bit n du mot 0x22 + n // 32). VU le 2026-10-17 : l'emplacement 1
# porte les bits 1, 8, 9 (Harry : une carte Endurance, deux cartes Sort),
# exactement la page « Jeu 1 » de la pensine (1 Endurance, 2 Sort obtenues).
_CARTES = 0x22
_MOTS_CARTES = 7
_NB_CARTES = 0xCB

# Les familles que la pensine nomme, par leur titre dans la table de textes EN
# JEU (`_JEU`) : même indice dans toutes les langues (VU fr, es, de, it).
FAMILLES: dict[str, Nom] = {
    "endurance": (50, "Endurance"), "sort": (47, "Sort"), "accio": (41, "Accio"),
    "magicus": (49, "Magicus Extremos"), "metamorphose": (51, "Métamorphose"),
    "style": (48, "Style de sort")}
# Les plages de la table de l'exe, dans le même ordre pour les trois :
# endurance (7), sort (7), [Ron : JINX_LUCKY], accio (7), magicus (8), deux ou
# trois cartes mixtes, métamorphose (4), style de sort (4), puis les autres.
PERSONNAGES: tuple[tuple[str, tuple[int, int], dict[str, tuple[int, int]]], ...] = (
    ("Harry", (1, 49), {"endurance": (1, 7), "sort": (8, 14), "accio": (15, 21),
                        "magicus": (22, 29), "metamorphose": (33, 36), "style": (37, 40)}),
    ("Ron", (50, 98), {"endurance": (50, 56), "sort": (57, 63), "accio": (65, 71),
                       "magicus": (72, 79), "metamorphose": (82, 85), "style": (86, 89)}),
    ("Hermione", (99, 147), {"endurance": (99, 105), "sort": (106, 112), "accio": (113, 119),
                             "magicus": (120, 127), "metamorphose": (130, 133),
                             "style": (134, 137)}))
CREATURES = (151, 180)    # cinq créatures, six cartes chacune, communes aux trois
TITRES_CARTES: dict[str, Nom] = {"folio": (618, "Folio Universitas"),
                                 "creatures": (605, "Créatures")}


@dataclass(frozen=True)
class Quete:
    nom: Nom
    trouves: int
    total: int


@dataclass(frozen=True)
class Partie:
    emplacement: int
    ecrite: datetime | None
    niveau: str                       # nom interne (« lvl_003_DragonWoods »)
    rang: int
    boucliers: int
    maitrise: tuple[float, ...] = ()  # les 16 jauges, valeurs brutes
    quetes: tuple[Quete, ...] = ()
    dragees: int = 0
    cartes: frozenset[int] = frozenset()   # indices de la table de l'exe

    @property
    def nom_rang(self) -> Nom | None:
        return RANGS.get(self.rang)


def compte(cartes: frozenset[int], plage: tuple[int, int]) -> int:
    """Les cartes possédées dans cette plage (bornes comprises)."""
    debut, fin = plage
    return sum(1 for c in cartes if debut <= c <= fin)


def _cartes(globales: dict[int, bytes]) -> frozenset[int]:
    mots = [_entier(globales, _CARTES + k) & 0xFFFFFFFF for k in range(_MOTS_CARTES)]
    return frozenset(32 * k + b for k, m in enumerate(mots) for b in range(32)
                     if m >> b & 1 and 0 < 32 * k + b < _NB_CARTES)


def _texte(d: bytes, debut: int, taille: int) -> str:
    return d[debut:debut + taille].split(b"\0", 1)[0].decode("ascii", "replace")


def _entites(corps: bytes) -> dict[str, dict[int, bytes]]:
    """nom d'entité → {indice d'attribut : charge}."""
    entites: dict[str, dict[int, bytes]] = {}
    p = 0
    while p + 12 <= len(corps):
        genre, taille, _ = struct.unpack_from("<III", corps, p)
        if genre == 0 and taille == 0:
            break
        if p + 12 + taille > len(corps):
            raise ValueError("morceau hors du corps")
        if genre == _ENTITE:
            bloc = corps[p + 12:p + 12 + taille]
            nom, attributs, j = "", {}, 0
            while j + 8 <= len(bloc):
                longueur, indice = struct.unpack_from("<II", bloc, j)
                if longueur < 8 or j + longueur > len(bloc):
                    break
                charge = bloc[j + 8:j + longueur]
                if indice == 0x80000000:
                    nom = charge.split(b"\0", 1)[0].decode("ascii", "replace")
                elif indice != 0x40000000:
                    attributs[indice] = charge
                j += longueur
            entites.setdefault(nom, attributs)
        p += 12 + taille
    return entites


def _entier(attributs: dict[int, bytes], indice: int) -> int:
    charge = attributs.get(indice, b"")
    return struct.unpack("<i", charge)[0] if len(charge) == 4 else 0


def _flottant(attributs: dict[int, bytes], indice: int) -> float:
    charge = attributs.get(indice, b"")
    valeur = struct.unpack("<f", charge)[0] if len(charge) == 4 else 0.0
    return valeur if valeur == valeur and 0.0 <= valeur < 1e6 else 0.0


def _quetes(globales: dict[int, bytes]) -> tuple[Quete, ...]:
    # Cinq attributs par quête à partir de 0x63 : type, ?, voulu, trouvé, état.
    par_type: dict[int, tuple[int, int]] = {}
    for k in range(20):
        base = 0x63 + 5 * k
        genre = _entier(globales, base)
        voulu, trouve = _entier(globales, base + 2), _entier(globales, base + 3)
        if 1 <= genre <= 20 and 0 < voulu <= 100 and 0 <= trouve <= voulu:
            par_type[genre] = (trouve, voulu)
    quetes = []
    for nom, genres in QUETES:
        lus = [par_type[g] for g in genres if g in par_type]
        if lus:
            quetes.append(Quete(nom, sum(t for t, _ in lus), sum(v for _, v in lus)))
    return tuple(quetes)


def lire(contenu: bytes) -> list[Partie]:
    """Les parties du fichier ; [] si ce n'est pas une sauvegarde de HP4 telle que relevée."""
    if len(contenu) < _TAILLE or contenu[:4] != b"20CM":
        return []
    parties = []
    for k in range(3):
        fiche = 0x10 + k * 0xAC
        rang, boucliers = struct.unpack_from("<ii", contenu, fiche + 0xAC)
        if rang < 0:
            continue
        try:
            ecrite: datetime | None = datetime.strptime(
                f"{_texte(contenu, fiche + 0x6C, 16)} {_texte(contenu, fiche + 0x8C, 16)}",
                "%d/%m/%Y %H:%M:%S")
        except ValueError:
            ecrite = None
        corps = contenu[0x220 + k * 0x2800:0x220 + (k + 1) * 0x2800]
        try:
            entites = _entites(corps)
        except (ValueError, struct.error):
            log.warning("Folio HP4 : emplacement %d illisible", k + 1, exc_info=True)
            entites = {}
        maitrise = entites.get("MagicMastery", {})
        globales = entites.get("GlobalData", {})
        parties.append(Partie(
            k + 1, ecrite, _texte(contenu, fiche + 0x0C, 0x40), rang,
            max(0, min(boucliers, BOUCLIERS)),
            tuple(_flottant(maitrise, i) for i in range(16)) if maitrise else (),
            _quetes(globales), max(0, _entier(globales, _DRAGEES)), _cartes(globales)))
    return parties


def part(partie: Partie, indice: int, maximum: float) -> float:
    """La jauge de l'écran : valeur ÷ maximum, bornée à 1."""
    if not partie.maitrise or maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, partie.maitrise[indice] / maximum))


# ── Les textes du jeu installé ──

_LANGUES = {"fr": "French", "es": "Spanish", "de": "German", "it": "Italian",
            "pt": "Portuguese_Portugal"}
_FRONT = "{1025472C-AB8F-438C-87FB-E0AA3DFE4007}.str"
_REPERE = (149, "Wingardium Leviosa")


def _table_loc(flux: bytes) -> tuple[str, ...]:
    """La plus grande table « LOCH/LOCL » du flux : textes UTF-16 LE par indice."""
    meilleure: tuple[str, ...] = ()
    p = flux.find(b"LOCH")
    while p >= 0:
        locl = p + 0x14
        if flux[locl:locl + 4] == b"LOCL" and locl + 16 <= len(flux):
            n = struct.unpack_from("<I", flux, locl + 12)[0]
            if 0 < n < 100000 and locl + 16 + 4 * n <= len(flux):
                textes = []
                for o in struct.unpack_from(f"<{n}I", flux, locl + 16):
                    a = locl + o
                    q = a
                    while q + 1 < len(flux) and flux[q:q + 2] != b"\0\0":
                        q += 2
                    textes.append(flux[a:q].decode("utf-16-le", "replace"))
                if len(textes) > len(meilleure):
                    meilleure = tuple(textes)
        p = flux.find(b"LOCH", p + 4)
    return meilleure


# La table EN JEU (pensine, Folio Universitas) : 2 763 textes, un autre flux
# que le front-end ; repère identique dans les quatre langues relevées.
_JEU = "{3932FD6C-38F4-4867-BC66-CE9355A07CF5}.str"
_REPERE_JEU = (49, "Magicus Extremos")


def textes(system: Path, langue: str) -> tuple[str, ...]:
    """Les textes du front-end du jeu installé dans cette langue ; () sinon."""
    return _textes(str(system), langue, _FRONT, _REPERE)


def textes_jeu(system: Path, langue: str) -> tuple[str, ...]:
    """Les textes de la pensine du jeu installé dans cette langue ; () sinon."""
    return _textes(str(system), langue, _JEU, _REPERE_JEU)


@lru_cache(maxsize=4)
def _textes(system_txt: str, langue: str, flux: str, repere: Nom) -> tuple[str, ...]:
    dossier = _LANGUES.get(langue)
    system = Path(system_txt)
    if dossier is None or not system.is_dir():
        return ()
    big = next((p for p in system.iterdir() if p.name.lower() == "data.big"), None)
    if big is None:
        return ()
    try:
        table = _table_loc(_entree_big(big, f"{dossier}/{flux}"))
    except (OSError, struct.error):
        log.warning("Folio HP4 : textes du jeu illisibles", exc_info=True)
        return ()
    # Une autre version du jeu rangerait autrement : alors on se tait.
    if len(table) <= repere[0] or table[repere[0]] != repere[1]:
        return ()
    return table


# Les images du menu sont dans le même flux, en blocs EA « SHPI » : six
# dragées 32 × 32 nommées « BEAN » (contour, bleue, verte, orange, violette,
# rouge), relevées le 2026-10-17. Le format 0x7B : un octet par pixel, puis un
# bloc attaché 0x2A qui porte la palette en B, V, R, A.
_DRAGEE = 5          # la rouge
_DOSSIERS_IMAGES = ("French", "English", "Spanish", "German", "Italian", "Portuguese_Portugal")


def images_shpi(flux: bytes, nom: bytes) -> list[tuple[int, int, bytes]]:
    """Les images 0x7B des blocs SHPI à image unique nommée `nom`, dans
    l'ordre du flux : (largeur, hauteur, pixels B V R A)."""
    trouvees = []
    p = flux.find(b"SHPI")
    while 0 <= p <= len(flux) - 24:
        if struct.unpack_from("<I", flux, p + 8)[0] == 1 and flux[p + 16:p + 20] == nom:
            image = _image_7b(flux, p + struct.unpack_from("<I", flux, p + 20)[0])
            if image is not None:
                trouvees.append(image)
        p = flux.find(b"SHPI", p + 4)
    return trouvees


def _image_7b(flux: bytes, q: int) -> tuple[int, int, bytes] | None:
    if q + 16 > len(flux) or flux[q] & 0x7F != 0x7B:
        return None
    largeur, hauteur = struct.unpack_from("<HH", flux, q + 4)
    if not (0 < largeur <= 512 and 0 < hauteur <= 512):
        return None
    indices = flux[q + 16:q + 16 + largeur * hauteur]
    saut, r = int.from_bytes(flux[q + 1:q + 4], "little"), q
    while saut and r + saut + 16 <= len(flux):
        r += saut
        if flux[r] & 0x7F == 0x2A:
            nombre = struct.unpack_from("<H", flux, r + 4)[0]
            palette = flux[r + 16:r + 16 + 4 * nombre]
            if len(indices) < largeur * hauteur or len(palette) < 4 * nombre or \
                    max(indices) >= nombre:
                return None
            pixels = b"".join(palette[4 * i:4 * i + 4] for i in indices)
            return largeur, hauteur, pixels
        saut = int.from_bytes(flux[r + 1:r + 4], "little")
    return None


def image_dragee(system: Path) -> tuple[int, int, bytes] | None:
    """La dragée du menu du jeu installé (32 × 32, B V R A), ou None."""
    return _image_dragee(str(system))


@lru_cache(maxsize=2)
def _image_dragee(system_txt: str) -> tuple[int, int, bytes] | None:
    system = Path(system_txt)
    try:
        big = next((p for p in system.iterdir() if p.name.lower() == "data.big"), None)
        if big is None:
            return None
        for dossier in _DOSSIERS_IMAGES:
            flux = _entree_big(big, f"{dossier}/{_FRONT}")
            if flux:
                dragees = images_shpi(flux, b"BEAN")
                return dragees[_DRAGEE] if len(dragees) > _DRAGEE else None
    except (OSError, struct.error):
        log.warning("Folio HP4 : images du menu illisibles", exc_info=True)
    return None


# Les objets à collectionner de la pensine, même flux, en 0x7B 128 × 64 (relevé le
# 2026-10-17) : l'objet au centre, une volute de chaque côté.
ICONES = {"boucliers": "collect_tw_shield", "cartes": "collect_vanishing_card"}


def image_menu(system: Path, cle: str) -> tuple[int, int, bytes] | None:
    """Une icône `ICONES` du menu du jeu installé (B V R A), ou None."""
    return _images_menu(str(system)).get(cle)


@lru_cache(maxsize=2)
def _images_menu(system_txt: str) -> dict[str, tuple[int, int, bytes]]:
    images: dict[str, tuple[int, int, bytes]] = {}
    try:
        big = next((p for p in Path(system_txt).iterdir() if p.name.lower() == "data.big"), None)
        if big is None:
            return images
        for dossier in _DOSSIERS_IMAGES:
            flux = _entree_big(big, f"{dossier}/{_FRONT}")
            if not flux:
                continue
            positions = images_nommees(flux)
            for cle, nom in ICONES.items():
                q = positions.get(nom)
                image = _image_7b(flux, q) if q is not None else None
                if image is not None:
                    images[cle] = image
            break
    except (OSError, struct.error):
        log.warning("Folio HP4 : icônes du menu illisibles", exc_info=True)
    return images


def nom(table: tuple[str, ...], ref: Nom) -> str | None:
    """Le texte du jeu pour ce nom, None s'il faut le nom français (par `tr()`)."""
    indice, _ = ref
    if 0 <= indice < len(table) and table[indice].strip():
        return table[indice].strip()
    return None


def releve(chemin: Path) -> list[Partie]:
    try:
        if chemin.stat().st_size > 4 * _TAILLE:
            return []
        return lire(chemin.read_bytes())
    except OSError:
        log.warning("Folio HP4 : %s illisible", chemin, exc_info=True)
        return []

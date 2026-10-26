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

import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from src.core import folio, images_ea
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


# Les jeux de cartes de la boutique (relevés le 2026-10-26, `notes/HP4.md`) :
# l'exe en garde la composition à 0x770E40, huit entiers par jeu de personnage
# (sept cartes et un 0), sept par jeu de quête ou de créature ; `data.big`
# nomme le flux de chaque jeu dans son index (« Harry_1 » → {363C1EAD-…}.str),
# et ce flux porte ses illustrations `wc_hry_set1_01`… dans l'ordre de la
# liste. VU sur Harry 1 et 2, Ron 1 et 6 : l'icône et la valeur imprimées sur
# chaque image sont celles de la carte de même rang. La dernière carte d'un
# jeu n'a pas d'illustration, ni la carte de la créature elle-même (sa
# cinquième image est une maquette « Dugbog 05 3D ») : `images` compte celles
# qui en ont. Les feux d'artifice (186-190, 201) n'ont pas de jeu dans la
# boutique du PC.
#
# Les titres sont ceux de la boutique, dans la table EN JEU (`textes_jeu`) :
# « Jeu 1 » à « Jeu 6 » (612-617) pour un personnage, « Jeu 1 » à « Jeu 3 »
# (607-609) pour les quêtes, le nom de la créature. Le repli français « Jeu {} »
# se complète du numéro du jeu.
@dataclass(frozen=True)
class JeuCartes:
    titre: Nom
    image: str                  # préfixe des illustrations : « wc_hry_set1 »
    flux: str                   # GUID de l'entrée `.str` de data.big
    cartes: tuple[int, ...]     # indices de la table de l'exe, dans l'ordre des images
    images: int                 # les premières cartes qui ont une illustration


def _jeux_perso(prefixe: str, flux: tuple[str, ...],
                cartes: tuple[tuple[int, ...], ...]) -> tuple[JeuCartes, ...]:
    return tuple(JeuCartes((612 + k, "Jeu {}"), f"wc_{prefixe}_set{k + 1}", f, c, 6)
                 for k, (f, c) in enumerate(zip(flux, cartes, strict=True)))


GROUPES_CARTES: tuple[tuple[Nom | str, tuple[JeuCartes, ...]], ...] = (
    ("Harry", _jeux_perso("hry", (
        "363C1EAD-12D1-4553-8756-7711F5893584", "4C452D7C-3A24-48E1-98F4-87D530ED7091",
        "A642D35A-D373-431D-8D26-B11C5EE5BBEA", "CFB3EF28-BB34-407B-AF5D-D8BB79B7A502",
        "5B3CFE57-6FA1-4E2E-9642-D651B615E6F4", "530C3FA0-673B-471F-9B9A-4E0049BECA19"), (
        (1, 2, 3, 8, 9, 15, 29), (4, 5, 10, 11, 16, 37, 7), (6, 12, 17, 39, 22, 41, 14),
        (13, 18, 38, 23, 33, 24, 47), (19, 40, 25, 44, 20, 26, 21), (30, 34, 202, 27, 32, 36, 28)))),
    ("Ron", _jeux_perso("ron", (
        "C8E5E838-E9E6-4034-A474-717187CF665F", "9CDFA275-1E74-4F92-8F97-0F0AF8B0EA41",
        "F69933C2-DD8A-4594-88CE-283E209B1B55", "94E071B2-8246-4C1D-AB85-AB9C34BE1E42",
        "734620E0-A008-44B3-B75F-85998EC55716", "677CE73E-C37B-4728-9893-FFE64E37C883"), (
        (57, 58, 59, 90, 83, 86, 96), (60, 61, 82, 93, 89, 50, 79), (62, 85, 87, 51, 72, 65, 63),
        (94, 88, 52, 73, 66, 74, 56), (80, 53, 75, 67, 81, 76, 78), (54, 68, 69, 77, 55, 70, 71)))),
    ("Hermione", _jeux_perso("hermione", (
        "8945393A-39D9-4651-9C0C-1808E59B8FD1", "5E306C0E-0600-4D1A-8AE5-37D5014D198B",
        "2899CA56-D2C2-4C86-B238-2BD83599FAB5", "CDBA9833-0E78-4449-A501-E7E28910F40C",
        "4C6A54D5-1C7F-4B87-AED5-532339A7C07A", "DCF10E48-D649-4081-A250-6D6C9FD134BA"), (
        (120, 121, 122, 113, 114, 138, 127), (123, 124, 115, 116, 141, 99, 126),
        (125, 117, 130, 100, 106, 134, 119), (118, 131, 101, 107, 137, 108, 112),
        (142, 102, 109, 135, 133, 110, 145), (103, 136, 128, 111, 104, 129, 105)))),
    # Un personnage garde son nom. Les jeux de quêtes suivent leurs images :
    # objets des niveaux, statues de dragon, cartes éphémères.
    ((606, "Quêtes"), (
        JeuCartes((607, "Jeu {}"), "wc_quests_set1", "05C7D38B-5A5C-4DBB-A3AF-1799186FC9DF",
                  (191, 192, 193, 194, 195, 149), 5),
        JeuCartes((608, "Jeu {}"), "wc_quests_set2", "976162D3-07DA-4D3A-8BA5-47DE05AF63F8",
                  (196, 197, 198, 199, 200, 150), 5),
        JeuCartes((609, "Jeu {}"), "wc_quests_set3", "243A020A-32F5-4FB6-A0BF-511AE7A54AA2",
                  (181, 182, 183, 184, 185, 148), 5))),
    ((605, "Créatures"), (
        JeuCartes((345, "Fangieux"), "wc_dugbog", "138851E3-044A-446E-8659-C23456EC245A",
                  (152, 154, 155, 153, 151, 156), 4),
        JeuCartes((585, "Salamandre"), "wc_salamander", "A6800F40-6335-4AA0-AF3A-08C6C406769B",
                  (158, 160, 161, 159, 157, 162), 4),
        JeuCartes((351, "Erkling"), "wc_erkling", "BC3D8AC8-FF71-4C2C-BCE6-FCB9873FCDF7",
                  (164, 166, 167, 165, 163, 168), 4),
        JeuCartes((591, "Scroutt à pétard"), "wc_skrewt", "B33214FF-7BCD-4133-BB1D-4C78FF3B3777",
                  (170, 172, 173, 171, 169, 174), 4),
        JeuCartes((516, "Vampirmite"), "wc_vampyr", "EA84238A-63FD-4F32-9886-689614A499FC",
                  (176, 178, 179, 177, 175, 180), 4))))


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


def image_carte(system: Path, jeu: JeuCartes, rang: int) -> tuple[int, int, bytes] | None:
    """L'illustration de la carte de rang `rang` (0 en premier) d'un jeu, telle
    que la boutique du jeu installé la montre : 512 × 256 pour un personnage,
    256 × 256 sinon (B V R A). None sans illustration ou sans le jeu.

    Environ 0,08 s à décoder : à appeler hors du fil de l'interface."""
    if not 0 <= rang < jeu.images:
        return None
    return _image_carte(str(system), jeu.flux, f"{jeu.image}_{rang + 1:02d}")


@lru_cache(maxsize=8)
def _image_carte(system_txt: str, flux: str, nom_image: str) -> tuple[int, int, bytes] | None:
    try:
        donnees, positions = _flux_cartes(system_txt, flux)
        q = positions.get(nom_image)
        return images_ea.image(donnees, q, cote_max=512) if q is not None else None
    except (OSError, struct.error):
        log.warning("Folio HP4 : carte %s illisible", nom_image, exc_info=True)
        return None


@lru_cache(maxsize=2)
def _flux_cartes(system_txt: str, flux: str) -> tuple[bytes, dict[str, int]]:
    """Le flux d'un jeu de cartes (1,2 Mo) et ses images : les cartes d'un même
    jeu se lisent à la suite, le flux ne se relit pas pour chacune."""
    big = next((p for p in Path(system_txt).iterdir() if p.name.lower() == "data.big"), None)
    if big is None:
        return b"", {}
    donnees = _entree_big(big, "{" + flux + "}.str")
    return donnees, images_nommees(donnees)


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


def resume(fichiers: dict[str, Path], system: Path, langue: str) -> folio.Resume | None:
    """La partie à montrer sur la fiche : les boucliers de l'armoire à trophées,
    et le rang en guise de lieu. Rien tant que la partie n'a rien gagné (Ludo,
    2026-10-15 : « tant qu'on a rien on laisse la description »)."""
    parties = [(p, chemin) for chemin in fichiers.values() for p in releve(chemin)]
    if not parties:
        return None
    partie, chemin = max(parties, key=lambda pc: pc[0].ecrite or datetime.min)
    if partie.boucliers <= 0 and partie.rang <= 0:
        return None
    rang = partie.nom_rang
    lieu = (nom(textes(system, langue), rang) or "") if rang is not None else ""
    quand = partie.ecrite or datetime.fromtimestamp(chemin.stat().st_mtime)
    return folio.Resume(partie, lieu, partie.boucliers, BOUCLIERS, quand, "boucliers")

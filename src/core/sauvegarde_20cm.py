"""Écrire dans la sauvegarde du joueur, à SON choix (décision C8 de Ludo, 2026-11-17) : la difficulté
propre de HP5 et la Nouvelle partie+ de HP4.

Ludo : « oui. éventuellement demander une nouvelle sauvegarde qu'on fabrique nous-mêmes ou réécrire sur la
sauvegarde actuelle ». Le joueur choisit dans l'onglet Difficulté (`ui/choix_sauvegarde`) : une partie NEUVE,
fabriquée dans un emplacement libre (la sienne ne bouge pas), la SIENNE réécrite (une copie de sécurité
d'abord, `copies_sauvegardes`), ou rien. Rien ne s'écrit jamais sans ce choix, ni pendant que le jeu tourne
(il réécrirait la partie en sortant) : c'est à l'appelant de le vérifier.

**Le conteneur `20CM`** (`HPGOF` de HP4, `HPOOTP` de HP5 ; atelier, `notes/doc/hp4/SAUVEGARDE.md` § 2 et
`doc/hp5/SAUVEGARDE.md` § 2, LU dans les exe et CALCULÉ à l'octet) : sept mots petit-boutistes, magie, taille
totale, taille de la partie 1 (les trois fiches de l'écran des parties), taille de la partie 2 (les trois
corps), CRC de chacune et CRC des 24 premiers octets. Le jeu refuse un fichier dont un seul ne concorde pas.

**HP5, la difficulté** (0 Facile, 1 Normal, 2 Difficile ; PROUVÉE par 0x5775B0) vit à TROIS endroits d'un
emplacement : la fiche (valeur gardée +0x8C et courante +0x90 de la ligne 1 du bloc de réglages), et surtout
le CORPS (+0x8C, le mot 20 du bloc GLOB de l'objet de partie, que le chargement remet en jeu), qui porte sa
propre somme à +0x14. VU le 2026-11-18 (essais 24 et 24c) : la fiche seule ne suffit pas ; les trois écrits,
l'écran des réglages de la partie dit « Facile » et le jeu garde 0 en réécrivant. Une partie NEUVE est la
même partie recopiée dans un emplacement libre (fiche et corps ne portent pas leur numéro, CALCULÉ sur les
trois parties de Ludo), à la difficulté choisie.

**HP4, la Nouvelle partie+** : repartir du premier niveau avec les cartes, dragées, quêtes et jauges d'une
partie avancée (les entités `GlobalData` et `MagicMastery` du corps), son rang et ses boucliers. VU le
2026-11-18 (essai 24b) : une partie tout juste commencée qui reçoit ces deux blocs se charge et se joue, la
pensine y montre les niveaux terminés. La partie FABRIQUÉE ici est cette partie-là : les blocs d'une partie
tout juste commencée (CALCULÉS sur celle de Ludo : le niveau en cours `lvl_001_CampsiteWoods`, ses deux
entrées d'historique, identiques à l'octet dans toute partie qui les a traversées, et `SaveFlags`, dont les
huit drapeaux valent 0), les deux blocs repris de la partie d'origine. Réécrire la sienne la remplace par
celle-là (son niveau et son historique sont perdus : la copie de sécurité les garde).
"""

import logging
import struct
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core import copies_sauvegardes, octets_gardes, sauvegardes
from src.core.ecriture_atomique import ecrire_octets_atomique
from src.core.game_data import GameData

log = logging.getLogger(__name__)

JEUX = ("hp4", "hp5")
PARTIES = 3
MAGIE = b"20CM"
ENTETE = 0x1C
_PLAFOND = 64 * 1024     # HP4 : 31 Ko, HP5 : 4 Ko

# ── Le conteneur ──

_TABLE: list[int] = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) if _c & 0x80000000 else _c << 1
        _c &= 0xFFFFFFFF
    _TABLE.append(_c)


class Illisible(ValueError):
    """Pas un fichier que le jeu accepterait, ou pas le format lu : rien ne s'y écrit."""


def crc(octets: bytes) -> int:
    """La somme du jeu (`FUN_0061E6AD` de gof_f.exe) : registre parti du complément des quatre premiers
    octets (gros-boutiste), chaque octet suivant entrant par le bas, résultat complémenté. Pas le
    CRC-32/BZIP2 : sur les mêmes octets il rend une autre valeur."""
    if len(octets) < 4:
        return 0
    r = ~int.from_bytes(octets[:4], "big") & 0xFFFFFFFF
    for x in octets[4:]:
        r = (((r << 8) & 0xFFFFFFFF) | x) ^ _TABLE[r >> 24]
    return ~r & 0xFFFFFFFF


def ouvrir(octets: bytes) -> tuple[bytes, bytes]:
    """Les deux parties du fichier, après les contrôles du jeu (taille, magie, trois CRC)."""
    if len(octets) < ENTETE:
        raise Illisible("fichier plus court que son en-tête")
    magie, total, t1, t2, c1, c2, ch = struct.unpack_from("<4sIIIIII", octets, 0)
    if magie != MAGIE or total != len(octets) or ENTETE + t1 + t2 != total:
        raise Illisible("en-tête 20CM inattendu")
    p1, p2 = octets[ENTETE:ENTETE + t1], octets[ENTETE + t1:]
    if (ch, c1, c2) != (crc(octets[:0x18]), crc(p1), crc(p2)):
        raise Illisible("somme de contrôle fausse")
    return p1, p2


def composer(p1: bytes, p2: bytes) -> bytes:
    """Le fichier complet pour ces deux parties, ses trois CRC recalculés."""
    debut = struct.pack("<4sIIIII", MAGIE, ENTETE + len(p1) + len(p2), len(p1), len(p2), crc(p1), crc(p2))
    return debut + struct.pack("<I", crc(debut)) + p1 + p2


def _decouper(p1: bytes, p2: bytes, fiche: int, corps: int) -> tuple[list[bytes], list[bytes]]:
    if len(p1) != fiche * PARTIES or len(p2) != corps * PARTIES:
        raise Illisible("parties de taille inattendue")
    return ([p1[k * fiche:(k + 1) * fiche] for k in range(PARTIES)],
            [p2[k * corps:(k + 1) * corps] for k in range(PARTIES)])


def _u32(octets: bytes, ou: int) -> int:
    valeur: int = struct.unpack_from("<I", octets, ou)[0]
    return valeur


def _i32(octets: bytes, ou: int) -> int:
    valeur: int = struct.unpack_from("<i", octets, ou)[0]
    return valeur


def _texte(octets: bytes) -> str:
    return octets.split(b"\0", 1)[0].decode("latin-1")


@dataclass(frozen=True)
class Partie:
    """Un emplacement occupé, tel que l'écran des parties du jeu le montre."""
    numero: int                  # 1 à 3
    ecrite: datetime | None
    avancement: int | None = None    # HP5 : pour cent
    difficulte: int | None = None    # HP5 : 0 Facile, 1 Normal, 2 Difficile (celle du corps, qui fait foi)
    rang: int | None = None          # HP4
    boucliers: int | None = None     # HP4


# ── HP5 : la difficulté ──

_FICHE5, _CORPS5 = 0x178, 0x400
_LIEU5, _DATE5, _POUR_CENT5, _REGLAGES5 = 0x04, 0x44, 0x74, 0x78
_DIFF_CHOIX, _DIFF_GARDEE, _DIFF_COURANTE = 0x88, 0x8C, 0x90
_VERSION_REGLAGES = 3
_MAGIE_CORPS5 = b"PTOO30.1"
_CORPS_TAILLE, _CORPS_SOMME, _CORPS_DIFFICULTE = 0x08, 0x14, 0x8C
DIFFICULTES = ("Facile", "Normal", "Difficile")     # clés tr() ; l'ordre du jeu


def _somme_corps5(corps: bytes) -> int:
    """La somme que le jeu range à corps + 0x14 : ses `taille / 4` premiers mots, ce mot-là compté à zéro."""
    taille = _u32(corps, _CORPS_TAILLE)
    if taille % 4 or not 0x18 <= taille <= len(corps):
        raise Illisible("corps de taille inattendue")
    mots: list[int] = list(struct.unpack_from(f"<{taille // 4}I", corps, 0))
    mots[_CORPS_SOMME // 4] = 0
    return sum(mots) & 0xFFFFFFFF


def _vide5(fiche: bytes) -> bool:
    return fiche[_LIEU5] == 0


def _controler5(fiche: bytes, corps: bytes) -> int:
    """La difficulté d'un emplacement occupé, après les contrôles du format lu ; lève Illisible sinon."""
    if _u32(fiche, _REGLAGES5) != _VERSION_REGLAGES or _u32(fiche, _DIFF_CHOIX) != len(DIFFICULTES):
        raise Illisible("bloc de réglages inattendu")
    if corps[:8] != _MAGIE_CORPS5 or _u32(corps, _CORPS_SOMME) != _somme_corps5(corps):
        raise Illisible("corps inattendu")
    difficulte = _u32(corps, _CORPS_DIFFICULTE)
    if difficulte >= len(DIFFICULTES) or _u32(fiche, _DIFF_GARDEE) != difficulte:
        raise Illisible("difficulté inattendue")
    return difficulte


def _date5(fiche: bytes) -> datetime | None:
    annee, mois, _semaine, jour, heure, minute, seconde = struct.unpack_from("<7I", fiche, _DATE5)
    try:
        return datetime(annee, mois, jour, heure, minute, seconde)
    except ValueError:
        return None


def _parties5(p1: bytes, p2: bytes) -> tuple[Partie | None, ...]:
    fiches, corps = _decouper(p1, p2, _FICHE5, _CORPS5)
    parties: list[Partie | None] = []
    for k in range(PARTIES):
        if _vide5(fiches[k]):
            parties.append(None)
            continue
        pour_cent = _u32(fiches[k], _POUR_CENT5)
        parties.append(Partie(k + 1, _date5(fiches[k]), pour_cent if pour_cent <= 100 else None,
                              _controler5(fiches[k], corps[k])))
    return tuple(parties)


def difficulte_hp5(octets: bytes, de: int, valeur: int, vers: int) -> bytes:
    """Le fichier où l'emplacement `vers` (1 à 3) porte la partie `de` à la difficulté `valeur` (0 à 2) :
    `vers == de` la réécrit, un `vers` libre en reçoit une copie. Les autres emplacements ne bougent pas."""
    p1, p2 = ouvrir(octets)
    fiches, corps = _decouper(p1, p2, _FICHE5, _CORPS5)
    if not 0 <= valeur < len(DIFFICULTES) or {de, vers} - set(range(1, PARTIES + 1)):
        raise ValueError("emplacement ou difficulté hors bornes")
    if _vide5(fiches[de - 1]) or (vers != de and not _vide5(fiches[vers - 1])):
        raise ValueError("la partie d'origine manque, ou l'emplacement visé n'est pas libre")
    _controler5(fiches[de - 1], corps[de - 1])
    fiche, le_corps = bytearray(fiches[de - 1]), bytearray(corps[de - 1])
    struct.pack_into("<2I", fiche, _DIFF_GARDEE, valeur, valeur)
    struct.pack_into("<I", le_corps, _CORPS_DIFFICULTE, valeur)
    struct.pack_into("<I", le_corps, _CORPS_SOMME, _somme_corps5(bytes(le_corps)))
    fiches[vers - 1], corps[vers - 1] = bytes(fiche), bytes(le_corps)
    return composer(b"".join(fiches), b"".join(corps))


# ── HP4 : la Nouvelle partie+ ──

_FICHE4, _CORPS4 = 0xAC, 0x2800
_DATE4, _HEURE4, _RANG4 = 0x60, 0x80, 0xA0
_VERSION_RW = 0x1C02002D
_SAUVE, _ENTITE, _HISTOIRE = 0x722, 0x705, 0x723
_NOM_ENTITE = 0x80000000
REPRIS = ("GlobalData", "MagicMastery")
_DRAPEAUX = "SaveFlags"
PREMIER_NIVEAU = "lvl_001_CampsiteWoods"
_HISTOIRE_NEUVE = (PREMIER_NIVEAU, "FrontEnd_CharacterSelect")


def _blocs(corps: bytes) -> list[tuple[int, bytes]]:
    """Les blocs RenderWare d'un corps, dans l'ordre : (type, bloc entier avec son en-tête de douze octets)."""
    liste, i = [], 0
    while i + 12 <= len(corps):
        type_, taille, version = struct.unpack_from("<III", corps, i)
        if type_ == 0 and taille == 0:
            break
        if version != _VERSION_RW or i + 12 + taille > len(corps):
            raise Illisible("bloc de corps inattendu")
        liste.append((type_, corps[i:i + 12 + taille]))
        i += 12 + taille
    if any(corps[i:]):
        raise Illisible("octets après le dernier bloc")
    return liste


def _enregistrements(bloc: bytes) -> list[tuple[int, int, int]]:
    """(début, longueur, indice) de chaque enregistrement d'une entité 0x705."""
    liste, i = [], 12
    while i + 8 <= len(bloc):
        longueur, indice = struct.unpack_from("<II", bloc, i)
        if longueur < 8 or i + longueur > len(bloc):
            raise Illisible("entité inattendue")
        liste.append((i, longueur, indice))
        i += longueur
    return liste


def _nom(type_: int, bloc: bytes) -> str:
    """Le nom d'une entité (enregistrement d'indice 0x80000000), ou le niveau d'un bloc d'historique."""
    if type_ == _HISTOIRE:
        return _texte(bloc[12:])
    if type_ != _ENTITE:
        return ""
    for debut, longueur, indice in _enregistrements(bloc):
        if indice == _NOM_ENTITE:
            return _texte(bloc[debut + 8:debut + longueur])
    return ""


def _drapeaux_neufs(bloc: bytes) -> bytes:
    """`SaveFlags` d'une partie tout juste commencée : les huit drapeaux (indices 0 à 7) à zéro."""
    neuf = bytearray(bloc)
    vus = 0
    for debut, longueur, indice in _enregistrements(bloc):
        if indice < 8:
            if longueur != 12:
                raise Illisible("drapeau de longueur inattendue")
            neuf[debut + 8:debut + 12] = bytes(4)
            vus += 1
    if vus != 8:
        raise Illisible("drapeaux inattendus")
    return bytes(neuf)


def _vide4(fiche: bytes) -> bool:
    return fiche[0] == 0


def _date4(fiche: bytes) -> datetime | None:
    try:
        return datetime.strptime(f"{_texte(fiche[_DATE4:_HEURE4])} {_texte(fiche[_HEURE4:_RANG4])}",
                                 "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def _parties4(p1: bytes, p2: bytes) -> tuple[Partie | None, ...]:
    fiches, corps = _decouper(p1, p2, _FICHE4, _CORPS4)
    parties: list[Partie | None] = []
    for k in range(PARTIES):
        if _vide4(fiches[k]):
            parties.append(None)
            continue
        _blocs(corps[k])
        parties.append(Partie(k + 1, _date4(fiches[k]), rang=_i32(fiches[k], _RANG4),
                              boucliers=_i32(fiches[k], _RANG4 + 4)))
    return tuple(parties)


def _champ(texte: str, taille: int) -> bytes:
    octets = texte.encode("ascii")
    if len(octets) >= taille:
        raise ValueError("texte trop long pour son champ")
    return octets + bytes(taille - len(octets))


def _corps_neuf(corps: bytes) -> bytes:
    """Le corps d'une partie tout juste commencée qui garde `REPRIS` de ce corps-ci."""
    liste = _blocs(corps)
    sauve = next((b for t, b in liste if t == _SAUVE), None)
    entites = {_nom(t, b): b for t, b in liste if t == _ENTITE}
    histoire = {_nom(t, b): b for t, b in liste if t == _HISTOIRE}
    if sauve is None or any(n not in entites for n in (*REPRIS, _DRAPEAUX)) \
            or any(n not in histoire for n in _HISTOIRE_NEUVE):
        raise Illisible("la partie d'origine n'a pas tous les blocs d'une partie neuve")
    charge = b"evas" + PREMIER_NIVEAU.encode("ascii") + b"\0"
    neuf_sauve = struct.pack("<III", _SAUVE, len(charge), _VERSION_RW) + charge
    blocs = (neuf_sauve, entites["GlobalData"], _drapeaux_neufs(entites[_DRAPEAUX]), entites["MagicMastery"],
             *(histoire[n] for n in _HISTOIRE_NEUVE))
    contenu = b"".join(blocs)
    if len(contenu) > _CORPS4:
        raise Illisible("corps trop grand")
    return contenu + bytes(_CORPS4 - len(contenu))


def nouvelle_partie_plus_hp4(octets: bytes, de: int, vers: int, maintenant: datetime) -> bytes:
    """Le fichier où l'emplacement `vers` (1 à 3) est une partie neuve au premier niveau, avec les cartes,
    dragées, quêtes, jauges, rang et boucliers de la partie `de` : `vers == de` la remplace, un `vers` libre
    la reçoit. Les autres emplacements ne bougent pas."""
    p1, p2 = ouvrir(octets)
    fiches, corps = _decouper(p1, p2, _FICHE4, _CORPS4)
    if {de, vers} - set(range(1, PARTIES + 1)):
        raise ValueError("emplacement hors bornes")
    if _vide4(fiches[de - 1]) or (vers != de and not _vide4(fiches[vers - 1])):
        raise ValueError("la partie d'origine manque, ou l'emplacement visé n'est pas libre")
    source = fiches[de - 1]
    fiche = (_champ(PREMIER_NIVEAU, _DATE4) + _champ(maintenant.strftime("%d/%m/%Y"), _HEURE4 - _DATE4)
             + _champ(maintenant.strftime("%H:%M:%S"), _RANG4 - _HEURE4) + source[_RANG4:])
    corps[vers - 1] = _corps_neuf(corps[de - 1])
    fiches[vers - 1] = fiche
    return composer(b"".join(fiches), b"".join(corps))


# ── Lire et écrire le fichier du joueur ──

_LECTEURS: dict[str, Callable[[bytes, bytes], tuple[Partie | None, ...]]] = {"hp4": _parties4, "hp5": _parties5}


def parties(jeu: str, octets: bytes) -> tuple[Partie | None, ...]:
    """Les trois emplacements (None = libre) ; lève Illisible si le fichier n'est pas le format lu."""
    if jeu not in _LECTEURS:
        raise ValueError(f"{jeu} : pas de sauvegarde 20CM")
    return _LECTEURS[jeu](*ouvrir(octets))


@dataclass(frozen=True)
class Fichier:
    """Le fichier de sauvegarde du joueur tel qu'il a été lu : c'est sur CES octets que le choix porte."""
    jeu: str
    rel: str
    chemin: Path
    octets: bytes
    parties: tuple[Partie | None, ...]

    @property
    def libre(self) -> int | None:
        """Le premier emplacement libre (1 à 3), None s'il n'y en a pas."""
        return next((k + 1 for k, p in enumerate(self.parties) if p is None), None)

    @property
    def occupees(self) -> tuple[Partie, ...]:
        return tuple(p for p in self.parties if p is not None)


def lire(game: GameData) -> Fichier | None:
    """Le fichier de sauvegarde de ce jeu (les parties du joueur, pas celles d'une seule vie), None s'il
    n'y en a pas ou s'il n'est pas le format lu (dans ce cas rien ne se propose, rien ne s'écrit)."""
    if game.id not in _LECTEURS:
        return None
    presents = sauvegardes.fichiers(game.sauvegardes)
    if len(presents) != 1:
        return None
    rel, chemin = next(iter(presents.items()))
    try:
        octets = octets_gardes.lire(chemin, _PLAFOND)
        return Fichier(game.id, rel, chemin, octets, parties(game.id, octets))
    except (OSError, Illisible):
        log.info("Sauvegarde de %s illisible ou d'un autre format : rien ne s'y écrit", game.id, exc_info=True)
        return None


def ecrire(game: GameData, lu: Fichier, octets: bytes) -> str:
    """Remplace le fichier du joueur par `octets`, après une copie de sécurité de son état actuel. Rend ""
    si c'est fait, sinon pourquoi rien n'a été écrit : "change" (le fichier n'est plus celui qui a été lu :
    le jeu l'a réécrit entre-temps), "copie" (la copie de sécurité n'a pas pu se faire), "ecriture"."""
    parties(lu.jeu, octets)      # ce qu'on écrit doit se relire comme le jeu le relira
    spec = game.sauvegardes
    try:
        if spec is None or octets_gardes.lire(lu.chemin, _PLAFOND) != lu.octets:
            return "change"
    except OSError:
        return "change"
    if not copies_sauvegardes.mettre_a_l_abri(game.id, spec, lu.rel):
        return "copie"
    try:
        ecrire_octets_atomique(lu.chemin, octets)
        if octets_gardes.lire(lu.chemin, _PLAFOND) != octets:
            return "ecriture"
    except OSError:
        log.warning("Sauvegarde de %s non écrite", game.id, exc_info=True)
        return "ecriture"
    log.info("Sauvegarde de %s réécrite au choix du joueur (%s)", game.id, lu.chemin)
    return ""

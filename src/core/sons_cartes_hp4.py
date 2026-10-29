"""Le son des cartes de HP4 : ce que la boutique du jeu joue quand une carte s'ouvre.

Relevé le 2026-10-29 (`notes/HP4.md` de l'atelier), lecture seule de la copie du joueur :

- La scène d'un jeu de cartes (le flux `{GUID}.str` de `data.big` que `folio_hp4`
  lit déjà pour les illustrations) nomme ses sons en `seed:audio`, banque
  `fe_cards` : `fe_cards\\0sal_roar\\0`. Certains jeux n'en ont aucun.
- La table `fe_cards.map` (flux du front-end `{2C4DCA3C-…}.str`) relie un son à ses
  échantillons : 75 fiches de 24 octets (hachage FNV-1 du nom, signature, rang),
  puis 75 nœuds dans l'ordre des rangs (40 octets, puis le nombre d'échantillons à
  +32, puis 16 octets par échantillon : son numéro, son poids).
- Les échantillons sont dans `speech.big`, `audio/fe_cards.sdt` : une banque EA
  « BNKl » version 5 (94 sons, table de décalages à 0x14, en-têtes « PT » à
  étiquettes : 0x85 nombre d'échantillons, 0x88 début des données, 0x84 fréquence,
  0x82 canaux), codée en EA-XA v2 (trames de 15 octets pour 28 échantillons, ou
  0xEE puis 28 échantillons 16 bits gros-boutistes). Le numéro d'un échantillon
  est son rang dans la banque, à partir de 1. Décodage vérifié à l'échantillon
  près contre vgmstream (sons 1 et 51).
"""

import logging
import re
import struct
from functools import lru_cache
from pathlib import Path

from src.core.images_ea import entree_big

log = logging.getLogger(__name__)

_FRONT = "{2C4DCA3C-9A49-41E8-A5C0-35DFA119D99B}.str"
_BANQUE = "audio/fe_cards.sdt"
# Octets 4 à 15 de chaque fiche de `fe_cards.map`, identiques pour les 75 sons.
_SIGNATURE = bytes.fromhex("01000000d00700005c837604")
_NOM_TABLE = b"\x00fe_cards\x00\x00\x00\x00\x00"
_SON_DE_SCENE =re.compile(rb"fe_cards\x00([a-z0-9_]+)\x00")
_COEFS = (0, 240, 460, 392, 0, 0, -208, -220)
_TRAME_PCM = 0xEE


def fnv1(nom: str) -> int:
    """Le hachage FNV-1 (32 bits) d'un nom de son, tel que la table le range."""
    h = 0x811C9DC5
    for octet in nom.encode("ascii"):
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= octet
    return h


def sons_de_scene(flux: bytes) -> list[str]:
    """Les sons qu'une scène de carte nomme, dans leur ordre d'apparition."""
    vus: dict[str, None] = {}
    for m in _SON_DE_SCENE.finditer(flux):
        vus.setdefault(m.group(1).decode("ascii"), None)
    return list(vus)


def table_echantillons(front: bytes) -> dict[int, tuple[int, ...]]:
    """Hachage FNV-1 d'un son → numéros de ses échantillons ; {} sans la table.

    Le flux du front-end porte aussi les tables des autres banques (`fe_general`…),
    de même signature : on part du nom de la banque, en tête de la sienne."""
    nom = front.find(_NOM_TABLE)
    premiere = front.find(_SIGNATURE, nom) if nom >= 0 else -1
    if premiere < 4:
        return {}
    debut = premiere - 4
    fiches: list[tuple[int, int]] = []
    p = debut
    while p + 24 <= len(front) and front[p + 4:p + 16] == _SIGNATURE:
        h, rang = struct.unpack_from("<I12xI", front, p)
        fiches.append((h, rang))
        p += 24
    noeuds: list[tuple[int, ...]] = []
    while len(noeuds) < len(fiches) and p + 40 <= len(front):
        n = struct.unpack_from("<H", front, p + 32)[0]
        if p + 40 + 16 * n > len(front):
            return {}
        noeuds.append(tuple(struct.unpack_from("<I", front, p + 40 + 16 * k)[0] for k in range(n)))
        p += 40 + 16 * n
    if len(noeuds) != len(fiches):
        return {}
    return {h: noeuds[rang] for h, rang in fiches if 0 <= rang < len(noeuds)}


def _etiquettes(banque: bytes, p: int) -> dict[int, int]:
    """Les étiquettes d'un en-tête « PT » (valeurs gros-boutistes)."""
    etiquettes: dict[int, int] = {}
    q = p + 4
    while q < len(banque):
        t = banque[q]
        q += 1
        if t == 0xFF:
            break
        if t in (0xFC, 0xFD, 0xFE):
            continue
        taille = banque[q]
        etiquettes[t] = int.from_bytes(banque[q + 1:q + 1 + taille], "big")
        q += 1 + taille
    return etiquettes


def echantillon(banque: bytes, numero: int) -> tuple[int, list[int]] | None:
    """L'échantillon `numero` (à partir de 1) : (fréquence, PCM 16 bits mono)."""
    if banque[:4] != b"BNKl":
        return None
    total = struct.unpack_from("<H", banque, 6)[0]
    if not 1 <= numero <= total:
        return None
    entree = 0x14 + 4 * (numero - 1)
    p = entree + struct.unpack_from("<I", banque, entree)[0]
    if banque[p:p + 2] != b"PT":
        return None
    e = _etiquettes(banque, p)
    if e.get(0x82, 1) != 1 or 0x85 not in e or 0x88 not in e:
        return None
    return e.get(0x84, 22050), decoder_ea_xa(banque, e[0x88], e[0x85])


def decoder_ea_xa(donnees: bytes, debut: int, total: int) -> list[int]:
    """EA-XA v2 mono → PCM 16 bits (arrêt propre si les données manquent)."""
    sortie: list[int] = []
    h1 = h2 = 0
    p = debut
    while len(sortie) < total:
        if p >= len(donnees):
            break
        info = donnees[p]
        if info == _TRAME_PCM:
            if p + 61 > len(donnees):
                break
            h1, h2 = struct.unpack_from(">hh", donnees, p + 1)
            sortie.extend(struct.unpack_from(">28h", donnees, p + 5))
            p += 61
            continue
        if p + 15 > len(donnees) or info >> 4 > 3:
            break
        c1, c2 = _COEFS[info >> 4], _COEFS[(info >> 4) + 4]
        decalage = (info & 0x0F) + 8
        for i in range(28):
            octet = donnees[p + 1 + i // 2]
            quartet = octet & 0x0F if i & 1 else octet >> 4
            s = ((((quartet ^ 8) - 8) << 28) >> decalage) + c1 * h1 + c2 * h2 >> 8
            s = max(-32768, min(32767, s))
            h2, h1 = h1, s
            sortie.append(s)
        p += 15
    return sortie[:total]


def wav(frequence: int, pcm: list[int]) -> bytes:
    """Un fichier WAV 16 bits mono."""
    corps = struct.pack(f"<{len(pcm)}h", *pcm)
    return (b"RIFF" + struct.pack("<I", 36 + len(corps)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, frequence, 2 * frequence, 2, 16)
            + b"data" + struct.pack("<I", len(corps)) + corps)


def ordre_des_sons(sons: list[str]) -> list[str]:
    """Les sons à essayer à l'ouverture d'une carte : l'entrée en scène d'abord
    (`sal_intro`, `dgb_intro`), puis les autres dans l'ordre de la scène. Le
    premier qui a un échantillon est joué (`psp_grn_*` n'en a pas)."""
    return sorted(sons, key=lambda s: "intro" not in s)


def son_carte(system: Path, flux: str) -> bytes | None:
    """Le WAV du son d'un jeu de cartes (`JeuCartes.flux`), None s'il n'en a
    pas ou que le jeu manque. Quelques dixièmes de seconde : hors du fil de
    l'interface."""
    return _son_carte(str(system), flux)


@lru_cache(maxsize=32)
def _son_carte(system_txt: str, flux: str) -> bytes | None:
    system = Path(system_txt)
    try:
        data = next((p for p in system.iterdir() if p.name.lower() == "data.big"), None)
        speech = next((p for p in system.iterdir() if p.name.lower() == "speech.big"), None)
        if data is None or speech is None:
            return None
        table = _table(str(data))
        sons = ordre_des_sons(sons_de_scene(entree_big(data, "{" + flux + "}.str")))
        numeros = next((n for n in (table.get(fnv1(s), ()) for s in sons) if n), ())
        if not numeros:
            return None
        lu = echantillon(_banque(str(speech)), numeros[0])
        return wav(*lu) if lu is not None and lu[1] else None
    except (OSError, struct.error, ValueError):
        log.warning("Cartes HP4 : son illisible pour %s", flux, exc_info=True)
        return None


@lru_cache(maxsize=1)
def _table(data_txt: str) -> dict[int, tuple[int, ...]]:
    return table_echantillons(entree_big(Path(data_txt), _FRONT))


@lru_cache(maxsize=1)
def _banque(speech_txt: str) -> bytes:
    return entree_big(Path(speech_txt), _BANQUE)

"""4 Go d'adresses pour les jeux 32 bits : le drapeau « Large Address Aware ».

Les huit exécutables sont des programmes 32 bits SANS ce drapeau (relevé le
2026-10-26, atelier `notes/CACHE_ET_CONFIG.md`) : Windows les borne à 2 Go
d'adresses, quelle que soit la mémoire du PC. Avec le drapeau, un programme
32 bits reçoit 4 Go sous Windows 64 bits (et sous Wine). C'est le préalable à
tout cache plus grand, packs HD de HP5 et HP6 compris (demande de Ludo,
2026-10-26 : « débloquer les 4 Go de RAM »).

Un bit de l'en-tête PE (`IMAGE_FILE_LARGE_ADDRESS_AWARE`, 0x20 des
caractéristiques COFF) et la somme de contrôle de l'en-tête optionnel,
recalculée comme `CheckSumMappedFile`. Posé juste avant chaque lancement :
une mise à jour ou une réparation qui remet l'exe d'origine le perd, le
lancement suivant le remet. Le launcher ne vérifie que la PRÉSENCE des
fichiers (`fichiers_essentiels`) : l'exe modifié n'y passe pas pour abîmé.

Seulement pour les jeux de `JEUX`, chacun lancé avec le drapeau et vu
démarrer : un exe qui vérifierait sa propre intégrité refuserait de partir.
"""

import logging
import struct
from pathlib import Path

from src.core.ecriture_atomique import ecrire_octets_atomique

log = logging.getLogger(__name__)

# Jeux lancés avec le drapeau, vus démarrer, adresse 0x90000000 accessible (essais du
# 2026-10-26). PAS hp7b : sa protection refuse l'exe modifié (« Impossible d'activer un
# module de sécurité requis (13000) »).
JEUX: frozenset[str] = frozenset({"hp1", "hp2", "hp3", "hp4", "hp5", "hp6", "hp7a"})

_LAA = 0x0020
_I386 = 0x014C
_TAILLE_MAX = 64 * 1024 * 1024     # les huit exes font moins de 20 Mo


def _entete(donnees: bytes) -> tuple[int, int] | None:
    """(position des caractéristiques COFF, position de la somme de contrôle),
    ou None si ce n'est pas un exécutable 32 bits x86 lisible."""
    if len(donnees) < 0x40 or donnees[:2] != b"MZ":
        return None
    pe = struct.unpack_from("<I", donnees, 0x3C)[0]
    if pe + 24 + 68 > len(donnees) or donnees[pe:pe + 4] != b"PE\0\0":
        return None
    machine = struct.unpack_from("<H", donnees, pe + 4)[0]
    if machine != _I386:
        return None
    return pe + 22, pe + 24 + 64


def somme_de_controle(donnees: bytes, position: int) -> int:
    """La somme de l'en-tête optionnel, champ lui-même compté à zéro
    (algorithme de `CheckSumMappedFile`)."""
    tampon = bytearray(donnees)
    tampon[position:position + 4] = b"\0\0\0\0"
    if len(tampon) % 2:
        tampon.append(0)
    total: int = sum(struct.unpack(f"<{len(tampon) // 2}H", tampon))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (total + len(donnees)) & 0xFFFFFFFF


def a_le_drapeau(exe: Path) -> bool | None:
    """Vrai/faux, ou None si le fichier n'est pas un exe 32 bits lisible."""
    try:
        with open(exe, "rb") as f:
            donnees = f.read(4096)
    except OSError:
        return None
    pos = _entete(donnees)
    if pos is None:
        return None
    return bool(struct.unpack_from("<H", donnees, pos[0])[0] & _LAA)


def poser(exe: Path, oui: bool = True) -> bool:
    """Pose (ou retire) le drapeau. Vrai si l'exe l'a désormais dans l'état
    voulu ; faux s'il est illisible, pas 32 bits, ou pas inscriptible. Ne lève
    jamais : sans le drapeau, le jeu tourne comme avant."""
    try:
        if exe.stat().st_size > _TAILLE_MAX:
            return False
        donnees = bytearray(exe.read_bytes())
    except OSError:
        log.warning("4 Go : %s illisible", exe, exc_info=True)
        return False
    pos = _entete(bytes(donnees[:4096]))
    if pos is None:
        return False
    caract = struct.unpack_from("<H", donnees, pos[0])[0]
    voulu = (caract | _LAA) if oui else (caract & ~_LAA)
    if voulu == caract:
        return True
    struct.pack_into("<H", donnees, pos[0], voulu)
    struct.pack_into("<I", donnees, pos[1], somme_de_controle(bytes(donnees), pos[1]))
    try:
        ecrire_octets_atomique(exe, bytes(donnees))
    except OSError:
        log.warning("4 Go : %s non inscriptible", exe, exc_info=True)
        return False
    log.info("4 Go : drapeau %s sur %s", "posé" if oui else "retiré", exe.name)
    return True


def appliquer(jeu: str, exe: Path) -> None:
    """Avant un lancement : le drapeau pour les jeux vus avec."""
    # L'en-tête d'abord (4 Ko) : `poser` relit tout l'exe, 18 Mo pour rien à
    # chaque lancement une fois le drapeau en place (audit du 2026-10-29).
    if jeu in JEUX and a_le_drapeau(exe) is False:
        poser(exe)

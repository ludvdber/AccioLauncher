"""Le compteur de morts du correctif : `accio_morts.tsv`, relu par le launcher (1.4, `notes/DIFFICULTE_1.4.md` § 9).

Les DLL de HP1, HP2 (`winmm`) et HP3 (`dinput8`) ajoutent une ligne par évènement à ce fichier, à côté de leur ini,
quand `[Accio.Game] DeathCounter=1` : quatre champs séparés par une tabulation, en UTF-8 : horodatage ISO local,
évènement (`mort`, `chute_balai`, `une_vie_fin`), carte, détail (`source/onelife.h` du correctif, `FormatLine`).

Pas encore branché : aucune clé `DeathCounter` n'est posée tant qu'une mort n'a pas été VUE en jeu, et la place du
compte dans le Carnet reste à regarder. Pur : aucune dépendance Qt.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

FICHIER = "accio_morts.tsv"
_OCTETS_MAX = 256_000


@dataclass(frozen=True)
class Releve:
    morts: int = 0
    chutes_balai: int = 0
    fins_une_vie: int = 0
    # (carte, morts), de la plus meurtrière à la moins ; à égalité, l'ordre alphabétique.
    par_carte: tuple[tuple[str, int], ...] = ()


def analyser(texte: str) -> Releve:
    """Une ligne qui n'a pas la forme écrite par la DLL ne compte pas : le fichier a pu être coupé en cours d'écriture."""
    evenements: Counter[str] = Counter()
    cartes: Counter[str] = Counter()
    for ligne in texte.splitlines():
        champs = ligne.split("\t")
        if len(champs) != 4:
            continue
        try:
            datetime.fromisoformat(champs[0])
        except ValueError:
            continue
        evenement, carte = champs[1], champs[2]
        evenements[evenement] += 1
        if evenement == "mort" and carte:
            cartes[carte] += 1
    return Releve(evenements["mort"], evenements["chute_balai"], evenements["une_vie_fin"],
                  tuple(sorted(cartes.items(), key=lambda kv: (-kv[1], kv[0]))))


def lire(dossier_exe: Path) -> Releve:
    """Le relevé du jeu installé dans ce dossier ; vide si le fichier est absent ou illisible."""
    try:
        with (dossier_exe / FICHIER).open("rb") as f:
            taille = f.seek(0, 2)
            f.seek(max(0, taille - _OCTETS_MAX))
            brut = f.read()
    except OSError:
        return Releve()
    if taille > _OCTETS_MAX:   # la première ligne lue est coupée
        brut = brut.partition(b"\n")[2]
    return analyser(brut.decode("utf-8", errors="replace"))

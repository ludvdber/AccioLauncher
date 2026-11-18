"""Le compteur de morts du correctif : `accio_morts.tsv`, relu par le launcher (1.4, `notes/DIFFICULTE_1.4.md` § 9).

Les DLL des six jeux (`winmm` de HP1/HP2, `dinput8` de HP3, `d3d9` de HP4 à HP6) ajoutent une ligne par évènement
à ce fichier, à côté de leur ini, quand `[Accio.Game] DeathCounter=1` : quatre champs séparés par une tabulation, en
UTF-8 : horodatage ISO local, évènement, carte, détail (`source/onelife.h` du correctif, `FormatLine`). Évènements :
`mort` ; `une_vie_fin`, dont le détail est la durée de la vie en secondes ; et deux qui ne sont PAS des morts (C5) :
`chute_balai` (Quidditch) et `chute_equipier` (un compagnon de HP3 que personne ne joue, un équipier de HP4).

Le launcher ne pose `DeathCounter=1` qu'avec le mode à une seule vie (`une_vie`) : le compteur seul n'est VU que dans
HP2. Le relevé se lit au retour de la partie (fin de vie annoncée) et dans le Carnet (Défis). La carte n'y est pas un
niveau sûr : la DLL écrit le paquet de l'acteur, `Save0` quand le niveau vient d'une sauvegarde (§ 8, défaut 5).
Pur : aucune dépendance Qt.
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
    chutes_equipier: int = 0
    plus_longue_vie: int = 0                 # secondes, 0 : aucune vie finie lisible
    derniere_fin: datetime | None = None     # la fin de vie la plus récente


def analyser(texte: str) -> Releve:
    """Une ligne qui n'a pas la forme écrite par la DLL ne compte pas : le fichier a pu être coupé en cours d'écriture."""
    evenements: Counter[str] = Counter()
    cartes: Counter[str] = Counter()
    plus_longue = 0
    derniere: datetime | None = None
    for ligne in texte.splitlines():
        champs = ligne.split("\t")
        if len(champs) != 4:
            continue
        try:
            quand = datetime.fromisoformat(champs[0])
        except ValueError:
            continue
        if quand.tzinfo is not None:        # la DLL écrit l'heure locale sans décalage ; une ligne qui en porte un
            quand = quand.astimezone().replace(tzinfo=None)   # se compare quand même aux autres
        evenement, carte, detail = champs[1], champs[2], champs[3].strip()
        evenements[evenement] += 1
        if evenement == "mort" and carte:
            cartes[carte] += 1
        elif evenement == "une_vie_fin":
            if detail.isascii() and detail.isdigit():
                plus_longue = max(plus_longue, int(detail))
            if derniere is None or quand > derniere:
                derniere = quand
    return Releve(evenements["mort"], evenements["chute_balai"], evenements["une_vie_fin"],
                  tuple(sorted(cartes.items(), key=lambda kv: (-kv[1], kv[0]))),
                  evenements["chute_equipier"], plus_longue, derniere)


def lire(dossier_exe: Path) -> Releve:
    """Le relevé du jeu installé dans ce dossier ; vide si le fichier est absent ou illisible."""
    try:
        with (dossier_exe / FICHIER).open("rb") as f:
            taille = f.seek(0, 2)
            # Un octet AVANT la fenêtre : s'il est « \n », la première ligne
            # est entière et n'est pas jetée avec la coupée (audit du 2026-11-16).
            debut = max(0, taille - _OCTETS_MAX - 1)
            f.seek(debut)
            brut = f.read()
    except OSError:
        return Releve()
    if debut > 0:   # la première ligne lue est coupée (ou n'est que la fin de la précédente)
        brut = brut.partition(b"\n")[2]
    return analyser(brut.decode("utf-8", errors="replace"))

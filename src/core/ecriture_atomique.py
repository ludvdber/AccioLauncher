"""Écriture atomique d'un fichier texte : un temporaire voisin, puis `os.replace`.

Un arrêt au milieu (plantage, coupure, disque plein) laisse l'ancien fichier
entier ou le nouveau entier, jamais un JSON tronqué qui ferait perdre la config
ou l'historique de jeu. Le temporaire naît dans le MÊME dossier : entre deux
volumes, un renommage devient une copie et n'est plus atomique.

La même dizaine de lignes vivait recopiée dans `config`, `stats`, `succes`,
`sauvegardes` et `discographie` (réunie le 2026-10-25).
"""

import contextlib
import os
import tempfile
from pathlib import Path


def ecrire_atomique(chemin: Path, texte: str, suffixe: str = ".tmp") -> None:
    """Remplace `chemin` par `texte` (UTF-8) d'un seul coup.

    Le dossier doit exister. Lève `OSError` si l'écriture échoue, et le
    temporaire ne reste pas derrière, même sur une interruption.
    """
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=suffixe)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texte)
        os.replace(tmp, chemin)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def ecrire_octets_atomique(chemin: Path, octets: bytes, suffixe: str = ".tmp") -> None:
    """Comme `ecrire_atomique`, pour des octets (un exécutable, `memoire_4go`)."""
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=suffixe)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(octets)
        os.replace(tmp, chemin)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def mettre_de_cote(chemin: Path) -> Path | None:
    """Renomme un fichier illisible en `<nom>.<date>.corrompu`, sans écraser.

    Le nom était fixe (`.corrompu`) : une seconde corruption, des mois plus
    tard, détruisait la première copie, celle qui portait l'historique complet
    (audit du 2026-10-29). Rend le nouveau chemin, ou None si le renommage a
    échoué (le fichier est peut-être verrouillé : ce n'est alors pas une
    corruption, voir `marquer_illisible`).
    """
    from datetime import datetime

    horodatage = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    cible = chemin.with_name(f"{chemin.stem}.{horodatage}.corrompu")
    n = 1
    while cible.exists():
        n += 1
        cible = chemin.with_name(f"{chemin.stem}.{horodatage}-{n}.corrompu")
    try:
        os.replace(chemin, cible)
    except OSError:
        return None
    return cible


# Fichiers qu'une lecture n'a pas pu OUVRIR (verrou d'un antivirus, d'une
# synchronisation) pendant cette session. Les repartir de vide puis les
# sauvegarder remplaçait la vraie config ou le vrai journal par des valeurs
# par défaut, définitivement (audit du 2026-10-29). Une lecture réussie les
# retire.
_ILLISIBLES: set[Path] = set()


def marquer_illisible(chemin: Path, illisible: bool = True) -> None:
    if illisible:
        _ILLISIBLES.add(chemin)
    else:
        _ILLISIBLES.discard(chemin)


def ne_pas_ecraser(chemin: Path) -> bool:
    """Vrai si ce fichier n'a pas pu être lu : on n'écrit pas par-dessus."""
    return chemin in _ILLISIBLES

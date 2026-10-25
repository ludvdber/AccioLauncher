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

"""Utilitaires Windows partagés (NTFS Zone.Identifier, ...)."""

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def remove_zone_identifier(root: Path, pattern: str = "*") -> int:
    """Supprime le flag NTFS Zone.Identifier des fichiers sous `root` matchant `pattern`.

    Windows pose ce flag sur tout fichier extrait d'archive téléchargée, ce qui
    bloque le chargement de DLL et déclenche des erreurs UE1 type
    "Can't find file for package".

    Retourne le nombre de fichiers traités.
    """
    if sys.platform != "win32" or not root.exists():
        return 0
    count = 0
    for f in root.rglob(pattern):
        if not f.is_file():
            continue
        try:
            os.remove(str(f) + ":Zone.Identifier")
            count += 1
        except OSError:
            pass
    return count

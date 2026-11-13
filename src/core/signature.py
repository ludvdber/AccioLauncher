"""La signature d'un fichier (ou d'un dossier) pour un cache « lu une fois tant qu'il ne change pas ».

(date de modification, taille) dit si un fichier a changé, SAUF s'il vient d'être écrit :
la date n'avance qu'au tic de l'horloge du système (16 ms sous Windows, 2 s sur une clé en
FAT32), et deux écritures de même taille dans le même tic gardent la même signature. La CI
Windows l'a montré le 2026-11-13 : « SSAAFactor=1.5 » réécrit en « SSAAFactor=2.0 » était
relu 1.5 (`test_un_et_demi_decimal_aller_retour`). Comme git (« racy git »), on ne se fie à
une date qu'une fois passée d'une marge ; avant, l'appelant relit sans garder.
"""

import os
import time

_MARGE_NS = 2_000_000_000          # le tic de FAT32, le plus grossier des systèmes de fichiers courants

type Signature = tuple[int, int]


def fiable(etat: os.stat_result) -> Signature | None:
    """(date, taille) si l'on peut s'y fier pour garder une lecture ; None s'il vient de changer."""
    if time.time_ns() - etat.st_mtime_ns < _MARGE_NS:
        return None                 # aussi une date dans le futur (horloge reculée)
    return etat.st_mtime_ns, etat.st_size

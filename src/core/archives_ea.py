"""Les archives d'EA des jeux 4 à 6 : lister, découper, extraire vers le cache.

Relevé le 2026-10-24 pour la Médiathèque (atelier, `notes/HP4.md`, `HP5.md`,
`HP6.md`, section « Musique et cinématiques ») :

- **BIGF** (`movies.big`, `music.big`) : « BIGF », taille totale (petit-
  boutiste), nombre d'entrées et taille de l'en-tête (gros-boutistes), puis
  par entrée : début, taille (gros-boutistes) et nom terminé par un zéro.
- **Flux audio SCHl** : blocs « étiquette sur 4 octets + taille sur 4 octets
  (petit-boutiste) », de `SCHl` à `SCEl`. Une `.mus` de musique en met
  plusieurs bout à bout après 256 octets d'en-tête, parfois séparés par du
  remplissage : chaque flux est un morceau (ou une transition très courte).
  Un flux seul est un fichier `.asf` qu'FFmpeg lit (`adpcm_ea_r3`, HP4).

L'archive n'est jamais écrite : on lit, et on recopie vers le cache. Aucune
fonction ne lève ; une archive illisible donne une liste vide.
"""

from __future__ import annotations

import logging
import os
import struct
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

log = logging.getLogger(__name__)

_EN_TETE_MUS = 256
_PAS_RECHERCHE = 1 << 16
_MAX_ENTREES = 100_000


@dataclass(frozen=True, slots=True)
class Entree:
    nom: str          # chemin dans l'archive, « / » comme séparateur
    debut: int
    taille: int


def _lire_entrees(chemin: Path) -> tuple[Entree, ...]:
    with chemin.open("rb") as f:
        tete = f.read(16)
        if len(tete) < 16 or tete[:4] not in (b"BIGF", b"BIG4"):
            return ()
        nombre, taille_tete = struct.unpack(">II", tete[8:16])
        if nombre > _MAX_ENTREES or taille_tete < 16:
            return ()
        bloc = f.read(taille_tete - 16)
    taille_archive = chemin.stat().st_size
    entrees: list[Entree] = []
    i = 0
    for _ in range(nombre):
        if i + 8 > len(bloc):
            break
        debut, taille = struct.unpack(">II", bloc[i:i + 8])
        fin = bloc.find(b"\0", i + 8)
        if fin < 0:
            break
        nom = bloc[i + 8:fin].decode("latin-1").replace("\\", "/")
        i = fin + 1
        if debut + taille <= taille_archive:
            entrees.append(Entree(nom, debut, taille))
    return tuple(entrees)


@lru_cache(maxsize=16)
def _entrees_en_cache(chemin: Path, _taille: int, _modifie: float) -> tuple[Entree, ...]:
    return _lire_entrees(chemin)


def lister(chemin: Path) -> tuple[Entree, ...]:
    """Les entrées d'une archive BIGF ; relu seulement si le fichier change."""
    try:
        st = chemin.stat()
        return _entrees_en_cache(chemin, st.st_size, st.st_mtime)
    except (OSError, ValueError, struct.error) as exc:
        log.debug("Archive EA illisible (%s) : %s", chemin, exc)
        return ()


def trouver(chemin: Path, nom: str) -> Entree | None:
    """L'entrée de ce nom, casse ignorée."""
    cherche = nom.lower()
    return next((e for e in lister(chemin) if e.nom.lower() == cherche), None)


def _flux(f: BinaryIO, debut: int, fin: int) -> list[tuple[int, int]]:
    flux: list[tuple[int, int]] = []
    pos, ouvert = debut, None
    while pos + 8 <= fin:
        f.seek(pos)
        tete = f.read(8)
        if len(tete) < 8:
            break
        etiquette, taille = tete[:4], struct.unpack("<I", tete[4:])[0]
        if etiquette == b"SCHl":
            ouvert = pos
        # Un bloc ne se suit que s'il ouvre un flux ou continue un flux ouvert.
        valide = (8 <= taille and pos + taille <= fin
                  and (etiquette == b"SCHl" or (ouvert is not None and etiquette.startswith(b"SC"))))
        if not valide:
            # Remplissage entre deux flux : on saute au prochain « SCHl ».
            f.seek(pos + 1)
            morceau = f.read(min(_PAS_RECHERCHE, fin - pos - 1))
            k = morceau.find(b"SCHl")
            if k < 0:
                if not morceau:
                    break
                pos += len(morceau)
                continue
            pos += 1 + k
            ouvert = None
            continue
        pos += taille
        if etiquette == b"SCEl" and ouvert is not None:
            flux.append((ouvert, pos - ouvert))
            ouvert = None
    return flux


def flux_schl(chemin: Path, entree: Entree) -> list[tuple[int, int]]:
    """(début absolu, taille) de chaque flux SCHl…SCEl d'une entrée `.mus`."""
    try:
        with chemin.open("rb") as f:
            return _flux(f, entree.debut + _EN_TETE_MUS, entree.debut + entree.taille)
    except (OSError, struct.error) as exc:
        log.debug("Flux de %s illisibles : %s", entree.nom, exc)
        return []


def extraire(chemin: Path, debut: int, taille: int, cible: Path) -> Path | None:
    """Recopie [debut, debut + taille) de l'archive dans `cible` (écriture atomique).

    Une cible déjà là et de la bonne taille sert telle quelle : c'est une
    extraction précédente.
    """
    try:
        if cible.is_file() and cible.stat().st_size == taille:
            return cible
        cible.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=cible.parent, suffix=".accio-tmp")
        try:
            with os.fdopen(fd, "wb") as ecrit, chemin.open("rb") as lu:
                lu.seek(debut)
                reste = taille
                while reste > 0:
                    morceau = lu.read(min(reste, 1 << 20))
                    if not morceau:
                        raise OSError("archive plus courte que prévu")
                    ecrit.write(morceau)
                    reste -= len(morceau)
            os.replace(tmp, cible)
        except OSError:
            try:
                os.remove(tmp)               # notre propre fichier temporaire
            except OSError:
                pass
            raise
    except OSError as exc:
        log.warning("Extraction de %s échouée : %s", cible.name, exc)
        return None
    return cible

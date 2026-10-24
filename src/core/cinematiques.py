"""Les cinématiques : les vidéos livrées avec les jeux, lues dans la copie du joueur.

Demandé par Ludo le 2026-10-24, avec la musique, dans la Médiathèque. Relevé
sur les jeux installés :

- **HP1 et HP2** n'ont AUCUN fichier vidéo : leurs cinématiques sont jouées
  par le moteur (scripts), rien à lister.
- **HP3** livre douze Bink dans `Movies/` : trois logos, deux fonds de menu et
  sept petites animations (256 × 256) que le moteur pose en texture dans ses
  cinématiques. L'option « Passer les logos » les renomme en `.bik.off` : le
  nom renommé compte aussi.
- **HP7 et HP8** livrent leurs vraies cinématiques en VP6 dans `pc/`, en
  1280 × 720 et SANS piste son (le son est rangé ailleurs, pas encore retrouvé).
- **HP4 à HP6** : dans les archives du jeu, pas encore ici.

Titres et seuils : `src/data/cinematiques.json`, embarqué. Le seuil suit la
règle des morceaux (`discographie.debloque`). Aucune fonction ne lève.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Cinematique:
    fichier: str      # nom du fichier sans extension, comme dans le jeu
    titre: str
    seuil: int


@dataclass(frozen=True, slots=True)
class Collection:
    dossier: str      # sous-dossier du jeu, casse ignorée
    extension: str    # « .bik », « .vp6 »
    sans_son: bool
    clips: tuple[Cinematique, ...]


def charger(chemin: Path | None = None) -> dict[str, Collection]:
    """Les cinématiques de chaque jeu, dans l'ordre du fichier ; vide si illisible."""
    if chemin is None:
        from src.core.config import CINEMATIQUES_PATH
        chemin = CINEMATIQUES_PATH
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Cinématiques illisibles (%s) : %s", chemin, exc)
        return {}
    jeux = data.get("jeux") if isinstance(data, dict) else None
    if not isinstance(jeux, dict):
        return {}
    resultat: dict[str, Collection] = {}
    for jeu, bloc in jeux.items():
        if not (isinstance(bloc, dict) and isinstance(bloc.get("dossier"), str)
                and isinstance(bloc.get("ext"), str) and isinstance(bloc.get("clips"), list)):
            continue
        clips = tuple(
            Cinematique(c["f"], c["t"], max(0, min(100, c["s"])))
            for c in bloc["clips"]
            if isinstance(c, dict) and isinstance(c.get("f"), str) and isinstance(c.get("t"), str)
            and isinstance(c.get("s"), int))
        resultat[str(jeu)] = Collection(bloc["dossier"], bloc["ext"].lower(),
                                        bloc.get("sans_son") is True, clips)
    return resultat


def _dossier(dossier_jeu: Path, nom: str) -> Path | None:
    try:
        for enfant in dossier_jeu.iterdir():
            if enfant.is_dir() and enfant.name.lower() == nom.lower():
                return enfant
    except OSError:
        return None
    return None


def presentes(collection: Collection, dossier_jeu: Path | None) -> dict[str, Path]:
    """Le chemin de chaque cinématique trouvée dans le jeu installé, par nom de fichier."""
    if dossier_jeu is None:
        return {}
    dossier = _dossier(dossier_jeu, collection.dossier)
    if dossier is None:
        return {}
    try:
        par_nom = {p.name.lower(): p for p in dossier.iterdir() if p.is_file()}
    except OSError:
        return {}
    trouvees: dict[str, Path] = {}
    for clip in collection.clips:
        nom = (clip.fichier + collection.extension).lower()
        chemin = par_nom.get(nom) or par_nom.get(nom + ".off")
        if chemin is not None:
            trouvees[clip.fichier] = chemin
    return trouvees

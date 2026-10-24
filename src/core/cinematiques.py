"""Les cinématiques : les vidéos livrées avec les jeux, lues dans la copie du joueur.

Demandé par Ludo le 2026-10-24, avec la musique, dans la Médiathèque. Relevé
sur les jeux installés (atelier, fiches `HPx.md`, « Musique et cinématiques ») :

- **HP1 et HP2** n'ont AUCUN fichier vidéo : leurs cinématiques sont jouées
  par le moteur (scripts), rien à lister.
- **HP3** livre douze Bink dans `Movies/` : trois logos, deux fonds de menu et
  sept petites animations (256 × 256). L'option « Passer les logos » les
  renomme en `.bik.off` : le nom renommé compte aussi.
- **HP4** les range dans `movies.big` (`archives_ea`) : la vidéo VP6 sans son
  dans `Movies/English`, et la VOIX à part, une `.asf` par langue
  (`Movies/French/…`). Les deux se jouent ensemble.
- **HP5 et HP6** : VP6 dans `movies.big`, sans piste son lisible.
- **HP7 et HP8** (`hp7a`, `hp7b`) : VP6 1280 × 720 dans `pc/`, sans piste son
  (le son est dans des paquets Wwise).

Une vidéo d'archive est recopiée une fois dans le cache avant d'être jouée
(`lisible`). Titres et seuils : `src/data/cinematiques.json`, embarqué. Le
seuil suit la règle des morceaux (`discographie.ouvert_au_seuil`). Aucune
fonction ne lève.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.core import archives_ea

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Cinematique:
    fichier: str      # nom du fichier sans extension, comme dans le jeu
    titre: str
    seuil: int


@dataclass(frozen=True, slots=True)
class Collection:
    dossier: str      # sous-dossier du jeu (ou chemin dans l'archive), casse ignorée
    extension: str    # « .bik », « .vp6 »
    sans_son: bool
    clips: tuple[Cinematique, ...]
    archive: str = ""                                 # « movies.big » : vidéos dans l'archive
    voix: dict[str, str] = field(default_factory=dict)  # langue → dossier des .asf (HP4)


@dataclass(frozen=True, slots=True)
class Source:
    """Où est une vidéo (ou une voix) : un fichier, ou une entrée d'archive."""
    chemin: Path
    entree: archives_ea.Entree | None = None


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
        voix = bloc.get("voix")
        resultat[str(jeu)] = Collection(
            bloc["dossier"], bloc["ext"].lower(), bloc.get("sans_son") is True, clips,
            bloc["archive"] if isinstance(bloc.get("archive"), str) else "",
            {str(k): v for k, v in voix.items() if isinstance(v, str)} if isinstance(voix, dict) else {})
    return resultat


def _dossier(dossier_jeu: Path, nom: str) -> Path | None:
    try:
        for enfant in dossier_jeu.iterdir():
            if enfant.is_dir() and enfant.name.lower() == nom.lower():
                return enfant
    except OSError:
        return None
    return None


def _index_archive(collection: Collection, dossier_jeu: Path) -> tuple[Path, dict[str, archives_ea.Entree]]:
    archive = dossier_jeu / collection.archive
    return archive, {e.nom.lower(): e for e in archives_ea.lister(archive)}


def _dans(dossier: str, nom: str) -> str:
    return f"{dossier}/{nom}".lower() if dossier else nom.lower()


def presentes(collection: Collection, dossier_jeu: Path | None,
              langue: str = "fr") -> dict[str, Source]:
    """La vidéo de chaque cinématique trouvée dans le jeu installé, par nom de fichier.

    HP4 : la version de la langue d'abord (ses logos y sont), sinon l'anglaise.
    """
    if dossier_jeu is None:
        return {}
    trouvees: dict[str, Source] = {}
    if collection.archive:
        archive, index = _index_archive(collection, dossier_jeu)
        dossiers = [collection.voix.get(langue, ""), collection.dossier, *collection.voix.values()]
        for clip in collection.clips:
            nom = clip.fichier + collection.extension
            entree = next((index[_dans(d, nom)] for d in dossiers
                           if d is not None and _dans(d, nom) in index), None)
            if entree is not None:
                trouvees[clip.fichier] = Source(archive, entree)
        return trouvees
    dossier = _dossier(dossier_jeu, collection.dossier)
    if dossier is None:
        return {}
    try:
        par_nom = {p.name.lower(): p for p in dossier.iterdir() if p.is_file()}
    except OSError:
        return {}
    for clip in collection.clips:
        nom = (clip.fichier + collection.extension).lower()
        chemin = par_nom.get(nom) or par_nom.get(nom + ".off")
        if chemin is not None:
            trouvees[clip.fichier] = Source(chemin)
    return trouvees


def voix(collection: Collection, dossier_jeu: Path | None, fichier: str,
         langue: str = "fr") -> Source | None:
    """La piste de voix séparée d'une cinématique (HP4), dans la langue voulue sinon en anglais."""
    if dossier_jeu is None or not collection.archive or not collection.voix:
        return None
    archive, index = _index_archive(collection, dossier_jeu)
    for dossier in (collection.voix.get(langue), collection.voix.get("en")):
        if dossier is not None:
            entree = index.get(_dans(dossier, fichier + ".asf"))
            if entree is not None:
                return Source(archive, entree)
    return None


def lisible(source: Source, cache: Path, jeu: str) -> Path | None:
    """Le fichier que le lecteur ouvrira : tel quel, ou recopié une fois dans le cache."""
    if source.entree is None:
        return source.chemin if source.chemin.is_file() else None
    langue = Path(source.entree.nom).parent.name
    cible = cache / "cinematiques" / jeu / langue / Path(source.entree.nom).name
    return archives_ea.extraire(source.chemin, source.entree.debut, source.entree.taille, cible)

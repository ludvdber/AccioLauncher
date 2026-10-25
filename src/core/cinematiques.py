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
- **HP5 et HP6** : VP6 dans `movies.big`, image seule (blocs MV0K/MV0F, aucun
  bloc son). HP5 range la narration de ses douze transitions de chapitre
  dans `movies.big` : `events/chapter_transition/<langue>_s.sdt`, douze flux
  SCHl (EALayer3) bout à bout, dans l'ordre ALPHABÉTIQUE des noms que liste
  `data.big › events/chapter_transition.str` (DL03, GP01… UH13). Vérifié par
  les durées : chaque fiche du `.str` porte celle de son son en millisecondes
  (85 179, 40 190…), égales à celles que mesure vgmstream. C'est la
  `Banque` ; converti en WAV par `vgmstream`.
- **HP7 et HP8** (`hp7a`, `hp7b`) : VP6 1280 × 720 dans `pc/`, sans piste son
  (le son est dans des paquets Wwise).

Une vidéo d'archive est recopiée une fois dans le cache avant d'être jouée
(`lisible`). Titres et seuils : `src/data/cinematiques.json`, embarqué. Le
seuil suit la règle des morceaux (`discographie.ouvert_au_seuil`). Aucune
fonction ne lève.
"""

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
class Banque:
    """Les voix rangées dans une banque `_s.sdt` : un flux par cinématique (HP5)."""
    archive: str
    fichiers: dict[str, str]     # langue → chemin de la banque dans l'archive
    ordre: tuple[str, ...]       # les cinématiques, dans l'ordre des flux


@dataclass(frozen=True, slots=True)
class Collection:
    dossier: str      # sous-dossier du jeu (ou chemin dans l'archive), casse ignorée
    extension: str    # « .bik », « .vp6 »
    sans_son: bool
    clips: tuple[Cinematique, ...]
    archive: str = ""                                 # « movies.big » : vidéos dans l'archive
    voix: dict[str, str] = field(default_factory=dict)  # langue → dossier des .asf (HP4)
    banque: Banque | None = None


@dataclass(frozen=True, slots=True)
class Source:
    """Où est une vidéo (ou une voix) : un fichier, ou une entrée d'archive."""
    chemin: Path
    entree: archives_ea.Entree | None = None
    convertir: bool = False      # EALayer3 : passe par vgmstream avant d'être lu


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
            {str(k): v for k, v in voix.items() if isinstance(v, str)} if isinstance(voix, dict) else {},
            _banque(bloc.get("banque")))
    return resultat


def _banque(bloc: object) -> Banque | None:
    if not isinstance(bloc, dict):
        return None
    archive, fichiers, ordre = bloc.get("archive"), bloc.get("fichiers"), bloc.get("ordre")
    if not (isinstance(archive, str) and isinstance(fichiers, dict) and isinstance(ordre, list)):
        return None
    return Banque(archive, {str(k): v for k, v in fichiers.items() if isinstance(v, str)},
                  tuple(o for o in ordre if isinstance(o, str)))


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
    """La piste de voix séparée d'une cinématique : une `.asf` par langue (HP4),
    sinon son flux dans la `Banque` (HP5). La langue voulue, sinon l'anglais."""
    if dossier_jeu is None:
        return None
    if collection.banque is not None:
        return _voix_banque(collection.banque, dossier_jeu, fichier, langue)
    if not collection.archive or not collection.voix:
        return None
    archive, index = _index_archive(collection, dossier_jeu)
    for dossier in (collection.voix.get(langue), collection.voix.get("en")):
        if dossier is not None:
            entree = index.get(_dans(dossier, fichier + ".asf"))
            if entree is not None:
                return Source(archive, entree)
    return None


def _voix_banque(banque: Banque, dossier_jeu: Path, fichier: str, langue: str) -> Source | None:
    """Le flux de `fichier` dans la banque de la langue (sinon anglaise, sinon la
    première présente). Rien si la banque n'a pas un flux par cinématique : un
    décalage donnerait à une vidéo la voix d'une autre."""
    cle = fichier.lower()
    ordre = [o.lower() for o in banque.ordre]
    if cle not in ordre:
        return None
    archive = dossier_jeu / banque.archive
    noms = [banque.fichiers[k] for k in (langue, "en") if k in banque.fichiers]
    noms += [n for n in banque.fichiers.values() if n not in noms]
    for nom in noms:
        entree = archives_ea.trouver(archive, nom)
        if entree is None:
            continue
        flux = archives_ea.flux_schl(archive, entree, en_tete=0)
        if len(flux) != len(ordre):
            log.warning("Banque %s : %d flux pour %d cinématiques", nom, len(flux), len(ordre))
            return None
        debut, taille = flux[ordre.index(cle)]
        sous = archives_ea.Entree(f"{Path(nom).parent}/{Path(nom).stem}_{cle}.asf", debut, taille)
        return Source(archive, sous, convertir=True)
    return None


def lisible(source: Source, cache: Path, jeu: str) -> Path | None:
    """Le fichier que le lecteur ouvrira : tel quel, ou recopié une fois dans le
    cache (et converti en WAV par vgmstream pour une voix de banque)."""
    if source.entree is None:
        return source.chemin if source.chemin.is_file() else None
    langue = Path(source.entree.nom).parent.name
    cible = cache / "cinematiques" / jeu / langue / Path(source.entree.nom).name
    extrait = archives_ea.extraire(source.chemin, source.entree.debut, source.entree.taille, cible)
    if extrait is None or not source.convertir:
        return extrait
    from src.core import vgmstream
    return vgmstream.convertir(extrait, extrait.with_suffix(".wav"))


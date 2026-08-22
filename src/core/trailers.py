"""Bandes-annonces : où elles vivent sur le disque, ce qui manque, ce qui a vieilli.

Elles ne sont plus embarquées dans l'exécutable. Deux d'entre elles suffisaient
à le faire passer de 74 à 160 Mo, et les huit l'auraient mené au-delà de 500 —
pour un ornement que tout le monde télécharge et que personne n'est obligé de
vouloir. Elles sont donc publiées en assets de release, déclarées par le
catalogue, et téléchargées sur demande.

Tout ici est PUR : aucun widget, aucun réseau. Le téléchargement lui-même vit
dans `src/ui/trailer_store.py`.
"""

import logging
import re
from pathlib import Path

from src.core.config import ASSETS_DIR, DEFAULT_INSTALL_PATH
from src.core.game_data import Trailer

log = logging.getLogger(__name__)

# Les bandes-annonces sont des données du LAUNCHER, pas d'un jeu : elles vivent
# à côté de `config.json`, `catalog_cache.json` et `i18n/`, à un chemin FIXE.
# Les mettre sous `config.install_path` les rendrait orphelines le jour où
# quelqu'un déplace ses jeux — 400 Mo abandonnés en silence, sans que rien à
# l'écran ne relie les deux.
TRAILERS_DIR = DEFAULT_INSTALL_PATH / "trailers"

# Ce que ce dossier a le droit de contenir. Sert de garde-fou au ménage : on ne
# supprime QUE ce qui répond à ce motif, jamais un fichier qu'on n'a pas écrit.
_MOTIF = re.compile(r"^(?P<id>[A-Za-z0-9][A-Za-z0-9._-]*)_video_v"
                    r"(?P<version>[A-Za-z0-9][A-Za-z0-9._-]*)\.mp4$")


def dossier() -> Path:
    """Dossier des bandes-annonces (pas créé ici — l'écriture s'en charge)."""
    return TRAILERS_DIR


def chemin_local(trailer: Trailer) -> Path:
    """Où CETTE version de CETTE bande-annonce doit se trouver."""
    return TRAILERS_DIR / trailer.filename


def present(trailer: Trailer) -> bool:
    """True si le fichier est là ET non vide.

    Un fichier de zéro octet est le résidu d'un téléchargement interrompu au
    pire moment : le compter comme présent afficherait une vidéo qui ne se
    lance jamais, sans que rien n'explique pourquoi.
    """
    chemin = chemin_local(trailer)
    try:
        return chemin.is_file() and chemin.stat().st_size > 0
    except OSError:
        return False


def manquantes(trailers) -> list[Trailer]:
    """Celles qu'il faut encore télécharger, dans l'ordre du catalogue."""
    return [t for t in trailers if not present(t)]


def poids_a_telecharger(trailers) -> int:
    """Mo à télécharger pour compléter la collection (0 si tout est là)."""
    return sum(t.size_mb for t in manquantes(trailers))


def chemin_a_jouer(game_id: str, trailers) -> Path | None:
    """Vidéo à jouer pour ce jeu, ou None s'il n'y en a pas sur le disque.

    Deux emplacements, dans cet ordre :

    1. la bande-annonce téléchargée, à la version que le catalogue attend ;
    2. `assets/videos/<id>_video.mp4`, l'ancien emplacement EMBARQUÉ.

    Le second n'est plus livré dans l'exécutable, mais il reste consulté : en
    développement les fichiers sont encore là, et quelqu'un peut vouloir
    déposer sa propre vidéo sans passer par le catalogue. Absence des deux =
    fond fixe, ce que la fiche sait déjà faire.
    """
    for t in trailers:
        if t.game_id == game_id:
            chemin = chemin_local(t)
            if present(t):
                return chemin
            break
    legacy = ASSETS_DIR / "videos" / f"{game_id}_video.mp4"
    try:
        if legacy.is_file() and legacy.stat().st_size > 0:
            return legacy
    except OSError:
        pass
    return None


def _fichiers() -> list[Path]:
    """Fichiers du dossier qui répondent à notre convention de nom."""
    try:
        return [f for f in TRAILERS_DIR.iterdir()
                if f.is_file() and _MOTIF.match(f.name)]
    except OSError:
        return []


def poids_disque() -> int:
    """Octets réellement occupés par les bandes-annonces."""
    total = 0
    for f in _fichiers():
        try:
            total += f.stat().st_size
        except OSError:
            continue
    return total


def nombre_present(trailers) -> int:
    """Combien de bandes-annonces du catalogue sont sur le disque."""
    return sum(1 for t in trailers if present(t))


def fichiers_perimes(trailers) -> list[Path]:
    """Fichiers à supprimer : anciennes versions et jeux disparus du catalogue.

    C'est le pendant obligatoire du nom de fichier versionné. Sans ce ménage,
    améliorer une bande-annonce laisserait l'ancienne sur le disque pour
    toujours : le poids doublerait à chaque révision, sans que personne ne
    puisse dire pourquoi.
    """
    attendus = {t.filename for t in trailers}
    return [f for f in _fichiers() if f.name not in attendus]


def supprimer(chemins) -> tuple[int, int]:
    """Supprime les fichiers donnés. Retourne (supprimés, octets libérés)."""
    n, octets = 0, 0
    for f in chemins:
        try:
            taille = f.stat().st_size
            f.unlink()
        except OSError as exc:
            log.warning("Bande-annonce non supprimée (%s) : %s", f.name, exc)
            continue
        n += 1
        octets += taille
    return n, octets


def supprimer_tout() -> tuple[int, int]:
    """Vide le dossier des bandes-annonces. Retourne (supprimés, octets libérés).

    Ne touche QUE les fichiers répondant au motif : si quelqu'un a déposé autre
    chose là, ce n'est pas à nous de le jeter.
    """
    resultat = supprimer(_fichiers())
    try:
        # Le dossier ne part que s'il est réellement vide — voir ci-dessus.
        TRAILERS_DIR.rmdir()
    except OSError:
        pass
    return resultat

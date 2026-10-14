"""Les nouveautés du launcher, montrées une fois, juste après sa mise à jour.

Maquette « Nouveautés du launcher » validée par Ludo le 2026-10-14. Une mise à
jour installée en un clic ne disait rien de ce qu'elle apportait : le joueur
voyait une barre de plus, une page refaite, et devait deviner. La page le dit
au premier lancement de la nouvelle version, puis revient à la demande depuis
le numéro de version d'À propos.

Le contenu vit dans `src/data/nouveautes.json`, EMBARQUÉ : il parle de cette
version-ci, il part avec elle, et il se lit sans réseau. Chaque texte porte
ses traductions à côté de lui (`{"fr": …, "en": …, "es": …}`), comme le
catalogue (règle 55) et pas dans les fichiers de langue : c'est du contenu, pas
de l'interface. Repli sur le français, comme le catalogue.

Un fichier absent, illisible ou sans entrée pour la version courante rend
None : la page ne s'ouvre pas, rien d'autre ne change.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from src.core.config import APP_VERSION, NOUVEAUTES_PATH
from src.core.i18n import SOURCE_LANGUAGE, get_language
from src.core.version_utils import compare_versions

log = logging.getLogger(__name__)

# L'ordre de la liste à l'écran.
GENRES = ("nouveau", "ameliore", "corrige")


@dataclass(frozen=True)
class PointFort:
    icone: str
    titre: str
    texte: str


@dataclass(frozen=True)
class Changement:
    genre: str
    texte: str


@dataclass(frozen=True)
class Nouveautes:
    version: str
    depuis: str
    points_forts: tuple[PointFort, ...]
    changements: tuple[Changement, ...]
    # Le nom de la version (« Revelio · Folio Magi ») : un numéro seul ne dit
    # rien à personne. Vide : la page ne montre que le numéro.
    nom: str = ""


def mise_a_jour_installee(precedente: str) -> bool:
    """La version lancée la dernière fois est-elle plus ancienne que celle-ci ?

    Vide : la config a été écrite par une version d'avant la 1.1.6, qui ne
    notait pas encore sa version. C'est donc aussi une mise à jour. Un premier
    lancement, lui, part de `Config()`, qui porte déjà la version courante.
    """
    return not precedente or compare_versions(APP_VERSION, precedente) > 0


def _liste(valeur) -> list:
    return valeur if isinstance(valeur, list) else []


def _texte(valeur, langue: str) -> str:
    """Le texte dans `langue`, sinon en français ; "" si rien d'utilisable."""
    if isinstance(valeur, str):
        return valeur.strip()
    if not isinstance(valeur, dict):
        return ""
    for code in (langue, SOURCE_LANGUAGE):
        texte = valeur.get(code)
        if isinstance(texte, str) and texte.strip():
            return texte.strip()
    return ""


def charger(version: str = APP_VERSION, langue: str | None = None,
            chemin: Path = NOUVEAUTES_PATH) -> Nouveautes | None:
    """Les nouveautés de `version` dans `langue` ; None s'il n'y en a pas."""
    langue = langue or get_language()
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Nouveautés illisibles (%s) : %s", chemin, exc)
        return None
    entrees = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(entrees, list):
        return None
    entree = next((e for e in entrees if isinstance(e, dict)
                   and e.get("version") == version), None)
    if entree is None:
        return None
    points = tuple(
        PointFort(str(p.get("icone", "")), _texte(p.get("titre"), langue),
                  _texte(p.get("texte"), langue))
        for p in _liste(entree.get("points_forts")) if isinstance(p, dict))
    changements = tuple(
        Changement(c.get("genre"), _texte(c.get("texte"), langue))
        for c in _liste(entree.get("changements"))
        if isinstance(c, dict) and c.get("genre") in GENRES)
    # Un texte vide ne s'affiche pas : une carte sans titre, une ligne sans phrase.
    points = tuple(p for p in points if p.titre and p.texte)
    changements = tuple(sorted((c for c in changements if c.texte),
                               key=lambda c: GENRES.index(c.genre)))
    if not points and not changements:
        return None
    return Nouveautes(version, str(entree.get("depuis", "")), points, changements,
                      _texte(entree.get("nom"), langue))


def a_montrer(precedente: str) -> bool:
    """Au premier lancement d'une version plus récente qui a ses nouveautés."""
    return (precedente != APP_VERSION and mise_a_jour_installee(precedente)
            and charger() is not None)

"""L'atelier : ce que les artistes peuvent refaire, métier par métier.

Maquette « L'atelier, tous les métiers » validée par Ludo le 2026-10-14. L'appel
aux artistes d'À propos ne parlait que des jaquettes et des fonds ; il y a aussi
des textures, des écrans de chargement, des vignettes de sauvegarde et des
vidéos à refaire. Chaque métier dit où se voit son travail, son format et la
liste de ce qui attend.

Le contenu vit dans `src/data/atelier.json`, EMBARQUÉ, chaque texte avec ses
traductions (`{"fr": …, "en": …, "es": …}`, repli sur le français), comme les
nouveautés. Un besoin pris par quelqu'un passe « en cours » dans le fichier, et
le joueur le voit à la mise à jour suivante du launcher.

Le métier « jaquettes » est le seul qui se remplit tout seul : ses besoins
viennent de la taille des images (`images_a_refaire.py`), donc il se vide à
mesure qu'elles arrivent, sans toucher au fichier.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from src.core.config import ATELIER_PATH
from src.core.i18n import SOURCE_LANGUAGE, get_language
from src.core.images_a_refaire import jaquette_a_refaire, fond_a_refaire

log = logging.getLogger(__name__)

CHERCHE = "cherche"
COURS = "cours"
FAIT = "fait"
ETATS = (CHERCHE, COURS, FAIT)

JAQUETTE = "jaquette"
FOND = "fond"


@dataclass(frozen=True)
class Besoin:
    jeu: str          # « HP3 », « HP7 · 1 »
    quoi: str
    detail: str
    etat: str
    genre: str = ""   # JAQUETTE ou FOND pour les besoins mesurés, sinon vide


@dataclass(frozen=True)
class Metier:
    id: str
    nom: str
    ou: str
    texte: str
    formats: tuple[str, ...]
    besoins: tuple[Besoin, ...]

    @property
    def ouverts(self) -> int:
        """Ce qui attend encore quelqu'un (ni pris, ni fait)."""
        return sum(1 for b in self.besoins if b.etat == CHERCHE)


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


def _liste(valeur) -> list:
    return valeur if isinstance(valeur, list) else []


def court(id_jeu: str) -> str:
    """« hp3 » → « HP3 » ; les deux parties des Reliques : « HP7 · 1 », « HP7 · 2 »."""
    trouve = re.fullmatch(r"hp(\d+)([ab]?)", id_jeu)
    if trouve is None:
        return id_jeu.upper()
    partie = {"a": " · 1", "b": " · 2"}.get(trouve.group(2), "")
    return f"HP{trouve.group(1)}{partie}"


def besoins_mesures(tailles: dict[str, tuple[tuple[int, int], tuple[int, int]]],
                    libelles: dict[str, str]) -> list[Besoin]:
    """Les jaquettes et fonds à refaire, d'après leur taille, dans l'ordre du catalogue.

    `tailles` : id → ((l, h) de la jaquette, (l, h) du fond).
    `libelles` : les mots traduits, fournis par l'interface (« Jaquette »,
    « Fond d'écran », « Carrée aujourd'hui », « {} × {} aujourd'hui »).
    """
    besoins: list[Besoin] = []
    for jeu, (jaquette, fond) in tailles.items():
        if jaquette_a_refaire(*jaquette):
            carree = jaquette[0] > 0 and jaquette[0] == jaquette[1]
            detail = (libelles["carree"] if carree
                      else libelles["taille"].format(*jaquette) if jaquette[0] > 0 else "")
            besoins.append(Besoin(court(jeu), libelles[JAQUETTE], detail, CHERCHE, JAQUETTE))
        if fond_a_refaire(*fond):
            detail = libelles["taille"].format(*fond) if fond[0] > 0 else ""
            besoins.append(Besoin(court(jeu), libelles[FOND], detail, CHERCHE, FOND))
    return besoins


def charger(mesures: list[Besoin] | None = None, langue: str | None = None,
            chemin: Path = ATELIER_PATH) -> list[Metier]:
    """Les métiers dans `langue`. `mesures` remplit le métier « auto ».

    Un fichier illisible rend une liste vide ; un métier sans nom ou sans
    besoin est écarté (un métier vide n'a rien à proposer).
    """
    langue = langue or get_language()
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Atelier illisible (%s) : %s", chemin, exc)
        return []
    metiers: list[Metier] = []
    for brut in _liste(data.get("metiers") if isinstance(data, dict) else None):
        if not isinstance(brut, dict):
            continue
        if brut.get("auto"):
            besoins = tuple(mesures or ())
        else:
            besoins = tuple(
                Besoin(str(b.get("jeu", "")), _texte(b.get("quoi"), langue),
                       _texte(b.get("detail"), langue), b.get("etat", CHERCHE))
                for b in _liste(brut.get("besoins"))
                if isinstance(b, dict) and b.get("etat", CHERCHE) in ETATS
                and _texte(b.get("quoi"), langue))
        nom = _texte(brut.get("nom"), langue)
        if not nom or not besoins:
            continue
        metiers.append(Metier(
            str(brut.get("id", "")), nom, _texte(brut.get("ou"), langue),
            _texte(brut.get("texte"), langue),
            tuple(t for t in (_texte(f, langue) for f in _liste(brut.get("formats"))) if t),
            besoins))
    return metiers


def pour_le_jeu(mesures: list[Besoin], id_jeu: str) -> Besoin | None:
    """Le besoin mesuré du jeu affiché, pour la pastille de la fiche : le fond
    d'abord, puisque c'est lui qui se voit en grand derrière la fiche."""
    siens = [b for b in mesures if b.jeu == court(id_jeu)]
    return next((b for b in siens if b.genre == FOND), siens[0] if siens else None)

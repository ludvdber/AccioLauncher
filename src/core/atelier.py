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

Le métier « jaquettes » est le seul qui se remplit tout seul : il liste TOUTES
les jaquettes et tous les fonds du catalogue (Ludo, 2026-10-14 : le but est
aussi de ne plus dépendre des images de Warner, donc même une image nette peut
être refaite). Celles que `images_a_refaire.py` juge trop petites sont
« prioritaires » (marquées « en priorité » dans l'atelier).
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.config import ATELIER_PATH
from src.core.i18n import get_language, texte_dans
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
    prioritaire: bool = False   # trop petite ou mal cadrée aujourd'hui


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


def _liste(valeur: object) -> list[Any]:
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
    """Toutes les jaquettes et tous les fonds, dans l'ordre du catalogue, avec
    leur taille d'aujourd'hui ; les trop petites sont marquées prioritaires.

    `tailles` : id → ((l, h) de la jaquette, (l, h) du fond).
    `libelles` : les mots traduits, fournis par l'interface (« Jaquette »,
    « Fond d'écran », « Carrée aujourd'hui », « {} × {} aujourd'hui »,
    « en priorité »).
    """
    besoins: list[Besoin] = []
    for jeu, (jaquette, fond) in tailles.items():
        carree = jaquette[0] > 0 and jaquette[0] == jaquette[1]
        for genre, taille, urgente, detail in (
                (JAQUETTE, jaquette, jaquette_a_refaire(*jaquette),
                 libelles["carree"] if carree else ""),
                (FOND, fond, fond_a_refaire(*fond), "")):
            if not detail and taille[0] > 0:
                detail = libelles["taille"].format(*taille)
            if urgente:
                detail = " · ".join(t for t in (detail, libelles["priorite"]) if t)
            besoins.append(Besoin(court(jeu), libelles[genre], detail, CHERCHE, genre, urgente))
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
                Besoin(str(b.get("jeu", "")), texte_dans(b.get("quoi"), langue),
                       texte_dans(b.get("detail"), langue), b.get("etat", CHERCHE))
                for b in _liste(brut.get("besoins"))
                if isinstance(b, dict) and b.get("etat", CHERCHE) in ETATS
                and texte_dans(b.get("quoi"), langue))
        nom = texte_dans(brut.get("nom"), langue)
        if not nom or not besoins:
            continue
        metiers.append(Metier(
            str(brut.get("id", "")), nom, texte_dans(brut.get("ou"), langue),
            texte_dans(brut.get("texte"), langue),
            tuple(t for t in (texte_dans(f, langue) for f in _liste(brut.get("formats"))) if t),
            besoins))
    return metiers

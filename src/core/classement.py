"""Le classement Accio (1.5) : les courses validées, publiées à côté du catalogue.

Ludo tranche (2026-11-22) : un joueur poste sa course sur le Discord (sa vidéo et son `course.json`) ; une
fois validée, Ludo l'ajoute à `classement.json` du dépôt des jeux, à côté de `games.json`, et le publie. Le
launcher le relit à chaque vérification des mises à jour (`updater.UpdateChecker._check_classement`), le
garde en cache dans `_Launcher/classement.json`, et le Carnet le montre, hors ligne compris
(`courses_page.py`). L'adresse est une constante de `liens` : jamais relue du catalogue (audit du
2026-10-29).

Le fichier, écrit à la main :

    {"format": 1, "jeux": {"hp2": {"Any%": [
        {"joueur": "Ludo", "temps": "31:04.512", "date": "2026-12-01", "code": "7KQ2-M4XP",
         "video": "https://youtu.be/..."}]}}}

`temps` s'écrit comme le Carnet l'affiche (`course.format_temps`). Tout est contrôlé : une entrée mal formée
est sautée (les autres restent), un fichier illisible est ignoré (le cache d'avant reste). Le texte vient du
réseau : un nom porte au plus 40 signes, sans caractère de contrôle ni de mise en forme invisible, et une
vidéo n'est gardée que sur un hôte connu, en https (un lien piégé ne s'ouvre pas d'un clic).
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.core import course, course_regles
from src.core.ecriture_atomique import ecrire_octets_atomique

log = logging.getLogger(__name__)

FORMAT = 1
OCTETS_MAX = 1_000_000                 # cent jeux de cent courses tiennent dix fois dedans
JOUEUR_MAX = 40
PAR_CATEGORIE_MAX = 100
_VIDEO_MAX = 300
_HOTES_VIDEO = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "twitch.tv",
                          "www.twitch.tv", "speedrun.com", "www.speedrun.com"})
_JEU = re.compile(r"[a-z0-9_]{1,16}")
_TEMPS = re.compile(r"(?:(\d{1,3}):)?([0-5]?\d):([0-5]\d)\.(\d{3})")


@dataclass(frozen=True)
class Entree:
    joueur: str
    temps_us: int    # le temps qui classe le jeu (réel pour HP4 à HP6, sans chargements pour HP1 à HP3)
    jour: str
    code: str        # "" s'il manque ou n'est pas un code de course
    video: str       # "" si absente ou refusée


@dataclass(frozen=True)
class Classement:
    jeux: dict[str, dict[str, tuple[Entree, ...]]]

    def de(self, game_id: str, categorie: str) -> tuple[Entree, ...]:
        return self.jeux.get(game_id, {}).get(categorie, ())

    def categories(self, game_id: str, ordre: tuple[str, ...] = ()) -> tuple[str, ...]:
        """Les catégories du jeu qui ont au moins une entrée : celles d'`ordre` (le catalogue) dans son ordre,
        puis les autres dans celui du fichier."""
        du_jeu = self.jeux.get(game_id, {})
        presentes = [c for c in du_jeu if du_jeu[c]]
        return tuple(sorted(presentes, key=lambda c: ordre.index(c) if c in ordre else len(ordre)))


VIDE = Classement({})


def temps_us(texte: str) -> int | None:
    """« 31:04.512 », « 1:02:03.456 » (`course.format_temps`) en microsecondes ; None s'il ne s'y lit pas."""
    m = _TEMPS.fullmatch(texte.strip())
    if m is None:
        return None
    h, mi, s, ms = (int(x) if x else 0 for x in m.groups())
    if not m.group(1) and mi > 59:
        return None
    return ((h * 60 + mi) * 60 + s) * 1_000_000 + ms * 1000


def _joueur(valeur: object) -> str | None:
    if not isinstance(valeur, str):
        return None
    nom = valeur.strip()
    if not nom or len(nom) > JOUEUR_MAX or any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in nom):
        return None
    return nom


def _video(valeur: object) -> str:
    if not isinstance(valeur, str) or not valeur or len(valeur) > _VIDEO_MAX:
        return ""
    try:
        morceaux = urlsplit(valeur)
        hote, port = morceaux.hostname, morceaux.port
    except ValueError:
        return ""
    if morceaux.scheme != "https" or morceaux.username or morceaux.password or hote not in _HOTES_VIDEO \
            or port not in (None, 443) or any(c.isspace() or not c.isprintable() for c in valeur):
        return ""
    return valeur


def _jour(valeur: object) -> str | None:
    """« 2026-12-01 » ; None pour tout le reste."""
    if not isinstance(valeur, str) or len(valeur) != 10:
        return None
    try:
        date.fromisoformat(valeur)
    except ValueError:
        return None
    return valeur


def _entree(brut: object) -> Entree | None:
    if not isinstance(brut, dict):
        return None
    joueur = _joueur(brut.get("joueur"))
    texte_temps = brut.get("temps")
    net = temps_us(texte_temps) if isinstance(texte_temps, str) else None
    jour = _jour(brut.get("date"))
    if joueur is None or not net or jour is None:
        return None
    code = brut.get("code")
    return Entree(joueur, net, jour, code if isinstance(code, str) and course.code_valide(code) else "",
                  _video(brut.get("video")))


def lire(brut: bytes) -> Classement | None:
    """Le classement de ces octets, trié par temps (à égalité, le plus ancien d'abord) ; None si le fichier
    entier ne se lit pas (trop gros, pas du JSON, pas du format connu)."""
    if len(brut) > OCTETS_MAX:
        return None
    try:
        donnees: Any = json.loads(brut.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(donnees, dict) or donnees.get("format") != FORMAT or not isinstance(donnees.get("jeux"), dict):
        return None
    jeux: dict[str, dict[str, tuple[Entree, ...]]] = {}
    for game_id, categories in donnees["jeux"].items():
        if not isinstance(game_id, str) or not _JEU.fullmatch(game_id) or not isinstance(categories, dict):
            continue
        du_jeu: dict[str, tuple[Entree, ...]] = {}
        for categorie, liste in categories.items():
            if not course_regles.categorie_valide(categorie) or not isinstance(liste, list):
                continue
            entrees = [e for e in map(_entree, liste[:PAR_CATEGORIE_MAX]) if e is not None]
            du_jeu[categorie] = tuple(sorted(entrees, key=lambda e: (e.temps_us, e.jour)))
        jeux[game_id] = du_jeu
    return Classement(jeux)


def chemin_cache() -> Path:
    """`_Launcher/classement.json` (suit `CONFIG_FILE_PATH`, que les tests redirigent)."""
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / "classement.json"


def garder(brut: bytes) -> bool:
    """Garde en cache le classement reçu, s'il se lit ; False sinon (le cache d'avant reste)."""
    if lire(brut) is None:
        log.warning("Classement distant illisible, ignoré")
        return False
    try:
        chemin = chemin_cache()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        ecrire_octets_atomique(chemin, brut)
    except OSError:
        log.warning("Classement : cache non écrit", exc_info=True)
        return False
    return True


def en_cache() -> Classement:
    """Le dernier classement reçu ; vide s'il n'y en a pas encore (ou s'il ne se lit plus)."""
    try:
        with chemin_cache().open("rb") as f:
            brut = f.read(OCTETS_MAX + 1)
    except OSError:
        return VIDE
    return lire(brut) or VIDE


def rang(entrees: tuple[Entree, ...], temps: int) -> int:
    """La place qu'un temps prendrait dans le classement (1 : premier) ; à égalité, derrière."""
    return 1 + sum(1 for e in entrees if e.temps_us <= temps)

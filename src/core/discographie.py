"""La discographie : quels morceaux le joueur a débloqués, et lesquels sont nouveaux.

Demandé par Ludo le 2026-10-24 : les musiques s'ouvrent au fil de la partie,
tout le jeu s'ouvre à 75 % (« le 100 % est peut-être compliqué »), et une
petite marque dit ce qui vient de s'ouvrir.

**Les morceaux et leur seuil** viennent de `src/data/discographie.json`,
EMBARQUÉ, généré depuis l'artefact « Discographie » où Ludo valide titres et
seuils (`archives/scripts/discographie.py` de l'atelier pour le brouillon). Le
seuil est un pourcentage d'avancement : la place, dans l'histoire, du lieu où
le morceau joue.

**L'avancement** se lit dans les sauvegardes, par les lecteurs du folio, et
c'est la partie la PLUS avancée qui compte :
- HP2 et HP3 écrivent l'étape de l'histoire (`CurrentGameState`,
  « GSTATE010 ») ; le pourcentage est son rang parmi les étapes du jeu,
  relevées dans `system/*.u` (25 pour HP2, 16 pour HP3) ;
- HP1 n'écrit que le niveau : son rang dans l'ordre de l'histoire.

**Les morceaux vus** (`_Launcher/musiques_vues.json`) : un morceau débloqué
qui n'y est pas encore est NOUVEAU ; la page Musique le note vu quand elle
montre le jeu. Aucune fonction ne lève.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.core.catalogue_blocs import Sauvegardes

log = logging.getLogger(__name__)

TOUT_A = 75
FICHIER_VUS = "musiques_vues.json"

# Relevées dans les paquets des jeux installés le 2026-10-24 (`GSTATE\d{3}`).
ETAPES_HP2 = ("GSTATE000", "GSTATE010", "GSTATE020", "GSTATE030", "GSTATE035", "GSTATE040",
              "GSTATE045", "GSTATE050", "GSTATE060", "GSTATE065", "GSTATE070", "GSTATE080",
              "GSTATE090", "GSTATE095", "GSTATE100", "GSTATE110", "GSTATE115", "GSTATE120",
              "GSTATE130", "GSTATE140", "GSTATE145", "GSTATE150", "GSTATE160", "GSTATE170",
              "GSTATE180")
ETAPES_HP3 = ("GSTATE000", "GSTATE010", "GSTATE020", "GSTATE030", "GSTATE040", "GSTATE050",
              "GSTATE060", "GSTATE065", "GSTATE070", "GSTATE075", "GSTATE080", "GSTATE085",
              "GSTATE090", "GSTATE100", "GSTATE110", "GSTATE120")
# Les niveaux de HP1 dans l'ordre de l'histoire : le début relevé carte par carte
# (`folio._ORDRE_HP1`), la suite d'après la numérotation Lev3 → Lev5 (estimée).
NIVEAUX_HP1 = ("lev_tut1", "lev_tut1b", "lev_tut2", "lev_tut3", "lev_tut3b",
               "lev2_hogfront", "lev2_inc_a", "lev2_inc_b", "lev2_hogfront_2",
               "lev2_remchase", "lev2_hogfront_3", "lev2_fire2", "lev2_fire1",
               "lev2_quid1", "lev3_intro", "lev3_lumos", "lev3_pretroll", "lev3_troll",
               "lev3_quid2", "lev3_predungeon", "lev3_dungeon", "lev3_dungeonb",
               "lev4_sneak", "lev4_sneak2", "snapes_office", "lev5_fluffy", "lev5_snare",
               "lev5_flykeys", "lev5_chess", "lev5_final")


@dataclass(frozen=True, slots=True)
class Morceau:
    fichier: str      # nom du fichier sans extension, comme dans le jeu
    titre: str
    seuil: int        # pourcentage d'avancement qui l'ouvre


def charger(chemin: Path | None = None) -> dict[str, tuple[Morceau, ...]]:
    """Les morceaux de chaque jeu, dans l'ordre du fichier ; vide si illisible."""
    if chemin is None:
        from src.core.config import DISCOGRAPHIE_PATH
        chemin = DISCOGRAPHIE_PATH
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Discographie illisible (%s) : %s", chemin, exc)
        return {}
    jeux = data.get("jeux") if isinstance(data, dict) else None
    if not isinstance(jeux, dict):
        return {}
    resultat: dict[str, tuple[Morceau, ...]] = {}
    for jeu, pistes in jeux.items():
        if not isinstance(pistes, list):
            continue
        resultat[str(jeu)] = tuple(
            Morceau(p["f"], p["t"], max(0, min(100, int(p["s"]))))
            for p in pistes
            if isinstance(p, dict) and isinstance(p.get("f"), str) and isinstance(p.get("t"), str)
            and isinstance(p.get("s"), int))
    return resultat


@dataclass(frozen=True, slots=True)
class Credit:
    """Qui a écrit la musique d'un jeu : affiché sous chaque morceau (Ludo, 2026-10-24)."""
    compositeur: str
    annee: int
    editeur: str


def charger_credits(chemin: Path | None = None) -> dict[str, Credit]:
    """Le crédit de chaque jeu ; vide si illisible (la page n'affiche alors rien)."""
    if chemin is None:
        from src.core.config import DISCOGRAPHIE_PATH
        chemin = DISCOGRAPHIE_PATH
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    credits = data.get("credits") if isinstance(data, dict) else None
    if not isinstance(credits, dict):
        return {}
    return {str(jeu): Credit(c["compositeur"], c["annee"], c["editeur"])
            for jeu, c in credits.items()
            if isinstance(c, dict) and isinstance(c.get("compositeur"), str)
            and isinstance(c.get("annee"), int) and isinstance(c.get("editeur"), str)}


def _rang(valeur: str, ordre: tuple[str, ...]) -> int | None:
    v = valeur.strip().upper() if ordre is not NIVEAUX_HP1 else valeur.strip().lower()
    return ordre.index(v) if v in ordre else None


def pourcentage(jeu: str, valeur: str) -> int | None:
    """Une étape (HP2, HP3) ou un niveau (HP1) en pourcentage de l'histoire."""
    ordre = {"hp1": NIVEAUX_HP1, "hp2": ETAPES_HP2, "hp3": ETAPES_HP3}.get(jeu)
    if ordre is None or not valeur:
        return None
    rang = _rang(valeur, ordre)
    return None if rang is None else round(rang * 100 / (len(ordre) - 1))


def avancement(jeu: str, spec: Sauvegardes | None) -> int | None:
    """Le pourcentage de la partie la plus avancée ; None sans partie lisible."""
    if spec is None:
        return None
    try:
        from src.core import folio, folio_hp2, folio_hp3, sauvegardes
        if jeu == "hp1":
            valeurs = [r.niveau for r in folio.emplacements_hp1(sauvegardes.fichiers(spec))]
        elif jeu == "hp2":
            valeurs = [r.histoire for r in folio_hp2.emplacements(spec)]
        elif jeu == "hp3":
            valeurs = [r.histoire for r in folio_hp3.emplacements(sauvegardes.fichiers(spec))]
        else:
            return None
    except (OSError, ValueError) as exc:
        log.debug("Avancement de %s illisible : %s", jeu, exc)
        return None
    lus = [p for p in (pourcentage(jeu, v) for v in valeurs) if p is not None]
    return max(lus) if lus else None


def ouvert_au_seuil(seuil: int, avance: int | None) -> bool:
    """La règle commune aux morceaux et aux cinématiques : ouvert dès le début
    (seuil 0), dès qu'UNE sauvegarde atteint le seuil, ou tout le jeu, générique
    compris, à 75 % (« tout débloquer d'un jeu après le 75 % », Ludo)."""
    if seuil <= 0:
        return True
    if avance is None:
        return False
    return avance >= TOUT_A or avance >= seuil


def debloque(morceau: Morceau, avance: int | None) -> bool:
    return ouvert_au_seuil(morceau.seuil, avance)


# ─── Morceaux vus ───

def chemin_vus() -> Path:
    """Résolu à l'appel — même garde de test que `sauvegardes.chemin_fichier`."""
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / FICHIER_VUS


def charger_vus(chemin: Path | None = None) -> dict[str, set[str]]:
    chemin = chemin or chemin_vus()
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(j): {f for f in v if isinstance(f, str)} for j, v in data.items() if isinstance(v, list)}


def nouveaux(jeu: str, ouverts: set[str], vus: dict[str, set[str]]) -> set[str]:
    return ouverts - vus.get(jeu, set())


def marquer_vus(jeu: str, fichiers: set[str], chemin: Path | None = None) -> None:
    """Ajoute ces morceaux aux vus (écriture atomique) ; rien si rien ne change."""
    chemin = chemin or chemin_vus()
    vus = charger_vus(chemin)
    avant = vus.get(jeu, set())
    if fichiers <= avant:
        return
    vus[jeu] = avant | fichiers
    tmp: str | None = None
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=".accio-tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as ecrit:
            json.dump({j: sorted(v) for j, v in sorted(vus.items())}, ecrit, ensure_ascii=False, indent=1)
        os.replace(tmp, chemin)
        tmp = None
    except OSError as exc:
        log.warning("Morceaux vus non enregistrés : %s", exc)
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)               # notre propre fichier temporaire
            except OSError:
                pass

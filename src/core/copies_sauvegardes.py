"""Une copie de chaque sauvegarde avant chaque partie, et le retour à une version.

Idée validée par Ludo (2026-10-03), avec sa question : « comment ça se passe
pour savoir quand copier ou effacer une copie ? ». Les deux réponses tiennent
ici.

**Quand copier : au lancement, ce qui a CHANGÉ depuis la dernière copie.**
Chaque version d'une sauvegarde porte un nom tiré de SA PROPRE date
d'écriture (`2026-10-03_143212.gz`) : si ce nom existe déjà, cette version est
déjà à l'abri, on ne copie rien. Une partie ne réécrit en général qu'un
emplacement, donc une partie coûte UNE copie, compressée (×3,2 mesuré sur les
`.usa` de HP1-HP3 : 2,4 Mo → 0,7 Mo ; les fichiers EA de HP4-HP8 font de 4 à
31 Ko). Avant la partie et non après : c'est la version que le plantage de
CETTE partie pourrait abîmer qui doit déjà être copiée.

**Quand effacer : jamais l'original, jamais la seule trace.** Le launcher
n'efface que ses PROPRES copies, et seulement celles qu'une plus récente
remplace, selon un calendrier à la Time Machine :

- les 5 dernières versions de chaque sauvegarde, quelles qu'elles soient ;
- la dernière de chaque jour, sur les 14 derniers jours ;
- la dernière de chaque mois, sur les 12 derniers mois ;
- la dernière de chaque année, pour toujours.

Une sauvegarde qui n'existe plus (effacée dans le jeu, ou par quelqu'un) garde
TOUTES ses copies : elles sont alors la seule chose qui reste d'elle. Seuls
les fichiers au nom exact d'une copie sont effacés ; rien d'autre du dossier.

**Revenir à une version** recopie d'abord l'état actuel (s'il n'est pas déjà
copié) : revenir en arrière n'efface donc jamais rien, on peut revenir au
« présent » de la même façon.

Rangé dans `_Launcher/copies_sauvegardes/<jeu>/<sauvegarde>/` : hors du dossier
du jeu, qu'une désinstallation emporte, et hors de Documents, que le jeu gère.
Aucune fonction ne lève.
"""

from __future__ import annotations

import gzip
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core import config as config_module
from src.core import sauvegardes
from src.core.game_data import Sauvegardes

log = logging.getLogger(__name__)

DOSSIER = "copies_sauvegardes"
_NOM = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})\.gz$")
_FORMAT = "%Y-%m-%d_%H%M%S"

DERNIERES = 5
JOURS = 14
MOIS = 12


@dataclass(frozen=True, slots=True)
class Version:
    """Une copie : quelle sauvegarde, écrite quand par le jeu, où."""

    rel: str            # chemin relatif au dossier des sauvegardes du jeu
    quand: datetime     # date d'écriture de la sauvegarde par le JEU
    chemin: Path        # la copie compressée
    taille: int         # octets de la copie


def racine() -> Path:
    """Fonction et non constante : les tests déplacent `CONFIG_FILE_PATH`."""
    return config_module.CONFIG_FILE_PATH.parent / DOSSIER


def _dossier_de(jeu: str, rel: str) -> Path | None:
    """Le dossier des copies d'UNE sauvegarde ; None si le nom est douteux."""
    parties = [p for p in rel.replace("\\", "/").split("/") if p]
    if not parties or any(p in (".", "..") or ":" in p for p in parties):
        return None
    return racine().joinpath(jeu, *parties)


def _date_du_nom(nom: str) -> datetime | None:
    m = _NOM.match(nom)
    if m is None:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None


# ─── Copier ───

def _copier(source: Path, dossier: Path) -> tuple[Path | None, bool]:
    """Copie compressée d'UNE version, si elle n'existe pas déjà.

    Rend (la copie, vrai si elle vient d'être faite) ; (None, False) en cas
    d'échec.

    La copie passe par un fichier temporaire, puis la source est relue : si le
    jeu l'a réécrite pendant qu'on la lisait, la copie est jetée plutôt que
    gardée à moitié — on recommencera au prochain lancement.
    """
    try:
        avant = source.stat()
    except OSError:
        return None, False
    nom = datetime.fromtimestamp(avant.st_mtime).strftime(_FORMAT) + ".gz"
    cible = dossier / nom
    if cible.exists():
        return cible, False
    tmp = None
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dossier, suffix=".tmp")
        with os.fdopen(fd, "wb") as brut, \
                gzip.GzipFile(filename=source.name, mode="wb", fileobj=brut,
                              compresslevel=6, mtime=int(avant.st_mtime)) as gz, \
                open(source, "rb") as lu:
            shutil.copyfileobj(lu, gz, 1 << 20)
        apres = source.stat()
        if (apres.st_mtime_ns, apres.st_size) != (avant.st_mtime_ns, avant.st_size):
            log.info("Copie de %s abandonnée : réécrite pendant la lecture", source.name)
            return None, False
        os.replace(tmp, cible)
        tmp = None
        return cible, True
    except OSError as exc:
        log.warning("Copie de %s impossible : %s", source, exc)
        return None, False
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)           # notre propre fichier temporaire
            except OSError:
                pass


def avant_partie(jeu: str, spec: Sauvegardes | None,
                 maintenant: datetime | None = None) -> int:
    """Copie les sauvegardes qui ont changé depuis leur dernière copie.

    Rend le nombre de copies NOUVELLES. Puis éclaircit, sauvegarde par
    sauvegarde, selon le calendrier du module.
    """
    if spec is None:
        return 0
    maintenant = maintenant or datetime.now()
    nouvelles = 0
    presents = sauvegardes.fichiers(spec)
    for rel, chemin in presents.items():
        dossier = _dossier_de(jeu, rel)
        if dossier is None:
            continue
        if _copier(chemin, dossier)[1]:
            nouvelles += 1
        eclaircir(dossier, maintenant, original_present=True)
    if nouvelles:
        log.info("Sauvegardes de %s : %d copie(s) avant la partie", jeu, nouvelles)
    return nouvelles


# ─── Éclaircir ───

def a_garder(dates: list[datetime], maintenant: datetime) -> set[datetime]:
    """Les versions que le calendrier garde (voir l'en-tête du module).

    Pure, pour être testée seule. Toute version qu'aucune règle ne retient est
    remplacée par une plus récente du même jour, mois ou année : c'est ce qui
    rend l'effacement sûr.
    """
    triees = sorted(set(dates), reverse=True)
    garde = set(triees[:DERNIERES])
    vus_jour: set = set()
    vus_mois: set = set()
    vus_an: set = set()
    for d in triees:                       # du plus récent au plus ancien
        age = (maintenant - d).days
        jour, mois, an = d.date(), (d.year, d.month), d.year
        if age < JOURS and jour not in vus_jour:
            garde.add(d)
        if (maintenant.year - d.year) * 12 + maintenant.month - d.month < MOIS \
                and mois not in vus_mois:
            garde.add(d)
        if an not in vus_an:
            garde.add(d)
        vus_jour.add(jour)
        vus_mois.add(mois)
        vus_an.add(an)
    return garde


def eclaircir(dossier: Path, maintenant: datetime, original_present: bool) -> int:
    """Efface les copies que le calendrier ne garde plus ; rend leur nombre.

    Sans original, rien n'est effacé. Seuls les fichiers au nom exact d'une
    copie sont regardés : rien d'autre du dossier ne peut l'être.
    """
    if not original_present:
        return 0
    try:
        copies = {d: p for p in dossier.iterdir()
                  if (d := _date_du_nom(p.name)) is not None and p.is_file()}
    except OSError:
        return 0
    garde = a_garder(list(copies), maintenant)
    effacees = 0
    for d, p in copies.items():
        if d in garde:
            continue
        try:
            p.unlink()
            effacees += 1
        except OSError as exc:
            log.debug("Copie %s non effacée : %s", p, exc)
    return effacees


# ─── Lire et revenir ───

def versions(jeu: str) -> dict[str, list[Version]]:
    """Les copies de chaque sauvegarde, la plus récente d'abord.

    Les sauvegardes qui n'existent plus sont listées aussi : leurs copies sont
    tout ce qui reste d'elles.
    """
    base = racine() / jeu
    resultat: dict[str, list[Version]] = {}
    if not base.is_dir():
        return resultat
    try:
        copies = [p for p in base.rglob("*.gz") if _date_du_nom(p.name) is not None]
    except OSError:
        return resultat
    for p in copies:
        rel = p.parent.relative_to(base).as_posix()
        try:
            taille = p.stat().st_size
        except OSError:
            continue
        resultat.setdefault(rel, []).append(
            Version(rel=rel, quand=_date_du_nom(p.name), chemin=p, taille=taille))
    for liste in resultat.values():
        liste.sort(key=lambda v: v.quand, reverse=True)
    return resultat


def taille_totale(jeu: str) -> int:
    return sum(v.taille for liste in versions(jeu).values() for v in liste)


def dossier_du_jeu(jeu: str) -> Path:
    return racine() / jeu


def revenir(jeu: str, spec: Sauvegardes, version: Version) -> bool:
    """Remet cette version à la place de la sauvegarde. True si c'est fait.

    L'état actuel est d'abord COPIÉ (s'il ne l'est pas déjà) ; si cette copie
    échoue, on ne remplace rien. La version remise garde sa date d'écriture
    d'origine : le menu du jeu et le relevé des parties la voient pour ce
    qu'elle est.
    """
    base = sauvegardes.dossier(spec)
    dossier = _dossier_de(jeu, version.rel)
    if base is None or dossier is None:
        return False
    cible = base / version.rel
    if cible.exists() and _copier(cible, dossier)[0] is None:
        log.warning("Retour de %s refusé : l'état actuel n'a pas pu être copié", cible)
        return False
    tmp = None
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=cible.parent, suffix=".accio-tmp")
        with os.fdopen(fd, "wb") as ecrit, gzip.open(version.chemin, "rb") as gz:
            shutil.copyfileobj(gz, ecrit, 1 << 20)
        horodatage = version.quand.timestamp()
        os.utime(tmp, (horodatage, horodatage))
        os.replace(tmp, cible)
        tmp = None
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        log.warning("Retour de %s impossible : %s", cible, exc)
        return False
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)           # notre propre fichier temporaire
            except OSError:
                pass
    log.info("%s : %s remise à sa version du %s", jeu, version.rel, version.quand)
    return True

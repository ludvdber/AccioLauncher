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

**Les fichiers qui vont avec** (`Sauvegardes.compagnons`, « with » au
catalogue) sont copiés et remis AVEC la sauvegarde : les états de zone
`*_pa.usa` de HP2, `GameSaveInfoN` de HP1. Ils vivent dans un dossier au nom de
la version, à côté d'elle (`2026-10-03_143212/`), un `.gz` par fichier. La
version prend la date du plus récent de ces fichiers.

Rangé dans `_Launcher/copies_sauvegardes/<jeu>/<sauvegarde>/` : hors du dossier
du jeu, qu'une désinstallation emporte, et hors de Documents, que le jeu gère.
Aucune fonction ne lève.
"""

import gzip
import logging
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.core import config as config_module
from src.core import sauvegardes
from src.core.catalogue_blocs import Sauvegardes

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
    taille: int         # octets de la copie, fichiers compagnons compris


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
        annee, mois, jour, heure, minute, seconde = map(int, m.groups())
        return datetime(annee, mois, jour, heure, minute, seconde)
    except ValueError:
        return None


# ─── Copier ───

def compagnons(source: Path, spec: Sauvegardes | None) -> list[Path]:
    """Les fichiers qui vont avec cette sauvegarde, dans son dossier.

    « {n} » d'un motif devient le numéro du nom de la sauvegarde (`Save2.usa`
    → `GameSaveInfo2`). Ne lève jamais.
    """
    if spec is None or not spec.compagnons:
        return []
    chiffres = "".join(c for c in source.stem if c.isdigit())
    trouves: dict[str, Path] = {}
    try:
        for motif in spec.compagnons:
            for p in source.parent.glob(motif.replace("{n}", chiffres)):
                if p.name != source.name and p.is_file():
                    trouves[p.name] = p
    except (OSError, ValueError) as exc:
        log.debug("Fichiers compagnons de %s illisibles : %s", source, exc)
    return [trouves[n] for n in sorted(trouves)]


def _gzip_vers(source: Path, dossier: Path, mtime: float) -> str:
    """Compresse `source` dans un temporaire de `dossier` ; rend son chemin."""
    fd, tmp = tempfile.mkstemp(dir=dossier, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as brut, \
                gzip.GzipFile(filename=source.name, mode="wb", fileobj=brut,
                              compresslevel=6, mtime=int(mtime)) as gz, \
                open(source, "rb") as lu:
            shutil.copyfileobj(lu, gz, 1 << 20)
    except BaseException:
        os.remove(tmp)                   # notre propre fichier temporaire
        raise
    return tmp


def _copier(source: Path, dossier: Path,
            spec: Sauvegardes | None = None) -> tuple[Path | None, bool]:
    """Copie compressée d'UNE version, si elle n'existe pas déjà.

    Rend (la copie, vrai si elle vient d'être faite) ; (None, False) en cas
    d'échec.

    La copie passe par des fichiers temporaires, puis les sources sont relues :
    si le jeu en a réécrit une pendant qu'on la lisait, la copie est jetée
    plutôt que gardée à moitié — on recommencera au prochain lancement.
    Une version copiée avant que ses compagnons ne soient déclarés les reçoit
    au passage suivant : ils ne sont pas plus récents qu'elle, puisqu'elle
    porte la date du plus récent.
    """
    sources = [source, *compagnons(source, spec)]
    try:
        avant = {p: p.stat() for p in sources}
    except OSError:
        return None, False
    stamp = datetime.fromtimestamp(max(st.st_mtime for st in avant.values())).strftime(_FORMAT)
    cible = dossier / (stamp + ".gz")
    groupe = dossier / stamp
    if cible.exists():
        if len(sources) == 1 or groupe.is_dir():
            return cible, False
        sources = sources[1:]            # compléter une version d'avant les compagnons
    temporaires: list[tuple[str, Path]] = []
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        for p in sources:
            temporaires.append((_gzip_vers(p, dossier, avant[p].st_mtime),
                                cible if p is source else groupe / (p.name + ".gz")))
        for p in sources:
            apres = p.stat()
            if (apres.st_mtime_ns, apres.st_size) != (avant[p].st_mtime_ns, avant[p].st_size):
                log.info("Copie de %s abandonnée : réécrite pendant la lecture", p.name)
                return None, False
        # Les compagnons d'abord, la version en dernier : tant que son `.gz`
        # n'existe pas, elle n'existe pas, et un groupe orphelin est refait.
        for tmp, arrivee in sorted(temporaires, key=lambda t: t[1] == cible):
            arrivee.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, arrivee)
        temporaires = []
        return cible, True
    except OSError as exc:
        log.warning("Copie de %s impossible : %s", source, exc)
        return None, False
    finally:
        for tmp, _ in temporaires:
            try:
                os.remove(tmp)           # nos propres fichiers temporaires
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
        if _copier(chemin, dossier, spec)[1]:
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
    vus_jour: set[date] = set()
    vus_mois: set[tuple[int, int]] = set()
    vus_an: set[int] = set()
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
            continue
        groupe = p.with_name(p.name.removesuffix(".gz"))
        if groupe.is_dir():
            shutil.rmtree(groupe, ignore_errors=True)   # ses compagnons, rien d'autre
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
        copies = [(p, quand) for p in base.rglob("*.gz")
                  if (quand := _date_du_nom(p.name)) is not None]
    except OSError:
        return resultat
    for p, quand in copies:
        rel = p.parent.relative_to(base).as_posix()
        try:
            taille = p.stat().st_size
            groupe = p.with_name(p.name.removesuffix(".gz"))
            if groupe.is_dir():
                taille += sum(c.stat().st_size for c in groupe.glob("*.gz"))
        except OSError:
            continue
        resultat.setdefault(rel, []).append(
            Version(rel=rel, quand=quand, chemin=p, taille=taille))
    for liste in resultat.values():
        liste.sort(key=lambda v: v.quand, reverse=True)
    return resultat


def dossier_du_jeu(jeu: str) -> Path:
    return racine() / jeu


def mettre_a_l_abri(jeu: str, spec: Sauvegardes, rel: str) -> bool:
    """Copie l'état actuel de `rel` s'il ne l'est pas déjà (avant de le remplacer).

    True si une copie existe désormais, False si elle n'a pas pu être faite.
    """
    base = sauvegardes.dossier(spec)
    dossier = _dossier_de(jeu, rel)
    if base is None or dossier is None:
        return False
    return _copier(base / rel, dossier, spec)[0] is not None


def revenir(jeu: str, spec: Sauvegardes, version: Version) -> bool:
    """Remet cette version à la place de la sauvegarde. True si c'est fait.

    L'état actuel est d'abord COPIÉ (s'il ne l'est pas déjà) ; si cette copie
    échoue, on ne remplace rien. La version remise garde sa date d'écriture
    d'origine : le menu du jeu et le relevé des parties la voient pour ce
    qu'elle est.

    Une version qui a ses compagnons les remet aussi, et retire ceux d'après
    elle (une zone visitée depuis) : ils sont dans la copie de l'état actuel.
    Une version d'avant les compagnons ne remet que la sauvegarde.
    """
    base = sauvegardes.dossier(spec)
    dossier = _dossier_de(jeu, version.rel)
    if base is None or dossier is None:
        return False
    cible = base / version.rel
    if cible.exists() and _copier(cible, dossier, spec)[0] is None:
        log.warning("Retour de %s refusé : l'état actuel n'a pas pu être copié", cible)
        return False
    groupe = version.chemin.with_name(version.chemin.name.removesuffix(".gz"))
    remis = [(gz, cible.parent / gz.name.removesuffix(".gz"))
             for gz in sorted(groupe.glob("*.gz"))] if groupe.is_dir() else []
    for gz, arrivee in remis:
        if not _remettre(gz, arrivee, None):
            return False
    # La sauvegarde en dernier : un retour interrompu laisse l'ancienne en place.
    if not _remettre(version.chemin, cible, version.quand.timestamp()):
        return False
    if groupe.is_dir():
        gardes = {arrivee.name for _, arrivee in remis}
        for p in compagnons(cible, spec):
            if p.name not in gardes:
                try:
                    p.unlink()
                except OSError as exc:
                    log.warning("Compagnon %s non retiré : %s", p, exc)
    log.info("%s : %s remise à sa version du %s", jeu, version.rel, version.quand)
    return True


def _remettre(gz_source: Path, cible: Path, horodatage: float | None) -> bool:
    """Décompresse `gz_source` à la place de `cible`, par un temporaire.

    Sans horodatage, le fichier reprend la date que gzip a gardée de l'original.
    """
    tmp = None
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=cible.parent, suffix=".accio-tmp")
        with os.fdopen(fd, "wb") as ecrit, gzip.open(gz_source, "rb") as gz:
            shutil.copyfileobj(gz, ecrit, 1 << 20)
        if horodatage is None:
            with open(gz_source, "rb") as brut:
                horodatage = float(int.from_bytes(brut.read(8)[4:8], "little"))
        # mkstemp crée en 0600 : la sauvegarde remise ressortait en rw-------
        # (Bazzite, 2026-10-20). Elle reprend les droits de celle qu'elle
        # remplace, ou ceux d'un fichier ordinaire.
        os.chmod(tmp, stat.S_IMODE(cible.stat().st_mode) if cible.exists() else 0o644)
        os.utime(tmp, (horodatage, horodatage))
        os.replace(tmp, cible)
        tmp = None
        return True
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        log.warning("Retour de %s impossible : %s", cible, exc)
        return False
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)           # notre propre fichier temporaire
            except OSError:
                pass

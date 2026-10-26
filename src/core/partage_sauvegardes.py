"""Exporter une sauvegarde en .zip, en importer une (.zip ou fichier seul).

Demande de Ludo (2026-10-26), conception dans l'atelier
(`notes/PARTAGE_SAUVEGARDES.md`, validée le 2026-10-24 avec sa crainte : « si
la personne a déjà toutes les sauvegardes utilisées il faudra faire
attention »).

**Exporter** ne touche à rien : la sauvegarde telle qu'elle est (ou une de ses
versions gardées par `copies_sauvegardes`) part dans un .zip avec ses fichiers
compagnons (`GameSaveInfoN` de HP1, états de zone de HP2) et un `accio.json`
qui dit de quel jeu et de quel emplacement elle vient. Chaque fichier garde sa
date d'écriture : à l'import, le relevé des parties ne prend pas l'import pour
une partie jouée.

**Importer** accepte un .zip (d'Accio ou non : on y cherche le fichier qui a
la forme d'une sauvegarde du jeu) ou le fichier de sauvegarde seul. Avant
d'écrire, l'état actuel de l'emplacement visé est copié dans les versions :
remplacer une partie ne la perd jamais. Les compagnons arrivent d'abord, la
sauvegarde en dernier (un import interrompu laisse l'ancienne en place). Un
fichier seul n'apporte pas de compagnons : les états de zone de l'ancienne
partie sont retirés (ils mélangeraient deux parties), le résumé d'emplacement
(`{n}`, HP1) reste jusqu'à ce que le jeu le réécrive.

Rien ne lit au-delà de `_TAILLE_MAX` ni ne suit un chemin du .zip : seuls les
NOMS de fichiers comptent, et ils doivent avoir la forme que le catalogue
déclare. Aucune fonction ne lève.
"""

import fnmatch
import gzip
import json
import logging
import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core import copies_sauvegardes, sauvegardes
from src.core.catalogue_blocs import Sauvegardes

log = logging.getLogger(__name__)

MANIFESTE = "accio.json"
FORMAT = 1
_TAILLE_MAX = 256 * 1024 * 1024
_ENTREES_MAX = 400

# Les emplacements que le menu de chaque jeu montre, à partir de `premier` :
# six chez HP2 (VU, `Slot1` à `Slot6`), six lus chez HP1 (`SaveSlots`, probable)
# et HP3. Un import n'ouvre jamais un emplacement que le menu ne montrerait pas.
EMPLACEMENTS_MENU = 6

# Ce qui peut empêcher un import, pour que l'interface le dise.
ILLISIBLE = "illisible"
AUTRE_JEU = "autre_jeu"
SANS_SAUVEGARDE = "sans_sauvegarde"
PLUSIEURS = "plusieurs"
TROP_GROS = "trop_gros"


@dataclass(frozen=True, slots=True)
class Fichier:
    nom: str
    donnees: bytes
    quand: float | None      # date d'écriture d'origine


@dataclass(frozen=True, slots=True)
class Paquet:
    """Ce qu'un fichier à importer contient, lu sans rien écrire."""

    principal: Fichier
    compagnons: tuple[Fichier, ...]
    jeu: str | None              # déclaré par un .zip d'Accio
    emplacement: str | None      # chemin relatif d'origine, déclaré de même
    complet: bool                # vrai : le paquet dit lui-même quels compagnons vont avec


def _motif_principal(spec: Sauvegardes) -> str:
    return spec.fichiers.rsplit("/", 1)[-1].lower()


def _est_principal(nom: str, spec: Sauvegardes) -> bool:
    bas = nom.lower()
    if any(fnmatch.fnmatch(bas, e.lower()) for e in spec.exclure):
        return False
    return fnmatch.fnmatch(bas, _motif_principal(spec))


def _est_compagnon(nom: str, spec: Sauvegardes) -> bool:
    bas = nom.lower()
    return any(fnmatch.fnmatch(bas, m.replace("{n}", "*").lower()) for m in spec.compagnons)


def a_plusieurs_emplacements(spec: Sauvegardes) -> bool:
    """HP1 à HP3 : un fichier (ou un dossier) par emplacement."""
    return "*" in spec.fichiers and not spec.emplacements


# ─── Exporter ───

def _horodatage(chemin: Path) -> float | None:
    try:
        return chemin.stat().st_mtime
    except OSError:
        return None


def _ecrire_zip(jeu: str, rel: str, fichiers: list[Fichier], destination: Path, version: str) -> bool:
    principal = fichiers[0]
    manifeste = {
        "format": FORMAT, "jeu": jeu, "emplacement": rel, "sauvegarde": principal.nom,
        "compagnons": [f.nom for f in fichiers[1:]],
        "ecrite": datetime.fromtimestamp(principal.quand).isoformat(timespec="seconds") if principal.quand else None,
        "launcher": version,
    }
    tmp = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=destination.parent, suffix=".accio-tmp")
        with os.fdopen(fd, "wb") as brut, zipfile.ZipFile(brut, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFESTE, json.dumps(manifeste, ensure_ascii=False, indent=2))
            for f in fichiers:
                quand = datetime.fromtimestamp(f.quand) if f.quand else datetime.now()
                info = zipfile.ZipInfo(f.nom, date_time=(max(1980, quand.year), quand.month, quand.day,
                                                         quand.hour, quand.minute, quand.second))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, f.donnees)
        os.replace(tmp, destination)
        tmp = None
        log.info("%s : %s exportée vers %s", jeu, rel, destination)
        return True
    except (OSError, ValueError) as exc:
        log.warning("Export de %s impossible : %s", rel, exc)
        return False
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)           # notre propre fichier temporaire
            except OSError:
                pass


def exporter(jeu: str, spec: Sauvegardes, rel: str, destination: Path, version: str = "") -> bool:
    """La sauvegarde `rel` telle qu'elle est, avec ses compagnons, dans `destination`."""
    base = sauvegardes.dossier(spec)
    if base is None:
        return False
    source = base / rel
    try:
        fichiers = [Fichier(p.name, p.read_bytes(), _horodatage(p))
                    for p in [source, *copies_sauvegardes.compagnons(source, spec)]]
    except OSError as exc:
        log.warning("Export de %s impossible : %s", rel, exc)
        return False
    return _ecrire_zip(jeu, rel, fichiers, destination, version)


def exporter_version(jeu: str, gardee: copies_sauvegardes.Version, destination: Path,
                     version: str = "") -> bool:
    """Une version gardée par `copies_sauvegardes`, compagnons compris."""
    groupe = gardee.chemin.with_name(gardee.chemin.name.removesuffix(".gz"))
    try:
        principal = Fichier(gardee.rel.rsplit("/", 1)[-1], gzip.decompress(gardee.chemin.read_bytes()),
                            gardee.quand.timestamp())
        compagnons = [Fichier(gz.name.removesuffix(".gz"), gzip.decompress(gz.read_bytes()), _date_gzip(gz))
                      for gz in sorted(groupe.glob("*.gz"))] if groupe.is_dir() else []
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        log.warning("Export de la version %s impossible : %s", gardee.chemin, exc)
        return False
    return _ecrire_zip(jeu, gardee.rel, [principal, *compagnons], destination, version)


def _date_gzip(gz: Path) -> float | None:
    """La date de l'original que gzip garde dans son en-tête (0 : inconnue)."""
    try:
        with open(gz, "rb") as brut:
            date = int.from_bytes(brut.read(8)[4:8], "little")
        return float(date) if date else None
    except OSError:
        return None


# ─── Lire ce qu'on importe ───

def lire(source: Path, spec: Sauvegardes) -> Paquet | str:
    """Le paquet que `source` contient, ou la raison du refus (constantes du module)."""
    try:
        taille = source.stat().st_size
    except OSError:
        return ILLISIBLE
    if taille > _TAILLE_MAX:
        return TROP_GROS
    if zipfile.is_zipfile(source):
        return _lire_zip(source, spec)
    if not _est_principal(source.name, spec) and a_plusieurs_emplacements(spec):
        return SANS_SAUVEGARDE
    try:
        donnees = source.read_bytes()
    except OSError:
        return ILLISIBLE
    if not donnees:
        return SANS_SAUVEGARDE
    # Un fichier seul : son nom peut avoir changé en route (« HPHBP0 (1) »), le
    # jeu à fichier unique ne regarde que la place où on le pose.
    nom = source.name if _est_principal(source.name, spec) else _motif_principal(spec)
    return Paquet(Fichier(nom, donnees, _horodatage(source)), (), None, None, False)


def _lire_zip(source: Path, spec: Sauvegardes) -> Paquet | str:
    try:
        with zipfile.ZipFile(source) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            if len(infos) > _ENTREES_MAX or sum(i.file_size for i in infos) > _TAILLE_MAX:
                return TROP_GROS
            manifeste: dict[str, object] = {}
            if MANIFESTE in z.namelist():
                brut = json.loads(z.read(MANIFESTE).decode("utf-8"))
                manifeste = brut if isinstance(brut, dict) else {}
            principaux = [i for i in infos if _est_principal(_nom(i), spec)]
            voulu = manifeste.get("sauvegarde")
            if isinstance(voulu, str):
                principaux = [i for i in principaux if _nom(i) == voulu] or principaux
            if not principaux:
                return SANS_SAUVEGARDE
            if len(principaux) > 1:
                return PLUSIEURS
            p = principaux[0]
            compagnons = tuple(Fichier(_nom(i), z.read(i), _date(i)) for i in infos
                               if i is not p and _est_compagnon(_nom(i), spec)
                               and _dossier(i) == _dossier(p))
            principal = Fichier(_nom(p), z.read(p), _date(p))
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeDecodeError, RuntimeError):
        return ILLISIBLE
    jeu = manifeste.get("jeu")
    rel = manifeste.get("emplacement")
    return Paquet(principal, compagnons, jeu if isinstance(jeu, str) else None,
                  rel if isinstance(rel, str) else None, bool(manifeste))


def _nom(info: zipfile.ZipInfo) -> str:
    return info.filename.replace("\\", "/").rsplit("/", 1)[-1]


def _dossier(info: zipfile.ZipInfo) -> str:
    return info.filename.replace("\\", "/").rpartition("/")[0]


def _date(info: zipfile.ZipInfo) -> float | None:
    try:
        return datetime(*info.date_time).timestamp()
    except (ValueError, OverflowError):
        return None


# ─── Où importer ───

def emplacements(jeu: str, spec: Sauvegardes) -> list[tuple[str, bool]]:
    """Les emplacements où l'on peut importer : (chemin relatif, déjà pris).

    Un jeu à fichier unique (HP4 à HP8) n'en a qu'un. Pour HP1 à HP3 : ceux
    que le menu montre, pris ou libres, jamais la sauvegarde rapide.
    """
    if not a_plusieurs_emplacements(spec):
        return [(spec.fichiers, spec.fichiers in sauvegardes.fichiers(spec))]
    pris = {rel.lower() for rel in sauvegardes.fichiers(spec)}
    rangee = []
    for n in range(spec.premier, spec.premier + EMPLACEMENTS_MENU):
        rel = spec.fichiers.replace("*", str(n), 1)
        if not sauvegardes.est_rapide(jeu, rel):
            rangee.append((rel, rel.lower() in pris))
    return rangee


def _dossier_cible(spec: Sauvegardes) -> Path | None:
    """Le dossier des sauvegardes ; s'il n'existe pas encore, celui du premier motif sans joker."""
    base = sauvegardes.dossier(spec)
    if base is not None:
        return base
    racine = sauvegardes.racines().get(spec.racine)
    motif = spec.dossiers[0] if spec.dossiers else ""
    if racine is None or not motif or any(c in motif for c in "*?["):
        return None
    return racine / motif


# ─── Importer ───

def importer(jeu: str, spec: Sauvegardes, paquet: Paquet, rel: str) -> bool:
    """Pose le paquet à l'emplacement `rel`. True si c'est fait.

    L'état actuel de cet emplacement est d'abord copié dans les versions ; si
    cette copie échoue, rien n'est écrit.
    """
    base = _dossier_cible(spec)
    parties = [p for p in rel.replace("\\", "/").split("/") if p]
    if base is None or not parties or any(p in (".", "..") or ":" in p for p in parties):
        return False
    cible = base.joinpath(*parties)
    if cible.exists() and not copies_sauvegardes.mettre_a_l_abri(jeu, spec, rel):
        log.warning("Import vers %s refusé : l'état actuel n'a pas pu être copié", cible)
        return False
    anciens = copies_sauvegardes.compagnons(cible, spec) if cible.exists() else []
    for f in paquet.compagnons:
        if not _poser(f, cible.parent / f.nom):
            return False
    # La sauvegarde en dernier : un import interrompu laisse l'ancienne en place.
    if not _poser(Fichier(cible.name, paquet.principal.donnees, paquet.principal.quand), cible):
        return False
    poses = {f.nom.lower() for f in paquet.compagnons}
    for p in anciens:
        resume = any("{n}" in m and fnmatch.fnmatch(p.name.lower(), m.replace("{n}", "*").lower())
                     for m in spec.compagnons)
        if p.name.lower() in poses or (resume and not paquet.complet):
            continue
        try:
            p.unlink()
        except OSError as exc:
            log.warning("Compagnon %s non retiré : %s", p, exc)
    log.info("%s : sauvegarde importée dans %s", jeu, rel)
    return True


def _poser(f: Fichier, cible: Path) -> bool:
    tmp = None
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=cible.parent, suffix=".accio-tmp")
        with os.fdopen(fd, "wb") as ecrit:
            ecrit.write(f.donnees)
        os.chmod(tmp, stat.S_IMODE(cible.stat().st_mode) if cible.exists() else 0o644)
        if f.quand:
            os.utime(tmp, (f.quand, f.quand))
        os.replace(tmp, cible)
        tmp = None
        return True
    except OSError as exc:
        log.warning("Import de %s impossible : %s", cible, exc)
        return False
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)           # notre propre fichier temporaire
            except OSError:
                pass

"""Les sauvegardes d'un jeu : où elles sont, et quelle partie a nourri laquelle.

**Le principe : on regarde AVANT et APRÈS.** Au lancement, le launcher relève
les sauvegardes du jeu (nom et date de modification) ; à la fermeture, il
relève à nouveau. Celle qui a changé est celle dans laquelle on vient de
jouer : elle reçoit la partie (date et durée). On ne lit RIEN du contenu des
fichiers — seulement leurs dates — et on n'y écrit jamais.

**Un fichier à part, `_Launcher/sauvegardes.json`**, et non un champ de
`sessions.json` : le journal des sessions reste la seule source du temps de
jeu. Une attribution perdue, fausse ou effacée ne peut donc jamais faire
baisser le total d'un jeu ; au pire une sauvegarde affiche moins que le jeu.

**Ce qui ne se devine pas n'est pas affiché.** Une sauvegarde qui existait
avant ce relevé a une date de création et une date de dernière écriture —
vraies, le disque les porte — mais aucun temps : on n'a vu aucune de ses
parties. Elle affiche « — », jamais une estimation.

Si plusieurs sauvegardes changent pendant une même partie (on en a chargé
une autre en route), la partie va à la plus RÉCEMMENT écrite : c'est là que
le joueur s'est arrêté, donc là qu'il reprendra.
"""

import fnmatch
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.core.game_data import Sauvegardes

log = logging.getLogger(__name__)

FICHIER = "sauvegardes.json"

# Clé des parties OBSERVÉES qui n'ont écrit aucune sauvegarde. Elles sont
# notées explicitement, et non déduites par soustraction : une soustraction
# compterait aussi les parties jouées AVANT ce relevé, et dirait « 13 min sans
# sauvegarde » d'un jeu dont on ne sait simplement rien.
SANS_SAUVEGARDE = ""

# Un dossier de sauvegardes raisonnable en porte une dizaine. Le plafond borne
# ce qu'un motif trop large (ou un dossier pollué) coûterait à chaque partie.
_MAX_FICHIERS = 64
# Même plafond que le journal des sessions, et pour la même raison.
_MAX_PARTIES = 20_000


@dataclass(frozen=True, slots=True)
class Etat:
    """Ce que le disque dit d'une sauvegarde, à un instant donné."""

    modifie: float      # horodatage de la dernière écriture
    cree: float | None  # horodatage de création, None si le système l'ignore


@dataclass(frozen=True, slots=True)
class Vue:
    """Une sauvegarde telle que la page de statistiques la montre."""

    fichier: str                # chemin relatif à la racine : identifiant stable
    numero: int | None          # emplacement, compté à partir de 1 ; None si unique
    commencee: date | None
    derniere: date | None
    parties: int
    temps: int | None           # None : aucune partie observée, on ne sait pas
    modifie: float = 0.0        # horodatage exact : départage deux « derniere » du même jour


# ─── Où chercher ───

def racines() -> dict[str, Path | None]:
    """Les racines que le catalogue a le droit de désigner.

    Fonction et non constante : `tests/conftest.py` la remplace, sans quoi la
    suite lirait les VRAIES sauvegardes de la machine qui la fait tourner.

    **C'est le SEUL endroit qui change pour Linux**, sur le modèle de
    `game_registry.disponible()`. Le catalogue ne contient aucun chemin
    Windows : il nomme une racine abstraite et donne des motifs RELATIFS en
    « / ». Sous Linux, le jeu tourne dans Wine, qui range ses Documents et son
    AppData dans le préfixe (`drive_c/users/<profil>/…`) : les deux racines y
    pointent, sans rien toucher au catalogue ni au reste de ce module.
    """
    from src.core.config import get_documents_dir
    if sys.platform != "win32":
        from src.core import compat
        return {"documents": get_documents_dir(), "localappdata": compat.appdata_local()}
    local = os.environ.get("LOCALAPPDATA")
    return {"documents": get_documents_dir(),
            "localappdata": Path(local) if local else None}


def dossier(spec: Sauvegardes) -> Path | None:
    """Le premier dossier déclaré qui existe réellement."""
    base = racines().get(spec.racine)
    if base is None or not base.is_dir():
        return None
    for motif in spec.dossiers:
        try:
            trouves = sorted(p for p in base.glob(motif) if p.is_dir())
        except (OSError, ValueError):
            continue
        if trouves:
            return trouves[0]
    return None


def releve(spec: Sauvegardes | None) -> dict[str, Etat]:
    """Les sauvegardes présentes, clé = chemin relatif au DOSSIER du jeu.

    Ne lève jamais : un relevé qui échoue rend un dictionnaire vide, et la
    partie se joue comme si de rien n'était.
    """
    if spec is None:
        return {}
    racine = dossier(spec)
    if racine is None:
        return {}
    etats: dict[str, Etat] = {}
    try:
        for chemin in racine.glob(spec.fichiers):
            if len(etats) >= _MAX_FICHIERS:
                break
            rel = chemin.relative_to(racine).as_posix()
            if any(fnmatch.fnmatch(rel, e) or fnmatch.fnmatch(chemin.name, e)
                   for e in spec.exclure):
                continue
            try:
                st = chemin.stat()
            except OSError:
                continue
            if not chemin.is_file():
                continue
            cree = getattr(st, "st_birthtime", None)
            if cree is None and sys.platform == "win32":
                cree = st.st_ctime       # sous Windows, c'est la création
            etats[rel] = Etat(modifie=st.st_mtime, cree=cree)
    except (OSError, ValueError) as exc:
        log.debug("Relevé des sauvegardes impossible : %s", exc)
    return etats


def modifiee(avant: dict[str, Etat], apres: dict[str, Etat]) -> str | None:
    """La sauvegarde dans laquelle on vient de jouer, ou None.

    Nouvelle ou réécrite ; s'il y en a plusieurs, la plus récemment écrite.
    """
    changees = [(etat.modifie, rel) for rel, etat in apres.items()
                if rel not in avant or avant[rel].modifie != etat.modifie]
    return max(changees)[1] if changees else None


def numero(rel: str, spec: Sauvegardes, nb_fichiers: int) -> int | None:
    """L'emplacement, compté à partir de 1, d'après le PREMIER nombre du nom.

    « Save0.usa » → 1 si le jeu numérote à partir de 0 ; « Slot1/Save0.usa »
    → 1 si c'est « Slot » qui porte le numéro à partir de 1. Un jeu à
    sauvegarde unique (HP5 à HP7) n'a pas de numéro : « Emplacement 1 » sur
    une seule carte laisserait croire qu'il en existe d'autres.
    """
    if nb_fichiers <= 1 and "*" not in spec.fichiers:
        return None
    trouve = re.search(r"\d+", rel)
    if trouve is None:
        return None
    n = int(trouve.group()) - spec.premier + 1
    return n if n >= 1 else None


# ─── Fichier ───

def chemin_fichier() -> Path:
    """Résolu à l'appel — même garde de test que `stats.chemin_journal`."""
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / FICHIER


def charger(chemin: Path | None = None) -> dict[tuple[str, str], dict]:
    """{(jeu, fichier): {"commencee": date | None, "parties": [(debut, duree)]}}.

    Un fichier illisible est mis de côté, jamais écrasé, comme le journal.
    """
    chemin = chemin or chemin_fichier()
    if not chemin.exists():
        return {}
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.warning("Relevé des sauvegardes illisible (%s) — mis de côté", exc)
        try:
            os.replace(chemin, chemin.with_suffix(".corrompu"))
        except OSError:
            pass
        return {}
    stock: dict[tuple[str, str], dict] = {}
    entrees = data.get("sauvegardes") if isinstance(data, dict) else None
    for e in entrees if isinstance(entrees, list) else ():
        if not isinstance(e, dict):
            continue
        jeu, fichier = e.get("jeu"), e.get("fichier")
        if not isinstance(jeu, str) or not jeu or not isinstance(fichier, str):
            continue
        commencee = _date(e.get("commencee"))
        parties = []
        for p in e.get("parties") or ():
            if not isinstance(p, dict):
                continue
            duree = p.get("duree")
            if not isinstance(duree, int) or isinstance(duree, bool) or duree <= 0:
                continue
            try:
                debut = datetime.fromisoformat(str(p.get("debut")))
            except (ValueError, TypeError):
                continue
            parties.append((debut, duree))
        stock[(jeu, fichier)] = {"commencee": commencee,
                                 "parties": parties[-_MAX_PARTIES:]}
    return stock


def _date(brut) -> date | None:
    try:
        return date.fromisoformat(str(brut)) if brut else None
    except ValueError:
        return None


def _ecrire(stock: dict[tuple[str, str], dict], chemin: Path) -> None:
    """Écriture atomique (tmp + rename), même contrat que le journal."""
    data = {"version": 1, "sauvegardes": [
        {"jeu": jeu, "fichier": fichier,
         "commencee": v["commencee"].isoformat() if v["commencee"] else None,
         "parties": [{"debut": d.isoformat(timespec="seconds"), "duree": s}
                     for d, s in v["parties"][-_MAX_PARTIES:]]}
        for (jeu, fichier), v in sorted(stock.items())
    ]}
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=1, ensure_ascii=False))
        os.replace(tmp, chemin)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _jour(horodatage: float | None) -> date | None:
    if horodatage is None:
        return None
    try:
        return datetime.fromtimestamp(horodatage).date()
    except (OverflowError, OSError, ValueError):
        return None


def attribuer(jeu: str, avant: dict[str, Etat], apres: dict[str, Etat],
              debut: datetime, duree: int, chemin: Path | None = None) -> str | None:
    """Donne la partie qui vient de finir à la sauvegarde qu'elle a écrite.

    Rend le fichier retenu, ou None si aucune sauvegarde n'a bougé : on a joué
    sans sauvegarder, et la partie est notée sous `SANS_SAUVEGARDE` pour que
    la page puisse le dire. Un échec d'écriture ne remonte jamais — même règle
    que le journal.
    """
    if duree <= 0:
        return None
    rel = modifiee(avant, apres)
    chemin = chemin or chemin_fichier()
    stock = charger(chemin)
    if rel is None:
        stock.setdefault((jeu, SANS_SAUVEGARDE), {"commencee": None, "parties": []})[
            "parties"].append((debut, int(duree)))
        try:
            _ecrire(stock, chemin)
        except OSError as exc:
            log.warning("Relevé des sauvegardes non mis à jour : %s", exc)
        return None
    entree = stock.setdefault((jeu, rel), {"commencee": None, "parties": []})
    # Une sauvegarde CRÉÉE pendant cette partie a commencé avec elle ; sinon
    # le disque sait mieux que nous quand elle est née.
    nee = debut.date() if rel not in avant else _jour(apres[rel].cree)
    if nee is not None and (entree["commencee"] is None or nee < entree["commencee"]):
        entree["commencee"] = nee
    entree["parties"].append((debut, int(duree)))
    try:
        _ecrire(stock, chemin)
    except OSError as exc:
        log.warning("Relevé des sauvegardes non mis à jour : %s", exc)
    return rel


# ─── Pour l'affichage ───

def temps_sans_sauvegarde(jeu: str, stock: dict[tuple[str, str], dict] | None = None) -> int:
    """Secondes jouées, depuis le relevé, sans qu'aucune sauvegarde soit écrite."""
    stock = charger() if stock is None else stock
    return sum(d for _, d in stock.get((jeu, SANS_SAUVEGARDE), {}).get("parties", ()))


def vues(jeu: str, spec: Sauvegardes | None,
         stock: dict[tuple[str, str], dict] | None = None) -> list[Vue]:
    """Les sauvegardes PRÉSENTES sur le disque, avec ce qu'on sait d'elles.

    Une sauvegarde supprimée n'est pas montrée — sa trace reste dans le
    fichier, et le temps de jeu, lui, n'a jamais dépendu d'elle.
    """
    etats = releve(spec)
    if not etats:
        return []
    stock = charger() if stock is None else stock
    resultat = []
    for rel, etat in etats.items():
        connu = stock.get((jeu, rel), {"commencee": None, "parties": []})
        parties = connu["parties"]
        commencee = connu["commencee"] or _jour(etat.cree)
        derniere = _jour(etat.modifie)
        if commencee and derniere and commencee > derniere:
            commencee = derniere        # une copie de fichier « crée » après coup
        resultat.append(Vue(
            fichier=rel,
            numero=numero(rel, spec, len(etats)),
            commencee=commencee,
            derniere=derniere,
            parties=len(parties),
            temps=sum(d for _, d in parties) if parties else None,
            modifie=etat.modifie,
        ))
    resultat.sort(key=lambda v: (v.numero is None, v.numero or 0, v.fichier))
    return resultat

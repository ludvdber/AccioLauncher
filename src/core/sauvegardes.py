"""Les sauvegardes d'un jeu : où elles sont, et quelle partie a nourri laquelle.

**Le principe : on regarde AVANT et APRÈS.** Au lancement, le launcher relève
les sauvegardes du jeu (nom et date de modification) ; à la fermeture, il
relève à nouveau. Celle qui a changé est celle dans laquelle on vient de
jouer : elle reçoit la partie (date et durée). On ne lit RIEN du contenu des
fichiers — seulement leurs dates — et on n'y écrit jamais.

**Une exception, déclarée par le catalogue : les emplacements rangés DANS un
fichier** (`Sauvegardes.emplacements`). HP4 garde ses trois parties dans un
seul `HPGOF` (vu à l'écran « Sélectionnez un emplacement », 2026-09-30) : ses
dates de fichier ne disent pas QUELLE partie a bougé. On lit alors son EN-TÊTE,
et seulement lui — la date et l'heure que le jeu y écrit pour chaque emplacement
— pour en faire trois sauvegardes distinctes, `HPGOF#1` à `#3`. Toujours en
lecture seule.

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

**Une nouvelle aventure dans un même emplacement** : à chaque attribution,
on note où en est la sauvegarde (`progression.mesure` : cartes, étape de
l'histoire…). Si ces compteurs ont BAISSÉ depuis la fois précédente, ce n'est
plus la même aventure : la date est ajoutée à `nouvelles`, et la carte de
l'emplacement ne montre plus que ce qui la suit. Rien n'est effacé : les
parties d'avant restent dans le fichier et sont résumées en une ligne.
"""

import fnmatch
import json
import logging
import os
import re
import sys
import tempfile
from collections.abc import Callable
from typing import Any
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.core.catalogue_blocs import Sauvegardes

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
    avancement: int | None = None   # pourcentage écrit par le jeu (HP5), sinon None


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
    rapide: bool = False        # la sauvegarde rapide (F5), hors des emplacements
    avancement: int | None = None   # « 14 % » tel que le jeu l'affiche (HP5)
    nouvelle: date | None = None    # l'aventure en cours a été commencée ce jour-là
    precedentes: int = 0            # aventures d'avant, dans le même emplacement
    temps_precedent: int | None = None   # leur temps ; None : aucune partie observée


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
    """Le dossier où l'on a joué en DERNIER, parmi ceux que déclare le catalogue.

    HP7 nomme le sien d'après la langue JOUÉE (« … – Deuxième Partie »,
    « … – Parte 2 »…, relevé dans les exe) : qui a changé de langue en a
    plusieurs. Le premier motif qui existe n'était donc pas forcément celui de
    la partie en cours. On prend le dossier qui porte la sauvegarde la plus
    récemment écrite ; sans sauvegarde nulle part, le premier trouvé.
    """
    base = racines().get(spec.racine)
    if base is None or not base.is_dir():
        return None
    candidats: list[Path] = []
    for motif in spec.dossiers:
        try:
            trouves = sorted(p for p in base.glob(motif) if p.is_dir())
        except (OSError, ValueError):
            continue
        candidats.extend(p for p in trouves if p not in candidats)
    if len(candidats) <= 1:
        return candidats[0] if candidats else None
    # max() garde le PREMIER des ex aequo : l'ordre du catalogue départage.
    return max(candidats, key=lambda d: _derniere_ecriture(d, spec))


def _derniere_ecriture(racine: Path, spec: Sauvegardes) -> float:
    """La date de la sauvegarde la plus récente du dossier, 0 s'il n'en a pas."""
    plus_recente = 0.0
    try:
        for n, chemin in enumerate(racine.glob(spec.fichiers)):
            if n >= _MAX_FICHIERS:
                break
            try:
                plus_recente = max(plus_recente, chemin.stat().st_mtime)
            except OSError:
                continue
    except (OSError, ValueError):
        pass
    return plus_recente


def fichiers(spec: Sauvegardes | None) -> dict[str, Path]:
    """Les FICHIERS de sauvegarde présents, clé = chemin relatif au dossier.

    Ce que `copies_sauvegardes` met à l'abri : un fichier entier, même quand il
    porte plusieurs emplacements (HP4). Mêmes motifs, exclusions et plafond que
    `releve`. Ne lève jamais.
    """
    if spec is None:
        return {}
    racine = dossier(spec)
    if racine is None:
        return {}
    trouves: dict[str, Path] = {}
    try:
        for chemin in racine.glob(spec.fichiers):
            if len(trouves) >= _MAX_FICHIERS:
                break
            rel = chemin.relative_to(racine).as_posix()
            if any(fnmatch.fnmatch(rel, e) or fnmatch.fnmatch(chemin.name, e)
                   for e in spec.exclure) or not chemin.is_file():
                continue
            trouves[rel] = chemin
    except (OSError, ValueError) as exc:
        log.debug("Liste des sauvegardes impossible : %s", exc)
    return trouves


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
            lire = _EMPLACEMENTS.get(spec.emplacements)
            if lire is None:
                etats[rel] = Etat(modifie=st.st_mtime, cree=cree)
                continue
            for n, ecrit, avancement in lire(_entete(chemin)):
                # Sans date lisible, celle du fichier : l'emplacement existe,
                # et c'est le mieux qu'on sache de lui.
                etats[f"{rel}#{n}"] = Etat(modifie=ecrit or st.st_mtime, cree=None,
                                           avancement=avancement)
    except (OSError, ValueError) as exc:
        log.debug("Relevé des sauvegardes impossible : %s", exc)
    return etats


def derniere_avancee(spec: Sauvegardes | None) -> Etat | None:
    """La partie écrite en dernier parmi celles dont le JEU dit l'avancement
    (HP5 : « 14 % »), ou None. L'en-tête seul est lu."""
    if spec is None or not spec.emplacements:
        return None
    avec = [e for e in releve(spec).values() if e.avancement is not None]
    return max(avec, key=lambda e: e.modifie, default=None)


# ─── Emplacements rangés dans un fichier ───

# Assez pour les trois fiches de HP5 (0x488) ; celles de HP4 s'arrêtent à 0x220.
_TAILLE_ENTETE = 0x500
_ENTETE_HP4 = 0x220


def _entete(chemin: Path) -> bytes:
    """Les premiers octets seulement : l'en-tête suffit, le reste n'est pas lu."""
    try:
        with open(chemin, "rb") as f:
            return f.read(_TAILLE_ENTETE)
    except OSError:
        return b""


def _texte(entete: bytes, debut: int, taille: int) -> str:
    return entete[debut:debut + taille].split(b"\0", 1)[0].decode("ascii", "replace")


Emplacement = tuple[int, "float | None", "int | None"]   # numéro, date écrite, avancement


def emplacements_hp4(entete: bytes) -> list[Emplacement]:
    """HP4 : (numéro, horodatage écrit par le jeu) de chaque emplacement OCCUPÉ.

    Relevé sur une vraie sauvegarde (2026-09-30) : magie `20CM`, puis trois
    fiches de 0xAC octets. Dans chacune, la date « 28/09/2026 » à +0x6C, l'heure
    « 12:23:58 » à +0x8C, et deux entiers à +0xAC (classement, niveau) qui
    valent -1 et -1 pour un emplacement vide — c'est ce qu'affiche le jeu
    (« Vide »). Tout écart de format rend une liste vide, jamais une exception :
    le jeu se lance quand même, les statistiques n'affichent rien de faux.
    """
    if len(entete) < _ENTETE_HP4 or entete[:4] != b"20CM":
        return []
    trouves: list[Emplacement] = []
    for k in range(3):
        base = 0x10 + k * 0xAC
        classement = int.from_bytes(entete[base + 0xAC:base + 0xB0], "little", signed=True)
        if classement < 0:
            continue
        jour = _texte(entete, base + 0x6C, 16)
        heure = _texte(entete, base + 0x8C, 16)
        try:
            ecrit = datetime.strptime(f"{jour} {heure}", "%d/%m/%Y %H:%M:%S").timestamp()
        except (ValueError, OverflowError, OSError):
            ecrit = None
        trouves.append((k + 1, ecrit, None))
    return trouves


def emplacements_hp5(entete: bytes) -> list[Emplacement]:
    """HP5 : (numéro, horodatage écrit par le jeu, pourcentage) de chaque partie.

    Relevé sur la sauvegarde de Ludo le 2026-10-15 et VU contre l'écran
    « Continuer aventure » (14 % le 01/10/26 à 16:08, 6 %, 1 %) : magie
    `20CM`, puis trois fiches de 0x178 octets à partir de 0x20. Dans chacune,
    le nom interne du lieu (« Hogwarts »), puis à +0x40 des entiers 32 bits :
    année, mois, jour de la semaine, jour, heure, minute, seconde ; le
    pourcentage à +0x70. Une fiche sans lieu ou sans date plausible n'est pas
    une partie (l'emplacement vide n'a pas encore été vu) : elle est sautée.
    """
    if len(entete) < 0x20 + 3 * 0x178 or entete[:4] != b"20CM":
        return []
    trouves: list[Emplacement] = []
    for k in range(3):
        base = 0x20 + k * 0x178
        if not re.fullmatch(r"[A-Za-z0-9_]+", _texte(entete, base, 0x40)):
            continue
        champs = [int.from_bytes(entete[base + 0x40 + 4 * i:base + 0x44 + 4 * i], "little")
                  for i in range(7)]
        annee, mois, _, jour, heure, minute, seconde = champs
        try:
            ecrit = datetime(annee, mois, jour, heure, minute, seconde).timestamp()
        except (ValueError, OverflowError, OSError):
            continue
        if not 2000 <= annee <= 2100:
            continue
        pourcent = int.from_bytes(entete[base + 0x70:base + 0x74], "little")
        trouves.append((k + 1, ecrit, pourcent if pourcent <= 100 else None))
    return trouves


_EMPLACEMENTS = {"hp4": emplacements_hp4, "hp5": emplacements_hp5}


def modifiee(avant: dict[str, Etat], apres: dict[str, Etat]) -> str | None:
    """La sauvegarde dans laquelle on vient de jouer, ou None.

    Nouvelle ou réécrite ; s'il y en a plusieurs, la plus récemment écrite.
    """
    changees = [(etat.modifie, rel) for rel, etat in apres.items()
                if rel not in avant or avant[rel].modifie != etat.modifie]
    return max(changees)[1] if changees else None


# La sauvegarde rapide (F5) par jeu : un fichier à part, que le menu du jeu ne
# range dans aucun emplacement. HP1 l'écrit dans `Save9.usa` (relevé en jeu le
# 2026-10-15), HP3 aussi (essai Q4, même jour) ; sans ce nom, elle s'affichait « Emplacement 10 ».
_RAPIDES = {"hp1": "save9.usa", "hp3": "save9.usa"}


def est_rapide(jeu: str, rel: str) -> bool:
    return _RAPIDES.get(jeu) == rel.rsplit("/", 1)[-1].lower()


def numero(rel: str, spec: Sauvegardes, nb_fichiers: int) -> int | None:
    """L'emplacement, compté à partir de 1, d'après le PREMIER nombre du nom.

    « Save0.usa » → 1 si le jeu numérote à partir de 0 ; « Slot1/Save0.usa »
    → 1 si c'est « Slot » qui porte le numéro à partir de 1. Un jeu à
    sauvegarde unique (HP5 à HP7) n'a pas de numéro : « Emplacement 1 » sur
    une seule carte laisserait croire qu'il en existe d'autres.

    Un emplacement lu dans un fichier (`HPGOF#2`) porte son numéro après le
    « # » : le jeu en montre toujours trois, donc « Emplacement 2 » est vrai
    même seul.
    """
    if "#" in rel:
        chiffres = rel.rsplit("#", 1)[1]
        return int(chiffres) if chiffres.isdigit() and int(chiffres) >= 1 else None
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


def charger(chemin: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """{(jeu, fichier): {"commencee": date | None, "parties": [(debut, duree)],
    "mesure": tuple[int, ...] | None, "nouvelles": [datetime]}}.

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
    stock: dict[tuple[str, str], dict[str, Any]] = {}
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
        mesure = e.get("mesure")
        if not (isinstance(mesure, list) and mesure
                and all(isinstance(m, int) and not isinstance(m, bool) for m in mesure)):
            mesure = None
        nouvelles = []
        for brut in e.get("nouvelles") or ():
            try:
                nouvelles.append(datetime.fromisoformat(str(brut)))
            except (ValueError, TypeError):
                continue
        stock[(jeu, fichier)] = {"commencee": commencee,
                                 "parties": parties[-_MAX_PARTIES:],
                                 "mesure": tuple(mesure) if mesure else None,
                                 "nouvelles": sorted(nouvelles)}
    return stock


def _entree(stock: dict[tuple[str, str], dict[str, Any]], cle: tuple[str, str]) -> dict[str, Any]:
    return stock.setdefault(cle, {"commencee": None, "parties": [], "mesure": None,
                                  "nouvelles": []})


def _date(brut: object) -> date | None:
    try:
        return date.fromisoformat(str(brut)) if brut else None
    except ValueError:
        return None


def _ecrire(stock: dict[tuple[str, str], dict[str, Any]], chemin: Path) -> None:
    """Écriture atomique (tmp + rename), même contrat que le journal."""
    def ligne(jeu: str, fichier: str, v: dict[str, Any]) -> dict[str, Any]:
        e: dict[str, Any] = {
            "jeu": jeu, "fichier": fichier,
            "commencee": v["commencee"].isoformat() if v["commencee"] else None,
            "parties": [{"debut": d.isoformat(timespec="seconds"), "duree": s}
                        for d, s in v["parties"][-_MAX_PARTIES:]]}
        # Absents tant qu'ils sont vides : un fichier d'avant reste identique.
        if v.get("mesure"):
            e["mesure"] = list(v["mesure"])
        if v.get("nouvelles"):
            e["nouvelles"] = [d.isoformat(timespec="seconds") for d in v["nouvelles"]]
        return e

    data = {"version": 1, "sauvegardes": [
        ligne(jeu, fichier, v) for (jeu, fichier), v in sorted(stock.items())]}
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
              debut: datetime, duree: int, chemin: Path | None = None,
              mesurer: Callable[[str], tuple[int, ...] | None] | None = None) -> str | None:
    """Donne la partie qui vient de finir à la sauvegarde qu'elle a écrite.

    Rend le fichier retenu, ou None si aucune sauvegarde n'a bougé : on a joué
    sans sauvegarder, et la partie est notée sous `SANS_SAUVEGARDE` pour que
    la page puisse le dire. Un échec d'écriture ne remonte jamais — même règle
    que le journal.

    `mesurer(rel)` dit où en est la sauvegarde (`progression.mesure`) : si
    elle a reculé depuis l'attribution précédente, cette partie ouvre une
    nouvelle aventure dans l'emplacement. La sauvegarde rapide n'en ouvre
    jamais : elle prend ce qu'on vient de charger, d'où qu'il vienne.
    """
    if duree <= 0:
        return None
    rel = modifiee(avant, apres)
    chemin = chemin or chemin_fichier()
    stock = charger(chemin)
    if rel is None:
        _entree(stock, (jeu, SANS_SAUVEGARDE))["parties"].append((debut, int(duree)))
        try:
            _ecrire(stock, chemin)
        except OSError as exc:
            log.warning("Relevé des sauvegardes non mis à jour : %s", exc)
        return None
    entree = _entree(stock, (jeu, rel))
    # Une sauvegarde CRÉÉE pendant cette partie a commencé avec elle ; sinon
    # le disque sait mieux que nous quand elle est née.
    nee = debut.date() if rel not in avant else _jour(apres[rel].cree)
    if nee is not None and (entree["commencee"] is None or nee < entree["commencee"]):
        entree["commencee"] = nee
    entree["parties"].append((debut, int(duree)))
    if mesurer is not None and not est_rapide(jeu, rel):
        from src.core import progression
        maintenant = mesurer(rel)
        # Sans partie déjà comptée ici, il n'y a pas d'aventure d'avant à séparer.
        if len(entree["parties"]) > 1 and progression.recommencee(entree["mesure"], maintenant):
            entree["nouvelles"] = [*entree["nouvelles"], debut]
            log.info("Sauvegardes : nouvelle aventure dans %s (%s), %s → %s",
                     rel, jeu, entree["mesure"], maintenant)
        if maintenant is not None:
            entree["mesure"] = maintenant
    try:
        _ecrire(stock, chemin)
    except OSError as exc:
        log.warning("Relevé des sauvegardes non mis à jour : %s", exc)
    return rel


# ─── Pour l'affichage ───

def temps_sans_sauvegarde(jeu: str, stock: dict[tuple[str, str], dict[str, Any]] | None = None) -> int:
    """Secondes jouées, depuis le relevé, sans qu'aucune sauvegarde soit écrite."""
    stock = charger() if stock is None else stock
    return sum(d for _, d in stock.get((jeu, SANS_SAUVEGARDE), {}).get("parties", ()))


def vues(jeu: str, spec: Sauvegardes | None,
         stock: dict[tuple[str, str], dict[str, Any]] | None = None) -> list[Vue]:
    """Les sauvegardes PRÉSENTES sur le disque, avec ce qu'on sait d'elles.

    Une sauvegarde supprimée n'est pas montrée — sa trace reste dans le
    fichier, et le temps de jeu, lui, n'a jamais dépendu d'elle.
    """
    if spec is None:
        return []
    etats = releve(spec)
    if not etats:
        return []
    stock = charger() if stock is None else stock
    resultat = []
    for rel, etat in etats.items():
        connu = stock.get((jeu, rel), {"commencee": None, "parties": []})
        parties = connu["parties"]
        nouvelles = connu.get("nouvelles") or []
        avant: list[tuple[datetime, int]] = []
        if nouvelles:
            # Ce qui précède la dernière nouvelle aventure est résumé, pas montré.
            avant = [p for p in parties if p[0] < nouvelles[-1]]
            parties = [p for p in parties if p[0] >= nouvelles[-1]]
        commencee = (nouvelles[-1].date() if nouvelles
                     else connu["commencee"] or _jour(etat.cree))
        derniere = _jour(etat.modifie)
        if commencee and derniere and commencee > derniere:
            commencee = derniere        # une copie de fichier « crée » après coup
        resultat.append(Vue(
            fichier=rel,
            numero=None if est_rapide(jeu, rel) else numero(rel, spec, len(etats)),
            commencee=commencee,
            derniere=derniere,
            parties=len(parties),
            temps=sum(d for _, d in parties) if parties else None,
            modifie=etat.modifie,
            rapide=est_rapide(jeu, rel),
            avancement=etat.avancement,
            nouvelle=nouvelles[-1].date() if nouvelles else None,
            precedentes=len(nouvelles),
            temps_precedent=sum(d for _, d in avant) if avant else None,
        ))
    resultat.sort(key=lambda v: (v.numero is None, v.numero or 0, v.fichier))
    return resultat

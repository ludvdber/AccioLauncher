"""Les succès : ce qu'une sauvegarde PROUVE, nommé et daté.

Idée de Ludo (2026-09-19, reconfirmée les 2026-10-15 et 2026-10-17) : des
succès « inventés », légitimes tant qu'ils reposent sur ce que la sauvegarde
prouve, **par sauvegarde**, datés à la partie où ils tombent, annoncés au
retour de partie.

**Rien n'est deviné.** Chaque succès est une condition sur ce que lisent les
lecteurs du folio (`folio_hp*.py`) : des cartes, des écussons, des compteurs
du jeu lui-même, avec les totaux que le jeu affiche. Pas de pourcentage
estimé, pas de temps de jeu (le merci du Ko-fi a été détaché des heures de
jeu pour la même raison : rien ici ne récompense de consommer les jeux d'EA).

**La date est celle d'une partie OBSERVÉE.** À la première fois qu'on regarde
une sauvegarde déjà jouée, ce qu'elle porte est noté SANS date (« avant le
suivi ») : on ne sait pas quand c'est arrivé. Seule une sauvegarde NÉE pendant
la partie qui vient de finir date ce qu'elle porte déjà de cette partie.

**Un fichier à part, `_Launcher/succes.json`**, comme `sauvegardes.json` :
une ligne par (jeu, sauvegarde, succès). Une sauvegarde effacée ou une
aventure recommencée dans le même emplacement n'efface rien : ce qui a été
obtenu l'a été.
"""

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.catalogue_blocs import Sauvegardes
from src.core.ecriture_atomique import ecrire_atomique

log = logging.getLogger(__name__)

FICHIER = "succes.json"


@dataclass(frozen=True)
class Succes:
    ident: str          # unique dans son jeu, stable : la clé du fichier
    titre: str          # clé tr()
    description: str    # clé tr()
    obtenu: Callable[[Any], bool]


@dataclass(frozen=True)
class Obtenu:
    succes: Succes
    sauvegarde: str              # la clé de `sauvegardes.releve`
    date: datetime | None        # None : déjà là au premier regard


# ─── Les succès de chaque jeu ───
# Les seuils sont des totaux que le JEU affiche (« / 25 », « / 125 »…) ou leur
# moitié ; aucun ne demande de savoir comment le jeu compte en dehors de la
# sauvegarde.

def _hp1() -> tuple[Succes, ...]:
    from src.core import folio
    autres = [m for m in folio.MAISONS if m != folio.GRYFFONDOR]
    return (
        Succes("carte", "Chocogrenouille", "Une première carte de sorcier dans le folio.",
               lambda r: len(r.cartes) >= 1),
        Succes("cartes_13", "Demi-folio", "13 cartes de sorcier sur 25.",
               lambda r: len(r.cartes) >= 13),
        Succes("cartes_25", "Folio complet", "Les 25 cartes de sorcier.",
               lambda r: len(r.cartes) >= 25),
        Succes("points_100", "Cent points pour Gryffondor", "Gryffondor atteint 100 points au sablier.",
               lambda r: r.points.get(folio.GRYFFONDOR, 0) >= 100),
        Succes("gryffondor_tete", "Gryffondor en tête",
               "Gryffondor devance les trois autres maisons au décompte des points.",
               lambda r: r.points.get(folio.GRYFFONDOR, 0) > max(r.points.get(m, 0) for m in autres)),
    )


def _hp2() -> tuple[Succes, ...]:
    from src.core import folio_hp2
    return (
        Succes("carte", "Chocogrenouille", "Une première carte de sorcier dans le folio.",
               lambda r: len(r.cartes) >= 1),
        Succes("cartes_50", "Collectionneur", "50 cartes de sorcier sur 101.",
               lambda r: len(r.cartes) >= 50),
        Succes("cartes_101", "Folio complet", "Les 101 cartes de sorcier.",
               lambda r: len(r.cartes) >= folio_hp2.CARTES),
        Succes("sorts", "Livre de sorts complet", "Les neuf sorts du livre, de Flipendo à Mimblewimble.",
               lambda r: all(any(c in r.sorts for c in classes) for classes, _n, _g in folio_hp2.SORTS)),
    )


def _hp3() -> tuple[Succes, ...]:
    from src.core import folio_hp3
    return (
        Succes("carte", "Chocogrenouille", "Une première carte de sorcier dans le folio.",
               lambda r: len(r.cartes) >= 1),
        Succes("cartes_40", "Collectionneur", "40 cartes de sorcier sur 80.",
               lambda r: len(r.cartes) >= 40),
        Succes("cartes_80", "Folio complet", "Les 80 cartes de sorcier.",
               lambda r: len(r.cartes) >= folio_hp3.CARTES),
        Succes("etoiles", "Sans faute", "Toutes les étoiles d'un défi.",
               lambda r: any(n.total and n.trouves >= n.total for n in r.etoiles)),
        Succes("secrets", "Rien ne lui échappe", "Tous les secrets d'un niveau.",
               lambda r: any(n.total and n.trouves >= n.total for n in r.secrets)),
    )


def _hp4() -> tuple[Succes, ...]:
    from src.core import folio_hp4
    return (
        Succes("carte", "Chocogrenouille", "Une première carte du Folio Universitas.",
               lambda p: len(p.cartes) >= 1),
        Succes("bouclier", "Premier bouclier", "Un bouclier de la Coupe dans l'armoire à trophées.",
               lambda p: p.boucliers >= 1),
        Succes("boucliers_19", "La moitié de l'armoire", "19 boucliers sur 38.",
               lambda p: p.boucliers >= 19),
        Succes("boucliers_38", "Armoire à trophées pleine", "Les 38 boucliers.",
               lambda p: p.boucliers >= folio_hp4.BOUCLIERS),
    )


def _hp5() -> tuple[Succes, ...]:
    from src.core import folio_hp5
    tous = (
        Succes("moitie", "À mi-parcours", "Le jeu affiche 50 % d'avancement.",
               lambda p: (p.pourcentage or 0) >= 50),
        Succes("cent", "Ordre accompli", "Le jeu affiche 100 % d'avancement.",
               lambda p: (p.pourcentage or 0) >= 100),
        Succes("decouverte", "Explorateur", "1 000 points de découverte sur 4 360.",
               lambda p: (p.decouverte or 0) >= 1000),
    )
    def ligne_pleine(i: int, total: int) -> Callable[[Any], bool]:
        return lambda p: p.compteurs is not None and p.compteurs[i] >= total

    # Une ligne de l'écran « Informations sur le jeu » remplie jusqu'au bout.
    return tous + tuple(
        Succes(f"complet_{c.premier}", c.libelle, "Ligne complète dans « Informations sur le jeu ».",
               ligne_pleine(i, c.total))
        for i, c in enumerate(folio_hp5.COMPTEURS))


def _hp6() -> tuple[Succes, ...]:
    from src.core import folio_hp6
    return (
        Succes("ecusson", "Premier écusson", "Un écusson de Poudlard trouvé.",
               lambda p: p.ecussons >= 1),
        Succes("ecussons_63", "La moitié des écussons", "63 écussons sur 125.",
               lambda p: p.ecussons >= 63),
        Succes("ecussons_125", "Tous les écussons", "Les 125 écussons.",
               lambda p: p.ecussons >= folio_hp6.ECUSSONS),
        Succes("mini_25", "Minicrestomètre plein", "Les 25 paliers de mini-écussons.",
               lambda p: folio_hp6.palier(p.mini_ecussons)[0] >= len(folio_hp6.PALIERS)),
        Succes("sorts", "Arsenal complet", "Les onze sorts du jeu appris.",
               lambda p: len(p.sorts) >= len(folio_hp6.SORTS)),
        Succes("badge", "Premier badge", "Un badge de club remporté.",
               lambda p: p.badges >= 1),
        Succes("badges", "Tous les badges", "Les 30 badges des clubs.",
               lambda p: p.badges_total > 0 and p.badges >= p.badges_total),
    )


_DEFINITIONS: dict[str, Callable[[], tuple[Succes, ...]]] = {
    "hp1": _hp1, "hp2": _hp2, "hp3": _hp3, "hp4": _hp4, "hp5": _hp5, "hp6": _hp6}


def du_jeu(jeu: str) -> tuple[Succes, ...]:
    """Les succès d'un jeu, dans l'ordre d'affichage ; vide s'il n'en a pas."""
    definir = _DEFINITIONS.get(jeu)
    return definir() if definir is not None else ()


# ─── Lecture d'une sauvegarde ───

def _partie(jeu: str, chemin: Path, n: int) -> Any:
    """Ce que le lecteur du folio rend pour cet emplacement, ou None."""
    from src.core import folio, folio_hp2, folio_hp3, folio_hp4, folio_hp5, folio_hp6
    if jeu == "hp1":
        r = folio.releve_hp1(chemin)
        return r if r is not None and r.lu else None
    if jeu == "hp2":
        r2 = folio_hp2.releve(chemin, n)
        return r2 if r2 is not None and r2.lu else None
    if jeu == "hp3":
        r3 = folio_hp3.releve(chemin)
        return r3 if r3 is not None and r3.lu else None
    if jeu == "hp4":
        return next((p for p in folio_hp4.releve(chemin) if p.emplacement == n), None)
    if jeu == "hp5":
        return next((p for p in folio_hp5.releve(chemin) if p.emplacement == n), None)
    if jeu == "hp6":
        return folio_hp6.releve(chemin)
    return None


def evaluer(jeu: str, spec: Sauvegardes | None, rel: str) -> set[str] | None:
    """Les identifiants des succès que porte la sauvegarde `rel`, ou None si
    elle ne se lit pas (on ne conclut alors rien, ni dans un sens ni dans
    l'autre)."""
    from src.core import progression
    definitions = du_jeu(jeu)
    ou = progression.cible(spec, rel) if definitions else None
    if ou is None:
        return None
    try:
        partie = _partie(jeu, *ou)
    except (OSError, ValueError, IndexError):
        return None
    if partie is None:
        return None
    porte = set()
    for s in definitions:
        try:
            if s.obtenu(partie):
                porte.add(s.ident)
        except (AttributeError, IndexError, TypeError, ValueError):
            log.warning("Succès %s/%s : condition illisible sur %s", jeu, s.ident, rel, exc_info=True)
    return porte


# ─── Fichier ───

def chemin_fichier() -> Path:
    """Résolu à l'appel — même garde de test que `sauvegardes.chemin_fichier`."""
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / FICHIER


def charger(chemin: Path | None = None) -> dict[tuple[str, str], dict[str, datetime | None]]:
    """{(jeu, sauvegarde): {ident: date | None}}. Un fichier illisible est mis
    de côté, jamais écrasé."""
    chemin = chemin or chemin_fichier()
    if not chemin.exists():
        return {}
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.warning("Succès illisibles (%s) — mis de côté", exc)
        try:
            os.replace(chemin, chemin.with_suffix(".corrompu"))
        except OSError:
            pass
        return {}
    stock: dict[tuple[str, str], dict[str, datetime | None]] = {}
    # Regardées sans rien porter encore : leur PREMIER succès sera daté.
    regardees = data.get("regardees") if isinstance(data, dict) else None
    for e in regardees if isinstance(regardees, list) else ():
        if isinstance(e, dict) and all(isinstance(e.get(k), str) and e.get(k) for k in ("jeu", "sauvegarde")):
            stock.setdefault((str(e["jeu"]), str(e["sauvegarde"])), {})
    lignes = data.get("obtenus") if isinstance(data, dict) else None
    for e in lignes if isinstance(lignes, list) else ():
        if not isinstance(e, dict):
            continue
        jeu, rel, ident = e.get("jeu"), e.get("sauvegarde"), e.get("succes")
        if not all(isinstance(v, str) and v for v in (jeu, rel, ident)):
            continue
        quand: datetime | None = None
        if e.get("date"):
            try:
                quand = datetime.fromisoformat(str(e["date"]))
            except ValueError:
                quand = None
        stock.setdefault((str(jeu), str(rel)), {})[str(ident)] = quand
    return stock


def remises(chemin: Path | None = None) -> dict[str, datetime]:
    """{jeu: moment où ses défis ont été remis à zéro} (`recommencer`)."""
    chemin = chemin or chemin_fichier()
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    brut = data.get("remises") if isinstance(data, dict) else None
    sortie: dict[str, datetime] = {}
    for jeu, quand in (brut.items() if isinstance(brut, dict) else ()):
        try:
            sortie[str(jeu)] = datetime.fromisoformat(str(quand))
        except ValueError:
            continue
    return sortie


def recommencer(jeu: str, quand: datetime, chemin: Path | None = None) -> None:
    """Remet les défis d'un jeu à zéro (Ludo, 2026-10-27 : « pour ceux qui
    veulent recommencer de zéro », ce que Steam ne permet pas).

    Ce qui était noté pour ce jeu est oublié, et ses sauvegardes écrites AVANT
    ce moment ne comptent plus (`obtenus`) : une partie déjà avancée redonne
    ses défis seulement quand on y rejoue.
    """
    chemin = chemin or chemin_fichier()
    stock = {cle: v for cle, v in charger(chemin).items() if cle[0] != jeu}
    toutes = remises(chemin)
    toutes[jeu] = quand
    _ecrire(stock, chemin, toutes)


def _ecrire(stock: dict[tuple[str, str], dict[str, datetime | None]], chemin: Path,
            dates_remise: dict[str, datetime] | None = None) -> None:
    """Écriture atomique (tmp + rename), même contrat que `sauvegardes.json`.
    Les remises à zéro déjà notées sont gardées."""
    if dates_remise is None:
        dates_remise = remises(chemin)
    lignes = [{"jeu": jeu, "sauvegarde": rel, "succes": ident,
               "date": quand.isoformat(timespec="seconds") if quand else None}
              for (jeu, rel), lignes_jeu in sorted(stock.items())
              for ident, quand in sorted(lignes_jeu.items())]
    regardees = [{"jeu": jeu, "sauvegarde": rel} for (jeu, rel), vus in sorted(stock.items()) if not vus]
    chemin.parent.mkdir(parents=True, exist_ok=True)
    ecrire_atomique(chemin, json.dumps(
        {"version": 1, "regardees": regardees, "obtenus": lignes,
         "remises": {jeu: q.isoformat(timespec="seconds") for jeu, q in sorted(dates_remise.items())}},
        indent=1, ensure_ascii=False))


# ─── Au retour de partie ───

def constater(jeu: str, spec: Sauvegardes | None, rel: str, fin: datetime, nee: bool,
              chemin: Path | None = None) -> list[Succes]:
    """Note ce que porte la sauvegarde qu'on vient d'écrire ; rend les succès
    NOUVEAUX de cette partie (à annoncer), dans l'ordre d'affichage.

    `nee` : la sauvegarde a été créée pendant cette partie. Sinon, une
    sauvegarde jamais regardée voit ce qu'elle porte noté sans date et rien
    n'est annoncé : on ne sait pas que c'est arrivé maintenant. Un échec
    d'écriture ne remonte jamais.
    """
    porte = evaluer(jeu, spec, rel)
    if porte is None:
        return []
    chemin = chemin or chemin_fichier()
    stock = charger(chemin)
    connus = stock.get((jeu, rel))
    datee = nee or connus is not None
    deja = connus or {}
    nouveaux = [s for s in du_jeu(jeu) if s.ident in porte and s.ident not in deja]
    if not nouveaux and connus is not None:
        return []
    ligne = stock.setdefault((jeu, rel), {})
    for s in nouveaux:
        ligne[s.ident] = fin if datee else None
    try:
        _ecrire(stock, chemin)
    except OSError as exc:
        log.warning("Succès non enregistrés : %s", exc)
    return nouveaux if datee else []


# ─── Pour l'affichage ───

def obtenus(jeu: str, sauvegardes_presentes: list[str], spec: Sauvegardes | None,
            stock: dict[tuple[str, str], dict[str, datetime | None]] | None = None) -> dict[str, Obtenu]:
    """Pour chaque succès du jeu obtenu au moins une fois : la PREMIÈRE fois.

    Ce que portent les sauvegardes présentes compte aussi, même jamais noté
    (aucune partie observée depuis l'arrivée des succès) : sans date. Une date
    connue passe avant « sans date », et la plus ancienne avant les autres.
    """
    definitions = {s.ident: s for s in du_jeu(jeu)}
    if not definitions:
        return {}
    stock = charger() if stock is None else stock
    remise = remises().get(jeu)
    vus: dict[str, Obtenu] = {}

    def garder(ident: str, rel: str, quand: datetime | None) -> None:
        s = definitions.get(ident)
        if s is None:
            return          # un succès retiré d'une version à l'autre
        avant = vus.get(ident)
        if (avant is None or (avant.date is None and quand is not None)
                or (quand is not None and avant.date is not None and quand < avant.date)):
            vus[ident] = Obtenu(s, rel, quand)

    for (j, rel), lignes in stock.items():
        if j == jeu:
            for ident, quand in lignes.items():
                garder(ident, rel, quand)
    for rel in sauvegardes_presentes:
        if remise is not None and not _ecrite_apres(spec, rel, remise):
            continue        # une partie d'avant la remise à zéro : il faut y rejouer
        for ident in evaluer(jeu, spec, rel) or ():
            garder(ident, rel, None)
    return vus


def _ecrite_apres(spec: Sauvegardes | None, rel: str, moment: datetime) -> bool:
    from src.core import progression
    ou = progression.cible(spec, rel)
    if ou is None:
        return False
    try:
        return datetime.fromtimestamp(ou[0].stat().st_mtime) > moment
    except OSError:
        return False

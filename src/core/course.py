r"""La course (1.5 « Speedrun ») : identifiant, empreinte des fichiers, journal du correctif, temps et
journal signé (atelier, `notes/SPEEDRUN_PLAN.md` § 2 à 4, `SPEEDRUN_LAUNCHER.md` § 1, 2 et 6 ; décisions
S7.1 à S7.7 de Ludo, `DECISIONS_LUDO_2026-11.md`).

**Le chrono est celui du correctif, pas du launcher.** Avec `[Accio.Game] RaceLog=1`, la DLL du jeu écrit
`accio_course.tsv` à côté de son ini : une ligne par évènement, CINQ champs séparés par une tabulation
(heure locale, microsecondes depuis l'ouverture du journal prises sur `QueryPerformanceCounter`, évènement,
carte, détail ; `source/race.h` du correctif). Le launcher le RETIRE avant de lancer, le LIT après la
fermeture, recalcule le temps sans chargements à partir des pauses (`charge_*`, `sauve_*`) et le compare à
celui de la ligne `fin` : un écart de plus d'une milliseconde dit un journal retouché.

**Ce que la signature vaut (S7.7, à dire tel quel)** : HMAC-SHA-256 du journal de course, avec une clé
dérivée d'un secret ÉCRIT DANS CE FICHIER et du code de la course. Le launcher est libre (GPL) : le secret se
lit ici, et quiconque recompile signe ce qu'il veut. La signature n'arrête qu'une retouche à la main du
fichier ; la vidéo, jugée par une personne, reste la preuve.

Pur : aucune dépendance Qt. Le calcul de l'empreinte lit des gigaoctets (archives `.big` de HP4 à HP6) : il
passe par un fil à part côté interface, et un cache par (taille, date) évite de relire ce qui n'a pas changé.
"""

import hashlib
import hmac
import json
import logging
import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, TypeGuard
from xml.sax.saxutils import escape

from src.core import signature
from src.core.ecriture_atomique import ecrire_atomique

log = logging.getLogger(__name__)

FICHIER = "accio_course.tsv"
JOURNAL = "course.json"
AVANT = "avant.json"
AVANT_RENDU = "avant.rendu.json"     # `avant.json` une fois les réglages rendus
SAUVEGARDES = "saves"
FORMAT = 1
JEUX: tuple[str, ...] = ("hp1", "hp2", "hp3", "hp4", "hp5", "hp6")
UE1: frozenset[str] = frozenset(("hp1", "hp2", "hp3"))
# Les catégories de la base de la 1.5 (Ludo, 2026-11-22) : écrites telles quelles dans la ligne ACCIO (ASCII).
# Le launcher ne vérifie pas ce que la catégorie exige (tout ramassé, aucun bug exploité) : la vidéo le montre.
ANY, CENT, SANS_BUG = "Any%", "100%", "Glitchless"
CATEGORIES: tuple[str, ...] = (ANY, CENT, SANS_BUG)
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"    # sans 0, O, 1, I : un code se recopie d'une vidéo
LONGUEUR_ID = 63                                # `race::IsRaceId` du correctif
FPS_MAX = 62.0                                  # la règle est 60 ; 2 de marge de mesure
ECART_MAX_US = 1000                             # entre la ligne `fin` et le recalcul
_OCTETS_MAX = 4_000_000                         # une course de 10 h : ~3 600 lignes `etat`, ~250 Ko
_BLOC = 1 << 20
# Le secret de la signature, LISIBLE PAR TOUS (en-tête du module) : il ne protège que d'une retouche à la main.
_SECRET = b"accio-course-1.5:protego-totalum:la-video-fait-foi"

# Les refus d'un temps, par code ; leur phrase est dans l'interface (`ui/course_resultat`).
SANS_SEANCE = "sans_seance"
RELANCE = "relance"
AUTRE_ID = "autre_id"
SANS_DEPART = "sans_depart"
DEPART_CHARGE = "depart_charge"
DEPART_CLIC = "depart_clic"
DEPART_INCONNU = "depart_inconnu"
SANS_FIN = "sans_fin"
RETOUCHE = "retouche"
TROP_D_IMAGES = "trop_d_images"
MODE_NON_TENU = "mode_non_tenu"
INTERDITS = "interdits"         # la DLL a dit une valeur interdite en course (ligne `reglages`)
SOUS_WINE = "sous_wine"


# ── L'identifiant ──

def tirer_code() -> str:
    """8 caractères tirés au hasard (`secrets`), lus `7KQ2-M4XP` ; le code nomme aussi le dossier de la course."""
    brut = "".join(secrets.choice(ALPHABET) for _ in range(8))
    return f"{brut[:4]}-{brut[4:]}"


def code_valide(code: str) -> bool:
    """La forme d'un code tiré : un nom de dossier sûr, rien d'autre."""
    return (len(code) == 9 and code[4] == "-"
            and all(c in ALPHABET for c in code[:4] + code[5:]))


def ligne_id(code: str, jour: date, courte: str, game_id: str, categorie: str) -> str:
    """`ACCIO 7KQ2-M4XP 2026-11-18 a3f9c1d2 HP2 Any%` : la ligne que le correctif dessine toute la course.
    ValueError pour une catégorie inconnue, au-delà de 63 caractères ou hors de l'ASCII imprimable (le
    correctif la refuserait en entier)."""
    if categorie not in CATEGORIES:
        raise ValueError(f"catégorie de course inconnue : {categorie!r}")
    texte = f"ACCIO {code} {jour.isoformat()} {courte} {game_id.upper()} {categorie}"
    if len(texte) > LONGUEUR_ID or not all(0x20 <= ord(c) <= 0x7E for c in texte):
        raise ValueError(f"identifiant de course refusé : {texte!r}")
    return texte


# ── L'empreinte des fichiers qui décident du jeu ──

@dataclass(frozen=True)
class Fichier:
    chemin: str     # relatif au dossier du jeu, en minuscules, séparé par « / »
    taille: int
    sha256: str


@dataclass(frozen=True)
class Empreinte:
    complete: str
    courte: str
    fichiers: tuple[Fichier, ...]


def _suffixes(game_id: str) -> frozenset[str]:
    if game_id in UE1:
        return frozenset((".exe", ".dll", ".u", ".int"))
    return frozenset((".exe", ".dll", ".big"))


def fichiers_du_jeu(game_id: str, dossier_jeu: Path, dossier_exe: Path) -> list[Path]:
    """Ceux qui doivent être les mêmes chez tous les coureurs, triés.

    HP1 à HP3 : l'exe et les DLL du dossier de l'exe (moteur ET correctif), les paquets de scripts `.u`,
    les textes `.int`, et les cartes `Maps/*.unr`. HP4 à HP6 : l'exe, les DLL (correctif compris) et les
    archives `.big` du dossier du jeu. JAMAIS l'ini du correctif, `User.ini` ni le fichier des réglages
    graphiques de HP3 : ils changent avec les réglages visuels permis (S7.6) ; l'ini part en clair dans
    le journal signé. Un paquet de la 1.4 ou un pack HD change l'empreinte : c'est voulu.
    """
    voulus = _suffixes(game_id)
    trouves = [p for p in _fichiers(dossier_exe) if p.suffix.lower() in voulus]
    if game_id in UE1:
        for sous in _sous_dossiers(dossier_jeu):
            if sous.name.lower() == "maps":
                trouves += [p for p in _fichiers(sous) if p.suffix.lower() == ".unr"]
    return sorted(set(trouves), key=lambda p: _relatif(p, dossier_jeu))


def _fichiers(dossier: Path) -> list[Path]:
    try:
        return [p for p in dossier.iterdir() if p.is_file()]
    except OSError:
        return []


def _sous_dossiers(dossier: Path) -> list[Path]:
    try:
        return [p for p in dossier.iterdir() if p.is_dir()]
    except OSError:
        return []


def _relatif(chemin: Path, dossier_jeu: Path) -> str:
    return chemin.relative_to(dossier_jeu).as_posix().lower()


type Cache = dict[str, list[Any]]


def lire_cache(chemin: Path) -> Cache:
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(brut, dict):
        return {}
    return {k: v for k, v in brut.items()
            if isinstance(k, str) and isinstance(v, list) and len(v) == 3
            and isinstance(v[0], int) and isinstance(v[1], int) and isinstance(v[2], str)}


def _sha256(chemin: Path, avance: Callable[[int], None]) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        while bloc := f.read(_BLOC):
            h.update(bloc)
            avance(len(bloc))
    return h.hexdigest()


def empreinte(game_id: str, dossier_jeu: Path, dossier_exe: Path, cache: Cache | None = None,
              progression: Callable[[int, int], None] | None = None,
              annule: Callable[[], bool] | None = None) -> Empreinte | None:
    """SHA-256 de la liste triée « chemin, taille, SHA-256 » ; `courte` = ses 8 premiers chiffres.

    `cache` (lu par `lire_cache`, rendu complété) garde le SHA-256 d'un fichier par (taille, date en ns),
    seulement quand la date est fiable (`signature.fiable`). None : aucun fichier, ou `annule()` vrai.
    """
    chemins = fichiers_du_jeu(game_id, dossier_jeu, dossier_exe)
    if not chemins:
        return None
    etats = [p.stat() for p in chemins]
    total = sum(e.st_size for e in etats)
    fait = 0

    def avance(n: int) -> None:
        nonlocal fait
        fait += n
        if progression is not None:
            progression(fait, total)

    liste: list[Fichier] = []
    for chemin, etat in zip(chemins, etats, strict=True):
        if annule is not None and annule():
            return None
        cle = str(chemin).lower()
        fiable = signature.fiable(etat)
        garde = cache.get(cle) if cache is not None else None
        if garde is not None and fiable is not None and garde[0] == etat.st_size and garde[1] == etat.st_mtime_ns:
            somme = str(garde[2])
            avance(etat.st_size)
        else:
            somme = _sha256(chemin, avance)
            if cache is not None and fiable is not None:
                cache[cle] = [etat.st_size, etat.st_mtime_ns, somme]
        liste.append(Fichier(_relatif(chemin, dossier_jeu), etat.st_size, somme))
    complete = hashlib.sha256(
        "".join(f"{f.chemin}\t{f.taille}\t{f.sha256}\n" for f in liste).encode("utf-8")).hexdigest()
    return Empreinte(complete, complete[:8], tuple(liste))


# ── Le journal du correctif ──

@dataclass(frozen=True)
class Ligne:
    heure: str
    us: int
    evenement: str
    carte: str
    detail: str
    brute: str = ""         # la ligne telle qu'écrite, sans sa fin : le sceau se calcule sur ses octets


@dataclass(frozen=True)
class Segment:
    """Un morceau de la course : d'une carte (ou d'un chapitre) à la suivante, en temps sans chargements."""
    carte: str
    net_us: int
    depuis_sauvegarde: bool = False      # la carte vient d'une partie rechargée (mourir et recharger est permis)


@dataclass(frozen=True)
class Resultat:
    seances: int = 0
    jeu_dll: str = ""                    # « HP5 » : ce que la ligne `seance` nomme
    version_fix: str = ""
    race_id: str = ""
    depart: str | None = None            # le détail de la ligne `depart` ; None : pas de départ
    fin: bool = False
    total_us: int = 0                    # ceux de la ligne `fin`
    pauses_us: int = 0
    net_us: int = 0
    total_calcule_us: int = 0            # recalculés depuis les pauses ; sans `fin`, jusqu'à la dernière ligne
    pauses_calcule_us: int = 0
    net_calcule_us: int = 0
    chargements: int = 0                 # pauses pendant la course
    rechargements: int = 0               # cartes venues d'une sauvegarde après le départ
    segments: tuple[Segment, ...] = ()
    fps_max: float | None = None
    fps_moyen: float | None = None
    # `reglages` (§ 8 quater du plan) : les valeurs que la DLL APPLIQUE (les dernières dites), et les clés
    # qu'elle dit interdites en course, toutes celles dites pendant la séance (HP4 à HP6 les redisent).
    reglages: tuple[tuple[str, str], ...] = ()
    interdits: tuple[str, ...] = ()
    # Les sceaux des lignes `etat` et `fin` : combien, et s'ils tiennent tous (None : aucun à vérifier).
    sceaux: int = 0
    sceaux_intacts: bool | None = None
    lignes: tuple[Ligne, ...] = field(default=(), repr=False)

    @property
    def net(self) -> int:
        """Le temps d'Accio (S7.4) : celui de la ligne `fin`, sinon le recalcul."""
        return self.net_us if self.fin else self.net_calcule_us


def _entier(texte: str) -> int | None:
    texte = texte.strip()
    signe = texte[1:] if texte[:1] == "-" else texte
    return int(texte) if signe.isascii() and signe.isdigit() else None


def _champs(detail: str) -> dict[str, str]:
    """`total=1;pauses=2;net=3` → {"total": "1", …} ; une partie sans « = » est gardée sous son nom."""
    sortie: dict[str, str] = {}
    for morceau in detail.split(";"):
        nom, _, valeur = morceau.partition("=")
        if nom.strip():
            sortie[nom.strip()] = valeur.strip()
    return sortie


def lignes(texte: str) -> list[Ligne]:
    """Les lignes de la forme écrite par la DLL ; les autres (fichier coupé en cours d'écriture) sont sautées.
    Rien n'est rogné : le sceau porte sur les octets tels qu'écrits (la DLL finit chaque ligne par « \\n »)."""
    sortie = []
    for brute in texte.split("\n"):
        champs = brute.split("\t")
        if len(champs) != 5:
            continue
        us = _entier(champs[1])
        if us is None or not champs[2]:
            continue
        sortie.append(Ligne(champs[0], us, champs[2], champs[3], champs[4], brute))
    return sortie


_FNV_DEPART, _FNV_FACTEUR, _64 = 14695981039346656037, 1099511628211, (1 << 64) - 1


def fnv1a64(octets: bytes, h: int = _FNV_DEPART) -> int:
    """FNV-1a 64 bits, celui du sceau du correctif (`race.h`)."""
    for b in octets:
        h = ((h ^ b) * _FNV_FACTEUR) & _64
    return h


def _sceaux(suite: list[Ligne]) -> tuple[int, bool | None]:
    """Chaque ligne `etat` et `fin` finit par `;sceau=<16 hex>` : FNV-1a de TOUS les octets de la séance
    avant elle, fins de ligne comprises. Une ligne qui devrait en porter un et n'en porte pas : retouchée."""
    h, vus, intacts = _FNV_DEPART, 0, True
    for ligne in suite:
        if ligne.evenement in ("etat", "fin"):
            vus += 1
            sceau = _champs(ligne.detail).get("sceau", "")
            try:
                intacts = intacts and len(sceau) == 16 and int(sceau, 16) == h
            except ValueError:
                intacts = False
        h = fnv1a64((ligne.brute + "\n").encode("utf-8"), h)
    return vus, (intacts if vus else None)


def _reglages(suite: list[Ligne]) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    valeurs: dict[str, str] = {}
    interdits: list[str] = []
    for ligne in suite:
        if ligne.evenement != "reglages":
            continue
        for cle, valeur in _champs(ligne.detail).items():
            if cle == "interdits":
                interdits += [c.strip() for c in valeur.split(",") if c.strip() and c.strip() not in interdits]
            else:
                valeurs[cle] = valeur
    return tuple(valeurs.items()), tuple(interdits)


def _pauses(suite: list[Ligne]) -> list[tuple[int, int | None]]:
    """Les pauses du chrono, comme `race::Run::Pause` : l'union des chargements et des sauvegardes, de la
    première ouverture à la dernière fermeture ; une pause encore ouverte à la fin se ferme à None."""
    chargement = sauvegarde = False
    ouverte: int | None = None
    sortie: list[tuple[int, int | None]] = []
    for ligne in suite:
        avant = chargement or sauvegarde
        if ligne.evenement == "charge_debut":
            chargement = True
        elif ligne.evenement == "charge_fin":
            chargement = False
        elif ligne.evenement == "sauve_debut":
            sauvegarde = True
        elif ligne.evenement == "sauve_fin":
            sauvegarde = False
        else:
            continue
        apres = chargement or sauvegarde
        if not avant and apres:
            ouverte = ligne.us
        elif avant and not apres and ouverte is not None:
            sortie.append((ouverte, ligne.us))
            ouverte = None
    if ouverte is not None:
        sortie.append((ouverte, None))
    return sortie


def _en_pause(pauses: list[tuple[int, int | None]], de: int, a: int) -> int:
    """Ce que les pauses prennent de [de, a]."""
    total = 0
    for debut, fin in pauses:
        bas, haut = max(debut, de), min(a if fin is None else fin, a)
        total += max(0, haut - bas)
    return total


def analyser(texte: str) -> Resultat:
    """Le résultat de la DERNIÈRE séance du journal (le correctif allonge le fichier d'une séance à l'autre ;
    le launcher le retire avant de lancer : plus d'une séance, c'est un jeu relancé pendant la course)."""
    toutes = lignes(texte)
    seances = [i for i, ligne in enumerate(toutes) if ligne.evenement == "seance"]
    if not seances:
        return Resultat(lignes=tuple(toutes))
    suite = toutes[seances[-1]:]
    entete = suite[0].detail.split(";")
    infos = _champs(suite[0].detail)
    departs = [ligne for ligne in suite if ligne.evenement == "depart"]
    fins = [ligne for ligne in suite if ligne.evenement == "fin"]
    reglages, interdits = _reglages(suite)
    sceaux, intacts = _sceaux(suite)
    base = Resultat(seances=len(seances), jeu_dll=entete[0] if entete else "",
                    version_fix=infos.get("fix", ""), race_id=infos.get("RaceId", ""), reglages=reglages,
                    interdits=interdits, sceaux=sceaux, sceaux_intacts=intacts, lignes=tuple(suite))
    if not departs:
        return base
    depart = departs[0]
    fin = fins[0] if fins else None
    bout = fin.us if fin is not None else max(ligne.us for ligne in suite)
    pauses = _pauses(suite)
    en_pause = _en_pause(pauses, depart.us, bout)
    chiffres = _champs(fin.detail) if fin is not None else {}
    images = [float(v) for ligne in suite if ligne.evenement == "etat"
              and (v := _champs(ligne.detail).get("fps", "")) and _flottant(v)]
    cartes = [ligne for ligne in suite if ligne.evenement == "carte" and depart.us <= ligne.us <= bout]
    return Resultat(
        seances=base.seances, jeu_dll=base.jeu_dll, version_fix=base.version_fix, race_id=base.race_id,
        depart=depart.detail, fin=fin is not None,
        total_us=_entier(chiffres.get("total", "")) or 0, pauses_us=_entier(chiffres.get("pauses", "")) or 0,
        net_us=_entier(chiffres.get("net", "")) or 0,
        total_calcule_us=bout - depart.us, pauses_calcule_us=en_pause, net_calcule_us=bout - depart.us - en_pause,
        chargements=sum(1 for d, f in pauses if (f is None or f > depart.us) and d < bout),
        rechargements=sum(1 for c in cartes if c.detail == "sauvegarde"),
        segments=_segments(depart, cartes, bout, pauses),
        fps_max=max(images) if images else None, fps_moyen=sum(images) / len(images) if images else None,
        reglages=reglages, interdits=interdits, sceaux=sceaux, sceaux_intacts=intacts, lignes=tuple(suite))


def _flottant(texte: str) -> bool:
    try:
        float(texte)
    except ValueError:
        return False
    return True


def _segments(depart: Ligne, cartes: list[Ligne], bout: int,
              pauses: list[tuple[int, int | None]]) -> tuple[Segment, ...]:
    """Le découpage par carte : un morceau commence au départ, puis à chaque carte d'un AUTRE nom (ou
    rechargée) ; il finit au morceau suivant, ou à la fin. Le temps de chaque morceau est sans chargements."""
    reperes: list[tuple[int, str, bool]] = [(depart.us, depart.carte, False)]
    for c in cartes:
        rechargee = c.detail == "sauvegarde"
        if not reperes[-1][1]:                       # le départ ne nommait pas sa carte (HP4 à HP6)
            reperes[-1] = (reperes[-1][0], c.carte, rechargee)
        elif c.carte != reperes[-1][1] or rechargee:
            reperes.append((c.us, c.carte, rechargee))
    sortie = []
    for i, (debut, carte, rechargee) in enumerate(reperes):
        fin = reperes[i + 1][0] if i + 1 < len(reperes) else bout
        sortie.append(Segment(carte, fin - debut - _en_pause(pauses, debut, fin), rechargee))
    return tuple(sortie)


def lire(dossier_exe: Path) -> str:
    """Le texte du journal du jeu installé dans ce dossier ; vide s'il est absent ou illisible."""
    try:
        with (dossier_exe / FICHIER).open("rb") as f:
            brut = f.read(_OCTETS_MAX)
    except OSError:
        return ""
    return brut.decode("utf-8", errors="replace")


def retirer(dossier_exe: Path) -> bool:
    """Retire le journal d'une course passée AVANT d'en lancer une (le correctif l'allongerait) ; il a déjà été
    recopié dans le dossier de sa course. False s'il est resté (fichier tenu)."""
    try:
        (dossier_exe / FICHIER).unlink(missing_ok=True)
    except OSError:
        log.warning("Course : %s non retiré dans %s", FICHIER, dossier_exe, exc_info=True)
        return False
    return True


# ── Le verdict ──

@dataclass(frozen=True)
class Attendu:
    race_id: str
    mode_tenu: bool
    sous_wine: bool = False


def verdict(resultat: Resultat, attendu: Attendu) -> tuple[str, ...]:
    """Les raisons de refuser le temps ; aucune = temps valable (la vidéo reste à juger)."""
    refus: list[str] = []
    if resultat.seances == 0:
        return (SANS_SEANCE,)
    if resultat.seances > 1:
        refus.append(RELANCE)
    if resultat.race_id != attendu.race_id:
        refus.append(AUTRE_ID)
    if resultat.depart is None:
        refus.append(SANS_DEPART)
    elif resultat.depart == "sauvegarde":
        refus.append(DEPART_CHARGE)
    elif resultat.depart.startswith("nouvelle") and "clic=non" in resultat.depart:
        refus.append(DEPART_CLIC)
    elif resultat.depart != "nouvelle":
        refus.append(DEPART_INCONNU)
    if resultat.depart is not None and not resultat.fin:
        refus.append(SANS_FIN)
    if resultat.sceaux_intacts is False or (resultat.fin and (
            abs(resultat.net_us - resultat.net_calcule_us) > ECART_MAX_US
            or abs(resultat.total_us - resultat.total_calcule_us) > ECART_MAX_US)):
        refus.append(RETOUCHE)
    if resultat.interdits:
        refus.append(INTERDITS)
    if resultat.fps_max is not None and resultat.fps_max > FPS_MAX:
        refus.append(TROP_D_IMAGES)
    if not attendu.mode_tenu:
        refus.append(MODE_NON_TENU)
    if attendu.sous_wine:
        refus.append(SOUS_WINE)
    return tuple(refus)


# ── Le dossier et le journal signé ──

def racine() -> Path:
    """`_Launcher/courses/` (suit `CONFIG_FILE_PATH`, que les tests redirigent)."""
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / "courses"


def dossier(code: str) -> Path:
    if not code_valide(code):
        raise ValueError(f"code de course invalide : {code!r}")
    return racine() / code


def creer_dossier(code: str) -> Path:
    """Le dossier NEUF de la course, avec `saves/` vide (HP4 à HP6 : `RaceSaves`). FileExistsError si le code
    a déjà servi : un dossier de course n'est jamais réutilisé, et ne s'efface qu'à la demande du joueur
    (Carnet, `mode_course.supprimer`)."""
    ou = dossier(code)
    ou.parent.mkdir(parents=True, exist_ok=True)
    ou.mkdir()
    (ou / SAUVEGARDES).mkdir()
    return ou


def _canonique(contenu: Mapping[str, object]) -> bytes:
    sans = {k: v for k, v in contenu.items() if k != "signature"}
    return json.dumps(sans, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _cle(code: str) -> bytes:
    return hmac.new(_SECRET, code.encode("ascii"), hashlib.sha256).digest()


def signer(contenu: Mapping[str, object]) -> str:
    code = contenu.get("code")
    if not isinstance(code, str) or not code_valide(code):
        raise ValueError("journal de course sans code valide")
    return hmac.new(_cle(code), _canonique(contenu), hashlib.sha256).hexdigest()


def resultat_en_dict(resultat: Resultat) -> dict[str, object]:
    sortie = asdict(resultat)
    sortie.pop("lignes")
    sortie["reglages"] = dict(resultat.reglages)
    sortie["interdits"] = list(resultat.interdits)
    sortie["segments"] = [[s.carte, s.net_us, s.depuis_sauvegarde] for s in resultat.segments]
    return sortie


def contenu(*, game_id: str, categorie: str, code: str, jour: date, ligne: str, empreinte_jeu: Empreinte,
            launcher: str, ini: str, ecarts: Iterable[tuple[str, str, str, str]], resultat: Resultat,
            refus: Iterable[str], plateforme: str, difficulte: str) -> dict[str, object]:
    """Ce que garde `course.json` ; `signature` à part (`ecrire_journal`)."""
    restes = [list(e) for e in ecarts]
    return {
        "format": FORMAT, "jeu": game_id, "categorie": categorie, "code": code, "date": jour.isoformat(),
        "ligne_id": ligne, "launcher": launcher, "correctif": resultat.version_fix, "plateforme": plateforme,
        "empreinte": {"complete": empreinte_jeu.complete, "courte": empreinte_jeu.courte,
                      "fichiers": [[f.chemin, f.taille, f.sha256] for f in empreinte_jeu.fichiers]},
        "ini": ini, "difficulte": difficulte,
        "mode_course": {"tenu": not restes, "ecarts": restes},
        # Les lignes BRUTES de la séance : le vérificateur y recalcule temps, verdict et sceaux.
        "journal": [li.brute for li in resultat.lignes],
        "resultat": resultat_en_dict(resultat), "refus": list(refus),
    }


def ecrire_journal(code: str, donnees: Mapping[str, object]) -> Path:
    """`_Launcher/courses/<code>/course.json`, signé, écrit d'un coup. OSError s'il ne s'écrit pas."""
    signe = dict(donnees)
    signe["signature"] = signer(signe)
    chemin = dossier(code) / JOURNAL
    ecrire_atomique(chemin, json.dumps(signe, ensure_ascii=False, indent=1, sort_keys=True))
    return chemin


def _est_dict(valeur: object) -> TypeGuard[dict[str, Any]]:
    return isinstance(valeur, dict) and all(isinstance(k, str) for k in valeur)


def lire_journal(chemin: Path) -> dict[str, Any] | None:
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return brut if _est_dict(brut) else None


@dataclass(frozen=True)
class Verification:
    lisible: bool
    signature: bool = False
    # Le verdict refait depuis les lignes brutes, et s'il dit la même chose que le fichier.
    refus: tuple[str, ...] = ()
    concorde: bool = False
    net_us: int = 0


def _texte_du_journal(donnees: Mapping[str, Any]) -> str:
    brut = donnees.get("journal")
    if not isinstance(brut, list):
        return ""
    return "".join(ligne + "\n" for ligne in brut if isinstance(ligne, str))


def verifier_journal(chemin: Path) -> Verification:
    """Signature, puis le verdict recalculé depuis les lignes brutes (`--verifier-course`)."""
    return verifier(lire_journal(chemin))


def verifier(donnees: Mapping[str, Any] | None) -> Verification:
    """Comme `verifier_journal`, sur un journal déjà lu."""
    if donnees is None or not isinstance(donnees.get("signature"), str):
        return Verification(lisible=False)
    try:
        attendue = signer(donnees)
    except ValueError:
        return Verification(lisible=False)
    signe = hmac.compare_digest(attendue, str(donnees["signature"]))
    resultat = analyser(_texte_du_journal(donnees))
    mode = donnees.get("mode_course")
    tenu = bool(mode.get("tenu")) if _est_dict(mode) else False
    refus = verdict(resultat, Attendu(str(donnees.get("ligne_id", "")), tenu,
                                      sous_wine=donnees.get("plateforme") != "win32"))
    garde = donnees.get("refus")
    concorde = isinstance(garde, list) and tuple(str(r) for r in garde) == refus
    return Verification(True, signe, refus, concorde, resultat.net)


@dataclass(frozen=True)
class Passee:
    """Une course gardée, telle que le Carnet la montre (lue dans son `course.json`)."""
    code: str
    jeu: str
    jour: str
    net_us: int
    fin: bool
    refus: tuple[str, ...]
    ecrite_ns: int                # date d'écriture du journal : l'ordre de deux courses du même jour
    categorie: str = ANY
    segments: tuple[Segment, ...] = ()

    @property
    def valable(self) -> bool:
        return self.fin and not self.refus


def _passee(chemin: Path) -> Passee | None:
    d = lire_journal(chemin)
    if d is None:
        return None
    r = d.get("resultat")
    refus = d.get("refus")
    if not _est_dict(r) or not isinstance(refus, list):
        return None
    fin = r.get("fin") is True
    net = r.get("net_us" if fin else "net_calcule_us")
    try:
        ecrite = chemin.stat().st_mtime_ns
    except OSError:
        return None
    return Passee(chemin.parent.name, str(d.get("jeu", "")), str(d.get("date", "")),
                  net if isinstance(net, int) else 0, fin, tuple(str(x) for x in refus), ecrite,
                  str(d.get("categorie", ANY)), _segments_lus(r.get("segments")))


def _segments_lus(brut: object) -> tuple[Segment, ...]:
    """Les `[carte, net_us, rechargée]` de `resultat_en_dict` ; une entrée mal formée est sautée."""
    if not isinstance(brut, list):
        return ()
    return tuple(Segment(s[0], s[1], s[2]) for s in brut
                 if isinstance(s, list) and len(s) == 3 and isinstance(s[0], str)
                 and isinstance(s[1], int) and not isinstance(s[1], bool) and isinstance(s[2], bool))


def passees(game_id: str | None = None) -> list[Passee]:
    """Les courses gardées d'un jeu (de tous : None), de la plus récente à la plus ancienne (lecture seule)."""
    try:
        dossiers = [p for p in racine().iterdir() if p.is_dir() and code_valide(p.name)]
    except OSError:
        return []
    lues = [c for p in dossiers if (c := _passee(p / JOURNAL)) is not None and game_id in (None, c.jeu)]
    return sorted(lues, key=lambda c: (c.jour, c.ecrite_ns), reverse=True)


def meilleure(courses_du_jeu: Iterable[Passee], categorie: str | None = None) -> Passee | None:
    """Le meilleur temps VALABLE (finie, sans refus) de la catégorie (de toutes : None) ; à égalité, la plus
    ancienne l'a eu d'abord."""
    valables = [c for c in courses_du_jeu if c.valable and categorie in (None, c.categorie)]
    return min(valables, key=lambda c: (c.net_us, c.jour, c.ecrite_ns)) if valables else None


@dataclass(frozen=True)
class Passage:
    """Le meilleur passage sur une carte : son temps sans chargements, la course qui l'a fait."""
    carte: str
    net_us: int
    code: str
    jour: str


def par_carte(courses_du_jeu: Iterable[Passee], categorie: str) -> tuple[Passage, ...]:
    """Le classement par niveau de la base de la 1.5 : pour chaque carte, le passage le plus court des courses
    VALABLES de la catégorie. Un passage venu d'une partie rechargée ne compte pas (il ne part pas de
    l'entrée de la carte), ni une carte sans nom. Dans l'ordre de la meilleure course, puis des autres ;
    à égalité, la plus ancienne course garde le passage."""
    valables = sorted((c for c in courses_du_jeu if c.valable and c.categorie == categorie),
                      key=lambda c: (c.jour, c.ecrite_ns))
    record = meilleure(valables)
    ordre: dict[str, None] = {}
    for c in ([record] if record is not None else []) + valables:
        ordre.update((s.carte, None) for s in c.segments if s.carte and not s.depuis_sauvegarde)
    meilleurs: dict[str, Passage] = {}
    for c in valables:
        for s in c.segments:
            if s.carte and not s.depuis_sauvegarde and (
                    s.carte not in meilleurs or s.net_us < meilleurs[s.carte].net_us):
                meilleurs[s.carte] = Passage(s.carte, s.net_us, c.code, c.jour)
    return tuple(meilleurs[carte] for carte in ordre)


def _temps_lss(us: int) -> str:
    """`01:02:03.4560000` : le temps tel que LiveSplit l'écrit (heures, minutes, secondes, sept décimales)."""
    us = max(0, us)
    h, reste = divmod(us, 3_600_000_000)
    m, reste = divmod(reste, 60_000_000)
    s, us = divmod(reste, 1_000_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{us:06d}0"


def livesplit(nom_jeu: str, categorie: str, courses_du_jeu: Iterable[Passee]) -> str | None:
    """Le fichier LiveSplit (.lss) de la catégorie : un segment par carte du meilleur temps valable, en temps de
    jeu (sans chargements, celui que LiveSplit compare quand il retire les chargements), son meilleur temps
    comme record ; le meilleur segment est pris parmi les courses valables qui ont suivi le MÊME parcours (les
    mêmes cartes dans le même ordre), sinon c'est celui du record. None sans temps valable ou sans segment."""
    de_la_categorie = [c for c in courses_du_jeu if c.categorie == categorie]
    valables = [c for c in de_la_categorie if c.valable]
    record = meilleure(valables)
    if record is None or not record.segments:
        return None
    parcours = [s.carte for s in record.segments]
    memes = [c for c in valables if [s.carte for s in c.segments] == parcours]
    segments = []
    cumul = 0
    for i, s in enumerate(record.segments):
        cumul += s.net_us
        meilleur = min(c.segments[i].net_us for c in memes)
        nom = s.carte or "?"
        segments.append(
            "    <Segment>\n"
            f"      <Name>{escape(nom + (' (rechargée)' if s.depuis_sauvegarde else ''))}</Name>\n"
            "      <Icon />\n"
            "      <SplitTimes>\n"
            "        <SplitTime name=\"Personal Best\">\n"
            f"          <GameTime>{_temps_lss(cumul)}</GameTime>\n"
            "        </SplitTime>\n"
            "      </SplitTimes>\n"
            f"      <BestSegmentTime>\n        <GameTime>{_temps_lss(meilleur)}</GameTime>\n      </BestSegmentTime>\n"
            "      <SegmentHistory />\n"
            "    </Segment>\n")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Run version="1.7.0">\n'
        "  <GameIcon />\n"
        f"  <GameName>{escape(nom_jeu)}</GameName>\n"
        f"  <CategoryName>{escape(categorie)}</CategoryName>\n"
        "  <LayoutPath />\n"
        "  <Metadata>\n    <Run id=\"\" />\n    <Platform usesEmulator=\"False\">PC</Platform>\n"
        "    <Region />\n    <Variables />\n  </Metadata>\n"
        "  <Offset>00:00:00</Offset>\n"
        f"  <AttemptCount>{len(de_la_categorie)}</AttemptCount>\n"
        "  <AttemptHistory />\n"
        "  <Segments>\n" + "".join(segments) + "  </Segments>\n"
        "  <AutoSplitterSettings />\n"
        "</Run>\n")


def format_temps(us: int) -> str:
    """`1:02:03.456` (heures seulement s'il y en a), au millième ; un temps négatif s'écrit 0."""
    ms = max(0, us) // 1000
    h, reste = divmod(ms, 3_600_000)
    m, reste = divmod(reste, 60_000)
    s, ms = divmod(reste, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms:03d}" if h else f"{m}:{s:02d}.{ms:03d}"


ARGUMENT_VERIFIER = "--verifier-course"


def demande_de_verification(argv: list[str]) -> Path | None:
    """`AccioLauncher --verifier-course <course.json>` : le fichier à vérifier, None sinon."""
    if ARGUMENT_VERIFIER not in argv:
        return None
    i = argv.index(ARGUMENT_VERIFIER)
    return Path(argv[i + 1]) if i + 1 < len(argv) else Path()


def rapport_verification(chemin: Path) -> tuple[str, int]:
    """Le rapport du vérificateur (texte, code de sortie : 0 temps valable et fichier intact, 1 sinon).

    Il ne remplace pas la vidéo (S7.7) : il dit si le fichier est celui qu'un launcher a signé, et si le
    temps recalculé depuis les lignes brutes est valable. L'empreinte se compare à la main avec celle du
    vérificateur pour la même archive du catalogue (ligne « Empreinte »)."""
    donnees = lire_journal(chemin)
    v = verifier(donnees)
    if donnees is None or not v.lisible:
        return f"{chemin} : journal de course illisible ou sans signature.", 1
    emp = donnees.get("empreinte")
    lignes_rapport = [
        f"Course {donnees.get('code', '?')} : {str(donnees.get('jeu', '?')).upper()} {donnees.get('categorie', '?')}, "
        f"{donnees.get('date', '?')}",
        f"Identifiant à l'écran : {donnees.get('ligne_id', '?')}",
        f"Signature : {'intacte' if v.signature else 'FAUSSE (fichier retouché, ou signé par un autre launcher)'}",
        f"Temps sans chargements recalculé : {format_temps(v.net_us)}",
        f"Verdict recalculé : {'temps valable' if not v.refus else ', '.join(v.refus)}"
        + ("" if v.concorde else " (DIFFÈRE de celui du fichier)"),
        f"Empreinte : {emp.get('complete', '?') if _est_dict(emp) else '?'}",
        f"Launcher {donnees.get('launcher', '?')}, correctif {donnees.get('correctif', '?')}, "
        f"{donnees.get('plateforme', '?')}",
        "La vidéo reste la preuve : le code à l'écran doit être celui du fichier, du départ à la fin.",
    ]
    return "\n".join(lignes_rapport), 0 if v.signature and v.concorde and not v.refus else 1

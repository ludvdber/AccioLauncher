"""Dire POURQUOI un jeu vient de s'arrêter, à partir de ce que Windows a noté.

Idée validée par Ludo le 2026-10-03, pour HP4-HP8 (HP1-HP3 ont déjà leur
propre journal, lu par `config_cassee`). Un jeu qui plante ne dit rien : la
fenêtre disparaît, et le joueur ne sait pas s'il doit réinstaller, mettre à
jour son pilote ou fermer Discord. Windows, lui, a tout noté. Deux sources,
toutes deux lisibles SANS élévation (vérifié sur le poste de Ludo) :

**① L'événement 1000 « Application Error » du journal Application.** Il nomme
le fichier où le plantage a eu lieu (`ModuleName`, `ModulePath`), le code
d'exception et le processus. Relevé réel : 30 plantages `c0000409` de
`hp8.exe` et 6 `c0000005` dans `d3d9.dll` 1.2.0.0 (le wrapper du correctif,
époque `fps.dll`).

**On ne retient un événement que s'il est CELUI de notre processus** : même
`ProcessId` que le `Popen`, même code d'exception que son code de sortie (un
processus tué par une exception non gérée sort AVEC ce code). C'est ce qui
écarte le bruit relevé le 2026-09-17 : chaque lancement de `hp8.exe` laisse
un `c0000409` 2 s après le départ, dans un AUTRE processus, alors que la
partie continue et sort en 0 (journal du launcher, 2026-10-01 19:18:17).

**② Les détections de Microsoft Defender (événement 1117).** Elles nomment le
fichier mis en quarantaine. Relevé réel : `HP8\\pc\\paul.dll` le 2026-08-30 à
l'installation. Le jeu démarre alors sur « lecteur CD introuvable », et rien
ne relie ce message à l'antivirus. **Temporaire** (Ludo) : disparaîtra avec
l'import des jeux du joueur, qui n'auront plus de fichier de ce genre. Un
antivirus tiers n'écrit pas ce journal : on n'en dit rien plutôt que d'en
supposer (règle 108).

Lecture seule, Windows seulement (Wine n'a pas ces journaux), ne lève jamais.
`wevtutil` coûte ~105 ms : l'appelant le fait hors du fil de l'interface.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
# B405/B314 relus le 2026-10-07 (règle 2) : le XML lu ici est la SORTIE de
# `wevtutil.exe` (chemin absolu), jamais un fichier venu d'ailleurs. Les
# attaques visées (entités en cascade, entités externes) exigent une DTD dans
# le document ; wevtutil n'en écrit pas et échappe le texte des événements, et
# expat ne résout plus les entités externes depuis Python 3.7.1. `defusedxml`
# ajouterait une dépendance à l'exécutable pour un risque absent.
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

from src.core.i18n import tr
from src.core.win_utils import commande_systeme

log = logging.getLogger(__name__)

# Résolu à l'import, sous garde (règle 6).
_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
_DELAI_S = 10
# Le plantage est noté AVANT que le processus ne meure ; la marge couvre
# l'écart d'horloge entre le relevé du lancement et l'horodatage de Windows.
_MARGE = timedelta(seconds=5)
# Les détections plus anciennes n'intéressent plus : 200 couvrent des mois.
_DETECTIONS = 200

# Un code de sortie à partir de 0xC0000000 est un statut d'ERREUR NT : le
# processus a été tué par une exception. En dessous, le jeu a choisi de sortir
# (HP6 sort en 1 à chaque fermeture normale, relevé le 2026-10-01).
_ERREUR_NT = 0xC0000000
DLL_INTROUVABLE = 0xC0000135
DLL_INVALIDE = 0xC000007B
DLL_INIT = 0xC0000142

# Les pilotes graphiques, par le début de leur nom de module (NVIDIA, AMD, Intel).
_PILOTES = re.compile(r"^(nvd3dum|nvwgf2um|nvoglv|nvldumd|atiumd|aticfx|atidxx|amdxx|"
                      r"amdihk|igdumd|igd9|igdusc|igc|igxelpicd|ig9icd|ig4icd|iglhxs)",
                      re.IGNORECASE)


@dataclass(frozen=True)
class Plantage:
    """Ce que Windows dit d'un plantage. `module` vide : rien n'a été noté."""
    code: int
    module: str = ""
    chemin_module: str = ""
    version_module: str = ""
    decalage: str = ""


@dataclass(frozen=True)
class Constat:
    """Ce qu'on dira au joueur. `genre` : « antivirus » ou « plantage »."""
    genre: str
    cause: str
    detail: str = ""
    fichiers: tuple[str, ...] = field(default_factory=tuple)


def code_de_plantage(code: object) -> int | None:
    """Le code non signé si c'est un statut d'erreur NT, None sinon."""
    if not isinstance(code, int) or isinstance(code, bool):
        return None
    code &= 0xFFFFFFFF
    return code if code >= _ERREUR_NT else None


def _temps_xpath(quand: datetime) -> str:
    """Horodatage UTC au format qu'attend le filtre XPath du journal."""
    if quand.tzinfo is None:
        quand = quand.astimezone()          # heure locale, comme `datetime.now()`
    return quand.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _evenements(canal: str, requete: str, combien: int) -> list[dict[str, str]]:
    """Les événements, du plus récent au plus ancien, en {nom de champ: valeur}.

    `/uni:true` : sortie UTF-16, la seule qui garde les accents des chemins
    (« Deuxième Partie » sortait illisible dans la page de code de la console).
    """
    if sys.platform != "win32":
        return []
    try:
        # Chemin système absolu (règle 1), liste d'arguments, aucun shell ;
        # la requête est construite ici, rien ne vient du catalogue.
        r = subprocess.run(  # nosec B603
            [commande_systeme("wevtutil.exe"), "qe", canal, f"/q:{requete}",
             "/f:xml", "/rd:true", f"/c:{combien}", "/uni:true"],
            capture_output=True, timeout=_DELAI_S, creationflags=_SANS_FENETRE)
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("Journal %s illisible : %s", canal, exc)
        return []
    if r.returncode != 0 or not r.stdout:
        return []
    return lire_evenements(r.stdout)


def lire_evenements(brut: bytes) -> list[dict[str, str]]:
    """Le XML de `wevtutil` (UTF-16, BOM ou non) en liste de dictionnaires."""
    try:
        texte = brut.decode("utf-16-le").lstrip("\ufeff")
        racine = ET.fromstring("<r>" + texte + "</r>")  # nosec B314
    except (UnicodeDecodeError, ET.ParseError):
        return []
    sortie = []
    for ev in racine:
        champs = {d.get("Name") or "": d.text or ""
                  for d in ev.findall("e:EventData/e:Data", _NS)}
        temps = ev.find("e:System/e:TimeCreated", _NS)
        champs["_temps"] = temps.get("SystemTime", "") if temps is not None else ""
        sortie.append(champs)
    return sortie


def _hex(texte: str) -> int | None:
    try:
        return int(texte, 16)
    except (TypeError, ValueError):
        return None


def choisir_evenement(evenements: list[dict[str, str]], exe: str, pid: int | None,
                      code: int) -> dict[str, str] | None:
    """L'événement 1000 de NOTRE processus, ou None. Raison dans l'en-tête.

    Le PREMIER de ce processus, pas le dernier : un plantage en entraîne
    souvent un second pendant que le processus meurt. Relevé réel (HP8,
    2026-09-17, même pid) : `d3d9.dll` du correctif à 14:56:43, puis
    `ntdll.dll` à 14:56:44. Le dernier aurait accusé Windows à tort.
    `evenements` va du plus récent au plus ancien (`/rd:true`).
    """
    for ev in reversed(evenements):
        if ev.get("AppName", "").lower() != exe.lower():
            continue
        if _hex(ev.get("ExceptionCode", "")) != code:
            continue
        if pid is not None and _hex(ev.get("ProcessId", "")) != pid:
            continue
        return ev
    return None


def plantage(exe: str, pid: int | None, code: int, debut: datetime) -> Plantage:
    """Ce que le journal Application dit du plantage de `exe` depuis `debut`."""
    requete = ("*[System[Provider[@Name='Application Error'] and (EventID=1000) and "
               f"TimeCreated[@SystemTime>='{_temps_xpath(debut - _MARGE)}']]]")
    ev = choisir_evenement(_evenements("Application", requete, 50), exe, pid, code)
    if ev is None:
        return Plantage(code)
    return Plantage(code, ev.get("ModuleName", ""), ev.get("ModulePath", ""),
                    ev.get("ModuleVersion", ""), ev.get("FaultingOffset", ""))


def _sous(chemin: str, dossier: Path) -> str | None:
    """Le chemin relatif de `chemin` dans `dossier`, sans égard à la casse."""
    c = PureWindowsPath(chemin)
    d = PureWindowsPath(str(dossier))
    parts_c = [p.lower() for p in c.parts]
    parts_d = [p.lower() for p in d.parts]
    if len(parts_c) <= len(parts_d) or parts_c[:len(parts_d)] != parts_d:
        return None
    return str(PureWindowsPath(*c.parts[len(parts_d):]))


def fichiers_en_quarantaine(detections: list[dict[str, str]], dossier: Path) -> list[str]:
    """Les fichiers du jeu que Defender a retirés et qui MANQUENT toujours.

    `Path` vaut « file:_C:\\…\\paul.dll », parfois plusieurs ressources jointes
    par « ; » (fichier, processus, entrée de registre). Un fichier revenu
    depuis (restauré, jeu réinstallé) n'est plus une cause.
    """
    trouves: list[str] = []
    for det in detections:
        for ressource in det.get("Path", "").split(";"):
            if not ressource.lower().startswith("file:_"):
                continue
            rel = _sous(ressource[len("file:_"):].strip(), dossier)
            # Windows ne distingue pas la casse : PC\Paul.dll et pc\paul.dll
            # sont le même fichier, à ne nommer qu'une fois.
            if rel is None or rel.lower() in (t.lower() for t in trouves):
                continue
            if not (dossier / Path(*PureWindowsPath(rel).parts)).exists():
                trouves.append(rel)
    return trouves


def quarantaine(dossier: Path) -> list[str]:
    """Les fichiers de `dossier` retirés par Microsoft Defender (événement 1117)."""
    detections = _evenements("Microsoft-Windows-Windows Defender/Operational",
                             "*[System[(EventID=1117)]]", _DETECTIONS)
    return fichiers_en_quarantaine(detections, dossier)


def _dans_windows(chemin: str) -> bool:
    parts = [p.lower() for p in PureWindowsPath(chemin).parts]
    return len(parts) > 1 and parts[1] == "windows"


def expliquer(p: Plantage, dossier: Path, exe: str) -> str:
    """La cause, en une ou deux phrases que le joueur peut suivre."""
    if p.code == DLL_INTROUVABLE:
        return tr("Windows n'a pas trouvé un fichier DLL dont le jeu a besoin. "
                  "« Vérifier / réparer les fichiers », dans les réglages du jeu, le remet en place.")
    if p.code in (DLL_INVALIDE, DLL_INIT):
        return tr("Un fichier DLL du jeu est abîmé ou n'a pas pu démarrer. "
                  "« Vérifier / réparer les fichiers », dans les réglages du jeu, le remet en place.")
    if not p.module:
        return tr("Windows n'a pas noté où le plantage a eu lieu.")
    if p.module.lower() == exe.lower():
        return tr("Le plantage a eu lieu dans le jeu lui-même ({}).").format(p.module)
    if _sous(p.chemin_module, dossier) is not None:
        return tr("Le plantage a eu lieu dans {}, un fichier installé avec le jeu "
                  "(un correctif ou un composant).").format(p.module)
    if _PILOTES.match(p.module):
        return tr("Le plantage a eu lieu dans le pilote de la carte graphique ({}). "
                  "Mettre ce pilote à jour règle le plus souvent ce cas.").format(p.module)
    if _dans_windows(p.chemin_module):
        return tr("Le plantage a eu lieu dans un composant de Windows ({}). La cause est "
                  "souvent ailleurs : un pilote graphique ancien, ou un programme qui "
                  "s'affiche par-dessus le jeu.").format(p.module)
    return tr("Le plantage a eu lieu dans {}, un programme extérieur au jeu qui s'y "
              "accroche (une surimpression comme celle de Discord, Steam ou RivaTuner, "
              "un enregistreur vidéo…). Essayez de jouer sans lui.").format(p.module)


def detail(p: Plantage, exe: str) -> str:
    """Une ligne technique, à coller telle quelle sur Discord."""
    morceaux = [exe, f"0x{p.code:08x}"]
    if p.module:
        morceaux.append(" ".join(x for x in (p.module, p.version_module) if x))
        if p.decalage:
            morceaux.append(f"+0x{p.decalage}")
    return " · ".join(morceaux)


def apres_la_partie(dossier: Path | None, exe: str, pid: int | None, code: object,
                    debut: datetime | None, partie: bool) -> Constat | None:
    """Ce qu'il faut dire au joueur après cette partie, ou None si rien.

    Un plantage d'abord par son code ; la quarantaine seulement si le
    lancement a échoué (pas de vraie partie) ou planté : un jeu qui a tourné
    n'a pas besoin du fichier, et le redire à chaque retour serait du bruit.
    """
    if sys.platform != "win32" or dossier is None or debut is None or not exe:
        return None
    nt = code_de_plantage(code)
    if nt is None and partie:
        return None
    retires = quarantaine(dossier)
    if retires:
        log.info("Fichiers du jeu en quarantaine Defender : %s", retires)
        return Constat("antivirus", "", fichiers=tuple(retires))
    if nt is None:
        return None
    p = plantage(exe, pid, nt, debut)
    log.info("Plantage : %s", detail(p, exe))
    return Constat("plantage", expliquer(p, dossier, exe), detail(p, exe))

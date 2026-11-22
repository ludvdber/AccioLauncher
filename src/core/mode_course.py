r"""Le Mode course (1.5) : les réglages du correctif tenus le temps d'une course, puis RENDUS au joueur
(atelier, `notes/SPEEDRUN_LAUNCHER.md` § 3 à 5 ; tables « Mode course » de `notes/doc/hpN/COURSE.md` § 4).

**Ce qui est tenu** : ce qui change le TEMPS du jeu ou sa logique, à la valeur du jeu d'origine — 60 images
par seconde au plus (règle d'Accio), `RealFrameTime`, `StepTimers` et `StepPacing` coupés (S7.5), la
difficulté et la une seule vie coupées, les mods, la caméra libre et l'hôte Lua de HP6 coupés, les outils de
mise au point (`[Accio.Shaders] Dump`, `[Accio.Test]`) coupés. **Tout le reste reste où le joueur l'a mis** :
image, fenêtre, son, manette, champ de vision (S7.6), et les réparations (`LumosFade` de HP2,
`TextMeasureCache` de HP3, `SPEEDRUN_PLAN.md` § 9). La difficulté de la 1.4 n'est pas réglée ici : elle doit
être « Normal » (`difficulte_presets`), sinon la course est refusée avant le lancement, raison dite.

**Les clés de la course** (`[Accio.Game] RaceLog=1`, `[Accio.Overlay] RaceId=<ligne>`, et pour HP4 à HP6
`[Accio.Game] RaceSaves=<dossier vide>`) sont posées par le launcher au départ et retirées après. **Elles ne
sont PAS dans les ini livrés de la 1.4** (règle du correctif : rien d'une autre version dans un ini livré) ;
la course n'est donc proposée que là où l'ini porte `RaceLog` : à la 1.5, `make_ini.py` du correctif les
réécrit à `0` et vide, `settings_test.cpp` cesse de les refuser, et les archives des six jeux les livrent.

**Rendre à l'octet** : `entrer` retient AVANT d'écrire, dans `_Launcher/courses/<code>/avant.json`, la valeur
de chaque clé qu'il va changer (None : la clé était absente) ; `sortir` les remet, retire les lignes qu'il a
ajoutées, et renomme le fichier `avant.rendu.json`. Un `avant.json` présent est donc l'état d'une course EN
COURS : un launcher tué pendant la partie le retrouve au démarrage suivant (`GameSession.courses_interrompues`),
et seules ces courses-là sont relues à chaque fin de partie, pas toutes celles du Carnet.
"""

import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.core import course, une_vie
from src.core import reglages_correctif as rc
from src.core.ecriture_atomique import ecrire_atomique
from src.core.game_data import GameData

log = logging.getLogger(__name__)

JEU, FENETRE, APERCU, SHADERS, TEST, DURETE = (
    "Accio.Game", "Accio.Window", "Accio.Overlay", "Accio.Shaders", "Accio.Test", "Accio.Hardcore")
CLE_JOURNAL = (JEU, "RaceLog")
CLE_ID = (APERCU, "RaceId")
CLE_SAUVEGARDES = (JEU, "RaceSaves")
REPLI_SAUVEGARDES = "Accio_Courses"      # <AppData\Local>\Accio_Courses\<code> quand le chemin est trop long


@dataclass(frozen=True)
class Tenue:
    """Une clé tenue pendant la course. `posee` est écrite si la valeur lue n'est pas permise."""
    section: str
    cle: str
    posee: str
    permis: frozenset[str] = frozenset()   # d'autres valeurs permises (casse ignorée)
    au_plus: int = 0                       # > 0 : un entier de 1 à `au_plus`
    absente: bool = True                   # absente = tenue (la DLL prend sa valeur livrée, la même)

    def tenue(self, valeur: str | None) -> bool:
        if valeur is None:
            return self.absente
        v = valeur.strip().lower()
        if self.au_plus:
            return v.isascii() and v.isdigit() and 1 <= int(v) <= self.au_plus
        return v == self.posee.lower() or v in {p.lower() for p in self.permis}


def _egal(section: str, cle: str, valeur: str, absente: bool = True) -> Tenue:
    return Tenue(section, cle, valeur, absente=absente)


_VIE = (_egal(JEU, "OneLife", "0"), _egal(JEU, "DeathCounter", "0"))
_OUTILS = (_egal(SHADERS, "Dump", "0"), _egal(TEST, "Telemetry", "0"), _egal(TEST, "TerrainTrace", "0"),
           _egal(TEST, "FrameTrace", "0"))
_DEGATS = (_egal(DURETE, "DamageTaken", "1"), _egal(DURETE, "DamageDealt", "1"))
# HP4 à HP6 : la limite et le plafond À 60, ensemble (avec `RealFrameTime=0`, le jeu avance de
# 1000 / `FrameRateCap` par image : deux valeurs différentes changeraient sa vitesse).
_CADENCE_D3D9 = (_egal(FENETRE, "FPSLimit", "60", absente=False), _egal(JEU, "FrameRateCap", "60", absente=False),
                 _egal(JEU, "RealFrameTime", "0", absente=False))
_UE1 = (Tenue(FENETRE, "FPSLimit", "60", au_plus=60, absente=False), _egal(JEU, "QuidditchDifficulty", "0"),
        *_VIE, *_DEGATS, *_OUTILS)

A_TENIR: dict[str, tuple[Tenue, ...]] = {
    "hp1": _UE1,
    "hp2": _UE1,
    # Le plafond du correctif à 0 : les 60 du jeu (120 changerait la cadence, `COURSE.md` de HP3).
    "hp3": (_egal(JEU, "FrameRateCap", "0"), *_VIE, *_DEGATS, *_OUTILS),
    "hp4": (*_CADENCE_D3D9, _egal(JEU, "AnimationRate", "0"), *_VIE, *_OUTILS, *_DEGATS,
            _egal(DURETE, "EnemyHits", "1"), _egal(DURETE, "EnemyRecovery", "1")),
    "hp5": (*_CADENCE_D3D9, _egal(JEU, "UnlockFrameRate", "1"), _egal(JEU, "SimulationStep", "0"),
            _egal(JEU, "StepTimers", "0", absente=False), _egal(JEU, "StepPacing", "0", absente=False),
            _egal(JEU, "WandGate", "0"), *_VIE, *_OUTILS, *_DEGATS,
            _egal(DURETE, "PlayerHealth", "1"), _egal(DURETE, "Invincible", "0")),
    "hp6": (*_CADENCE_D3D9, _egal(JEU, "UnlockFrameRate", "1"), _egal(JEU, "ModsFolder", "0"),
            _egal(JEU, "LuaFolder", ""), _egal(JEU, "FreeCamera", "0"),
            # Les modes 2 et 3 imposent l'heure que le jeu lit (`SPEEDRUN_PLAN.md` § 9) ; 0 et 1 sont visuels.
            Tenue("Accio.Graphics", "SkyMode", "1", permis=frozenset(("0",))),
            *_VIE, *_OUTILS, *_DEGATS, _egal(DURETE, "EnemyReaction", "1"), _egal(DURETE, "RemovedSpells", ""),
            _egal(DURETE, "PlayerHealth", "1"), _egal(DURETE, "PlayerRegen", "1"), _egal(DURETE, "Invincible", "0")),
}


# ── Ce que porte l'ini ──

def ini(game: GameData, install_path: Path) -> Path | None:
    """L'ini du correctif de ce jeu s'il connaît la course (il porte `RaceLog`, et `RaceSaves` pour HP4 à HP6)."""
    if game.id not in A_TENIR:
        return None
    chemin = rc.ini_du_correctif(Path(install_path) / Path(game.executable).parent)
    if rc.valeur_posee(chemin, *CLE_JOURNAL) is None:
        return None
    if game.id not in course.UE1 and rc.valeur_posee(chemin, *CLE_SAUVEGARDES) is None:
        return None
    return chemin


@dataclass(frozen=True)
class Ecart:
    section: str
    cle: str
    valeur: str | None      # None : la clé est absente
    posee: str


def ecarts(game_id: str, chemin_ini: Path) -> list[Ecart]:
    """Les clés que la course changera le temps de la partie (puis rendra)."""
    sortie = []
    for t in A_TENIR.get(game_id, ()):
        valeur = rc.valeur_posee(chemin_ini, t.section, t.cle)
        if not t.tenue(valeur):
            sortie.append(Ecart(t.section, t.cle, valeur, t.posee))
    return sortie


def actif(chemin_ini: Path | None) -> bool:
    """La DLL écrira le journal d'une course à la prochaine partie."""
    return chemin_ini is not None and rc.valeur_posee(chemin_ini, *CLE_JOURNAL) not in (None, "", "0")


def dossier_sauvegardes(code: str) -> tuple[Path, str] | None:
    """Le dossier des sauvegardes de la course, et `RaceSaves` tel que le JEU le lira (sous Linux, le
    chemin vu par Wine) : `_Launcher/courses/<code>/saves`, sinon (chemin trop long, ou hors de la page
    de codes) `<AppData\\Local>\\Accio_Courses\\<code>`, sinon None (course refusée)."""
    from src.core import sauvegardes
    local = sauvegardes.racines().get("localappdata")
    candidats = [course.dossier(code) / course.SAUVEGARDES]
    if local is not None:
        candidats.append(local / REPLI_SAUVEGARDES / code)
    for chemin in candidats:
        texte = une_vie.pour_le_jeu(chemin, plafond=True)
        if texte is not None:
            return chemin, texte
    return None


# ── La course en cours : `avant.json` ──

@dataclass(frozen=True)
class EnCours:
    code: str
    jeu: str
    categorie: str
    jour: date
    ligne_id: str
    ini: Path
    retenues: tuple[tuple[str, str, str | None], ...]   # (section, clé, valeur d'avant)
    ecarts_au_depart: tuple[Ecart, ...]
    empreinte: course.Empreinte
    difficulte: str
    sauvegardes: str = ""


def _vers_json(e: EnCours) -> str:
    return json.dumps({
        "code": e.code, "jeu": e.jeu, "categorie": e.categorie, "date": e.jour.isoformat(), "ligne_id": e.ligne_id,
        "ini": str(e.ini), "retenues": [list(r) for r in e.retenues],
        "ecarts": [[x.section, x.cle, x.valeur, x.posee] for x in e.ecarts_au_depart],
        "empreinte": {"complete": e.empreinte.complete, "courte": e.empreinte.courte,
                      "fichiers": [[f.chemin, f.taille, f.sha256] for f in e.empreinte.fichiers]},
        "difficulte": e.difficulte, "sauvegardes": e.sauvegardes,
    }, ensure_ascii=False, indent=1)


def _depuis_json(brut: dict[str, Any]) -> EnCours | None:
    try:
        emp = brut["empreinte"]
        return EnCours(
            code=str(brut["code"]), jeu=str(brut["jeu"]), categorie=str(brut["categorie"]),
            jour=date.fromisoformat(str(brut["date"])), ligne_id=str(brut["ligne_id"]), ini=Path(str(brut["ini"])),
            retenues=tuple((str(s), str(c), None if v is None else str(v)) for s, c, v in brut["retenues"]),
            ecarts_au_depart=tuple(Ecart(str(s), str(c), None if v is None else str(v), str(p))
                                   for s, c, v, p in brut["ecarts"]),
            empreinte=course.Empreinte(str(emp["complete"]), str(emp["courte"]), tuple(
                course.Fichier(str(c), int(t), str(h)) for c, t, h in emp["fichiers"])),
            difficulte=str(brut["difficulte"]), sauvegardes=str(brut.get("sauvegardes", "")))
    except (KeyError, TypeError, ValueError):
        return None


def _lire_avant(dossier_course: Path) -> EnCours | None:
    """La course en cours de ce dossier, None si ses réglages sont rendus (ou son fichier illisible)."""
    try:
        brut = json.loads((dossier_course / course.AVANT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _depuis_json(brut) if isinstance(brut, dict) else None


def en_cours(game_id: str | None = None) -> list[EnCours]:
    """Les courses dont les réglages ne sont pas encore rendus (une seule en temps normal ; d'autres après un
    launcher tué pendant la partie), du jeu nommé ou de tous."""
    try:
        dossiers = sorted(p for p in course.racine().iterdir() if p.is_dir() and course.code_valide(p.name))
    except OSError:
        return []
    sortie = []
    for d in dossiers:
        e = _lire_avant(d) if (d / course.AVANT).is_file() else None
        if e is not None and (game_id is None or e.jeu == game_id):
            sortie.append(e)
    return sortie


# ── Entrer, sortir ──

class CourseRefusee(Exception):
    """La course ne peut pas partir ; `args[0]` est le code de la raison (l'interface la dit)."""


def entrer(game: GameData, chemin_ini: Path, categorie: str, empreinte: course.Empreinte, difficulte: str,
           jour: date | None = None, fantome: str | None = None) -> EnCours:
    """Tire le code, crée le dossier NEUF de la course, retient puis pose les clés tenues et celles de la
    course, retire le journal d'une course passée et pose le fantôme (`course.fantome` ; None : aucun, et
    celui d'une course passée est retiré). `RaceLog` est posée en DERNIER : un échec en route
    laisse le correctif sans course, et ce qui a été posé est rendu aussitôt."""
    jour = jour or date.today()
    code = course.tirer_code()
    ligne = course.ligne_id(code, jour, empreinte.courte, game.id, categorie)
    ou = course.creer_dossier(code)
    sauvegardes = ""
    if game.id not in course.UE1:
        trouve = dossier_sauvegardes(code)
        if trouve is None:
            raise CourseRefusee("sauvegardes")
        trouve[0].mkdir(parents=True, exist_ok=True)
        sauvegardes = trouve[1]
    restes = ecarts(game.id, chemin_ini)
    a_poser = [(x.section, x.cle, x.posee) for x in restes] + [(*CLE_ID, ligne)]
    if sauvegardes:
        a_poser.append((*CLE_SAUVEGARDES, sauvegardes))
    a_poser.append((*CLE_JOURNAL, "1"))
    retenues = tuple((s, c, rc.valeur_posee(chemin_ini, s, c)) for s, c, _ in a_poser)
    etat = EnCours(code, game.id, categorie, jour, ligne, chemin_ini, retenues, tuple(restes), empreinte,
                   difficulte, sauvegardes)
    ecrire_atomique(ou / course.AVANT, _vers_json(etat))
    try:
        for s, c, v in a_poser:
            rc.poser_valeur(chemin_ini, s, c, v)
    except (OSError, ValueError) as exc:
        log.warning("Course : clé non posée dans %s (%s)", chemin_ini, exc)
        sortir(etat)
        raise CourseRefusee("ini") from exc
    if not course.retirer(chemin_ini.parent):
        sortir(etat)
        raise CourseRefusee("journal_tenu")
    course.poser_fantome(chemin_ini.parent, fantome)
    return etat


def sortir(etat: EnCours) -> bool:
    """Rend chaque clé retenue (`RaceLog` d'abord : la partie suivante n'est plus une course), retire celles
    que l'ini ne portait pas, retire le fantôme, puis renomme `avant.json` en `avant.rendu.json`. False si
    l'ini n'a pas pu être rendu (le fichier reste « à rendre » : le prochain démarrage réessaie)."""
    course.poser_fantome(etat.ini.parent, None)
    ordre = sorted(etat.retenues, key=lambda r: (r[0], r[1]) != CLE_JOURNAL)
    try:
        for section, cle, avant in ordre:
            if avant is None:
                rc.retirer_valeur(etat.ini, section, cle)
            else:
                rc.poser_valeur(etat.ini, section, cle, avant)
    except (OSError, ValueError):
        log.warning("Course %s : réglages non rendus dans %s", etat.code, etat.ini, exc_info=True)
        return False
    try:
        ou = course.dossier(etat.code)
        os.replace(ou / course.AVANT, ou / course.AVANT_RENDU)
    except OSError:
        log.warning("Course %s : avant.json non renommé", etat.code, exc_info=True)
    return True


# ── Après la partie ──

@dataclass(frozen=True)
class Conclusion:
    code: str
    jeu: str
    resultat: course.Resultat
    refus: tuple[str, ...]
    journal: Path | None        # course.json, None s'il n'a pas pu s'écrire
    rendu: bool
    ligne_id: str = ""
    categorie: str = course.ANY


def conclure(etat: EnCours, launcher: str) -> Conclusion:
    """Le jeu s'est fermé : copie brute du journal du correctif, verdict, `course.json` signé, puis les
    réglages rendus. L'ini est gardé en clair TEL QUE POSÉ (avant d'être rendu)."""
    ou = course.dossier(etat.code)
    texte = course.lire(etat.ini.parent)
    try:
        (ou / course.FICHIER).write_bytes(texte.encode("utf-8"))
    except OSError:
        log.warning("Course %s : copie du journal impossible", etat.code, exc_info=True)
    try:
        texte_ini = etat.ini.read_text(encoding="utf-8", errors="replace")
    except OSError:
        texte_ini = ""
    resultat = course.analyser(texte)
    tenu = not etat.ecarts_au_depart or all(
        rc.valeur_posee(etat.ini, x.section, x.cle) == x.posee for x in etat.ecarts_au_depart)
    refus = course.verdict(resultat, course.Attendu(etat.ligne_id, tenu, sous_wine=sys.platform != "win32"))
    donnees = course.contenu(
        game_id=etat.jeu, categorie=etat.categorie, code=etat.code, jour=etat.jour, ligne=etat.ligne_id,
        empreinte_jeu=etat.empreinte, launcher=launcher, ini=texte_ini,
        ecarts=() if tenu else [(x.section, x.cle, str(x.valeur), x.posee) for x in etat.ecarts_au_depart],
        resultat=resultat, refus=refus, plateforme=sys.platform, difficulte=etat.difficulte)
    try:
        journal: Path | None = course.ecrire_journal(etat.code, donnees)
    except (OSError, ValueError):
        log.warning("Course %s : course.json non écrit", etat.code, exc_info=True)
        journal = None
    return Conclusion(etat.code, etat.jeu, resultat, refus, journal, sortir(etat), etat.ligne_id,
                      etat.categorie)


# ── Au lancement ──

def arguments(game: GameData, install_path: Path) -> tuple[str, ...] | None:
    """Ce que la course impose à la ligne de commande, None hors course. Une course part d'une NOUVELLE
    partie (S7.1) : jamais la reprise de la dernière. HP2 : nouvelle partie à Privet Drive sur l'emplacement
    7, hors des six du joueur (la forme VUE de la une seule vie, `une_vie.NOUVELLE_HP2`)."""
    if not actif(ini(game, install_path)):
        return None
    return une_vie.NOUVELLE_HP2 if game.id == "hp2" else ()


# ── Le Carnet ──

def supprimer(code: str) -> bool:
    """Efface une course gardée, à la DEMANDE du joueur (le Carnet confirme d'abord) : son dossier, et le
    repli de ses sauvegardes sous `<AppData\\Local>\\Accio_Courses` s'il a servi. Rien d'autre n'efface un
    dossier de course. Refusé (False) pour une course dont les réglages ne sont pas encore rendus : son
    `avant.json` est ce qui permet de les rendre."""
    ou = course.dossier(code)
    if _lire_avant(ou) is not None:
        return False
    from src.core import sauvegardes
    local = sauvegardes.racines().get("localappdata")
    try:
        shutil.rmtree(ou)
        if local is not None and (repli := local / REPLI_SAUVEGARDES / code).is_dir():
            shutil.rmtree(repli)
    except OSError:
        log.warning("Course %s : dossier non effacé", code, exc_info=True)
        return False
    return True

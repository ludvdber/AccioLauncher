"""Journal des sessions de jeu, et tout ce qui s'en déduit.

**Un journal, pas une collection de compteurs.** Le launcher savait déjà deux
choses par jeu : un temps cumulé et une date de dernière partie
(`config.playtime_seconds` / `config.last_played`). C'est le strict minimum, et
surtout c'est un cul-de-sac : « durée moyenne d'une session » ne se déduit pas
d'un cumul, « série de jours consécutifs » non plus, ni l'heure à laquelle
quelqu'un joue. Chaque nouvelle statistique aurait demandé son propre compteur,
donc sa propre écriture, sa propre migration, et son propre risque de dériver
des autres.

On enregistre donc l'ÉVÉNEMENT — une session : quel jeu, quand, combien de
temps — et tout le reste est un calcul sur cette liste. Une statistique qu'on
n'a pas encore imaginée sera calculable rétroactivement sur l'historique déjà
constitué ; c'est exactement ce qui manquait ici.

**L'histoire d'avant le journal n'est pas perdue.** À sa création, le journal
prend un instantané des cumuls déjà en config (`herite`). Ce temps-là compte
dans les totaux — il a réellement été joué — mais dans RIEN d'autre : il n'a ni
date, ni durée de session, ni heure. La séparation est structurelle et non un
drapeau posé sur chaque entrée : `Historique.sessions` ne contient que de
vraies sessions, `Historique.herite` vit à côté, et une seule fonction
(`temps_par_jeu`) additionne les deux. Aucune moyenne, aucune série et aucun
histogramme ne peut donc être faussé par de l'hérité, même écrit distraitement.

**Le fichier vit à côté de `config.json`**, et son chemin est résolu À L'APPEL
depuis `config.CONFIG_FILE_PATH` : c'est ce que `tests/conftest.py` redirige
vers un dossier temporaire. Un journal à chemin figé aurait échappé à cette
garde — or elle existe parce que des statistiques de jeu réelles ont déjà été
écrasées par un test, le 2026-08-18.
"""

import json
import logging
import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

JOURNAL_NAME = "sessions.json"

# La partie EN COURS, hors du journal et dans son propre fichier. Elle y est
# réécrite périodiquement pendant qu'on joue, pour une raison mesurée : une
# session n'était écrite qu'à la FERMETURE du jeu, or c'est précisément
# pendant la partie que le launcher dort dans la zone de notification — donc
# qu'on le quitte par son menu, qu'une mise à jour Windows le tue, ou qu'il
# plante. Plus une partie était LONGUE, plus elle avait de chances d'œtre
# perdue : un biais silencieux qui contaminait la moyenne, le record, les
# séries et les plages horaires à la fois.
#
# Le fichier est séparé pour ne pas réécrire tout le journal chaque minute, et
# `vu_a` est une date OBSERVÉE, jamais estimée : au redémarrage, une partie
# interrompue vaut ce qu'on a vraiment vu d'elle, pas une durée devinée.
EN_COURS_NAME = "session_en_cours.json"

# Une session par jour pendant 54 ans. Le plafond n'est pas là pour oublier de
# l'histoire — il borne ce qu'un fichier corrompu ou trafiqué peut charger en
# mémoire, au même titre que le plafond d'octets du téléchargeur.
_MAX_SESSIONS = 20_000

# En dessous, ce n'est pas une partie : un double-clic malheureux, un jeu qui
# refuse de démarrer. Le seuil est le même que celui appliqué à la volée par
# `MainWindow._on_game_exited` depuis toujours ; il est redit ici pour que le
# journal reste propre même si un autre appelant arrive un jour.
DUREE_MINIMALE = 10


@dataclass(frozen=True, slots=True)
class Tentative:
    """Un lancement qui n'est jamais devenu une partie.

    Le launcher OBSERVAIT déjà ces événements et les jetait : `ProcessMonitor`
    lisait le code de sortie pour le journaliser, `add_playtime` sortait avant
    d'écrire dès que la durée était sous le seuil. Or c'est la SEULE chose que
    cette page puisse dire à quelqu'un qu'il ne sait pas déjà — « HP7 partie 1,
    six essais, aucun au-delà de trois secondes » est actionnable, « 4 min de
    jeu au total » ne l'est pas.

    C'est aussi la signature exacte du défaut du sous-dossier `pc` de HP7,
    relevée dans CLAUDE.md : sortie 0 en 0,5 s, aucun fichier écrit, rien dans
    le journal d'événements Windows, pas de fenêtre. Un jeu de 2001-2011 sur
    Windows 11 échoue en silence ; il faut donc l'enregistrer au moment où on
    le voit, ce moment ne revient pas.

    **Liste SÉPARÉE de `sessions`, jamais un drapeau dedans.** L'invariant qui
    fait la valeur du module — `sessions` ne contient que de vraies parties,
    donc aucune moyenne ni série ne peut être faussée, même écrite
    distraitement — tomberait le jour où quelqu'un oublie de filtrer. Même
    raisonnement structurel que `herite`, appliqué une deuxième fois. Accessoire
    et décisif : `_parse_session` REFUSE déjà au parsing une durée sous le
    seuil, donc une tentative glissée dans `sessions` serait relue puis jetée
    sans un mot.
    """

    jeu: str
    debut: datetime
    duree: int          # secondes, < DUREE_MINIMALE par construction
    code: int | None    # code de sortie du processus, None si inconnu


@dataclass(frozen=True, slots=True)
class Session:
    """Une partie : quel jeu, quand elle a commencé, combien de temps."""

    jeu: str
    debut: datetime
    duree: int  # secondes

    @property
    def jour(self) -> date:
        return self.debut.date()


@dataclass(frozen=True, slots=True)
class Historique:
    """Ce que le launcher a observé de lui-même.

    `sessions` est le détail (depuis la création du journal), `herite` le temps
    cumulé AVANT lui — voir l'en-tête du module pour la raison de la séparation.
    """

    sessions: tuple[Session, ...] = ()
    herite: dict[str, int] = field(default_factory=dict)
    demarrages: int = 0
    octets_telecharges: int = 0
    tentatives: tuple[Tentative, ...] = ()

    @property
    def vide(self) -> bool:
        """Aucune session ET aucun temps hérité : il n'y a rien à montrer."""
        return not self.sessions and not any(self.herite.values())


# ─── Fichier ───

def chemin_journal():
    """Résolu à l'appel, jamais à l'import — voir l'en-tête du module."""
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / JOURNAL_NAME


def _lire_brut(chemin) -> dict:
    if not chemin.exists():
        return {}
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        # Un journal illisible ne doit ni faire planter le launcher ni
        # disparaître en silence sous la prochaine écriture : on le met de côté
        # sous un autre nom. C'est un historique personnel, il ne se reconstruit
        # pas.
        log.warning("Journal de sessions illisible (%s) — mis de côté", exc)
        try:
            os.replace(chemin, chemin.with_suffix(".corrompu"))
        except OSError:
            pass
        return {}
    return data if isinstance(data, dict) else {}


def _parse_session(brut) -> Session | None:
    """Une entrée fautive est ignorée, jamais fatale — le reste de l'historique
    vaut mieux que rien."""
    if not isinstance(brut, dict):
        return None
    jeu = brut.get("jeu")
    duree = brut.get("duree")
    if not isinstance(jeu, str) or not jeu:
        return None
    if not isinstance(duree, int) or isinstance(duree, bool) or duree < DUREE_MINIMALE:
        return None
    try:
        debut = datetime.fromisoformat(str(brut.get("debut")))
    except (ValueError, TypeError):
        return None
    return Session(jeu=jeu, debut=debut, duree=duree)


def _parse_tentative(brut) -> "Tentative | None":
    """Une tentative fautive est ignorée, jamais fatale — comme une session."""
    if not isinstance(brut, dict):
        return None
    jeu = brut.get("jeu")
    duree = brut.get("duree")
    if not isinstance(jeu, str) or not jeu:
        return None
    if not isinstance(duree, int) or isinstance(duree, bool) or duree < 0:
        return None
    code = brut.get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        code = None
    try:
        debut = datetime.fromisoformat(str(brut.get("debut")))
    except (ValueError, TypeError):
        return None
    return Tentative(jeu=jeu, debut=debut, duree=duree, code=code)


def charger(chemin=None) -> Historique:
    """Lit le journal. Un fichier absent, vide ou fautif rend un historique vide."""
    data = _lire_brut(chemin or chemin_journal())
    brutes = data.get("sessions")
    sessions: list[Session] = []
    if isinstance(brutes, list):
        for entree in brutes[-_MAX_SESSIONS:]:
            s = _parse_session(entree)
            if s is not None:
                sessions.append(s)
    sessions.sort(key=lambda s: s.debut)

    herite = {}
    for gid, secondes in (data.get("herite") or {}).items():
        if isinstance(gid, str) and isinstance(secondes, int) and not isinstance(secondes, bool):
            herite[gid] = max(0, secondes)

    tentatives: list[Tentative] = []
    for entree in (data.get("tentatives") or [])[-_MAX_SESSIONS:]:
        t = _parse_tentative(entree)
        if t is not None:
            tentatives.append(t)
    tentatives.sort(key=lambda t: t.debut)

    def _entier(cle) -> int:
        v = data.get(cle)
        return max(0, v) if isinstance(v, int) and not isinstance(v, bool) else 0

    return Historique(tuple(sessions), herite,
                      _entier("demarrages"), _entier("octets_telecharges"),
                      tuple(tentatives))


def _ecrire_donnees(data: dict, chemin) -> None:
    """Écriture atomique (tmp + rename), même contrat que `Config.save`.

    Prend le dictionnaire déjà formé plutôt qu'un `Historique` : incrémenter
    un compteur n'a pas à matérialiser les sessions pour les resérialiser
    aussitôt (voir `_muter_compteur`).
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    texte = json.dumps(data, indent=1, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texte)
        os.replace(tmp, chemin)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ecrire(hist: Historique, chemin) -> None:
    """Sérialise l'historique complet, sessions comprises."""
    _ecrire_donnees(
        {
            "version": 1,
            "herite": hist.herite,
            "demarrages": hist.demarrages,
            "octets_telecharges": hist.octets_telecharges,
            "sessions": [
                {"jeu": s.jeu, "debut": s.debut.isoformat(timespec="seconds"),
                 "duree": s.duree}
                for s in hist.sessions[-_MAX_SESSIONS:]
            ],
            "tentatives": [
                {"jeu": t.jeu, "debut": t.debut.isoformat(timespec="seconds"),
                 "duree": t.duree, "code": t.code}
                for t in hist.tentatives[-_MAX_SESSIONS:]
            ],
        },
        chemin,
    )


def amorcer(playtime_seconds: dict[str, int], chemin=None) -> bool:
    """Crée le journal s'il n'existe pas, en y gelant les cumuls déjà connus.

    Idempotente : une fois le fichier créé, elle ne touche plus à `herite` —
    sans quoi le temps joué depuis serait recompté à chaque démarrage.

    Rend True si le journal vient d'être créé.
    """
    chemin = chemin or chemin_journal()
    if chemin.exists():
        return False
    herite = {gid: int(s) for gid, s in (playtime_seconds or {}).items()
              if isinstance(s, int) and not isinstance(s, bool) and s > 0}
    try:
        _ecrire(Historique(herite=herite), chemin)
    except OSError as exc:
        log.warning("Journal de sessions non créé : %s", exc)
        return False
    log.info("Journal de sessions créé (%d jeu(x) hérité(s))", len(herite))
    return True


def _muter(chemin, transformer) -> None:
    """Lit, applique `transformer`, réécrit. Un échec d'écriture ne remonte
    jamais : perdre une statistique n'est pas une raison d'interrompre une
    partie qui vient de se terminer."""
    chemin = chemin or chemin_journal()
    try:
        _ecrire(transformer(charger(chemin)), chemin)
    except OSError as exc:
        log.warning("Journal de sessions non mis à jour : %s", exc)


def _muter_compteur(chemin, cle: str, delta: int) -> None:
    """Incrémente un des deux compteurs SANS matérialiser l'historique.

    `demarrages` et `octets_telecharges` sont les seuls entiers du journal :
    les toucher ne demande de connaître aucune session. Passer par `_muter` en
    reconstruisait pourtant la totalité — une `datetime` par entrée, un tri,
    puis une resérialisation — pour ajouter 1. Le coût est linéaire, et
    `enregistrer_demarrage` le payait AVANT le premier rendu de la fenêtre :
    mesuré sur ce poste, 105 ms au plafond de 20 000 sessions contre 43 ms
    ici, 33 contre 18 à 5 000. Le reste du fichier est réécrit tel quel, donc
    rien de ce qu'on ne comprend pas ne se perd en route.
    """
    chemin = chemin or chemin_journal()
    data = _lire_brut(chemin)
    if not data:
        # Journal encore inexistant : le chemin complet sait en écrire un neuf.
        # N'arrive pas en pratique — `amorcer` tourne à la construction du
        # GameManager, donc avant qu'aucun compteur ne bouge.
        _muter(chemin, lambda h: replace(h, **{cle: getattr(h, cle) + delta}))
        return
    ancien = data.get(cle)
    if not isinstance(ancien, int) or isinstance(ancien, bool):
        ancien = 0
    data[cle] = max(0, ancien + delta)
    try:
        _ecrire_donnees(data, chemin)
    except OSError as exc:
        log.warning("Journal de sessions non mis à jour : %s", exc)


def enregistrer_session(jeu: str, debut: datetime, duree: int, chemin=None) -> None:
    """Ajoute une partie au journal."""
    if not jeu or duree < DUREE_MINIMALE:
        return
    session = Session(jeu=jeu, debut=debut, duree=int(duree))
    # `replace` et non un `Historique(...)` reconstruit champ par champ : les
    # quatre étaient recopiés POSITIONNELLEMENT à trois endroits, donc un champ
    # ajouté un jour au milieu aurait décalé les valeurs en silence.
    _muter(chemin, lambda h: replace(h, sessions=h.sessions + (session,)))


def enregistrer_demarrage(chemin=None) -> None:
    """Un démarrage du launcher de plus."""
    _muter_compteur(chemin, "demarrages", 1)


def enregistrer_telechargement(octets: int, chemin=None) -> None:
    """Cumule ce que le launcher a réellement rapatrié."""
    if octets <= 0:
        return
    _muter_compteur(chemin, "octets_telecharges", int(octets))


def enregistrer_tentative(jeu: str, debut: datetime, duree: int,
                          code: int | None = None, chemin=None) -> None:
    """Consigne un lancement qui n'a pas donné de partie.

    Rien ne l'affiche aujourd'hui, et c'est volontaire : ce qui n'est pas
    enregistré maintenant est perdu pour toujours, alors qu'un affichage se
    calcule rétroactivement sur l'historique déjà constitué le jour où on
    saura quoi en montrer. C'est tout l'intérêt d'un journal d'événements.
    """
    if not jeu or duree < 0:
        return
    t = Tentative(jeu=jeu, debut=debut, duree=int(duree), code=code)
    _muter(chemin, lambda h: replace(h, tentatives=h.tentatives + (t,)))


# ─── Partie en cours ───

def chemin_en_cours():
    """Résolu à l'appel, comme `chemin_journal` — même garde de test."""
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / EN_COURS_NAME


def ouvrir_session(jeu: str, debut: datetime, chemin=None) -> None:
    """Note qu'une partie commence. À appeler AU LANCEMENT."""
    _ecrire_en_cours(jeu, debut, debut, chemin)


def battre_session(vu_a: datetime, chemin=None) -> None:
    """Rafraîchit « dernière fois où on a vu le jeu tourner ».

    Appelée périodiquement pendant la partie. C'est ce battement, et lui seul,
    qui permet de récupérer une durée OBSERVÉE si le launcher meurt en route.
    """
    chemin = chemin or chemin_en_cours()
    data = _lire_brut(chemin)
    jeu, debut = data.get("jeu"), data.get("debut")
    if not isinstance(jeu, str) or not jeu or not isinstance(debut, str):
        return
    try:
        _ecrire_en_cours(jeu, datetime.fromisoformat(debut), vu_a, chemin)
    except ValueError:
        return


def fermer_session(chemin=None) -> None:
    """La partie s'est terminée normalement : plus rien à récupérer."""
    chemin = chemin or chemin_en_cours()
    try:
        chemin.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Partie en cours non effacée : %s", exc)


def recuperer_session_interrompue(chemin=None) -> Session | None:
    """Rattrape une partie que le launcher n'a pas vue se terminer.

    La durée retenue est `vu_a - debut`, c'est-à-dire ce qu'on a réellement
    OBSERVÉ — jamais une estimation de ce qui a pu se passer ensuite. C'est une
    borne basse, et c'est la seule valeur que la règle « aucun chiffre deviné »
    autorise ici. Le fichier est effacé dans tous les cas : une partie ne se
    rattrape qu'une fois.

    Rend la session enregistrée, ou None s'il n'y avait rien à rattraper.
    """
    chemin = chemin or chemin_en_cours()
    data = _lire_brut(chemin)
    fermer_session(chemin)
    jeu = data.get("jeu")
    if not isinstance(jeu, str) or not jeu:
        return None
    try:
        debut = datetime.fromisoformat(str(data.get("debut")))
        vu_a = datetime.fromisoformat(str(data.get("vu_a")))
    except (ValueError, TypeError):
        return None
    duree = int((vu_a - debut).total_seconds())
    if duree < DUREE_MINIMALE:
        return None
    enregistrer_session(jeu, debut, duree)
    log.info("Partie interrompue rattrapée : %s, %d s observées", jeu, duree)
    return Session(jeu=jeu, debut=debut, duree=duree)


def _ecrire_en_cours(jeu: str, debut: datetime, vu_a: datetime, chemin) -> None:
    chemin = chemin or chemin_en_cours()
    try:
        _ecrire_donnees({"jeu": jeu,
                         "debut": debut.isoformat(timespec="seconds"),
                         "vu_a": vu_a.isoformat(timespec="seconds")}, chemin)
    except OSError as exc:
        # Perdre le filet ne doit pas empêcher de jouer.
        log.warning("Partie en cours non notée : %s", exc)


# ─── Dérivations (pures) ───

def temps_par_jeu(hist: Historique) -> dict[str, int]:
    """Secondes par jeu, hérité COMPRIS — c'est la seule dérivation où il entre."""
    total = Counter(hist.herite)
    for s in hist.sessions:
        total[s.jeu] += s.duree
    return {gid: secondes for gid, secondes in total.items() if secondes > 0}


def temps_total(hist: Historique) -> int:
    return sum(temps_par_jeu(hist).values())


def parties_par_jeu(hist: Historique) -> dict[str, int]:
    return dict(Counter(s.jeu for s in hist.sessions))


def duree_moyenne(hist: Historique) -> int:
    """Moyenne sur les VRAIES sessions ; 0 s'il n'y en a aucune."""
    if not hist.sessions:
        return 0
    return round(sum(s.duree for s in hist.sessions) / len(hist.sessions))


def plus_longue(hist: Historique) -> Session | None:
    return max(hist.sessions, key=lambda s: s.duree, default=None)


def derniere_par_jeu(hist: Historique) -> dict[str, date]:
    dernier: dict[str, date] = {}
    for s in hist.sessions:
        jour = s.jour
        if jour > dernier.get(s.jeu, date.min):
            dernier[s.jeu] = jour
    return dernier


def jours_joues(hist: Historique) -> list[date]:
    """Jours distincts où au moins une partie a été lancée, triés."""
    return sorted({s.jour for s in hist.sessions})


def serie_actuelle(hist: Historique, aujourdhui: date | None = None) -> int:
    """Jours consécutifs joués, en cours.

    La série reste vivante si la dernière partie date d'HIER : la journée n'est
    pas finie, et l'annoncer rompue avant minuit serait faux — c'est le seul
    endroit où ce détail se décide.
    """
    jours = jours_joues(hist)
    if not jours:
        return 0
    aujourdhui = aujourdhui or date.today()
    dernier = jours[-1]
    if (aujourdhui - dernier).days > 1:
        return 0
    serie, attendu = 0, dernier
    for jour in reversed(jours):
        if jour == attendu:
            serie += 1
            attendu -= timedelta(days=1)
        elif jour < attendu:
            break
    return serie


def meilleure_serie(hist: Historique) -> int:
    jours = jours_joues(hist)
    if not jours:
        return 0
    record = courante = 1
    for precedent, jour in zip(jours, jours[1:]):
        courante = courante + 1 if (jour - precedent).days == 1 else 1
        record = max(record, courante)
    return record


def par_heure(hist: Historique) -> list[int]:
    """Secondes jouées par heure de DÉBUT (24 cases).

    Rattacher une partie à son heure de début plutôt que de l'étaler sur les
    heures traversées : c'est le moment où quelqu'un décide de jouer qui est
    intéressant, et c'est aussi le seul que le launcher observe réellement.
    """
    cases = [0] * 24
    for s in hist.sessions:
        cases[s.debut.hour] += s.duree
    return cases


def par_jour_semaine(hist: Historique) -> list[int]:
    """Secondes par jour de la semaine (0 = lundi)."""
    cases = [0] * 7
    for s in hist.sessions:
        cases[s.debut.weekday()] += s.duree
    return cases


def plage_de_predilection(hist: Historique, largeur: int = 3) -> tuple[int, int] | None:
    """Fenêtre de `largeur` heures où le plus de temps a été lancé.

    Une seule heure serait trop pointue pour dire quelque chose de vrai
    (« tu joues à 21 h » sur trois parties), une plage se reconnaît.
    """
    cases = par_heure(hist)
    if not any(cases):
        return None
    meilleur = max(range(24), key=lambda h: sum(cases[(h + i) % 24] for i in range(largeur)))
    return meilleur, (meilleur + largeur) % 24


def jour_prefere(hist: Historique) -> int | None:
    cases = par_jour_semaine(hist)
    return max(range(7), key=cases.__getitem__) if any(cases) else None


def premiere_session(hist: Historique) -> datetime | None:
    return hist.sessions[0].debut if hist.sessions else None

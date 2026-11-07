"""Le journal du correctif, relu au retour d'une partie (idée décidée par Ludo, 2026-11-05).

Chaque DLL du correctif écrit à côté de l'exe du jeu un `<dll>_accio.log` (`d3d9`, `winmm`, `dinput8`, `xinput`) :
une ligne par réglage posé, et une ligne qui le dit quand un réglage n'a pas pu s'appliquer (« NOT set », « not
found », « not the build read »…). Un joueur ne lit jamais ce fichier : un réglage resté sans effet ressemblait à un
réglage cassé, et l'issue arrivait sans la preuve (#28). Ce module trouve ces lignes, pour la partie QUI VIENT DE
FINIR seulement :

- un journal plus vieux que le début de la partie (marge 2 s, comme `config_cassee`) n'est pas de cette partie ;
- une DLL peut ajouter à son journal au lieu de le réécrire : on ne lit qu'à partir de sa DERNIÈRE ligne de
  démarrage (« Accio Launcher PC fix … ») ;
- un REPLI prévu par la DLL (« refused, again without… », « the game's own used ») n'est pas un échec : le
  correctif a réessayé sans l'option, le jeu tourne. Liste tenue avec le banc de santé de l'atelier
  (`banc_sante.py`, mêmes motifs).

Pur : aucune dépendance Qt. `GameSession` l'appelle au retour du jeu, `diagnostic` pour le rapport.
"""
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

JOURNAUX = ("d3d9_accio.log", "winmm_accio.log", "dinput8_accio.log", "xinput_accio.log")

# Ce qu'écrivent les DLL quand un réglage ne s'applique pas (relevé dans les sources du correctif 2.4.0).
_ECHEC = re.compile(r"\bNOT\b|not found|not the build read|failed|FAILED|missing|unexpected|hook refused")
# Replis prévus : la DLL retente sans l'option (ou garde celle du jeu) et le dit. Informatifs.
_REPLI = re.compile(r"refused.*again|refused, back to|game.s own used|game format kept|removed spells refused"
                    r"|Setup: not found in this exe")
_DEMARRAGE = "Accio Launcher PC fix"
_HORODATAGE = re.compile(r"^\[\d+\]\s*")
_MARGE_S = 2.0
# Au-delà, le journal est une autre histoire (build d'exe inconnu : tout échoue) ; le rapport a le fichier entier.
LIGNES_MAX = 8
_OCTETS_MAX = 256_000


@dataclass(frozen=True)
class Echec:
    """Une ligne du journal d'une DLL qui dit qu'un réglage n'a pas pu s'appliquer."""

    journal: str
    ligne: str


def lignes_en_echec(texte: str) -> tuple[str, ...]:
    """Les lignes d'échec du DERNIER démarrage écrit dans `texte`, sans horodatage, sans doublon, dans l'ordre."""
    lignes = texte.splitlines()
    depart = max((i for i, ligne in enumerate(lignes) if _DEMARRAGE in ligne), default=0)
    vues: list[str] = []
    for brute in lignes[depart:]:
        ligne = _HORODATAGE.sub("", brute).strip()
        if ligne and _ECHEC.search(ligne) and not _REPLI.search(ligne) and ligne not in vues:
            vues.append(ligne)
    return tuple(vues[:LIGNES_MAX])


def _lire(chemin: Path) -> str:
    try:
        with chemin.open("rb") as f:
            taille = f.seek(0, 2)
            f.seek(max(0, taille - _OCTETS_MAX))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def echecs(dossier_exe: Path, depuis: datetime | None = None) -> tuple[Echec, ...]:
    """Les échecs écrits par les DLL du correctif de ce dossier.

    `depuis` : début de la partie ; un journal plus ancien (marge 2 s) est ignoré. None : le dernier démarrage de
    chaque journal, quel que soit son âge (rapport « Copier le rapport »).
    """
    trouves: list[Echec] = []
    for nom in JOURNAUX:
        chemin = dossier_exe / nom
        try:
            if not chemin.is_file():
                continue
            if depuis is not None and chemin.stat().st_mtime < depuis.timestamp() - _MARGE_S:
                continue
        except OSError:
            continue
        trouves += [Echec(nom, ligne) for ligne in lignes_en_echec(_lire(chemin))]
    return tuple(trouves)


def signature(trouves: tuple[Echec, ...]) -> str:
    """Empreinte courte et stable : la même panne au lancement suivant ne se signale pas deux fois."""
    texte = "\n".join(f"{e.journal}\t{e.ligne}" for e in trouves)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16] if texte else ""

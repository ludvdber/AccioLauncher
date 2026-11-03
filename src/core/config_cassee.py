"""Reconnaître, au retour d'un jeu UE1, l'arrêt fatal que son journal raconte.

**Ce qu'on lit : le journal que le moteur écrit lui-même**, à côté de sa
configuration dans Documents (`HP.log`, `Game.log`, `hppoa.log` : le nom de
l'exe), réécrit à chaque démarrage. Une erreur fatale y laisse un bloc de
lignes `Critical:` (« appError called: », puis le message, puis l'historique).

`apres_la_partie` rend un `Arret` pour toute ligne `Critical:`, avec son genre :
« affichage » (le moteur n'a pas ouvert son rendu) se répare en remettant la
configuration ; « dessin » est l'arrêt PENDANT une image (HP3 : moins
d'anticrénelage, `reglages_graphiques.repli_apres_echec`) ; « autre » (un
`Bitmap.LoadFile`, fichier du JEU qui manque) n'a que le rapport à offrir.

**Pas de seuil de durée** : la boîte « Critical Error » garde le processus en
vie jusqu'à ce qu'on la ferme ; c'est la DATE du journal qui le rattache à
cette partie. Lecture seule, ne lève jamais.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.game_data import GameData
from src.core.post_install import destination_config

log = logging.getLogger(__name__)

# Ce qu'un journal UE1 dit d'un affichage qui n'a pas pu s'ouvrir. Comparé en
# minuscules, sur les seules lignes « Critical: ».
_SIGNES = ("rendev", "renderdevice", "viewport", "d3d11drv", "d3ddrv", "setres")
# … sauf quand l'historique montre une image EN COURS de dessin.
_EN_DESSIN = ("viewport::repaint", "ugameengine::draw")
# La fin suffit : le bloc fatal est le dernier écrit.
_FIN = 64_000
# Un journal écrit un peu AVANT le lancement noté n'est pas le nôtre ; la marge
# couvre l'arrondi des dates de fichier (2 s sous FAT, 1 s ailleurs).
_MARGE_S = 2.0

AFFICHAGE = "affichage"
DESSIN = "dessin"
AUTRE = "autre"


@dataclass(frozen=True)
class Arret:
    """Un arrêt fatal lu au journal du jeu.

    `ligne` : la première ligne « Critical: » qui porte un message, telle que
    le joueur l'a vue dans la boîte du jeu. `genre` : AFFICHAGE, DESSIN ou AUTRE.
    """
    ligne: str
    genre: str


def journal(game: GameData) -> Path | None:
    """Le journal du moteur : `<exe>.log`, dans le dossier de sa configuration."""
    pi = game.post_install
    if pi is None or not pi.config_files or not game.executable:
        return None
    nom = Path(game.executable).stem.lower() + ".log"
    dossiers: list[Path] = []
    for cf in pi.config_files:
        d = destination_config(cf.destination).parent
        if d not in dossiers:
            dossiers.append(d)
    for d in dossiers:
        try:
            for f in d.iterdir():
                if f.name.lower() == nom and f.is_file():
                    return f
        except OSError:
            continue
    return None


def _lire_la_fin(chemin: Path) -> str:
    """La fin du journal. UE1 écrit en UTF-16 avec BOM ou en ANSI selon la version.

    Le BOM est au DÉBUT et on lit la FIN : il est lu à part, et le départ de la
    lecture est aligné sur deux octets, sans quoi chaque caractère UTF-16
    serait coupé en deux.
    """
    with chemin.open("rb") as f:
        bom = f.read(2)
        f.seek(0, 2)
        taille = f.tell()
        depart = max(len(bom), taille - _FIN)
        if bom in (b"\xff\xfe", b"\xfe\xff"):
            depart += (depart - 2) % 2
            f.seek(depart)
            return f.read().decode("utf-16-le" if bom == b"\xff\xfe" else "utf-16-be",
                                   errors="replace")
        f.seek(0 if taille <= _FIN else depart)
        return f.read().decode("cp1252", errors="replace")


def arret_fatal(texte: str) -> Arret | None:
    """L'arrêt fatal que le journal raconte, None s'il n'y en a pas.

    La ligne rendue est la première « Critical: » qui porte un message (pas
    « appError called: ») : c'est celle qu'on cherche sur Discord.
    """
    critiques = [ligne.strip()[len("Critical:"):].strip()
                 for ligne in texte.splitlines()
                 if ligne.strip().startswith("Critical:")]
    ligne = next((c for c in critiques
                  if c and not c.lower().startswith("apperror called")), "")
    if not ligne:
        return None
    # Un arrêt PENDANT le dessin d'une image (historique « UGameEngine::Draw »,
    # « Viewport::Repaint ») : l'affichage s'était ouvert, la remise mentirait.
    if any(d in c.lower() for c in critiques for d in _EN_DESSIN):
        return Arret(ligne, DESSIN)
    if any(signe in c.lower() for c in critiques for signe in _SIGNES):
        return Arret(ligne, AFFICHAGE)
    return Arret(ligne, AUTRE)


def apres_la_partie(game: GameData, debut: datetime | None) -> Arret | None:
    """L'arrêt fatal que le jeu vient d'écrire dans son journal, None sinon."""
    if debut is None:
        return None
    chemin = journal(game)
    if chemin is None:
        return None
    try:
        if chemin.stat().st_mtime < debut.timestamp() - _MARGE_S:
            return None          # journal d'une partie précédente
        texte = _lire_la_fin(chemin)
    except OSError:
        return None
    arret = arret_fatal(texte)
    if arret is not None:
        log.info("%s : arrêt fatal au journal (%s, %s) : %s",
                 game.id, chemin.name, arret.genre, arret.ligne)
    return arret

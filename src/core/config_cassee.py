"""Reconnaître, au retour d'un jeu, une configuration qui l'empêche de démarrer.

Suite de `reparation_config` (Ludo, 2026-10-03 : idée retenue). Remettre la
configuration ne sert à rien si personne ne pense à le faire : le joueur dont
HP2 ne démarre plus voit une boîte « Critical Error » en anglais, la ferme, et
conclut que le jeu est cassé. Il retélécharge des gigaoctets, ou il abandonne.

**Ce qu'on lit : le journal que le moteur UE1 écrit lui-même**, à côté de sa
configuration dans Documents (`HP.log`, `Game.log`, `hppoa.log` : le nom de
l'exe). Il est réécrit à chaque démarrage, et une erreur fatale y laisse
toujours le même bloc (relevé dans un vrai `HP.log`, 2026-09-26) :

    Critical: appError called:
    Critical: Assertion failed: Bitmap.LoadFile(Filename) [File:…] [Line: 189]
    Critical: Windows GetLastError: …
    Exit: Executing UObject::StaticShutdownAfterError

**Seules les erreurs d'AFFICHAGE comptent** : « Assertion failed: RenDev » (le
moteur n'a pas pu ouvrir sa carte de rendu, cas type après le menu vidéo du
jeu), et celles qui citent la fenêtre ou le moteur de rendu dans leur
historique. Un `Bitmap.LoadFile` est un fichier du JEU qui manque : remettre la
configuration n'y ferait rien, et le proposer serait mentir (règle 108).

**Pas de seuil de durée** : la boîte « Critical Error » garde le processus en
vie jusqu'à ce qu'on la ferme. Un jeu qui ne démarre pas peut donc « durer »
une minute. C'est la DATE du journal qui dit qu'il vient de cette partie.

Lecture seule, ne lève jamais.
"""

from __future__ import annotations

import logging
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


def erreur_d_affichage(texte: str) -> str | None:
    """La ligne qui nomme l'erreur, si le journal finit sur une erreur d'affichage.

    Rend la première ligne « Critical: » qui porte un message (pas « appError
    called: »), pour la montrer telle quelle : c'est celle qu'on cherche sur
    Discord. None si aucune ligne critique ne parle d'affichage.
    """
    critiques = [ligne.strip()[len("Critical:"):].strip()
                 for ligne in texte.splitlines()
                 if ligne.strip().startswith("Critical:")]
    if not any(signe in c.lower() for c in critiques for signe in _SIGNES):
        return None
    # Un arrêt PENDANT le dessin d'une image : l'affichage s'était ouvert, la
    # configuration n'y est pour rien. Cas réel (HP3, joueur sur Intel UHD,
    # 2026-10-06) : « SetRenderTarget failed(D3DERR_INVALIDCALL) », historique
    # « … UGameEngine::Draw <- UWindowsViewport::Repaint … » — « viewport »
    # y figure, et proposer la remise aurait été mentir (règle 108).
    if any(d in c.lower() for c in critiques for d in _EN_DESSIN):
        return None
    for c in critiques:
        if c and not c.lower().startswith("appError called".lower()):
            return c
    return None


def apres_la_partie(game: GameData, debut: datetime | None) -> str | None:
    """L'erreur d'affichage que le jeu vient d'écrire, None sinon."""
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
    ligne = erreur_d_affichage(texte)
    if ligne:
        log.info("%s : erreur d'affichage au journal (%s) : %s", game.id, chemin.name, ligne)
    return ligne

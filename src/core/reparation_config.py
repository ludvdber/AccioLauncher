"""Remettre la configuration d'origine d'un jeu, sans rien retélécharger.

Remarque de Ludo (2026-10-03) : « parfois les gens font une vérification du jeu
mais c'est leur .ini qui est corrompu à cause qu'ils ont touché aux paramètres
graphiques dans le jeu ». Le cas type : HP1/HP2, menu vidéo du jeu → « Assertion
failed: RenDev », et le jeu ne redémarre plus (mémoire « options vidéo UE1 »).
Or « Vérifier / réparer » retélécharge l'archive (des gigaoctets) et réinstalle
le dossier du JEU, alors que ce fichier vit dans DOCUMENTS : la réparation ne
le touchait pas.

Ici : les fichiers que le catalogue déclare (`post_install.config_files`) sont
recopiés depuis le dossier du jeu, comme à l'installation. Ce qui était en
place est d'abord COPIÉ dans `_Launcher/configs_remplacees/<jeu>/<date>/`,
jamais effacé : le `.bak` posé à côté par `apply_config_files` est écrasé à
chaque copie, et quelqu'un qui a réglé son jeu à la main doit pouvoir le
retrouver. Les patchs du catalogue (`ini_patches`) repassent au lancement
suivant, comme toujours.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core import config as config_module
from src.core.game_data import GameData
from src.core.post_install import apply_config_files, destination_config

log = logging.getLogger(__name__)

DOSSIER = "configs_remplacees"


@dataclass(frozen=True)
class Resultat:
    remis: tuple[Path, ...]              # fichiers remis, égaux à leur modèle
    echoues: tuple[str, ...]             # destinations qui n'ont pas pu l'être
    gardes: Path | None                  # où sont les anciens, None si rien n'existait


def _dossier_du_jeu(game: GameData) -> str | None:
    return Path(game.executable).parts[0] if game.executable else None


def _modele(game: GameData, install_path: Path, source: str) -> Path:
    base = install_path / _dossier_du_jeu(game) if _dossier_du_jeu(game) else install_path
    return base / source


def disponible(game: GameData, install_path: Path) -> bool:
    """Vrai si le jeu déclare une configuration ET que ses modèles sont là."""
    pi = game.post_install
    return pi is not None and any(
        _modele(game, install_path, cf.source).is_file() for cf in pi.config_files)


def fichiers(game: GameData) -> list[Path]:
    """Les fichiers qui seront remis, pour les nommer dans la question."""
    pi = game.post_install
    return [destination_config(cf.destination) for cf in pi.config_files] if pi else []


def remettre(game: GameData, install_path: Path, maintenant: datetime | None = None) -> Resultat:
    """Garde une copie de la configuration en place, puis remet celle du jeu."""
    pi = game.post_install
    if pi is None or not pi.config_files:
        return Resultat((), (), None)
    horodatage = (maintenant or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    gardes = config_module.CONFIG_FILE_PATH.parent / DOSSIER / game.id / horodatage
    a_garder = [d for d in fichiers(game) if d.is_file()]
    for i, dest in enumerate(a_garder):
        # Deux fichiers de même nom dans deux dossiers : le second prend un numéro.
        nom = dest.name if dest.name not in {a.name for a in a_garder[:i]} else f"{i}_{dest.name}"
        try:
            gardes.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, gardes / nom)
        except OSError as exc:
            # Sans copie de côté, on ne remplace RIEN : c'est peut-être le
            # réglage que la personne a mis une soirée à trouver.
            log.warning("Configuration de %s non remise : copie de %s impossible (%s)",
                        game.id, dest, exc)
            return Resultat((), tuple(str(d) for d in fichiers(game)), None)
    paires = [(cf.source, cf.destination) for cf in pi.config_files]
    apply_config_files(install_path, _dossier_du_jeu(game), paires)

    remis, echoues = [], []
    for cf in pi.config_files:
        dest = destination_config(cf.destination)
        modele = _modele(game, install_path, cf.source)
        try:
            egal = modele.read_bytes() == dest.read_bytes()
        except OSError:
            egal = False
        (remis if egal else echoues).append(dest if egal else str(dest))
    log.info("Configuration de %s remise : %d fichier(s), %d échec(s), anciens dans %s",
             game.id, len(remis), len(echoues), gardes if a_garder else "—")
    return Resultat(tuple(remis), tuple(echoues), gardes if a_garder else None)

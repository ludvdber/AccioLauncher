r"""Captures d'écran : un dossier par jeu, HORS du dossier du jeu.

Les jeux déposaient leurs captures à côté de leur exécutable (le correctif PC
dans `screenshots\`, le moteur Unreal de HP1-HP3 dans `System\`) : désinstaller
ou réparer un jeu les emportait. Elles vivent désormais dans les Images de
l'utilisateur, `Accio Launcher/<nom du jeu>`, que le lanceur ne supprime jamais.

Deux chemins y mènent :

- **le correctif PC** (HP4 et suivants) écrit directement dans le dossier : le
  lanceur lui en donne le chemin à chaque lancement (`ScreenshotFolder` dans son
  `d3d9.ini`), sous la forme que lit le JEU — `Z:\home\…` sous Wine ;
- **les autres** gardent leur emplacement ; le lanceur en SORT les captures à
  la fin de chaque partie et quand on ouvre le dossier (bloc `screenshots` du
  catalogue), et convertit au passage les BMP d'Unreal en PNG.

Le dossier porte le nom LISIBLE du jeu, dans la langue du lanceur au moment où
il est créé ; ensuite on le retrouve sous n'importe lequel de ses noms
(`GameData.noms`) : changer de langue ne coupe pas une collection en deux.
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtGui import QImage

from src.core import reglages_correctif
from src.core.game_data import GameData

log = logging.getLogger(__name__)

NOM_RACINE = "Accio Launcher"
EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tga")
_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def racine() -> Path:
    """`Images/Accio Launcher` — résolu À L'APPEL (les tests le redirigent).

    QStandardPaths suit la redirection de Windows (OneDrive, dossier déplacé)
    comme `XDG_PICTURES_DIR` sous Linux ; à défaut, `~/Pictures`.
    """
    images = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return (Path(images) if images else Path.home() / "Pictures") / NOM_RACINE


def nom_de_dossier(nom: str) -> str:
    """Un nom de jeu devenu nom de dossier valable sous Windows ET sous Linux.

    « : » et « ? » sont interdits par Windows ; un point ou une espace finale y
    sont retirés en silence, ce qui ferait deux noms pour un même dossier.
    """
    propre = _INTERDITS.sub(" ", nom)
    propre = re.sub(r"\s+", " ", propre).strip().rstrip(". ")
    return propre or "Jeu"


def dossier(game: GameData) -> Path:
    """Le dossier des captures de ce jeu (qui n'existe pas forcément encore)."""
    base = racine()
    for nom in (game.name, *game.noms):
        candidat = base / nom_de_dossier(nom)
        if candidat.is_dir():
            return candidat
    return base / nom_de_dossier(game.name or game.id)


def images(chemin: Path) -> list[Path]:
    """Les images d'un dossier, sans descendre dans les sous-dossiers."""
    try:
        return sorted(p for p in chemin.iterdir()
                      if p.is_file() and p.suffix.lower() in EXTENSIONS)
    except OSError:
        return []


def nombre(game: GameData) -> int:
    return len(images(dossier(game)))


# ── Le correctif écrit directement dans le dossier ──

_SECTION = "Accio.Window"
_CLE = "ScreenshotFolder"


def chemin_pour_le_jeu(chemin: Path) -> str:
    """Le chemin tel que le JEU le lira : natif sous Windows, `C:\\…`/`Z:\\…` sous Wine."""
    if sys.platform == "win32":
        return str(chemin)
    from src.core import compat
    return compat.chemin_windows(chemin)


def preparer(game: GameData, install_path: Path) -> bool:
    """Au lancement : donne au correctif le dossier des captures de ce jeu.

    Seulement le NOUVEAU correctif (section `[Accio.Window]`) : l'ancien ne lit
    pas cette clé. Le dossier est créé ici — le correctif sait le faire, mais un
    dossier créé par le lanceur existe déjà quand on clique « Ouvrir ». Rend True
    si l'ini porte désormais le bon chemin.
    """
    ini = reglages_correctif.chemin_ini(install_path / Path(game.executable).parent)
    if not ini.is_file() or not reglages_correctif.est_nouveau_correctif(ini):
        return False
    cible = dossier(game)
    try:
        cible.mkdir(parents=True, exist_ok=True)
        reglages_correctif.poser_valeur(ini, _SECTION, _CLE, chemin_pour_le_jeu(cible))
    except (OSError, ValueError):
        # Le jeu démarre quand même : ses captures iront à côté de l'exe, d'où
        # `ramasser` les sortira à la fin de la partie.
        log.warning("Captures : dossier non transmis au correctif (%s)", ini, exc_info=True)
        return False
    return True


# ── Les autres : on sort leurs captures du dossier du jeu ──

def _destination(dans: Path, source: Path, extension: str) -> Path:
    """Nom daté d'après le fichier (sa date d'écriture), jamais un écrasement."""
    try:
        quand = datetime.fromtimestamp(source.stat().st_mtime)
    except OSError:
        quand = datetime.now()
    base = quand.strftime("%Y-%m-%d_%H-%M-%S")
    cible = dans / f"{base}{extension}"
    n = 2
    while cible.exists():
        cible = dans / f"{base}_{n}{extension}"
        n += 1
    return cible


def _deplacer(source: Path, dans: Path) -> bool:
    """Déplace une capture ; un BMP devient PNG (quatre fois plus léger, lisible partout).

    La source n'est supprimée qu'une fois la copie ÉCRITE : une conversion
    ratée garde le fichier d'origine, et on le déplace tel quel.
    """
    if source.suffix.lower() == ".bmp":
        image = QImage(str(source))
        if not image.isNull():
            cible = _destination(dans, source, ".png")
            if image.save(str(cible), "PNG"):
                try:
                    source.unlink()
                except OSError:
                    # La copie est là ; la source reviendra au prochain passage,
                    # et deviendra une seconde copie. Mieux vaut qu'un doublon.
                    log.warning("Captures : %s copié mais pas retiré", source)
                return True
            cible.unlink(missing_ok=True)
    cible = _destination(dans, source, source.suffix.lower())
    try:
        source.replace(cible)
    except OSError:
        # Autre volume (Images sur D:, jeux sur C:) : copier puis retirer.
        try:
            cible.write_bytes(source.read_bytes())
            source.unlink()
        except OSError:
            cible.unlink(missing_ok=True)
            log.warning("Captures : %s non déplacé", source, exc_info=True)
            return False
    return True


def a_ramasser(game: GameData, install_path: Path) -> list[Path]:
    """Les captures que le jeu a laissées dans son propre dossier."""
    trouves: list[Path] = []
    for motif in game.captures:
        try:
            trouves += [p for p in install_path.glob(motif)
                        if p.is_file() and p.suffix.lower() in EXTENSIONS]
        except (OSError, ValueError):
            continue
    return sorted(set(trouves))


def ramasser(game: GameData, install_path: Path) -> int:
    """Sort les captures du dossier du jeu vers le sien. Rend le nombre déplacé.

    N'échoue jamais : c'est un rangement, pas une opération que l'utilisateur
    attend ; ce qui n'a pas pu bouger restera pour le passage suivant.
    """
    sources = a_ramasser(game, install_path)
    if not sources:
        return 0
    cible = dossier(game)
    try:
        cible.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.warning("Captures : %s impossible à créer", cible, exc_info=True)
        return 0
    faits = sum(_deplacer(s, cible) for s in sources)
    if faits:
        log.info("Captures : %d rangée(s) dans %s", faits, cible)
    return faits

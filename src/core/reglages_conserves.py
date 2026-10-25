"""Garder les réglages du joueur quand un jeu est réinstallé (changement de version, réparation).

Relevé le 2026-10-14 (Ludo, puis le code) : changer de version SUPPRIME le
dossier du jeu, et réparer réextrait l'archive par-dessus. Les réglages rangés
À CÔTÉ de l'exécutable partaient avec : le `d3d9.ini` du correctif (image,
touches, HP4 et suivants) et la configuration des réglages graphiques. La page
des versions ne pouvait promettre que les sauvegardes.

Ici : ces fichiers sont LUS avant l'opération (`mettre_de_cote`), puis reportés
clé par clé dans le fichier neuf de la nouvelle version (`reposer`). Fusion et
non recopie : une version plus récente du correctif peut ajouter des clés ou en
retirer ; recopier l'ancien fichier les perdrait. Ce qui existe des deux côtés
prend la valeur du joueur, le reste suit la nouvelle version.

Le fichier neuf est d'abord gardé comme copie d'origine (`.origine`), pour que
« Remettre les réglages d'origine » rende ceux de la NOUVELLE version.

Les configurations rangées dans Documents (HP1 à HP3) ne sont pas concernées :
l'installation ne les écrase plus (`post_install.apply_config_files`).
"""

import logging
import re
import shutil
from pathlib import Path

from src.core import reglages_correctif, reglages_graphiques
from src.core.game_data import GameData

log = logging.getLogger(__name__)

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_CLE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*=(.*)$")


def fichiers(game: GameData, install_path: Path) -> list[tuple[Path, Path]]:
    """(fichier de réglages, sa copie d'origine), à côté de l'exécutable du jeu."""
    dossier = install_path / Path(game.executable).parent
    ini = reglages_correctif.chemin_ini(dossier)
    conf = reglages_graphiques.chemin(dossier)
    return [(ini, reglages_correctif.chemin_origine(ini)),
            (conf, reglages_graphiques.chemin_origine(conf))]


def mettre_de_cote(game: GameData, install_path: Path) -> dict[Path, bytes]:
    """Le contenu des fichiers de réglages présents, lu AVANT l'opération."""
    gardes: dict[Path, bytes] = {}
    for chemin, _origine in fichiers(game, install_path):
        try:
            if chemin.is_file():
                gardes[chemin] = chemin.read_bytes()
        except OSError:
            log.warning("Réglages : %s illisible, il ne sera pas gardé", chemin, exc_info=True)
    return gardes


def valeurs(texte: str) -> dict[tuple[str, str], str]:
    """{(section, clé) en minuscules : ligne d'origine de la clé} pour les clés ACTIVES."""
    trouvees: dict[tuple[str, str], str] = {}
    section = ""
    for ligne in texte.splitlines():
        m = _SECTION.match(ligne)
        if m:
            section = m.group(1).strip().lower()
            continue
        m = _CLE.match(ligne)
        if m:
            trouvees.setdefault((section, m.group(1).lower()), ligne.strip())
    return trouvees


def fusionner(neuf: str, ancien: str) -> tuple[str, int]:
    """Le fichier neuf avec les valeurs de l'ancien là où les deux ont la clé.

    Rend (texte, nombre de clés reprises). La mise en page, les commentaires et
    la fin de ligne du fichier neuf sont gardés.
    """
    reprises = valeurs(ancien)
    fin = "\r\n" if "\r\n" in neuf else "\n"
    lignes = neuf.split(fin)
    section = ""
    changees = 0
    for i, ligne in enumerate(lignes):
        m = _SECTION.match(ligne)
        if m:
            section = m.group(1).strip().lower()
            continue
        m = _CLE.match(ligne)
        if not m:
            continue
        ancienne = reprises.get((section, m.group(1).lower()))
        if ancienne is not None and ancienne != ligne.strip():
            lignes[i] = ancienne
            changees += 1
    return fin.join(lignes), changees


def reposer(game: GameData, install_path: Path, gardes: dict[Path, bytes]) -> int:
    """Reporte les réglages gardés dans les fichiers de la nouvelle installation.

    Rend le nombre de fichiers reposés. N'échoue jamais : le jeu est installé,
    au pire avec les réglages de la nouvelle version.
    """
    reposes = 0
    origines = dict(fichiers(game, install_path))
    for chemin, brut in gardes.items():
        try:
            ancien = brut.decode("utf-8", errors="surrogateescape")
            if chemin.is_file():
                origine = origines.get(chemin)
                if origine is not None and not origine.exists():
                    shutil.copy2(chemin, origine)
                neuf = chemin.read_bytes().decode("utf-8", errors="surrogateescape")
                texte, changees = fusionner(neuf, ancien)
                if changees:
                    tmp = chemin.with_name(chemin.name + ".tmp")
                    tmp.write_bytes(texte.encode("utf-8", errors="surrogateescape"))
                    tmp.replace(chemin)
                log.info("Réglages repris dans %s : %d clé(s)", chemin.name, changees)
            else:
                # La nouvelle version ne fournit pas ce fichier : on remet le sien.
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.write_bytes(brut)
                log.info("Réglages remis tels quels : %s", chemin)
            reposes += 1
        except OSError:
            log.warning("Réglages : %s n'a pas pu être reposé", chemin, exc_info=True)
    return reposes

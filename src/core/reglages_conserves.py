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

**Seulement ce que le joueur a CHANGÉ** (Ludo, 2026-11-13 : « les joueurs perdent leurs
paramètres ? ça ne doit pas arriver ») : une clé que le joueur n'a jamais touchée (même
valeur que la copie d'origine de l'ANCIENNE version) prend la valeur de la nouvelle. Avant,
toute l'ancienne valeur l'emportait : un défaut corrigé par une nouvelle version
(1920×1080 → l'écran, un plafond, un halo) n'atteignait jamais un joueur déjà installé.
Sans copie d'origine (un joueur qui n'a jamais rien réglé depuis le launcher avant le
2026-11-13), on ne sait pas ce qu'il a retouché à la main : tout le sien est gardé, comme
avant. Depuis, chaque installation garde sa copie d'origine (`garder_les_origines`).

Les configurations rangées dans Documents (HP1 à HP3) ne sont pas concernées :
l'installation ne les écrase plus (`post_install.apply_config_files`).
"""

import logging
import re
import shutil
from pathlib import Path

from src.core import reglages_correctif, reglages_graphiques
from src.core.game_data import GameData
from src.core.ecriture_atomique import ecrire_octets_atomique

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
    """Le contenu des fichiers de réglages présents, et de leur copie d'origine (ce que
    livrait l'ancienne version), lus AVANT l'opération."""
    gardes: dict[Path, bytes] = {}
    for chemin, origine in fichiers(game, install_path):
        for f in (chemin, origine):
            try:
                if f.is_file():
                    gardes[f] = f.read_bytes()
            except OSError:
                log.warning("Réglages : %s illisible, il ne sera pas gardé", f, exc_info=True)
    if not any(f in gardes for f, _o in fichiers(game, install_path)):
        return {}     # une copie d'origine seule ne garde rien
    return gardes


def garder_les_origines(game: GameData, install_path: Path) -> None:
    """Après une installation : la copie d'origine de chaque fichier de réglages, si elle manque.

    Elle dit à la mise à jour suivante ce que le joueur a changé (`fusionner`). Un échec
    ne coûte que cette précision.
    """
    for chemin, origine in fichiers(game, install_path):
        try:
            if chemin.is_file() and not origine.exists():
                shutil.copy2(chemin, origine)
        except OSError:
            log.warning("Réglages : copie d'origine de %s impossible", chemin, exc_info=True)


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


def fusionner(neuf: str, ancien: str, livre: str | None = None) -> tuple[str, int]:
    """Le fichier neuf avec les valeurs de l'ancien là où les deux ont la clé.

    `livre` : la copie d'origine de l'ANCIENNE version ; une clé que le joueur y a
    laissée telle quelle n'est pas reprise (la nouvelle version a le dernier mot sur ce
    qu'il n'a pas choisi). None : tout l'ancien est repris.
    Rend (texte, nombre de clés reprises). La mise en page, les commentaires et
    la fin de ligne du fichier neuf sont gardés.
    """
    reprises = valeurs(ancien)
    if livre is not None:
        d_origine = valeurs(livre)
        reprises = {k: v for k, v in reprises.items() if _valeur(d_origine.get(k)) != _valeur(v)}
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


def _valeur(ligne: str | None) -> str | None:
    """La valeur d'une ligne « Clé=valeur », sans espaces autour : « Width = 1920 » et « Width=1920 » sont égales."""
    if ligne is None:
        return None
    return ligne.split("=", 1)[1].strip()


def reposer(game: GameData, install_path: Path, gardes: dict[Path, bytes]) -> int:
    """Reporte les réglages gardés dans les fichiers de la nouvelle installation.

    Rend le nombre de fichiers reposés. N'échoue jamais : le jeu est installé,
    au pire avec les réglages de la nouvelle version.
    """
    reposes = 0
    origines = dict(fichiers(game, install_path))
    for chemin, brut in gardes.items():
        if chemin not in origines:
            continue    # une copie d'origine : elle sert de repère, elle ne se repose pas
        origine = origines[chemin]
        livre = gardes.get(origine)
        try:
            ancien = brut.decode("utf-8", errors="surrogateescape")
            if chemin.is_file():
                if livre is not None or not origine.exists():
                    # Réparation : l'ancienne copie est encore là, elle devient celle de la version posée.
                    shutil.copy2(chemin, origine)
                neuf = chemin.read_bytes().decode("utf-8", errors="surrogateescape")
                texte, changees = fusionner(
                    neuf, ancien, livre.decode("utf-8", errors="surrogateescape") if livre is not None else None)
                if changees:
                    ecrire_octets_atomique(chemin, texte.encode("utf-8", errors="surrogateescape"))
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

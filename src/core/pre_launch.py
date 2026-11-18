"""Étapes de pré-lancement d'un jeu : substitution de variables, patches INI,
fichiers à créer/supprimer, déblocage DLL.

Reçoit le `Config` et le `GameData` en paramètres — pas de couplage à GameManager.
"""

import logging
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from src.core.config import Config, get_documents_dir
from src.core.ecriture_atomique import ecrire_octets_atomique
from src.core.catalogue_blocs import IniPatch
from src.core.game_data import GameData
from src.core.post_install import apply_config_files, destination_config
from src.core.system_checks import check_d3d11_feature_level
from src.core.win_utils import remove_zone_identifier

log = logging.getLogger(__name__)

# Encodage du MOTEUR (règle 81) : UE1 écrit en ANSI, et lire en UTF-8 plantait
# pour tout profil « Frédéric ». `surrogateescape` garde à l'octet les lignes
# recopiées. Sous Wine : la page ANSI du préfixe (`_encodage_ini`), cp1252 en repli.
_INI_ENCODING = "mbcs" if sys.platform == "win32" else "cp1252"
_INI_ERRORS = "surrogateescape"


def _encodage_ini() -> str:
    """Page de codes dans laquelle le moteur lit et écrit ses INI, ici."""
    if sys.platform == "win32":
        return _INI_ENCODING
    from src.core import compat
    return compat.encodage_ansi(defaut=_INI_ENCODING)

# CRLF imposé (règle 82) : sous Linux, `os.linesep` réécrivait tout en LF.
_INI_NEWLINE = "\r\n"


def besoin_de_documents(game: GameData) -> bool:
    """Ce jeu a-t-il besoin du dossier Documents pour fonctionner ?

    LU dans le catalogue (`%DOCUMENTS%` de `pre_launch`, racine de `saves`),
    jamais une liste d'identifiants écrite ici.
    """
    if game.sauvegardes is not None and game.sauvegardes.racine == "documents":
        return True
    pl = game.pre_launch
    if pl is None:
        return False
    chemins = [*pl.create_files, *pl.delete_files, *(p.file for p in pl.ini_patches)]
    return any("%DOCUMENTS%" in c for c in chemins)


def documents_inutilisable() -> Path | None:
    """Rend le dossier Documents quand Windows n'y donne pas accès, sinon None.

    Un Documents redirigé vers un emplacement disparu (OneDrive délié) fait
    planter HP1-HP3 sur « General protection fault » (rapport réel). La sonde
    ÉCRIT pour de bon : `os.access` ignore les ACL sous Windows.
    """
    docs = get_documents_dir()
    try:
        docs.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=docs, prefix=".accio-"):
            pass
    except OSError as exc:
        log.warning("Dossier Documents inutilisable (%s) : %s", exc, docs)
        return docs
    return None


def substitute_vars(raw: str, game: GameData, config: Config) -> str:
    r"""Remplace %DOCUMENTS% et %INSTALL_DIR% par leurs vraies valeurs.

    Le catalogue écrit à la Windows ; sous POSIX « \ » n'est pas un séparateur
    (règle 77) : on normalise le GABARIT, jamais les valeurs substituées.
    """
    if sys.platform != "win32":
        raw = raw.replace("\\", "/")
    docs_dir = get_documents_dir()
    install_dir = str(config.install_path / Path(game.executable).parts[0])
    return raw.replace("%DOCUMENTS%", str(docs_dir)).replace("%INSTALL_DIR%", install_dir)


def substituer_pour_le_jeu(raw: str, game: GameData, config: Config) -> str:
    r"""Comme `substitute_vars`, pour une VALEUR que le jeu lira (INI, registre).

    Sous Linux, le jeu (sous Wine) attend un chemin Windows : antislashs
    GARDÉS, variables en `C:\users\…` ou `Z:\…` (`compat.chemin_windows`).
    """
    if sys.platform == "win32":
        return substitute_vars(raw, game, config)
    from src.core import compat
    pfx = compat.prefixe()
    dossier_jeu = config.install_path / Path(game.executable.replace("\\", "/")).parts[0]
    return (raw.replace("%DOCUMENTS%", compat.chemin_windows(get_documents_dir(), pfx))
            .replace("%INSTALL_DIR%", compat.chemin_windows(dossier_jeu, pfx)))


def resolve_safe_path(raw: str, game: GameData, config: Config) -> Path | None:
    """Résout un chemin pré-lancement avec substitution de variables et anti-path-traversal.

    Retourne None si le chemin est hors des zones autorisées (Documents ou install_path),
    ou s'il ne désigne pas un `.ini` : la zone couvre tout Documents, où vivent
    les SAUVEGARDES, et ce chemin vient du catalogue distant, qui ne fait que
    créer, supprimer ou patcher des `.ini`.
    """
    docs_dir = get_documents_dir()
    p = Path(substitute_vars(raw, game, config))
    if p.suffix.lower() != ".ini":
        log.warning("Chemin pré-lancement refusé (un .ini attendu) : %s", p)
        return None
    try:
        p.resolve().relative_to(docs_dir)
        return p
    except ValueError:
        pass
    try:
        p.resolve().relative_to(config.install_path.resolve())
        return p
    except ValueError:
        log.warning("Chemin hors zones autorisées, refusé : %s", p)
        return None


def unblock_game_dlls(system_dir: Path) -> None:
    """Supprime le flag Zone.Identifier des DLL du jeu (Windows bloque les DLL téléchargées)."""
    count = remove_zone_identifier(system_dir, pattern="*.dll")
    if count > 0:
        log.info("%d DLL débloquée(s) dans %s", count, system_dir)


def delete_pre_launch_files(game: GameData, config: Config) -> None:
    """Supprime les fichiers listés dans pre_launch.delete_files (ex: Detected.ini)."""
    if game.pre_launch is None or not game.pre_launch.delete_files:
        return
    for raw in game.pre_launch.delete_files:
        p = resolve_safe_path(raw, game, config)
        if p is None:
            continue
        if p.exists():
            try:
                p.unlink()
                log.debug("Fichier pré-lancement supprimé : %s", p)
            except OSError as exc:
                log.warning("Impossible de supprimer %s : %s", p, exc)


def create_pre_launch_files(game: GameData, config: Config) -> None:
    """Crée les fichiers vides listés dans pre_launch.create_files (ex: Running.ini)."""
    if game.pre_launch is None or not game.pre_launch.create_files:
        return
    for raw in game.pre_launch.create_files:
        p = resolve_safe_path(raw, game, config)
        if p is None:
            continue
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
            log.debug("Fichier pré-lancement créé : %s", p)
        except OSError as exc:
            log.warning("Impossible de créer %s : %s", p, exc)


def restaurer_configs_manquantes(game: GameData, config: Config) -> None:
    """Remet la configuration réglée d'un jeu quand son fichier a DISPARU.

    Règle 106 : sinon UE1 régénère son INI et ouvre son assistant sur une
    liste de cartes vidéo VIDE. Seul un fichier ABSENT est recopié ; mêmes
    gardes que l'installation.
    """
    manquants = [(cf.source, cf.destination)
                 for cf in game.post_install.config_files
                 if not destination_config(cf.destination).exists()]
    if not manquants:
        return
    log.info("Configuration absente pour %s, restaurée depuis le jeu : %s",
             game.id, ", ".join(dest for _, dest in manquants))
    game_dir = Path(game.executable).parts[0] if game.executable else None
    apply_config_files(config.install_path, game_dir, manquants)


def apply_ini_patches(game: GameData, config: Config) -> None:
    """Applique les patches INI avant le lancement du jeu.

    Patche ligne par ligne (sans configparser.write pour préserver les commentaires).
    Si la valeur cible utilise D3D11Drv et que le GPU ne supporte pas DX11,
    bascule sur la valeur de fallback (généralement D3DDrv).
    """
    if game.pre_launch is None or not game.pre_launch.ini_patches:
        return
    for patch in game.pre_launch.ini_patches:
        effective_value = patch.value
        if patch.fallback and "D3D11Drv" in patch.value and not check_d3d11_feature_level():
            log.warning("GPU ne supporte pas DX11 feature level 11_0, fallback : %s → %s",
                        patch.value, patch.fallback)
            effective_value = patch.fallback
        ecrire_cle_ini(patch, game, config, effective_value)


def _meme_nom(a: str, b: str) -> bool:
    """Sections et clés d'un ini d'UE1 se comparent SANS casse, comme le moteur :
    « [engine.engine] » est la section du catalogue, et l'écriture en ajoutait
    une seconde à côté, l'ancienne valeur restant lue (audit du 2026-11-16)."""
    return a.casefold() == b.casefold()


def _entete(ligne: str) -> str | None:
    """Le nom de la section qu'ouvre cette ligne, None si ce n'en est pas une."""
    propre = ligne.strip()
    return propre[1:-1] if propre.startswith("[") and propre.endswith("]") else None


def lire_cle_ini(patch: IniPatch, game: GameData, config: Config) -> str | None:
    """La valeur que porte `[section] clé` du fichier du patch, None si absente.

    Même lecture que l'écriture (encodage du moteur, fins de ligne
    universelles) : ce qu'on compare est exactement ce qu'on écrirait.
    """
    ini_path = resolve_safe_path(patch.file, game, config)
    if ini_path is None:
        return None
    try:
        with ini_path.open("r", encoding=_encodage_ini(), errors=_INI_ERRORS) as f:
            lignes = f.read().splitlines()
    except (OSError, UnicodeError):
        return None
    section: str | None = None
    for ligne in lignes:
        if (nom := _entete(ligne)) is not None:
            section = nom
            continue
        if section is not None and _meme_nom(section, patch.section):
            propre = ligne.strip()
            egal = propre.find("=")
            if egal > 0 and _meme_nom(propre[:egal].rstrip(), patch.key):
                return propre[egal + 1:].strip()
    return None


def ecrire_cle_ini(patch: IniPatch, game: GameData, config: Config,
                   valeur: str | None = None) -> bool:
    """Pose `[section] clé=valeur` dans le fichier du patch. True si c'est fait."""
    return ecrire_cles_ini(patch.file, patch.section,
                           {patch.key: patch.value if valeur is None else valeur}, game, config)


def ecrire_cles_ini(fichier: str, section: str, valeurs: Mapping[str, str],
                    game: GameData, config: Config) -> bool:
    """Pose chaque `clé=valeur` dans `[section]` du fichier, en UNE lecture et
    UNE écriture (règle 140). True si c'est fait.

    Patche ligne par ligne (sans configparser.write, pour garder commentaires et
    ordre) ; sections et clés sans casse, comme le moteur ; seule la PREMIÈRE
    ligne d'une clé change, toute autre ligne reste à l'octet. Un fichier
    ABSENT n'est pas créé : c'est le jeu qui l'écrit.
    """
    ini_path = resolve_safe_path(fichier, game, config)
    if ini_path is None:
        return False
    if not ini_path.exists():
        log.warning("Fichier INI introuvable, skip : %s", ini_path)
        return False
    restant = {cle: substituer_pour_le_jeu(v, game, config) for cle, v in valeurs.items()}
    # Un saut de ligne ajouterait ses propres lignes à l'ini.
    if any(c in s for s in (section, *restant, *restant.values()) for c in "\r\n"):
        log.warning("Patch INI refusé (saut de ligne) : [%s] %s", section, ", ".join(restant))
        return False
    poses = dict(restant)
    encodage = _encodage_ini()
    try:
        with ini_path.open("r", encoding=encodage,
                           errors=_INI_ERRORS) as f:
            # Lecture en « newline universel » : toutes les fins de
            # ligne sont normalisées, ce que suppose le patch ci-dessous.
            lines = f.read().splitlines(keepends=True)
        current_section: str | None = None
        for i, line in enumerate(lines):
            if (nom := _entete(line)) is not None:
                current_section = nom
                continue
            if current_section is not None and _meme_nom(current_section, section):
                stripped = line.strip()
                eq_pos = stripped.find("=")
                if eq_pos > 0:
                    lue = stripped[:eq_pos].rstrip()
                    cle = next((k for k in restant if _meme_nom(k, lue)), None)
                    if cle is not None:
                        lines[i] = f"{cle}={restant.pop(cle)}\n"
        if restant:
            # Dans SA section, après sa dernière ligne non vide. En fin de
            # fichier, la clé tombait sous la DERNIÈRE section : le lancement
            # suivant ne la trouvait toujours pas et en ajoutait une autre
            # (grand audit du 2026-11-02).
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            nouvelles = [f"{cle}={v}\n" for cle, v in restant.items()]
            debut = next((i for i, line in enumerate(lines)
                          if (nom := _entete(line)) is not None and _meme_nom(nom, section)), None)
            if debut is None:
                lines += [f"[{section}]\n", *nouvelles]
            else:
                fin = next((i for i in range(debut + 1, len(lines))
                            if _entete(lines[i]) is not None), len(lines))
                while fin > debut + 1 and not lines[fin - 1].strip():
                    fin -= 1
                lines[fin:fin] = nouvelles
        # Encodage du MOTEUR : en UTF-8, UE1 lisait « FrÃ©dÃ©ric ». Encodé
        # AVANT de toucher au fichier, puis posé d'un seul coup : un « w » le
        # vidait d'abord, et une valeur hors de la page ANSI ou un disque plein
        # laissaient le HP.ini du joueur à 0 octet (audit du 2026-10-29).
        octets = "".join(lines).replace("\n", _INI_NEWLINE).encode(encodage, _INI_ERRORS)
        ecrire_octets_atomique(ini_path, octets)
        log.info("Patch INI appliqué : [%s] %s dans %s", section,
                 ", ".join(f"{cle}={v}" for cle, v in poses.items()), ini_path)
        return True
    except (OSError, UnicodeError) as exc:
        # UnicodeError : chemin hors page ANSI, que le jeu ne lirait pas non plus.
        log.warning("Impossible de patcher %s : %s", ini_path, exc)
        return False


# Couche DPI (règle 104). Un jeu non conscient du DPI est VIRTUALISÉ : à 125 %,
# une fenêtre de 2560×1440 est CRÉÉE à 3200×1800 (mesuré sur hp8.exe), alors
# que la résolution choisie reste juste. `__COMPAT_LAYER` fait comme l'onglet
# Compatibilité sans rien écrire : la variable ne vit que dans le processus lancé.
_COMPAT_LAYER = "__COMPAT_LAYER"
_DPI_AWARE = "HighDpiAware"
# Marque que le correctif du jeu cherche dans son environnement : lui absent,
# il affiche « à lancer depuis Accio Launcher » et arrête le jeu. Posée par le
# seul launcher, à chaque lancement (Windows ici, Wine dans `compat`).
_MARQUE_LANCEMENT = "ACCIO_LAUNCH"


def env_de_lancement(dpi_aware: bool,
                     base: Mapping[str, str] | None = None) -> dict[str, str] | None:
    """Environnement à donner au jeu, ou None pour lui laisser le nôtre.

    Sous Windows il porte toujours `ACCIO_LAUNCH` (le correctif ne démarre
    qu'avec cette marque) et, pour les jeux qui le déclarent, la couche DPI.
    Une couche déjà posée (`WINXPSP3`…) est gardée. None hors Windows, où le
    lancement passe par Wine (`compat.environnement` pose la marque).
    """
    if sys.platform != "win32":
        return None
    env = dict(os.environ if base is None else base)
    env[_MARQUE_LANCEMENT] = "1"
    if dpi_aware:
        couches = env.get(_COMPAT_LAYER, "").split()
        if not any(c.lower() == _DPI_AWARE.lower() for c in couches):
            couches.append(_DPI_AWARE)
        env[_COMPAT_LAYER] = " ".join(couches)
    return env

"""Étapes de pré-lancement d'un jeu : substitution de variables, patches INI,
fichiers à créer/supprimer, déblocage DLL.

Reçoit le `Config` et le `GameData` en paramètres — pas de couplage à GameManager.
"""

import logging
import sys
from pathlib import Path

from src.core.config import Config, get_documents_dir
from src.core.game_data import GameData
from src.core.system_checks import check_d3d11_feature_level
from src.core.win_utils import remove_zone_identifier

log = logging.getLogger(__name__)

# Encodage des .ini de jeu. Ces fichiers ne nous appartiennent pas : c'est le
# MOTEUR qui les écrit, et UE1 écrit en ANSI (page de codes du système). Les
# lire en UTF-8 strict levait `UnicodeDecodeError` dès que le chemin de
# sauvegarde contenait un accent — c'est-à-dire pour tout utilisateur dont le
# profil s'appelle « Frédéric ». Cette exception dérive de `ValueError`, pas
# d'`OSError` : elle traversait le `except OSError` d'`apply_ini_patches`, puis
# `launch_game`, puis `on_play` (qui ne rattrape que RuntimeError/OSError), et
# ressortait en rapport de plantage au lieu d'un lancement de jeu.
#
# `surrogateescape` garantit l'aller-retour EXACT des octets qu'on ne touche
# pas (vérifié, y compris sur des séquences non décodables) : on ne peut donc
# pas abîmer une ligne qu'on se contente de recopier.
_INI_ENCODING = "mbcs" if sys.platform == "win32" else "utf-8"
_INI_ERRORS = "surrogateescape"


def substitute_vars(raw: str, game: GameData, config: Config) -> str:
    """Remplace %DOCUMENTS% et %INSTALL_DIR% par leurs vraies valeurs."""
    docs_dir = get_documents_dir()
    install_dir = str(config.install_path / Path(game.executable).parts[0])
    return raw.replace("%DOCUMENTS%", str(docs_dir)).replace("%INSTALL_DIR%", install_dir)


def resolve_safe_path(raw: str, game: GameData, config: Config) -> Path | None:
    """Résout un chemin pré-lancement avec substitution de variables et anti-path-traversal.

    Retourne None si le chemin est hors des zones autorisées (Documents ou install_path).
    """
    docs_dir = get_documents_dir()
    p = Path(substitute_vars(raw, game, config))
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


def apply_ini_patches(game: GameData, config: Config) -> None:
    """Applique les patches INI avant le lancement du jeu.

    Patche ligne par ligne (sans configparser.write pour préserver les commentaires).
    Si la valeur cible utilise D3D11Drv et que le GPU ne supporte pas DX11,
    bascule sur la valeur de fallback (généralement D3DDrv).
    """
    if game.pre_launch is None or not game.pre_launch.ini_patches:
        return
    for patch in game.pre_launch.ini_patches:
        ini_path = resolve_safe_path(patch.file, game, config)
        if ini_path is None:
            continue
        if not ini_path.exists():
            log.warning("Fichier INI introuvable, skip : %s", ini_path)
            continue
        effective_value = patch.value
        if patch.fallback and "D3D11Drv" in patch.value and not check_d3d11_feature_level():
            log.warning("GPU ne supporte pas DX11 feature level 11_0, fallback : %s → %s",
                        patch.value, patch.fallback)
            effective_value = patch.fallback
        value = substitute_vars(effective_value, game, config)
        try:
            lines = ini_path.read_text(
                encoding=_INI_ENCODING, errors=_INI_ERRORS).splitlines(keepends=True)
            current_section: str | None = None
            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    current_section = stripped[1:-1]
                    continue
                if current_section == patch.section:
                    eq_pos = stripped.find("=")
                    if eq_pos > 0 and stripped[:eq_pos].rstrip() == patch.key:
                        lines[i] = f"{patch.key}={value}\n"
                        found = True
                        break
            if not found:
                section_exists = any(
                    line.strip() == f"[{patch.section}]" for line in lines
                )
                if not section_exists:
                    if lines and not lines[-1].endswith("\n"):
                        lines.append("\n")
                    lines.append(f"[{patch.section}]\n")
                lines.append(f"{patch.key}={value}\n")
            # Réécrit dans l'encodage du MOTEUR, pas dans le nôtre : en UTF-8,
            # UE1 relisait « Frédéric » comme « FrÃ©dÃ©ric » et cherchait ses
            # sauvegardes dans un dossier inexistant.
            ini_path.write_text("".join(lines),
                                encoding=_INI_ENCODING, errors=_INI_ERRORS)
            log.info("Patch INI appliqué : [%s] %s=%s dans %s",
                     patch.section, patch.key, value, ini_path)
        except (OSError, UnicodeError) as exc:
            # UnicodeError couvre le cas résiduel d'un chemin impossible à
            # écrire dans la page de codes ANSI — auquel cas le jeu ne saurait
            # de toute façon pas le lire : on journalise et on lance quand même.
            log.warning("Impossible de patcher %s : %s", ini_path, exc)

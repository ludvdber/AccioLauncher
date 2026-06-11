"""Gestionnaire de catalogue + état des jeux + lancement de processus."""

import logging
import platform
import shutil
import stat
import subprocess
from datetime import date
from enum import StrEnum, auto
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from src.core.config import Config
from src.core.game_data import Catalog, GameData, load_catalog
from src.core.pre_launch import (
    apply_ini_patches,
    create_pre_launch_files,
    delete_pre_launch_files,
    unblock_game_dlls,
)
from src.core.system_checks import check_vcredist_x86

log = logging.getLogger(__name__)


class GameState(StrEnum):
    """États possibles d'un jeu."""
    NOT_INSTALLED = auto()
    DOWNLOADING = auto()
    INSTALLING = auto()
    INSTALLED = auto()


class GameEntry(NamedTuple):
    """Jeu enrichi avec son état — retourné par GameManager.get_games()."""
    game: GameData
    state: GameState


def _is_safe_relative(path_str: str) -> bool:
    """Vérifie qu'un chemin relatif ne sort pas de sa racine (anti path-traversal)."""
    normalized = path_str.replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    p = PurePosixPath(normalized)
    if p.is_absolute():
        return False
    try:
        p.relative_to(".")
    except ValueError:
        return False
    return ".." not in p.parts


class GameManager:
    """Gère le catalogue de jeux et leur état (installé, non installé, etc.)."""

    __slots__ = ("config", "_catalog", "_games", "_index", "_states", "_new_game_ids")

    def __init__(self, config: Config) -> None:
        self.config = config
        self._catalog = load_catalog()
        self._games = self._catalog.games
        self._index: dict[str, GameData] = {g.id: g for g in self._games}
        self._states: dict[str, GameState] = {
            g.id: self._detect_state(g) for g in self._games
        }
        # Jeux apparus via un reload de catalogue pendant la session (badge « NOUVEAU »)
        self._new_game_ids: set[str] = set()
        log.info("Catalogue chargé : %d jeux (v%s)", len(self._games), self._catalog.catalog_version)

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    def reload_catalog(self, catalog: Catalog) -> None:
        """Recharge le catalogue (ex: après un update distant). Préserve les états."""
        old_states = dict(self._states)
        self._catalog = catalog
        self._games = catalog.games
        self._index = {g.id: g for g in self._games}
        self._states = {}
        for g in self._games:
            if g.id in old_states:
                self._states[g.id] = old_states[g.id]
            else:
                self._states[g.id] = self._detect_state(g)
                if self._states[g.id] == GameState.NOT_INSTALLED:
                    self._new_game_ids.add(g.id)
                    log.info("Nouveau jeu disponible : %s", g.name)
        log.info("Catalogue rechargé : %d jeux (v%s)", len(self._games), catalog.catalog_version)

    def is_new(self, game_id: str) -> bool:
        """True si le jeu est apparu via un reload de catalogue et n'a pas encore été vu."""
        return game_id in self._new_game_ids

    def mark_seen(self, game_id: str) -> None:
        """Retire le badge « NOUVEAU » d'un jeu (l'utilisateur l'a sélectionné)."""
        self._new_game_ids.discard(game_id)

    def refresh_states(self) -> None:
        """Re-détecte l'état de tous les jeux sur le disque.

        Nécessaire après un changement d'install_path : les états en mémoire
        pointent sinon vers l'ancien dossier. Préserve les états transitoires
        (téléchargement/installation en cours) pour ne pas casser une opération.
        """
        for g in self._games:
            if self._states.get(g.id) in (GameState.DOWNLOADING, GameState.INSTALLING):
                continue
            self._states[g.id] = self._detect_state(g)
        log.info("États re-détectés (%d jeux)", len(self._games))

    def redetect_state(self, game_id: str) -> None:
        """Force la re-détection disque d'un seul jeu (après annulation/erreur d'opération).

        Contrairement à un set NOT_INSTALLED aveugle, ceci préserve un jeu encore
        installé quand un téléchargement de mise à jour/réparation échoue.
        """
        game = self._index.get(game_id)
        if game is not None:
            self._states[game_id] = self._detect_state(game)

    def _detect_state(self, game: GameData) -> GameState:
        """Détecte l'état d'un jeu en vérifiant le disque."""
        if not _is_safe_relative(game.executable):
            log.warning("Chemin executable suspect ignoré : %s", game.executable)
            return GameState.NOT_INSTALLED
        exe_path = self.config.install_path / game.executable
        try:
            exe_path.resolve().relative_to(self.config.install_path.resolve())
        except ValueError:
            log.warning("Path traversal détecté dans _detect_state : %s", exe_path)
            return GameState.NOT_INSTALLED
        if exe_path.exists():
            return GameState.INSTALLED
        return GameState.NOT_INSTALLED

    def get_game_by_id(self, game_id: str) -> GameData | None:
        return self._index.get(game_id)

    def get_games(self) -> list[GameEntry]:
        """Retourne la liste des jeux enrichis avec leur état."""
        return [
            GameEntry(game=game, state=self._states[game.id])
            for game in self._games
        ]

    def get_game_path(self, game_id: str) -> Path | None:
        """Retourne le chemin racine du jeu."""
        game = self._index.get(game_id)
        if game is None:
            return None
        if not _is_safe_relative(game.executable):
            return None
        return self.config.install_path / Path(game.executable).parts[0]

    def get_state(self, game_id: str) -> GameState:
        return self._states.get(game_id, GameState.NOT_INSTALLED)

    def is_installed(self, game_id: str) -> bool:
        return self._states.get(game_id) == GameState.INSTALLED

    def installed_version(self, game_id: str) -> str | None:
        """Retourne la version installée d'un jeu, ou None."""
        return self.config.installed_versions.get(game_id)

    def has_update(self, game_id: str) -> bool:
        """Vérifie si une mise à jour est disponible pour un jeu installé."""
        if not self.is_installed(game_id):
            return False
        game = self._index.get(game_id)
        if game is None:
            return False
        installed = self.installed_version(game_id)
        return installed is not None and installed != game.recommended_version

    def set_game_state(self, game_id: str, state: GameState) -> None:
        if game_id not in self._index:
            log.warning("Jeu inconnu : %s", game_id)
            return
        self._states[game_id] = state
        log.info("État de %s → %s", game_id, state)

    def launch_game(self, game_id: str) -> subprocess.Popen | None:
        """Lance le .exe du jeu en processus détaché."""
        game = self._index.get(game_id)
        if game is None:
            log.warning("Impossible de lancer un jeu inconnu : %s", game_id)
            return None
        if not _is_safe_relative(game.executable):
            log.warning("Chemin executable non sûr : %s", game.executable)
            return None
        exe_path = self.config.install_path / game.executable
        try:
            exe_path.resolve().relative_to(self.config.install_path.resolve())
        except ValueError:
            log.warning("Path traversal détecté : %s", exe_path)
            return None
        if not exe_path.exists():
            log.warning("Exécutable introuvable : %s", exe_path)
            return None

        if not check_vcredist_x86():
            raise RuntimeError("vcredist_x86_missing")

        # Pré-lancement (cf. src/core/pre_launch.py)
        unblock_game_dlls(exe_path.parent)
        delete_pre_launch_files(game, self.config)
        create_pre_launch_files(game, self.config)
        apply_ini_patches(game, self.config)

        log.info("Lancement de %s (%s)", game.name, exe_path)
        popen_kwargs: dict = {"cwd": str(exe_path.parent)}
        if platform.system() == "Windows":
            popen_kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            popen_kwargs["start_new_session"] = True
        return subprocess.Popen([str(exe_path)], **popen_kwargs)

    def apply_pre_launch_patches(self, game: GameData) -> None:
        """Façade rétro-compat — délègue à pre_launch.apply_ini_patches."""
        apply_ini_patches(game, self.config)

    # ──────────────────── Stats de jeu ────────────────────

    def add_playtime(self, game_id: str, seconds: int) -> None:
        """Cumule le temps d'une session et date la dernière partie (persisté en config)."""
        if game_id not in self._index or seconds <= 0:
            return
        self.config.playtime_seconds[game_id] = (
            self.config.playtime_seconds.get(game_id, 0) + int(seconds)
        )
        self.config.last_played[game_id] = date.today().isoformat()
        self.config.save()
        log.info("Temps de jeu de %s : +%d s (total %d s)",
                 game_id, seconds, self.config.playtime_seconds[game_id])

    def get_playtime(self, game_id: str) -> int:
        """Temps de jeu cumulé en secondes (0 si jamais joué)."""
        return self.config.playtime_seconds.get(game_id, 0)

    def last_played(self, game_id: str) -> str | None:
        """Date ISO de la dernière session, ou None."""
        return self.config.last_played.get(game_id)

    def save_installed_version(self, game_id: str, version: str | None = None) -> None:
        """Sauvegarde la version du jeu installé dans la config."""
        game = self._index.get(game_id)
        if game is None:
            return
        ver = version or game.recommended_version
        self.config.installed_versions[game_id] = ver
        self.config.save()

    def uninstall_game(self, game_id: str) -> bool:
        """Supprime le dossier du jeu. Retourne True si succès."""
        game_path = self.get_game_path(game_id)
        game = self._index.get(game_id)
        if game is None or game_path is None or not game_path.exists():
            log.warning("Rien à désinstaller pour %s (chemin: %s)", game_id, game_path)
            return False
        try:
            game_path.resolve().relative_to(self.config.install_path.resolve())
        except ValueError:
            log.error("Path traversal détecté lors de la désinstallation : %s", game_path)
            return False

        log.info("Désinstallation de %s — suppression de : %s", game.name, game_path)
        try:
            def _force_remove_readonly(_func, path, _exc_info):
                """Retire le flag read-only et réessaie la suppression."""
                Path(path).chmod(stat.S_IWRITE)
                _func(path)
            shutil.rmtree(game_path, onexc=_force_remove_readonly)
        except OSError as exc:
            log.error("Échec de la suppression de %s : %s", game_path, exc)
            return False
        self._states[game_id] = GameState.NOT_INSTALLED
        self.config.installed_versions.pop(game_id, None)
        self.config.save()
        log.info("Désinstallation terminée : %s (%s supprimé)", game_id, game_path)
        return True

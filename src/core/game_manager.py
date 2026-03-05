import logging
import platform
import shutil
import subprocess
from enum import StrEnum, auto
from pathlib import Path, PurePosixPath

from src.core.config import Config
from src.core.game_data import Catalog, GameData, GameVersion, load_catalog

log = logging.getLogger(__name__)


class GameState(StrEnum):
    """États possibles d'un jeu."""
    NOT_INSTALLED = auto()
    DOWNLOADING = auto()
    INSTALLING = auto()
    INSTALLED = auto()


def _is_safe_relative(path_str: str) -> bool:
    """Vérifie qu'un chemin relatif ne sort pas de sa racine (anti path-traversal)."""
    p = PurePosixPath(path_str.replace("\\", "/"))
    if p.is_absolute():
        return False
    try:
        p.relative_to(".")
    except ValueError:
        return False
    return ".." not in p.parts


class GameManager:
    """Gère le catalogue de jeux et leur état (installé, non installé, etc.)."""

    __slots__ = ("config", "_catalog", "_games", "_index", "_states")

    def __init__(self, config: Config) -> None:
        self.config = config
        self._catalog = load_catalog()
        self._games = self._catalog.games
        self._index: dict[str, GameData] = {g.id: g for g in self._games}
        self._states: dict[str, GameState] = {
            g.id: self._detect_state(g) for g in self._games
        }
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
                    log.info("Nouveau jeu disponible : %s", g.name)
        log.info("Catalogue rechargé : %d jeux (v%s)", len(self._games), catalog.catalog_version)

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

    def get_games(self) -> list[dict]:
        """Retourne la liste des jeux enrichis avec leur état."""
        return [
            {"game": game, "state": self._states[game.id]}
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

        log.info("Lancement de %s (%s)", game.name, exe_path)
        popen_kwargs: dict = {"cwd": str(exe_path.parent)}
        if platform.system() == "Windows":
            popen_kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            popen_kwargs["start_new_session"] = True
        return subprocess.Popen([str(exe_path)], **popen_kwargs)

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
            shutil.rmtree(game_path)
        except OSError as exc:
            log.error("Échec de la suppression de %s : %s", game_path, exc)
            return False
        self._states[game_id] = GameState.NOT_INSTALLED
        self.config.installed_versions.pop(game_id, None)
        self.config.save()
        log.info("Désinstallation terminée : %s (%s supprimé)", game_id, game_path)
        return True

import logging
import shutil
import subprocess
from enum import StrEnum, auto
from pathlib import Path

from src.core.config import Config
from src.core.game_data import GameData, load_catalog

log = logging.getLogger(__name__)


class GameState(StrEnum):
    """États possibles d'un jeu."""
    NOT_INSTALLED = auto()
    DOWNLOADING = auto()
    INSTALLING = auto()
    INSTALLED = auto()


class GameManager:
    """Gère le catalogue de jeux et leur état (installé, non installé, etc.)."""

    __slots__ = ("config", "_games", "_index", "_states")

    def __init__(self, config: Config) -> None:
        self.config = config
        self._games = load_catalog()
        self._index: dict[str, GameData] = {g.id: g for g in self._games}
        # État initial détecté depuis le disque
        self._states: dict[str, GameState] = {
            g.id: self._detect_state(g) for g in self._games
        }
        log.info("Catalogue chargé : %d jeux", len(self._games))

    def _detect_state(self, game: GameData) -> GameState:
        """Détecte l'état d'un jeu en vérifiant le disque."""
        exe_path = self.config.install_path / game.executable
        if exe_path.exists():
            return GameState.INSTALLED
        return GameState.NOT_INSTALLED

    def get_game_by_id(self, game_id: str) -> GameData | None:
        """Retourne un jeu par son identifiant en O(1)."""
        return self._index.get(game_id)

    def get_games(self) -> list[dict]:
        """Retourne la liste des jeux enrichis avec leur état."""
        return [
            {"game": game, "state": self._states[game.id]}
            for game in self._games
        ]

    def get_game_path(self, game_id: str) -> Path | None:
        """Retourne le chemin racine du jeu (premier dossier du chemin de l'exécutable)."""
        game = self._index.get(game_id)
        if game is None:
            return None
        # Premier composant du chemin = dossier racine du jeu (ex: "HP3" pour "HP3/system/hppoa.exe")
        return self.config.install_path / Path(game.executable).parts[0]

    def is_installed(self, game_id: str) -> bool:
        """Vérifie si le dossier ET l'exécutable existent."""
        return self._states.get(game_id) == GameState.INSTALLED

    def set_game_state(self, game_id: str, state: GameState) -> None:
        """Met à jour l'état d'un jeu (utilisé par le downloader/installer)."""
        if game_id not in self._index:
            log.warning("Jeu inconnu : %s", game_id)
            return
        self._states[game_id] = state
        log.info("État de %s → %s", game_id, state)

    def launch_game(self, game_id: str) -> bool:
        """Lance le .exe du jeu en processus détaché. Retourne True si succès."""
        game = self._index.get(game_id)
        if game is None:
            log.warning("Impossible de lancer un jeu inconnu : %s", game_id)
            return False

        exe_path = self.config.install_path / game.executable
        if not exe_path.exists():
            log.warning("Exécutable introuvable : %s", exe_path)
            return False

        log.info("Lancement de %s (%s)", game.name, exe_path)
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(exe_path.parent),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return True

    def uninstall_game(self, game_id: str) -> bool:
        """Supprime le dossier du jeu. Retourne True si succès."""
        game_path = self.get_game_path(game_id)
        game = self._index.get(game_id)
        if game is None or game_path is None or not game_path.exists():
            log.warning("Rien à désinstaller pour %s (chemin: %s)", game_id, game_path)
            return False

        log.info("Désinstallation de %s — suppression de : %s", game.name, game_path)
        try:
            shutil.rmtree(game_path)
        except OSError as exc:
            log.error("Échec de la suppression de %s : %s", game_path, exc)
            return False
        self._states[game_id] = GameState.NOT_INSTALLED
        log.info("Désinstallation terminée : %s (%s supprimé)", game_id, game_path)
        return True

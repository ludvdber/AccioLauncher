import logging
import os
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

        self._apply_pre_launch_patches(game)

        log.info("Lancement de %s (%s)", game.name, exe_path)
        popen_kwargs: dict = {"cwd": str(exe_path.parent)}
        if platform.system() == "Windows":
            popen_kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            popen_kwargs["start_new_session"] = True
        return subprocess.Popen([str(exe_path)], **popen_kwargs)

    @staticmethod
    def _resolve_documents_path(raw: str) -> Path:
        """Résout %DOCUMENTS% vers le dossier Mes Documents de l'utilisateur."""
        docs = Path(os.path.expandvars("%USERPROFILE%")) / "Documents"
        return Path(raw.replace("%DOCUMENTS%", str(docs)))

    def _apply_pre_launch_patches(self, game: GameData) -> None:
        """Applique les patches INI avant le lancement du jeu (ligne par ligne, sans configparser.write)."""
        if game.pre_launch is None or not game.pre_launch.ini_patches:
            return
        docs_dir = (Path(os.path.expandvars("%USERPROFILE%")) / "Documents").resolve()
        for patch in game.pre_launch.ini_patches:
            ini_path = self._resolve_documents_path(patch.file)
            # Protection path traversal : le fichier doit rester sous Documents
            try:
                ini_path.resolve().relative_to(docs_dir)
            except ValueError:
                log.warning("Chemin INI hors de Documents, refusé : %s", ini_path)
                continue
            if not ini_path.exists():
                log.warning("Fichier INI introuvable, skip : %s", ini_path)
                continue
            value = patch.value.replace("%DOCUMENTS%", str(docs_dir))
            try:
                lines = ini_path.read_text(encoding="utf-8").splitlines(keepends=True)
                current_section: str | None = None
                found = False
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        current_section = stripped[1:-1]
                        continue
                    if current_section == patch.section:
                        # Matcher key= ou key = (insensible aux espaces autour du =)
                        eq_pos = stripped.find("=")
                        if eq_pos > 0 and stripped[:eq_pos].rstrip() == patch.key:
                            lines[i] = f"{patch.key}={value}\n"
                            found = True
                            break
                if not found:
                    # Ajouter la section si elle n'existe pas, puis la clé
                    section_exists = any(
                        l.strip() == f"[{patch.section}]" for l in lines
                    )
                    if not section_exists:
                        if lines and not lines[-1].endswith("\n"):
                            lines.append("\n")
                        lines.append(f"[{patch.section}]\n")
                    lines.append(f"{patch.key}={value}\n")
                ini_path.write_text("".join(lines), encoding="utf-8")
                log.info("Patch INI appliqué : [%s] %s=%s dans %s",
                         patch.section, patch.key, value, ini_path)
            except OSError as exc:
                log.warning("Impossible de patcher %s : %s", ini_path, exc)

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

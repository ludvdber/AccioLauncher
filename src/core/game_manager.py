import logging
import platform
import shutil
import subprocess
import sys
from enum import StrEnum, auto
from pathlib import Path, PurePosixPath

from src.core.config import Config, get_documents_dir
from src.core.game_data import Catalog, GameData, GameVersion, load_catalog

log = logging.getLogger(__name__)


def check_vcredist_x86() -> bool:
    """Vérifie si le Visual C++ Redistributable x86 (2015-2022) est installé."""
    if sys.platform != "win32":
        return True
    import winreg
    for sub_key in (
        r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_key) as key:
                val, _ = winreg.QueryValueEx(key, "Installed")
                if val == 1:
                    return True
        except OSError:
            continue
    return False


def check_d3d11_feature_level() -> bool:
    """Vérifie si le GPU supporte DirectX 11 (feature level 11_0).

    Crée un device D3D11 temporaire pour tester le support matériel.
    Retourne False si le GPU ne supporte pas DX11 ou en cas d'erreur.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        d3d11 = ctypes.WinDLL("d3d11")
        device = ctypes.c_void_p()
        feature_level = ctypes.c_uint()
        context = ctypes.c_void_p()
        # D3D_DRIVER_TYPE_HARDWARE=1, D3D11_SDK_VERSION=7
        hr = d3d11.D3D11CreateDevice(
            None, 1, None, 0, None, 0, 7,
            ctypes.byref(device), ctypes.byref(feature_level), ctypes.byref(context),
        )
        if hr < 0:
            return False
        supported = feature_level.value >= 0xb000  # D3D_FEATURE_LEVEL_11_0
        # Libérer les objets COM (IUnknown::Release = vtable index 2)
        for obj in (context, device):
            if obj.value:
                vtable = ctypes.cast(
                    ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0],
                    ctypes.POINTER(ctypes.c_void_p),
                )
                release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
                release(obj)
        return supported
    except Exception:
        return False


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

        # Pré-lancement : débloquer DLL, supprimer/créer fichiers, appliquer patches INI
        self._unblock_game_dlls(exe_path.parent)
        self._delete_pre_launch_files(game)
        self._create_pre_launch_files(game)
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
    def _unblock_game_dlls(system_dir: Path) -> None:
        """Supprime le flag Zone.Identifier des DLL du jeu (Windows bloque les DLL téléchargées)."""
        if sys.platform != "win32":
            return
        import os
        count = 0
        for dll in system_dir.glob("*.dll"):
            try:
                os.remove(str(dll) + ":Zone.Identifier")
                count += 1
            except OSError:
                pass
        if count > 0:
            log.info("%d DLL débloquée(s) dans %s", count, system_dir)

    def _delete_pre_launch_files(self, game: GameData) -> None:
        """Supprime les fichiers listés dans pre_launch.delete_files (ex: Detected.ini)."""
        if game.pre_launch is None or not game.pre_launch.delete_files:
            return
        docs_dir = get_documents_dir()
        install_dir = str(self.config.install_path / Path(game.executable).parts[0])
        for raw in game.pre_launch.delete_files:
            resolved = raw.replace("%DOCUMENTS%", str(docs_dir)).replace("%INSTALL_DIR%", install_dir)
            p = Path(resolved)
            # Protection path traversal
            try:
                p.resolve().relative_to(docs_dir)
            except ValueError:
                try:
                    p.resolve().relative_to(self.config.install_path.resolve())
                except ValueError:
                    log.warning("Chemin delete_files hors zones autorisées : %s", p)
                    continue
            if p.exists():
                try:
                    p.unlink()
                    log.debug("Fichier pré-lancement supprimé : %s", p)
                except OSError as exc:
                    log.warning("Impossible de supprimer %s : %s", p, exc)

    def _create_pre_launch_files(self, game: GameData) -> None:
        """Crée les fichiers vides listés dans pre_launch.create_files (ex: Running.ini)."""
        if game.pre_launch is None or not game.pre_launch.create_files:
            return
        docs_dir = get_documents_dir()
        install_dir = str(self.config.install_path / Path(game.executable).parts[0])
        for raw in game.pre_launch.create_files:
            resolved = raw.replace("%DOCUMENTS%", str(docs_dir)).replace("%INSTALL_DIR%", install_dir)
            p = Path(resolved)
            try:
                p.resolve().relative_to(docs_dir)
            except ValueError:
                try:
                    p.resolve().relative_to(self.config.install_path.resolve())
                except ValueError:
                    log.warning("Chemin create_files hors zones autorisées : %s", p)
                    continue
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
                log.debug("Fichier pré-lancement créé : %s", p)
            except OSError as exc:
                log.warning("Impossible de créer %s : %s", p, exc)

    def _apply_pre_launch_patches(self, game: GameData) -> None:
        """Applique les patches INI avant le lancement du jeu (ligne par ligne, sans configparser.write)."""
        if game.pre_launch is None or not game.pre_launch.ini_patches:
            return
        docs_dir = get_documents_dir()
        install_dir = str(self.config.install_path / Path(game.executable).parts[0])
        for patch in game.pre_launch.ini_patches:
            raw_file = patch.file.replace("%DOCUMENTS%", str(docs_dir)).replace("%INSTALL_DIR%", install_dir)
            ini_path = Path(raw_file)
            # Protection path traversal : le fichier doit rester sous Documents ou install_dir
            try:
                ini_path.resolve().relative_to(docs_dir)
            except ValueError:
                try:
                    ini_path.resolve().relative_to(self.config.install_path.resolve())
                except ValueError:
                    log.warning("Chemin INI hors des zones autorisées, refusé : %s", ini_path)
                    continue
            if not ini_path.exists():
                log.warning("Fichier INI introuvable, skip : %s", ini_path)
                continue
            # Fallback renderer : si la valeur utilise D3D11Drv et le GPU ne supporte pas DX11
            effective_value = patch.value
            if patch.fallback and "D3D11Drv" in patch.value and not check_d3d11_feature_level():
                log.warning("GPU ne supporte pas DX11 feature level 11_0, fallback : %s → %s",
                            patch.value, patch.fallback)
                effective_value = patch.fallback
            value = effective_value.replace("%DOCUMENTS%", str(docs_dir)).replace("%INSTALL_DIR%", install_dir)
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
            def _force_remove_readonly(_func, path, _exc_info):
                """Retire le flag read-only et réessaie la suppression."""
                import stat
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

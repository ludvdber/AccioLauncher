import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PathLike = str | Path

# --- Mode frozen (PyInstaller) ---
IS_FROZEN = getattr(sys, "frozen", False)

if IS_FROZEN:
    # PyInstaller extrait les données dans sys._MEIPASS
    _BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    # Mode développement : racine du projet
    _BUNDLE_DIR = Path(__file__).parent.parent

# --- Chemins des ressources embarquées ---
GAMES_JSON_PATH = _BUNDLE_DIR / "data" / "games.json"
ASSETS_DIR = _BUNDLE_DIR.parent / "assets" if not IS_FROZEN else _BUNDLE_DIR / "assets"

# --- Chemins utilisateur (toujours dans ~/Games/AccioLauncher) ---
DEFAULT_INSTALL_PATH = Path.home() / "Games" / "AccioLauncher"
DEFAULT_CACHE_PATH = DEFAULT_INSTALL_PATH / ".cache"
CONFIG_FILE_PATH = DEFAULT_INSTALL_PATH / "config.json"

APP_VERSION = "0.1.0"


@dataclass(slots=True)
class Config:
    """Charge et sauvegarde les préférences utilisateur."""

    install_path: Path = field(default_factory=lambda: DEFAULT_INSTALL_PATH)
    cache_path: Path = field(default_factory=lambda: DEFAULT_CACHE_PATH)
    langue: str = "fr"
    delete_archives: bool = True
    resume_downloads: bool = True
    autoplay_videos: bool = True
    mute_videos: bool = False
    check_updates: bool = True
    dismissed_launcher_version: str = ""
    installed_versions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def exists(cls) -> bool:
        """Vérifie si un fichier de configuration existe déjà."""
        return CONFIG_FILE_PATH.exists()

    @classmethod
    def load(cls) -> "Config":
        """Charge la configuration depuis le fichier JSON."""
        if CONFIG_FILE_PATH.exists():
            try:
                data = json.loads(CONFIG_FILE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return cls()
            return cls(
                install_path=Path(data.get("install_path", str(DEFAULT_INSTALL_PATH))),
                cache_path=Path(data.get("cache_path", str(DEFAULT_CACHE_PATH))),
                langue=data.get("langue", "fr"),
                delete_archives=data.get("delete_archives", True),
                resume_downloads=data.get("resume_downloads", True),
                autoplay_videos=data.get("autoplay_videos", True),
                mute_videos=data.get("mute_videos", False),
                check_updates=data.get("check_updates", True),
                dismissed_launcher_version=data.get("dismissed_launcher_version", ""),
                installed_versions=data.get("installed_versions", {}),
            )
        return cls()

    def save(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE_PATH.write_text(
            json.dumps(
                {
                    "install_path": str(self.install_path),
                    "cache_path": str(self.cache_path),
                    "langue": self.langue,
                    "delete_archives": self.delete_archives,
                    "resume_downloads": self.resume_downloads,
                    "autoplay_videos": self.autoplay_videos,
                    "mute_videos": self.mute_videos,
                    "check_updates": self.check_updates,
                    "dismissed_launcher_version": self.dismissed_launcher_version,
                    "installed_versions": self.installed_versions,
                },
                indent=4,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

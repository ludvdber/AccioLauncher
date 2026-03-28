import ctypes
import ctypes.wintypes
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PathLike = str | Path


def get_documents_dir() -> Path:
    """Retourne le vrai dossier Documents via l'API Windows (gère OneDrive, dossiers redirigés).

    Fallback sur %USERPROFILE%/Documents si l'API échoue ou hors Windows.
    """
    if sys.platform == "win32":
        try:
            CSIDL_PERSONAL = 5
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, 0, buf)
            if buf.value:
                return Path(buf.value).resolve()
        except (OSError, ValueError):
            pass
    return (Path(os.path.expandvars("%USERPROFILE%")) / "Documents").resolve()


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

LOCAL_CATALOG_PATH = DEFAULT_INSTALL_PATH / "catalog_cache.json"

APP_VERSION = "0.4.5"


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
            except (json.JSONDecodeError, OSError) as exc:
                import logging
                logging.getLogger(__name__).warning("Config corrompue, valeurs par défaut : %s", exc)
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
        """Sauvegarde la configuration dans le fichier JSON (écriture atomique)."""
        CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(
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
        )
        # Écriture atomique : tmp + rename pour éviter la corruption
        fd, tmp_path = tempfile.mkstemp(
            dir=CONFIG_FILE_PATH.parent, suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, CONFIG_FILE_PATH)
        except OSError:
            # Nettoyage si le replace échoue
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

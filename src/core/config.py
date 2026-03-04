import json
from dataclasses import dataclass, field
from pathlib import Path

# Type aliases (Python 3.12+)
type PathLike = str | Path

# Chemins par défaut
DEFAULT_INSTALL_PATH = Path.home() / "Games" / "AccioLauncher"
DEFAULT_CACHE_PATH = DEFAULT_INSTALL_PATH / ".cache"
GAMES_JSON_PATH = Path(__file__).parent.parent / "data" / "games.json"
CONFIG_FILE_PATH = DEFAULT_INSTALL_PATH / "config.json"

APP_VERSION = "1.0.0"


@dataclass(slots=True)
class Config:
    """Charge et sauvegarde les préférences utilisateur."""

    install_path: Path = field(default_factory=lambda: DEFAULT_INSTALL_PATH)
    cache_path: Path = field(default_factory=lambda: DEFAULT_CACHE_PATH)
    langue: str = "fr"

    @classmethod
    def exists(cls) -> bool:
        """Vérifie si un fichier de configuration existe déjà."""
        return CONFIG_FILE_PATH.exists()

    @classmethod
    def load(cls) -> "Config":
        """Charge la configuration depuis le fichier JSON."""
        if CONFIG_FILE_PATH.exists():
            data = json.loads(CONFIG_FILE_PATH.read_text(encoding="utf-8"))
            return cls(
                install_path=Path(data.get("install_path", str(DEFAULT_INSTALL_PATH))),
                cache_path=Path(data.get("cache_path", str(DEFAULT_CACHE_PATH))),
                langue=data.get("langue", "fr"),
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
                },
                indent=4,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

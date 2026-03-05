import json
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import GAMES_JSON_PATH

# Type alias pour les entrées de registre post-installation
type RegistryEntries = list[str]


@dataclass(frozen=True, slots=True)
class PostInstall:
    """Données de post-installation d'un jeu."""
    registry: RegistryEntries = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GameData:
    """Données immuables d'un jeu du catalogue."""

    id: str
    name: str
    year: int
    description: str
    developer: str
    archive_name: str
    archive_size_mb: int
    download_url: str
    executable: str
    cover_image: str
    tags: tuple[str, ...] = ()
    post_install: PostInstall = field(default_factory=PostInstall)

    @classmethod
    def from_dict(cls, data: dict) -> "GameData":
        """Crée un GameData depuis un dictionnaire JSON."""
        pi = data.get("post_install", {})
        return cls(
            id=data["id"],
            name=data["name"],
            year=data["year"],
            description=data["description"],
            developer=data["developer"],
            archive_name=data["archive_name"],
            archive_size_mb=data["archive_size_mb"],
            download_url=data["download_url"],
            executable=data["executable"],
            cover_image=data["cover_image"],
            tags=tuple(data.get("tags", [])),
            post_install=PostInstall(registry=pi.get("registry", [])),
        )


def load_catalog() -> tuple[GameData, ...]:
    """Charge le catalogue complet depuis games.json. Retourne un tuple immuable."""
    raw = json.loads(GAMES_JSON_PATH.read_text(encoding="utf-8"))
    return tuple(GameData.from_dict(entry) for entry in raw)

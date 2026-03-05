import json
from dataclasses import dataclass, field

from src.core.config import GAMES_JSON_PATH

RegistryEntries = list[str]


@dataclass(frozen=True, slots=True)
class PostInstall:
    """Données de post-installation d'un jeu."""
    registry: RegistryEntries = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ChangelogEntry:
    """Une entrée du changelog (une version)."""
    version: str
    date: str
    changes: tuple[str, ...]


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
    version: str = "1.0"
    changelog: tuple[ChangelogEntry, ...] = ()
    tags: tuple[str, ...] = ()
    post_install: PostInstall = field(default_factory=PostInstall)

    @classmethod
    def from_dict(cls, data: dict) -> "GameData":
        """Crée un GameData depuis un dictionnaire JSON."""
        required = ("id", "name", "year", "description", "developer",
                     "archive_name", "archive_size_mb", "download_url",
                     "executable", "cover_image")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"Champs manquants dans games.json : {missing}")
        pi = data.get("post_install", {})
        changelog = tuple(
            ChangelogEntry(
                version=entry.get("version", "1.0"),
                date=entry.get("date", ""),
                changes=tuple(entry.get("changes", [])),
            )
            for entry in data.get("changelog", [])
        )
        return cls(
            id=data["id"],
            name=data["name"],
            year=int(data["year"]),
            description=data["description"],
            developer=data["developer"],
            archive_name=data["archive_name"],
            archive_size_mb=int(data["archive_size_mb"]),
            download_url=data["download_url"],
            executable=data["executable"],
            cover_image=data["cover_image"],
            version=data.get("version", "1.0"),
            changelog=changelog,
            tags=tuple(data.get("tags", [])),
            post_install=PostInstall(registry=pi.get("registry", [])),
        )


def load_catalog() -> tuple[GameData, ...]:
    """Charge le catalogue complet depuis games.json. Retourne un tuple immuable."""
    import logging
    log = logging.getLogger(__name__)
    try:
        raw = json.loads(GAMES_JSON_PATH.read_text(encoding="utf-8"))
        return tuple(GameData.from_dict(entry) for entry in raw)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.error("Impossible de charger le catalogue de jeux : %s", e)
        return ()

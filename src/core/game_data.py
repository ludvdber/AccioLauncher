import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import GAMES_JSON_PATH

log = logging.getLogger(__name__)

RegistryEntries = list[str]


@dataclass(frozen=True, slots=True)
class PostInstall:
    """Données de post-installation d'un jeu."""
    registry: RegistryEntries = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GameVersion:
    """Une version téléchargeable d'un jeu."""
    version: str
    date: str
    download_url: str | None
    download_parts: list[str] | None
    size_mb: int
    changes: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "GameVersion":
        return cls(
            version=data.get("version", "1.0"),
            date=data.get("date", ""),
            download_url=data.get("download_url"),
            download_parts=data.get("download_parts"),
            size_mb=int(data.get("size_mb", 0)),
            changes=tuple(data.get("changes", [])),
        )


@dataclass(frozen=True, slots=True)
class GameData:
    """Données immuables d'un jeu du catalogue."""

    id: str
    name: str
    year: int
    description: str
    developer: str
    executable: str
    cover_image: str
    latest_version: str
    recommended_version: str
    versions: tuple[GameVersion, ...] = ()
    tags: tuple[str, ...] = ()
    post_install: PostInstall = field(default_factory=PostInstall)

    @property
    def current_download(self) -> GameVersion | None:
        """Retourne la version recommandée (ou la dernière disponible)."""
        for v in self.versions:
            if v.version == self.recommended_version:
                return v
        return self.versions[-1] if self.versions else None

    def get_version(self, version_str: str) -> GameVersion | None:
        """Retourne une version spécifique par son numéro."""
        for v in self.versions:
            if v.version == version_str:
                return v
        return None

    @classmethod
    def from_dict(cls, data: dict) -> "GameData":
        """Crée un GameData depuis un dictionnaire JSON."""
        required = ("id", "name", "year", "description", "developer",
                     "executable", "cover_image")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"Champs manquants dans games.json : {missing}")
        pi = data.get("post_install", {})
        versions = tuple(
            GameVersion.from_dict(v) for v in data.get("versions", [])
        )
        return cls(
            id=data["id"],
            name=data["name"],
            year=int(data["year"]),
            description=data["description"],
            developer=data["developer"],
            executable=data["executable"],
            cover_image=data["cover_image"],
            latest_version=data.get("latest_version", "1.0"),
            recommended_version=data.get("recommended_version", "1.0"),
            versions=versions,
            tags=tuple(data.get("tags", [])),
            post_install=PostInstall(registry=pi.get("registry", [])),
        )


@dataclass(frozen=True, slots=True)
class Catalog:
    """Catalogue complet de jeux avec métadonnées."""
    catalog_version: str
    catalog_url: str
    games: tuple[GameData, ...]


def _parse_catalog(raw: dict | list) -> Catalog:
    """Parse un JSON brut en Catalog. Accepte l'ancien format (liste) et le nouveau (dict)."""
    if isinstance(raw, list):
        # Ancien format : liste directe de jeux
        games = tuple(GameData.from_dict(entry) for entry in raw)
        return Catalog(catalog_version="0", catalog_url="", games=games)
    return Catalog(
        catalog_version=raw.get("catalog_version", "0"),
        catalog_url=raw.get("catalog_url", ""),
        games=tuple(GameData.from_dict(g) for g in raw.get("games", [])),
    )


def load_catalog(path: Path | None = None) -> Catalog:
    """Charge le catalogue depuis games.json. Retourne un Catalog."""
    src = path or GAMES_JSON_PATH
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
        return _parse_catalog(raw)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.error("Impossible de charger le catalogue de jeux : %s", e)
        return Catalog(catalog_version="0", catalog_url="", games=())

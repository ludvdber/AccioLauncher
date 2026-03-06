import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import GAMES_JSON_PATH

log = logging.getLogger(__name__)

RegistryEntries = list[str]


@dataclass(frozen=True, slots=True)
class ConfigFile:
    """Fichier de configuration à copier après installation."""
    source: str       # relatif au dossier du jeu (ex: "config/hppoa.ini")
    destination: str   # chemin avec ~ (ex: "~/Documents/MonJeu/hppoa.ini")

    @classmethod
    def from_dict(cls, data: dict) -> "ConfigFile":
        return cls(source=data["source"], destination=data["destination"])


@dataclass(frozen=True, slots=True)
class IniPatch:
    """Patch INI à appliquer avant le lancement du jeu."""
    file: str       # chemin avec %DOCUMENTS% comme variable
    section: str    # ex: "FirstRun"
    key: str        # ex: "Reconfig"
    value: str      # ex: "0"

    @classmethod
    def from_dict(cls, data: dict) -> "IniPatch":
        return cls(file=data["file"], section=data["section"],
                   key=data["key"], value=data["value"])


@dataclass(frozen=True, slots=True)
class PreLaunch:
    """Données de pré-lancement d'un jeu."""
    ini_patches: tuple[IniPatch, ...] = ()


@dataclass(frozen=True, slots=True)
class PostInstall:
    """Données de post-installation d'un jeu."""
    registry: RegistryEntries = field(default_factory=list)
    config_files: tuple[ConfigFile, ...] = ()


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
    pre_launch: PreLaunch | None = None

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
        pl = data.get("pre_launch")
        versions = tuple(
            GameVersion.from_dict(v) for v in data.get("versions", [])
        )
        pre_launch: PreLaunch | None = None
        if pl:
            pre_launch = PreLaunch(
                ini_patches=tuple(IniPatch.from_dict(p) for p in pl.get("ini_patches", [])),
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
            post_install=PostInstall(
                registry=pi.get("registry", []),
                config_files=tuple(ConfigFile.from_dict(cf) for cf in pi.get("config_files", [])),
            ),
            pre_launch=pre_launch,
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
    """Charge le catalogue le plus récent (embarqué ou cache local)."""
    from src.core.version_utils import compare_versions
    from src.core.config import LOCAL_CATALOG_PATH as _LOCAL_CATALOG_PATH

    src = path or GAMES_JSON_PATH
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
        catalog = _parse_catalog(raw)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.error("Impossible de charger le catalogue de jeux : %s", e)
        catalog = Catalog(catalog_version="0", catalog_url="", games=())

    # Charger le cache local s'il est plus récent
    if path is None:
        try:
            if _LOCAL_CATALOG_PATH.exists():
                raw_cache = json.loads(_LOCAL_CATALOG_PATH.read_text(encoding="utf-8"))
                cached = _parse_catalog(raw_cache)
                if cached.games and compare_versions(cached.catalog_version, catalog.catalog_version) > 0:
                    log.info("Cache local plus récent : v%s > v%s", cached.catalog_version, catalog.catalog_version)
                    return cached
        except (json.JSONDecodeError, OSError, ValueError) as e:
            log.warning("Cache catalogue invalide, ignoré : %s", e)

    return catalog

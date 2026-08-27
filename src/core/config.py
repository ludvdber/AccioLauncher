import ctypes
import ctypes.wintypes
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


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
    if sys.platform == "win32":
        return (Path(os.path.expandvars("%USERPROFILE%")) / "Documents").resolve()
    # Hors Windows, `expandvars` ne connaît pas %USERPROFILE% : la chaîne restait
    # littérale et `resolve()` fabriquait « <dossier courant>/%USERPROFILE%/Documents ».
    return (Path.home() / "Documents").resolve()


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
I18N_DIR = _BUNDLE_DIR / "data" / "i18n"

# Langue proposee quand rien n'est encore choisi. Volontairement l'anglais
# et non le francais : le launcher vise un public international, et le
# premier lancement demande de toute facon la langue (onboarding).
DEFAULT_LANGUAGE = "en"
ASSETS_DIR = _BUNDLE_DIR.parent / "assets" if not IS_FROZEN else _BUNDLE_DIR / "assets"

# --- Chemins utilisateur (toujours dans ~/Games/AccioLauncher) ---
#
# UN SEUL sous-dossier pour tout ce qui appartient au launcher, et la racine
# pour les jeux — rien d'autre. Avant le 2026-08-26, `~/Games/AccioLauncher`
# melangeait les dossiers de jeux (HP2, HP7, HP8...) avec `.cache`, `trailers`,
# `accio_launcher.log`, `catalog_cache.json` et `config.json`. Quelqu'un qui
# ouvre ce dossier veut y voir ses JEUX ; le reste est de la plomberie, et une
# plomberie visible invite a la supprimer au hasard.
#
# Le nom commence par un tiret bas pour se poser en tete de liste dans
# l'explorateur et pour ne ressembler a aucun identifiant de jeu.
DEFAULT_INSTALL_PATH = Path.home() / "Games" / "AccioLauncher"
LAUNCHER_DIR_NAME = "_Launcher"
# Donnees du launcher : emplacement FIXE, independant de `install_path`.
# Deplacer ses jeux sur un autre disque ne doit ni deplacer la configuration ni
# rendre les journaux introuvables au moment ou on en a besoin.
LAUNCHER_DATA_PATH = DEFAULT_INSTALL_PATH / LAUNCHER_DIR_NAME
CONFIG_FILE_PATH = LAUNCHER_DATA_PATH / "config.json"
LOCAL_CATALOG_PATH = LAUNCHER_DATA_PATH / "catalog_cache.json"
LOG_DIR = LAUNCHER_DATA_PATH / "logs"

# Le cache de telechargement, LUI, suit les jeux : une archive de 7 Go doit
# atterrir sur le meme volume que son extraction, sinon la verification
# d'espace disque ment et le rangement final devient une copie.
DEFAULT_CACHE_PATH = DEFAULT_INSTALL_PATH / LAUNCHER_DIR_NAME / "cache"


def cache_pour(install_path: Path) -> Path:
    """Ou ranger les archives quand les jeux vivent dans `install_path`."""
    return Path(install_path) / LAUNCHER_DIR_NAME / "cache"


# Traductions fournies par l'utilisateur, appliquees par-dessus celles
# embarquees : permet a un traducteur de tester son fichier sans release.
USER_I18N_DIR = LAUNCHER_DATA_PATH / "i18n"

APP_VERSION = "1.0.1"


def _as_str(value: object, default: str) -> str:
    """Coerce une valeur JSON en str, sinon le défaut (config trafiquée à la main)."""
    return value if isinstance(value, str) else default


def _as_dict(value: object) -> dict:
    """Coerce une valeur JSON en dict, sinon un dict vide (config trafiquée à la main)."""
    return value if isinstance(value, dict) else {}


def _as_bool(value: object, default: bool) -> bool:
    """Coerce une valeur JSON en bool, sinon le défaut."""
    return value if isinstance(value, bool) else default


def _as_vitesse(value: object) -> float:
    """Dernière vitesse observée, en octets/s. 0.0 si absurde ou mal typée.

    Une vitesse négative ferait annoncer un temps de téléchargement négatif ;
    une chaîne faisait lever `float()` — rattrapé, mais toute la config
    retombait alors aux valeurs par défaut pour un seul champ décoratif.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value) if value > 0 else 0.0


def _as_map(value: object, type_valeur: type) -> dict:
    """Dict dont on ne garde QUE les paires (str → type_valeur) exploitables.

    `_as_dict` ne validait que le conteneur. Une VALEUR mal typée traversait
    donc `Config.load()` et n'explosait que bien plus loin, sur un site qui ne
    pouvait rien en faire : `last_played` mélangeant str et int faisait lever
    `last_played_game_id()` — appelée au démarrage pour choisir le jeu affiché,
    donc rapport de plantage à l'ouverture. Une config abîmée doit retomber sur
    les valeurs par défaut, c'est ce que `load()` promet.
    """
    brut = _as_dict(value)
    return {k: v for k, v in brut.items()
            if isinstance(k, str) and isinstance(v, type_valeur)
            and not isinstance(v, bool)}


@dataclass(slots=True)
class Config:
    """Charge et sauvegarde les préférences utilisateur."""

    install_path: Path = field(default_factory=lambda: DEFAULT_INSTALL_PATH)
    cache_path: Path = field(default_factory=lambda: DEFAULT_CACHE_PATH)
    langue: str = DEFAULT_LANGUAGE
    theme: str = "poudlard"
    season: str = "auto"  # particules saisonnières : auto | aucune | halloween | noel
    delete_archives: bool = True
    autoplay_videos: bool = True
    # Muet par DÉFAUT : un logiciel qui fait du bruit dès sa première
    # ouverture est une mauvaise surprise, et le son se rétablit d'un clic
    # sur la barre audio qui accompagne la vidéo.
    mute_videos: bool = True
    # L'utilisateur veut-il les bandes-annonces ? Répondu à l'écran 4 de
    # l'assistant, modifiable dans les Paramètres. PERSISTÉ et non traité en
    # choix jetable : un téléchargement coupé (fermeture, réseau) reprend alors
    # tout seul au démarrage suivant, au lieu de laisser sept vidéos sur huit
    # et personne pour s'en apercevoir. Défaut False — un launcher mis à jour
    # depuis une version qui embarquait les vidéos ne doit rien télécharger
    # sans qu'on le lui demande.
    trailers_optin: bool = False
    # Dernière vitesse de téléchargement observée (octets/s), pour estimer
    # une durée AVANT de cliquer : « 2,4 Go » ne décide personne, « ≈ 3 min » si.
    last_download_speed: float = 0.0
    discord_presence: bool = True
    dismissed_launcher_version: str = ""
    # Un seul remerciement Ko-fi (cap des 10 h de jeu) dans la vie du launcher.
    kofi_milestone_thanked: bool = False
    installed_versions: dict[str, str] = field(default_factory=dict)
    # Stats de jeu : cumul par jeu (secondes) et date de dernière session (ISO)
    playtime_seconds: dict[str, int] = field(default_factory=dict)
    last_played: dict[str, str] = field(default_factory=dict)
    # Langue choisie POUR CHAQUE JEU (id → code i18n). Distincte de `langue`,
    # qui est celle de l'interface : un francophone peut vouloir jouer en
    # anglais, et c'est justement l'absence de bascule qui bloquait tout le
    # monde — pas le défaut retenu. Voir `GameManager.game_language`.
    game_language: dict[str, str] = field(default_factory=dict)

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
                if not isinstance(data, dict):
                    raise ValueError(f"racine JSON de type {type(data).__name__}, attendu objet")
                return cls(
                    install_path=Path(_as_str(data.get("install_path"), str(DEFAULT_INSTALL_PATH))),
                    cache_path=Path(_as_str(data.get("cache_path"), str(DEFAULT_CACHE_PATH))),
                    # Tous les champs texte passent par `_as_str` : il n'y avait
                    # aucune raison que deux d'entre eux soient protégés et
                    # trois non — `langue=42` traversait et arrivait tel quel
                    # jusqu'au sélecteur de langue.
                    langue=_as_str(data.get("langue"), DEFAULT_LANGUAGE),
                    theme=_as_str(data.get("theme"), "poudlard"),
                    season=_as_str(data.get("season"), "auto"),
                    delete_archives=_as_bool(data.get("delete_archives"), True),
                    autoplay_videos=_as_bool(data.get("autoplay_videos"), True),
                    mute_videos=_as_bool(data.get("mute_videos"), True),
                    trailers_optin=_as_bool(data.get("trailers_optin"), False),
                    last_download_speed=_as_vitesse(data.get("last_download_speed")),
                    discord_presence=_as_bool(data.get("discord_presence"), True),
                    dismissed_launcher_version=_as_str(
                        data.get("dismissed_launcher_version"), ""),
                    kofi_milestone_thanked=_as_bool(
                        data.get("kofi_milestone_thanked"), False),
                    installed_versions=_as_map(data.get("installed_versions"), str),
                    playtime_seconds=_as_map(data.get("playtime_seconds"), int),
                    last_played=_as_map(data.get("last_played"), str),
                    game_language=_as_map(data.get("game_language"), str),
                )
            except (json.JSONDecodeError, OSError, ValueError, TypeError, AttributeError) as exc:
                import logging
                logging.getLogger(__name__).warning("Config corrompue, valeurs par défaut : %s", exc)
                return cls()
        return cls()

    def save(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON (écriture atomique)."""
        CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(
            {
                "install_path": str(self.install_path),
                "cache_path": str(self.cache_path),
                "langue": self.langue,
                "theme": self.theme,
                "season": self.season,
                "delete_archives": self.delete_archives,
                "autoplay_videos": self.autoplay_videos,
                "mute_videos": self.mute_videos,
                "trailers_optin": self.trailers_optin,
                "last_download_speed": self.last_download_speed,
                "discord_presence": self.discord_presence,
                "dismissed_launcher_version": self.dismissed_launcher_version,
                "kofi_milestone_thanked": self.kofi_milestone_thanked,
                "installed_versions": self.installed_versions,
                "playtime_seconds": self.playtime_seconds,
                "last_played": self.last_played,
                "game_language": self.game_language,
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


# --- Migration de l'ancienne arborescence (avant le 2026-08-26) ---

# Ce que la racine contenait en vrac, et ou chaque chose va desormais. Les
# dossiers de JEUX n'y figurent pas : ils restent exactement ou ils sont, et
# c'est tout l'interet de l'operation.
#
# Les destinations sont TOUTES relatives a la racine, sans exception. Elles ne
# l'etaient pas : huit d'entre elles partaient du dossier de donnees et la
# neuvieme de la racine, si bien que la boucle devait deviner laquelle par un
# prefixe. Une entree ajoutee sans connaitre cette convention tacite serait
# allee au mauvais endroit, en silence, dans le seul code du projet dont une
# erreur se paie en reinstallation de plusieurs gigaoctets.
_A_DEPLACER = tuple(
    (ancien, f"{LAUNCHER_DIR_NAME}/{destination}") for ancien, destination in (
        ("config.json", "config.json"),
        ("catalog_cache.json", "catalog_cache.json"),
        ("i18n", "i18n"),
        ("trailers", "trailers"),
        ("accio_launcher.log", "logs/accio_launcher.log"),
        ("accio_launcher.log.1", "logs/accio_launcher.log.1"),
        ("accio_launcher.log.2", "logs/accio_launcher.log.2"),
        ("accio_launcher.log.3", "logs/accio_launcher.log.3"),
        (".cache", "cache"),
    )
)


def migrer_arborescence(racine: Path | None = None) -> list[str]:
    """Range l'ancien fourre-tout dans `_Launcher/`. Idempotent, sans reseau.

    Doit tourner AVANT `Config.exists()` : sans elle, un `config.json` reste a
    l'ancien emplacement, le launcher le croit absent et rouvre l'assistant de
    premier lancement — a quelqu'un qui a deja huit jeux installes.

    Tout se passe sur le meme volume, donc chaque deplacement est un renommage :
    mesure sur le dossier reel, l'ensemble prend quelques millisecondes meme
    avec 1 Go de bandes-annonces. Ce qui existe deja a l'arrivee n'est jamais
    ecrase — on prefere laisser un doublon a l'ancien emplacement plutot que de
    detruire ce qui a ete ecrit depuis.

    Retourne la liste de ce qui a bouge (vide si rien a faire), pour le journal.
    """
    racine = Path(racine) if racine is not None else DEFAULT_INSTALL_PATH
    if not racine.is_dir():
        return []
    donnees = racine / LAUNCHER_DIR_NAME
    deplaces: list[str] = []

    for ancien_nom, destination in _A_DEPLACER:
        source = racine / ancien_nom
        if not source.exists():
            continue
        cible = racine / destination
        if cible.exists():
            continue
        try:
            cible.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, cible)
        except OSError as exc:
            # Un fichier verrouille (journal ouvert par une autre instance) ne
            # doit pas empecher le reste : on reessaiera au prochain demarrage.
            log.warning("Migration impossible pour %s : %s", ancien_nom, exc)
            continue
        deplaces.append(ancien_nom)

    if deplaces:
        _corriger_cache_path(donnees / "config.json", racine)
    return deplaces


def _corriger_cache_path(fichier: Path, racine: Path) -> None:
    """Repointe `cache_path` s'il designe encore l'ancien `.cache`.

    Le chemin du cache est PERSISTE dans la configuration : deplacer le dossier
    sans corriger la valeur ferait recreer un `.cache` a la racine au premier
    telechargement, et l'operation n'aurait servi a rien.
    """
    try:
        data = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    ancien = data.get("cache_path")
    if not isinstance(ancien, str):
        return
    if Path(ancien) != racine / ".cache":
        return
    data["cache_path"] = str(cache_pour(Path(data.get("install_path", racine))))
    try:
        fichier.write_text(json.dumps(data, indent=4, ensure_ascii=False),
                           encoding="utf-8")
    except OSError as exc:
        log.warning("cache_path non corrige : %s", exc)

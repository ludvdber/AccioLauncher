"""Le catalogue des jeux : versions, fiche de jeu, chargement et fusion.

Les blocs secondaires et leurs validateurs vivent dans `catalogue_blocs`.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import GAMES_JSON_PATH
from src.core.chemins import refus_de_chemin
from src.core.catalogue_blocs import (  # noqa: F401  (réexportés)
    _tags_valides,
    _https_ou_rien,
    _sha256_valide,
    _taille_mo,
    _loc,
    ConfigFile,
    IniPatch,
    GameLanguage,
    LanguageRegistry,
    ManetteRegistre,
    LangueFichiers,
    LanguageFiles,
    _INI_INTERDIT_NOM,
    _INI_INTERDIT_VALEUR,
    _parse_language_files,
    _parse_manette_registre,
    _parse_language_registry,
    Resolution,
    _parse_resolution,
    PreLaunch,
    PostInstall,
    _annee_valide,
    _ips_max_valide,
    _url_aide_valide,
    _sous_dossier_valide,
    _MAX_SURCHARGES_DLL,
    _surcharges_dll_valides,
    RACINES_SAUVEGARDES,
    Sauvegardes,
    FORMATS_EMPLACEMENTS,
    _motif_sur,
    _tous_les_noms,
    _touche_capture,
    _motifs_captures,
    _parse_sauvegardes,
    _JETON_SUR,
    Trailer,
    _parse_trailers,
    Contributor,
    _parse_contributors,
)

log = logging.getLogger(__name__)

# Le jeu se joue-t-il à la manette ? Trois réponses, jamais davantage : un
# vocabulaire FERMÉ, parce que le libellé affiché en dépend et que le catalogue
# est distant. Toute autre valeur vaut « non renseigné » (rien ne s'affiche).
NIVEAUX_MANETTE = ("yes", "partial", "no")


def _niveau_manette(valeur: object) -> str:
    """`yes` / `partial` / `no`, sinon vide. Jamais une valeur devinée."""
    if isinstance(valeur, str) and valeur in NIVEAUX_MANETTE:
        return valeur
    if valeur not in (None, ""):
        log.warning("Niveau de manette inconnu ignoré : %r", valeur)
    return ""


@dataclass(frozen=True, slots=True)
class GameVersion:
    """Une version téléchargeable d'un jeu."""
    version: str
    date: str
    download_url: str | None
    download_parts: list[str] | None
    size_mb: int
    changes: tuple[str, ...]
    # Empreintes SHA-256 (hex) — optionnelles : la vérification est sautée si absentes.
    sha256: str | None = None              # fichier final (téléchargement simple)
    sha256_parts: tuple[str, ...] = ()     # une empreinte par part (multi-parts)

    @property
    def is_available(self) -> bool:
        """True si cette version a réellement une archive à télécharger.

        Une entrée de catalogue peut exister sans source publiée : un jeu
        annoncé dont les archives ne sont pas encore en ligne. Sans ce
        contrôle, le bouton « TÉLÉCHARGER » reste actif, le téléchargeur
        échoue sur « Aucune URL de téléchargement », et l'utilisateur reçoit
        « Vérifiez votre connexion internet » — le launcher accuse sa
        connexion alors que c'est le catalogue qui est incomplet.
        """
        return bool(self.download_url or self.download_parts)

    @classmethod
    def from_dict(cls, data: dict) -> "GameVersion":
        return cls(
            version=data.get("version", "1.0"),
            date=data.get("date", ""),
            download_url=_https_ou_rien(data.get("download_url")),
            download_parts=_https_ou_rien(data.get("download_parts")),
            size_mb=_taille_mo(data.get("size_mb", 0)),
            changes=tuple(_loc(data, "changes", [])),
            sha256=_sha256_valide(data.get("sha256")),
            sha256_parts=tuple(
                h for h in (_sha256_valide(x) for x in data.get("sha256_parts", []) or ())
                if h is not None
            ),
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
    # Runtimes exigés par le jeu, en plus du socle commun. Déclaré par le
    # CATALOGUE (donc modifiable sans republier l'exécutable) et non codé en
    # dur : HP7 réclame Visual C++ 2005, qui est un runtime distinct du
    # 2015-2022 vérifié pour tous les jeux. Sans cette déclaration, HP7 se
    # serait lancé puis refermé aussitôt, sans le moindre message.
    requires: tuple[str, ...] = ()
    # Mise en garde propre à CE jeu, affichée dans le bandeau d'alerte avant
    # le téléchargement ET une fois installé. Déclarée par le CATALOGUE, donc
    # traduisible (bloc `i18n`) et modifiable à distance : le cas qui l'a fait
    # naître est HP7 partie 2, dont une DLL est mise en quarantaine par les
    # antivirus — le jeu s'installe « avec succès » puis refuse de démarrer,
    # sans le moindre message. Vide pour les sept autres jeux : un bandeau ne
    # s'affiche que lorsqu'il y a une DÉVIATION à signaler.
    warning: str = ""
    warning_url: str = ""   # « En savoir plus » — https uniquement, validé au parsing
    # Langues proposées par le jeu + ce qu'elles écrivent dans le registre.
    # None quand le jeu n'en propose pas par le registre (seuls HP7a et HP7b le
    # font) ; sans aucun bloc de langue, le sélecteur n'apparaît nulle part.
    language_registry: LanguageRegistry | None = None
    # Même chose pour un jeu qui lit sa langue dans ses FICHIERS (HP1). Un jeu
    # déclare l'un OU l'autre ; `langues` rend celui qui existe.
    language_files: LanguageFiles | None = None
    # Où le jeu range « jouer à la manette » (HP5, HP6) ; None ailleurs.
    manette_registre: ManetteRegistre | None = None
    # Ce jeu doit-il être lancé en se déclarant conscient du DPI ?
    #
    # Windows VIRTUALISE un programme qui ne l'est pas : sur un écran mis à
    # l'échelle, il multiplie par le facteur tout ce que le programme demande,
    # fenêtre comprise. Invisible en plein écran exclusif ; visible dès qu'une
    # vraie fenêtre existe. Mesuré le 2026-08-30 sur les deux parties de HP7,
    # que leur wrapper `d3d9.dll` force en mode fenêtré : 3200×1800 sur un
    # écran de 2560×1440 à 125 %, soit exactement le facteur d'échelle.
    #
    # Déclaré PAR JEU et par le CATALOGUE, comme `requires` — donc modifiable à
    # distance sans republier l'exécutable, et surtout : les six autres jeux ne
    # changent pas de comportement. Consigne explicite de Ludo (2026-08-30),
    # et c'est la bonne règle — aucun d'eux n'a été mesuré, et un jeu qui va
    # bien n'a pas besoin qu'on lui change son environnement de lancement.
    dpi_aware: bool = False
    # Les options vidéo DU JEU sont-elles un piège ?
    #
    # Relevé le 2026-09-20 dans HP1 et HP2 : une seule carte de rendu est
    # livrée, `d3d11drv.dll`. Ni SoftDrv, ni D3DDrv, ni OpenGLDrv (vérifié,
    # zéro fichier). Or le menu vidéo du moteur, lui, les propose TOUTES —
    # elles sont écrites dans le .ini d'origine. En choisir une autre donne un
    # paquet introuvable, donc `RenDev` nul, donc « Assertion failed: RenDev
    # [WinViewport.cpp:351] » à l'initialisation : le jeu ne redémarre plus.
    #
    # À partir de HP5 le moteur change et ses réglages fonctionnent : le champ
    # est donc PAR JEU, et rien ne s'affiche pour ceux qui vont bien.
    display_locked: bool = False
    # Le jeu se RELANCE-t-il lui-même (le processus lancé meurt, un autre prend
    # sa place) ? Vrai pour HP1 et HP2, dont l'assistant UE1 ré-exécute un
    # enfant au chargement d'une sauvegarde : le launcher attend alors 10 s
    # avant de les croire fermés. Mesuré le 2026-10-07 (audit P6-005) : HP3 à
    # HP6 ne se relancent pas, et leur joueur attendait ces 10 s pour rien
    # devant son bureau. Faux par défaut, donc sans attente.
    relance: bool = False
    # « Se joue à la manette » : `yes`, `partial` ou `no`, vide tant que le jeu
    # n'a pas été ESSAYÉ manette en main (une affirmation fausse discrédite la
    # fiche, donc « non renseigné » ne s'affiche pas). Par jeu et dans le
    # catalogue, comme `requires` : la réponse diffère d'un jeu à l'autre et
    # change quand un correctif arrive. `controller_note` dit CE qui manque
    # (traduisible), en infobulle de la pastille.
    controller: str = ""
    controller_note: str = ""
    # Où écrire la taille de la fenêtre (`catalogue_blocs.Resolution`) ; None :
    # le launcher ne règle pas la résolution de ce jeu.
    resolution: Resolution | None = None
    # Année de scolarité que ce jeu raconte — 1 à 7, ou 0 pour « hors
    # programme ».
    #
    # Elle vient du CATALOGUE et jamais du RANG du jeu dans la liste, et c'est
    # tout l'intérêt du champ : le catalogue accueillera un jour la Coupe du
    # Monde de Quidditch, qui n'est l'année de personne. Déduire l'année d'un
    # index aurait fait de ce jeu une « 9ᵉ année » et décalé tout ce qui le
    # suit ; sans `annee`, il est simplement hors des cours.
    #
    # Une année peut porter PLUSIEURS jeux : les deux parties des Reliques de
    # la Mort sont la même septième année, celle qui ne s'est pas passée à
    # Poudlard. C'est ce que disent leurs titres, donc le modèle le dit aussi.
    annee: int = 0
    # Où le jeu range ses sauvegardes ; None tant qu'on ne l'a pas relevé.
    sauvegardes: Sauvegardes | None = None
    # DLL que le jeu LIVRE et que Wine fournit aussi : sous Linux, Wine
    # charge SA version si on ne lui dit rien, même quand celle du jeu est à
    # côté de l'exe (vérifié sous Wine 9.0, docs/LINUX.md § 3). Le jeu
    # démarre alors sans son wrapper — plus de fenêtré forcé, de bride FPS
    # ni de champ de vision corrigé —, sans que rien ne le signale. Chaque nom
    # part en `n,b` (la DLL du jeu d'abord) dans `WINEDLLOVERRIDES`.
    #
    # Relevé DANS les archives, jamais deviné : c'est l'intersection entre ce
    # qu'elles livrent et ce que Wine fournit. Ignoré sous Windows, qui charge
    # d'office la DLL du dossier du jeu. Par jeu et dans le catalogue, comme
    # `dpi_aware` : un jeu ajouté déclare les siennes sans nouvelle release.
    dll_overrides: tuple[str, ...] = ()
    # Plafond d'images/s sous Linux (0 = aucun), passé à DXVK (`DXVK_FRAME_RATE`).
    # HP3 : sous Windows, c'est dgVoodoo qui le tient (`FPSLimit = 60`) ; sous
    # Proton dgVoodoo plante et c'est DXVK qui rend le jeu (2026-10-01), donc le
    # plafond doit voyager AVEC le jeu, pas avec le wrapper. Ignoré sous Windows.
    max_fps: int = 0
    # Réglages du correctif PC (HP4-HP6) que le lanceur peut changer, CONFIRMÉS
    # en jeu un par un (`src/core/reglages_correctif.py`). Dans le catalogue et
    # non dans le code : un réglage vu en jeu un mardi doit pouvoir s'ouvrir le
    # mardi, sans republier l'exécutable. Un identifiant que ce lanceur ne
    # connaît pas est ignoré à l'affichage.
    fix_settings: tuple[str, ...] = ()
    # Tous les noms du jeu, une entrée par langue du catalogue. Le dossier des
    # captures porte le nom LISIBLE du jeu ; quelqu'un qui change la langue du
    # lanceur doit retrouver le sien, pas en voir naître un second.
    noms: tuple[str, ...] = ()
    # Bloc `screenshots` : la touche de capture du jeu, telle qu'on la montre
    # (« F12 »), et où le JEU dépose lui-même ses captures (motifs relatifs au
    # dossier des jeux) — le lanceur les en sort vers le dossier des captures,
    # pour qu'une désinstallation ne les emporte pas. Mêmes gardes que `saves`.
    touche_capture: str = ""
    captures: tuple[str, ...] = ()

    @property
    def langues(self) -> "LanguageRegistry | LanguageFiles | None":
        """Le bloc de langues du jeu, registre ou fichiers : ce que voit l'UI."""
        return self.language_registry or self.language_files

    @property
    def langue_par_fichiers(self) -> bool:
        """True si la langue passe par les FICHIERS du jeu. Le registre, déclaré,
        l'emporte toujours — la même règle que `langues`, en un seul endroit
        (un test a greffé un registre sur HP1, qui a aussi ses fichiers : tester
        `language_files` d'abord partait sur le mauvais chemin)."""
        return self.language_registry is None and self.language_files is not None

    @property
    def current_download(self) -> GameVersion | None:
        """Retourne la version recommandée (ou la dernière disponible)."""
        for v in self.versions:
            if v.version == self.recommended_version:
                return v
        return self.versions[-1] if self.versions else None

    @property
    def is_downloadable(self) -> bool:
        """True si le jeu a au moins une version réellement téléchargeable.

        Faux pour un jeu annoncé au catalogue dont aucune archive n'est encore
        publiée : l'UI affiche « Bientôt disponible » à la place du bouton.
        """
        return any(v.is_available for v in self.versions)

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

        # La présence d'une clé ne dit rien de son contenu : `"name": null`
        # passait le contrôle et donnait une fiche de jeu sans titre. Un jeu mal
        # formé doit être IGNORÉ par `_parse_catalog`, pas affiché à moitié.
        for champ in ("id", "name", "developer", "executable", "cover_image"):
            valeur = data[champ]
            if not isinstance(valeur, str) or not valeur.strip():
                raise ValueError(
                    f"Champ {champ!r} invalide dans games.json : {valeur!r} "
                    "(chaîne non vide attendue)")

        # Validation anti path-traversal de l'executable au parsing (défense en
        # profondeur) : la barrière commune à tout chemin venu du dehors.
        executable = data["executable"]
        raison = refus_de_chemin(executable)
        if raison is not None:
            raise ValueError(f"executable non sûr ({raison}) : {executable[:60]!r}")
        # Le manager en tire le dossier du jeu (son premier composant) :
        # « . » ou « ./ » passeraient la barrière sans nommer aucun fichier.
        if not [c for c in executable.replace("\\", "/").split("/") if c not in ("", ".")]:
            raise ValueError(f"executable sans nom de fichier : {executable!r}")
        pi = data.get("post_install", {})
        pl = data.get("pre_launch")
        versions = tuple(
            GameVersion.from_dict(v) for v in data.get("versions", [])
        )
        pre_launch: PreLaunch | None = None
        if pl:
            pre_launch = PreLaunch(
                ini_patches=tuple(IniPatch.from_dict(p) for p in pl.get("ini_patches", [])),
                delete_files=tuple(pl.get("delete_files", [])),
                create_files=tuple(pl.get("create_files", [])),
            )
        return cls(
            id=data["id"],
            name=_loc(data, "name", ""),
            year=int(data["year"]),
            description=_loc(data, "description", ""),
            developer=data["developer"],
            executable=data["executable"],
            cover_image=data["cover_image"],
            latest_version=data.get("latest_version", "1.0"),
            recommended_version=data.get("recommended_version", "1.0"),
            versions=versions,
            tags=_tags_valides(_loc(data, "tags", [])),
            requires=tuple(r for r in data.get("requires", []) or ()
                           if isinstance(r, str)),
            warning=_loc(data, "warning", ""),
            warning_url=_url_aide_valide(data.get("warning_url", "")),
            language_registry=_parse_language_registry(data.get("language_registry")),
            language_files=(None if data.get("language_registry") is not None
                            else _parse_language_files(data.get("language_files"))),
            manette_registre=_parse_manette_registre(data.get("controller_registry")),
            # `is True` et non `bool(...)` : le catalogue est DISTANT, et une
            # chaîne non vide ou un nombre y suffiraient à activer un réglage
            # qui change la façon dont on lance un exécutable.
            dpi_aware=data.get("dpi_aware") is True,
            display_locked=data.get("display_locked") is True,
            relance=data.get("relance") is True,
            controller=_niveau_manette(data.get("controller")),
            controller_note=_loc(data, "controller_note", ""),
            resolution=_parse_resolution(data.get("resolution")),
            annee=_annee_valide(data.get("annee")),
            sauvegardes=_parse_sauvegardes(data.get("saves")),
            dll_overrides=_surcharges_dll_valides(data.get("dll_overrides")),
            max_fps=_ips_max_valide(data.get("max_fps")),
            fix_settings=tuple(r for r in (data.get("fix_settings") if isinstance(data.get("fix_settings"), list) else ())
                               if isinstance(r, str) and _JETON_SUR.match(r)),
            noms=_tous_les_noms(data),
            touche_capture=_touche_capture(data.get("screenshots")),
            captures=_motifs_captures(data.get("screenshots")),
            post_install=PostInstall(
                config_files=tuple(ConfigFile.from_dict(cf) for cf in pi.get("config_files", [])),
                sous_dossier=_sous_dossier_valide(pi.get("sous_dossier", "")),
            ),
            pre_launch=pre_launch,
        )


@dataclass(frozen=True, slots=True)
class Catalog:
    """Catalogue complet de jeux avec métadonnées."""
    catalog_version: str
    catalog_url: str
    games: tuple[GameData, ...]
    trailers: tuple[Trailer, ...] = ()
    contributors: tuple[Contributor, ...] = ()


def _parse_catalog(raw: dict | list) -> Catalog:
    """Parse un JSON brut en Catalog. Accepte l'ancien format (liste) et le nouveau (dict).

    Tolère un JSON mal typé (cache trafiqué / tronqué) : un jeu invalide est
    ignoré, un contenu aberrant lève ValueError (rattrapée par load_catalog qui
    retombe sur le catalogue embarqué). Ne JAMAIS laisser un TypeError remonter.
    """
    if isinstance(raw, list):
        entries = raw
        version, url = "0", ""
        trailers = ()
        contributors = ()
    elif isinstance(raw, dict):
        entries = raw.get("games", [])
        version = raw.get("catalog_version", "0")
        url = raw.get("catalog_url", "")
        trailers = _parse_trailers(raw.get("trailers"))
        contributors = _parse_contributors(raw.get("contributors"))
    else:
        raise ValueError(f"catalogue de type {type(raw).__name__}, attendu objet ou liste")

    if not isinstance(entries, list):
        raise ValueError(f"'games' de type {type(entries).__name__}, attendu liste")

    games = []
    for entry in entries:
        if not isinstance(entry, dict):
            log.warning("Entrée de catalogue ignorée (type %s)", type(entry).__name__)
            continue
        try:
            games.append(GameData.from_dict(entry))
        # OverflowError : `"year": 1e999` est du JSON valide, lu comme l'infini,
        # et `int()` le refuse par cette exception-là — qui n'est PAS une
        # ValueError. Elle traversait `load_catalog` : un cache abîmé faisait
        # planter chaque démarrage. Trouvé en préparant le fuzzing.
        except (ValueError, TypeError, AttributeError, KeyError, OverflowError) as exc:
            log.warning("Jeu invalide ignoré dans le catalogue : %s", exc)
    return Catalog(catalog_version=str(version), catalog_url=str(url),
                   games=tuple(games), trailers=trailers,
                   contributors=contributors)


def load_catalog(path: Path | None = None) -> Catalog:
    """Charge le catalogue le plus récent (embarqué ou cache local)."""
    from src.core.version_utils import compare_versions
    from src.core.config import LOCAL_CATALOG_PATH as _LOCAL_CATALOG_PATH

    src = path or GAMES_JSON_PATH
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
        catalog = _parse_catalog(raw)
    except (json.JSONDecodeError, OSError, ValueError, TypeError, AttributeError) as e:
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
        except (json.JSONDecodeError, OSError, ValueError, TypeError, AttributeError) as e:
            log.warning("Cache catalogue invalide, ignoré : %s", e)

    return catalog

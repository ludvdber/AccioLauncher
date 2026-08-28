import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import GAMES_JSON_PATH
from src.core import game_registry as registre
from src.core.i18n import SOURCE_LANGUAGE, get_language

log = logging.getLogger(__name__)



# Noms de périphériques réservés par Windows : ouvrir « CON » ouvre la console,
# pas un fichier — quel que soit le dossier et quelle que soit l'extension.
_PERIPHERIQUES = frozenset(
    ["con", "prn", "aux", "nul"]
    + ["com%d" % i for i in range(1, 10)]
    + ["lpt%d" % i for i in range(1, 10)]
)


def _tags_valides(tags) -> tuple:
    """Tags du catalogue, réduits à une liste de chaînes.

    Un dict passait sans broncher : Python itère alors ses CLÉS, qui se
    retrouvaient affichées en pastilles sous la description. Ce qui n'est pas
    une liste ne donne aucun tag, ce qui est le comportement attendu d'un champ
    mal formé — mieux vaut pas de tag qu'un tag inventé.
    """
    if not isinstance(tags, (list, tuple)):
        return ()
    return tuple(t for t in tags if isinstance(t, str))


def _est_peripherique(nom: str) -> bool:
    """True si `nom` est un nom de périphérique Windows réservé."""
    return nom.split(".")[0].strip().lower() in _PERIPHERIQUES


def _https_ou_rien(url):
    """Écarte au PARSING toute URL de téléchargement non-https.

    Le téléchargeur refuse déjà tout sauf https (`_validate_url`, plus
    `_ensure_response_https` sur l'URL d'arrivée après redirection) : la
    sécurité ne dépend pas de cette fonction. Ce qu'elle apporte, c'est le
    MOMENT du refus. Une coquille dans `games.json` — `http` au lieu de
    `https` — ne se voyait qu'au clic de l'utilisateur, sous la forme d'un
    message technique sur une version présentée comme téléchargeable. Écartée
    ici, la version devient simplement « bientôt disponible », ce qui est vrai.

    Accepte une chaîne ou une liste de parts ; retourne None / [] si tout est
    écarté, ce que `is_available` interprète correctement.
    """
    if isinstance(url, str):
        return url if url.startswith("https://") else None
    if isinstance(url, (list, tuple)):
        gardees = [u for u in url if isinstance(u, str) and u.startswith("https://")]
        # Tout ou rien : une liste de parts trouée décalerait les empreintes.
        return list(url) if len(gardees) == len(url) and gardees else None
    return None


def _sha256_valide(value) -> str | None:
    """Empreinte hexadécimale de 64 caractères, ou None.

    Le catalogue est mis à jour à distance : une coquille (`"sha256": 12345`,
    une empreinte tronquée) ne doit pas remonter jusqu'au comparateur. Elle y
    provoquait un `AttributeError` sur `.lower()`, donc un rapport de plantage
    pour une faute de frappe. Pas d'empreinte vaut mieux qu'une fausse.
    """
    if not isinstance(value, str):
        return None
    hexa = value.strip().lower()
    if len(hexa) == 64 and all(c in "0123456789abcdef" for c in hexa):
        return hexa
    if value:
        log.warning("Empreinte SHA-256 mal formée dans le catalogue, ignorée : %r", value)
    return None


def _taille_mo(value) -> int:
    """Taille annoncée en Mo, jamais négative.

    Une valeur négative avait deux effets fâcheux et silencieux : la
    vérification d'espace disque passait toujours (`needed_space_mb` rendait un
    nombre négatif), et le plafond du téléchargeur tombait à 0, c'est-à-dire
    DÉSACTIVÉ. Un catalogue trafiqué n'a donc pas à pouvoir lever le plafond.
    """
    try:
        taille = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, taille)


def _loc(data: dict, key: str, default):
    """Valeur du champ `key` dans la langue active, sinon en français.

    Les traductions du catalogue voyagent DANS le catalogue (bloc `i18n` par
    jeu et par version) et non dans le dictionnaire du launcher : le catalogue
    se met à jour à distance, indépendamment des releases, donc un jeu ajouté
    doit pouvoir arriver déjà traduit sans qu'on republie l'exécutable.

    La résolution se fait au parsing — `set_language()` tourne avant
    `load_catalog()` — ce qui laisse `game.name` directement utilisable par
    l'UI, sans champ « traduit » parallèle à oublier quelque part.

    Le repli est par CHAMP : une traduction partielle (nom traduit, changelog
    pas encore) reste utilisable telle quelle.
    """
    lang = get_language()
    if lang != SOURCE_LANGUAGE:
        block = data.get("i18n")
        if isinstance(block, dict):
            translated = block.get(lang)
            if isinstance(translated, dict) and key in translated:
                value = translated[key]
                # Un bloc i18n trafiqué ne doit pas changer le TYPE du champ…
                if isinstance(value, type(default)):
                    # …ni le VIDER. `from_dict` valide que le nom français est
                    # une chaîne non vide, mais cette validation portait sur le
                    # champ source : une traduction vide passait derrière et
                    # donnait une fiche de jeu sans titre. Un champ traduit vide
                    # se comporte désormais comme un champ absent, c'est-à-dire
                    # qu'il retombe sur le français — le repli par CHAMP prévu.
                    if isinstance(value, str) and not value.strip():
                        log.warning("Traduction vide (%s/%s) — repli sur le français", lang, key)
                    else:
                        return value
    return data.get(key, default)


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
    fallback: str | None = None  # valeur de repli si la valeur principale échoue

    @classmethod
    def from_dict(cls, data: dict) -> "IniPatch":
        return cls(file=data["file"], section=data["section"],
                   key=data["key"], value=data["value"],
                   fallback=data.get("fallback"))


@dataclass(frozen=True, slots=True)
class GameLanguage:
    """Une langue proposée par un jeu, et ce qu'elle écrit dans le registre."""
    code: str                                  # « fr », « en »… (code i18n)
    label: str                                 # écrit DANS sa propre langue
    values: tuple[tuple[str, str | int], ...]  # (nom, valeur) — frozen ⇒ tuple
    # Fichier dont la PRÉSENCE prouve que cette langue est réellement installée,
    # relatif au dossier d'installation. Le registre ne fait que SÉLECTIONNER
    # une langue : les fichiers, eux, viennent du disque d'origine, et un jeu
    # installé en français n'a que les fichiers français. Sans ce contrôle, le
    # sélecteur proposerait une langue que l'installation ne sait pas faire.
    # Vide = pas de contrôle (la langue est toujours proposée).
    requires_file: str = ""

    @property
    def as_dict(self) -> dict:
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class LanguageRegistry:
    """Où un jeu lit sa langue, et ce qu'il faut y écrire pour chacune.

    Déclaré par le CATALOGUE et non codé en dur : les valeurs attendues sont
    propres à chaque jeu (« French », « fr_FR », un REG_DWORD…), personne ne
    peut les deviner, et elles doivent pouvoir être corrigées sans republier
    l'exécutable — c'est exactement ce que le catalogue distant permet.
    """
    root: str
    key: str
    view: int
    languages: tuple[GameLanguage, ...]
    # Valeurs posées AVEC n'importe quelle langue, dans la MÊME clé. Elles ne
    # dépendent pas du choix du joueur mais de son installation : HP7 lit
    # « Install Dir » pour retrouver ses données (relevé dans hp7.exe et
    # hp8.exe le 2026-08-22), et sans elle le jeu ne démarre pas — c'est
    # normalement l'installeur EA qui l'écrit, et il n'a jamais tourné ici.
    # Elles voyagent avec la langue plutôt que dans un bloc à part pour une
    # raison concrète : même clé, donc UNE seule écriture et UNE seule invite
    # UAC. `%INSTALL_DIR%` y est substitué au moment de l'écriture.
    common: tuple[tuple[str, str | int], ...] = ()

    def get(self, code: str) -> GameLanguage | None:
        return next((lg for lg in self.languages if lg.code == code), None)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(lg.code for lg in self.languages)


def _est_relatif_sur(chemin: str) -> bool:
    r"""True si ce chemin de catalogue peut être joint au dossier d'un jeu.

    Mêmes refus que pour `executable` : pas de remontée, pas de racine, pas de
    lettre de lecteur, pas d'octet nul. Normaliser AVANT de vérifier — sous
    POSIX « \ » n'est pas un séparateur, et le garde-fou serait inopérant.
    """
    if not chemin or "\x00" in chemin or len(chemin) > 260:
        return False
    norm = chemin.replace("\\", "/")
    if norm.startswith("/") or (len(norm) >= 2 and norm[1] == ":"):
        return False
    return ".." not in norm.split("/")


def _parse_language_registry(data) -> "LanguageRegistry | None":
    """Lit le bloc `language_registry`, ou None s'il est absent ou douteux.

    TOUT ou RIEN : une déclaration à moitié valide est rejetée en entier plutôt
    que d'écrire la moitié des valeurs dans le registre d'un utilisateur. Un
    catalogue distant n'a pas droit à l'à-peu-près ici.
    """
    if not isinstance(data, dict):
        return None
    root = data.get("root", "HKCU")
    cle = data.get("key", "")
    try:
        view = int(data.get("view", 32))
    except (TypeError, ValueError):
        return None
    if view not in (32, 64):
        return None
    raison = registre.refus_de_cle(root, cle)
    if raison is not None:
        log.warning("Bloc language_registry ignoré (%s) : %r", raison, cle)
        return None

    brut = data.get("languages")
    if not isinstance(brut, dict) or not brut:
        return None
    langues: list[GameLanguage] = []
    for code, entree in brut.items():
        if not isinstance(code, str) or not isinstance(entree, dict):
            return None
        valeurs = entree.get("values")
        if not isinstance(valeurs, dict) or not valeurs:
            return None
        paires: list[tuple[str, str | int]] = []
        for nom, valeur in valeurs.items():
            raison = registre.refus_de_valeur(nom, valeur)
            if raison is not None:
                log.warning("Valeur de langue refusée (%s) : %r", raison, nom)
                return None
            paires.append((nom, valeur))
        label = entree.get("label")
        if not isinstance(label, str) or not label.strip():
            label = code
        fichier = entree.get("requires_file", "")
        if not isinstance(fichier, str):
            return None
        # Même validation que `executable` : ce chemin vient du catalogue
        # distant et sert à composer un chemin sur le disque de l'utilisateur.
        if fichier and not _est_relatif_sur(fichier):
            log.warning("requires_file non sûr, bloc de langue ignoré : %r", fichier)
            return None
        langues.append(GameLanguage(code=code, label=label, values=tuple(paires),
                                    requires_file=fichier))

    # Valeurs communes (« Install Dir »…). Même exigence de tout-ou-rien : une
    # seule refusée annule le bloc entier. Le refus porte sur le GABARIT, avant
    # substitution ; `ecrire_valeurs` revalidera le résultat, ce qui est le
    # vrai garde-fou — la substitution pourrait théoriquement tout changer.
    communes: list[tuple[str, str | int]] = []
    brut_communes = data.get("values", {})
    if not isinstance(brut_communes, dict):
        return None
    for nom, valeur in brut_communes.items():
        raison = registre.refus_de_valeur(nom, valeur)
        if raison is not None:
            log.warning("Valeur commune refusée (%s) : %r", raison, nom)
            return None
        communes.append((nom, valeur))

    return LanguageRegistry(root=root, key=cle, view=view, languages=tuple(langues),
                            common=tuple(communes))


@dataclass(frozen=True, slots=True)
class PreLaunch:
    """Données de pré-lancement d'un jeu."""
    ini_patches: tuple[IniPatch, ...] = ()
    delete_files: tuple[str, ...] = ()
    create_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PostInstall:
    """Données de post-installation d'un jeu."""
    config_files: tuple[ConfigFile, ...] = ()
    # Sous-dossier dans lequel ranger le jeu après extraction (« pc » pour HP7).
    # Vide = on ne range rien, ce qui est le cas des sept autres jeux.
    sous_dossier: str = ""


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


def _url_aide_valide(brut) -> str:
    """URL d'aide du catalogue, ou chaîne vide si elle n'est pas acceptable.

    HTTPS EXCLUSIVEMENT, et jamais une exception : le catalogue se met à jour à
    distance, donc cette valeur est la seule chaîne du catalogue qui finisse
    dans `QDesktopServices.openUrl`. Un `file://`, un `javascript:` ou un simple
    `http://` n'y a rien à faire, et un catalogue mal formé doit dégrader (pas
    de lien) plutôt que priver l'utilisateur de l'avertissement lui-même.
    """
    if not isinstance(brut, str):
        return ""
    url = brut.strip()
    if not url.lower().startswith("https://") or len(url) <= len("https://"):
        if url:
            log.warning("URL d'aide refusée (https attendu) : %r", url)
        return ""
    return url


def _sous_dossier_valide(brut) -> str:
    """Nom du sous-dossier de rangement, ou chaîne vide s'il n'est pas sûr.

    Ce nom vient du catalogue DISTANT et sert à composer un chemin sur le
    disque de l'utilisateur, puis à y DÉPLACER tout un jeu. Un `..`, un
    séparateur ou une lettre de lecteur enverrait l'installation ailleurs :
    même exigence que `executable`, mais en plus strict — un seul composant,
    jamais un chemin. `_JETON_SUR` refuse déjà `..`, `/`, `\\` et `:`.
    """
    if not isinstance(brut, str) or not brut:
        return ""
    nom = brut.strip()
    if not _JETON_SUR.match(nom) or nom in (".", ".."):
        log.warning("Sous-dossier de rangement refusé : %r", brut)
        return ""
    return nom


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
    # None quand le jeu n'en propose pas : c'est le cas de sept jeux sur huit,
    # et le sélecteur ne doit alors apparaître nulle part.
    language_registry: LanguageRegistry | None = None

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

        # Validation anti path-traversal de l'executable au parsing (défense en profondeur)
        executable = data["executable"]
        normalized = executable.replace("\\", "/")
        if (len(normalized) >= 2 and normalized[1] == ":") or normalized.startswith("/") \
                or ".." in normalized.split("/"):
            raise ValueError(f"executable non sûr : {executable!r}")
        # Trois refus de plus, sans exploitation démontrée mais sans usage
        # légitime non plus : un octet nul tronque le chemin au niveau de l'API
        # Windows, un nom de périphérique réservé (CON, NUL, COM1…) ouvre un
        # flux au lieu d'un fichier, et un chemin déraisonnablement long échoue
        # de toute façon plus loin — autant le dire ici, où le message est clair.
        if "\x00" in executable:
            raise ValueError(f"executable non sûr (octet nul) : {executable!r}")
        if len(executable) > 260:
            raise ValueError(
                f"executable trop long ({len(executable)} caractères) : {executable[:40]!r}…")
        if any(_est_peripherique(part) for part in normalized.split("/")):
            raise ValueError(f"executable non sûr (nom réservé) : {executable!r}")
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
            post_install=PostInstall(
                config_files=tuple(ConfigFile.from_dict(cf) for cf in pi.get("config_files", [])),
                sous_dossier=_sous_dossier_valide(pi.get("sous_dossier", "")),
            ),
            pre_launch=pre_launch,
        )


# Un identifiant de jeu et une version de bande-annonce viennent du catalogue
# DISTANT et finissent tous les deux dans un NOM DE FICHIER. Sans ce filtre,
# une version « ../../../evil » ferait écrire hors du dossier des trailers —
# c'est le même risque que les chemins `executable`, au même endroit du code.
_JETON_SUR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class Trailer:
    """Bande-annonce d'un jeu, hébergée HORS de l'exécutable.

    Les vidéos ne sont plus embarquées : à elles seules, deux d'entre elles
    faisaient passer l'exe de 74 à 160 Mo, et les huit l'auraient mené au-delà
    de 500 — pour un ornement que tout le monde télécharge et que personne
    n'est obligé de vouloir.
    """

    game_id: str
    version: str
    url: str
    size_mb: int = 0
    sha256: str | None = None

    @property
    def filename(self) -> str:
        """Nom du fichier LOCAL — il porte la VERSION, et ce n'est pas cosmétique.

        Le nom de l'asset distant, lui, ne la porte pas : deux releases peuvent
        publier `hp1_video.mp4` à l'identique. Un fichier nommé d'après l'asset
        ferait donc rejouer l'ancienne bande-annonce pour toujours — exactement
        le défaut déjà payé sur les parts d'archive de HP5.
        """
        return f"{self.game_id}_video_v{self.version}.mp4"


def _parse_trailers(raw) -> tuple[Trailer, ...]:
    """Lit le bloc `trailers` du catalogue. Une entrée douteuse est IGNORÉE.

    Jamais d'exception : une bande-annonce est un ornement, et un catalogue
    trafiqué ne doit pas priver quelqu'un de sa bibliothèque de jeux.
    """
    if not isinstance(raw, dict):
        return ()
    trailers = []
    for game_id, entree in raw.items():
        if not isinstance(entree, dict):
            log.warning("Bande-annonce ignorée (%s) : entrée de type %s",
                        game_id, type(entree).__name__)
            continue
        version = entree.get("version")
        url = _https_ou_rien(entree.get("url"))
        if not isinstance(version, str) or url is None:
            log.warning("Bande-annonce ignorée (%s) : version ou url absente/non-https", game_id)
            continue
        if not _JETON_SUR.match(str(game_id)) or not _JETON_SUR.match(version):
            log.warning("Bande-annonce refusée (%s v%s) : identifiant ou version "
                        "impropre à un nom de fichier", game_id, version)
            continue
        taille = entree.get("size_mb", 0)
        trailers.append(Trailer(
            game_id=str(game_id),
            version=version,
            url=url,
            size_mb=taille if isinstance(taille, int) and taille >= 0 else 0,
            sha256=_sha256_valide(entree.get("sha256")),
        ))
    return tuple(trailers)


@dataclass(frozen=True, slots=True)
class Contributor:
    """Quelqu'un à remercier dans l'À propos.

    Dans le CATALOGUE et non dans le code : remercier quelqu'un ne doit pas
    attendre une release. Une traduction rendue un mardi doit pouvoir être
    créditée le mardi, sinon la personne voit passer trois versions sans son
    nom et n'en propose pas une deuxième.

    `role` est traduisible par le bloc `i18n` de l'entrée, comme partout
    ailleurs dans le catalogue. `url` est FACULTATIVE — quelqu'un peut ne rien
    vouloir de public — et passe par la même validation https que `warning_url`,
    puisqu'elle atteint le navigateur de l'utilisateur.
    """
    name: str
    role: str = ""
    url: str = ""


def _parse_contributors(raw) -> tuple[Contributor, ...]:
    """Bloc `contributors` du catalogue. Tolérant : une entrée fautive est sautée."""
    if not isinstance(raw, list):
        if raw is not None:
            log.warning("'contributors' de type %s, ignoré", type(raw).__name__)
        return ()
    sortie: list[Contributor] = []
    for entree in raw:
        if not isinstance(entree, dict):
            log.warning("Contributeur ignoré (type %s)", type(entree).__name__)
            continue
        nom = _loc(entree, "name", "")
        if not isinstance(nom, str) or not nom.strip():
            log.warning("Contributeur sans nom, ignoré")
            continue
        role = _loc(entree, "role", "")
        sortie.append(Contributor(
            name=nom.strip(),
            role=role.strip() if isinstance(role, str) else "",
            url=_url_aide_valide(entree.get("url", "")),
        ))
    return tuple(sortie)


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
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
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

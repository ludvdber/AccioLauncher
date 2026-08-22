"""Gestionnaire de catalogue + état des jeux + lancement de processus."""

import logging
import shutil
import stat
import subprocess
import sys
from datetime import date
from enum import StrEnum, auto
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from src.core import game_registry as registre
from src.core.config import Config
from src.core.game_data import Catalog, GameData, GameVersion, load_catalog
from src.core.i18n import get_language
from src.core.pre_launch import (
    apply_ini_patches,
    create_pre_launch_files,
    delete_pre_launch_files,
    substitute_vars,
    unblock_game_dlls,
)
from src.core.system_checks import prerequis_manquants
from src.core.version_utils import update_disponible

log = logging.getLogger(__name__)


class GameState(StrEnum):
    """États possibles d'un jeu."""
    NOT_INSTALLED = auto()
    DOWNLOADING = auto()
    INSTALLING = auto()
    INSTALLED = auto()


class GameEntry(NamedTuple):
    """Jeu enrichi avec son état — retourné par GameManager.get_games()."""
    game: GameData
    state: GameState


def _is_safe_relative(path_str: str) -> bool:
    """Vérifie qu'un chemin relatif ne sort pas de sa racine (anti path-traversal)."""
    normalized = path_str.replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    p = PurePosixPath(normalized)
    if p.is_absolute():
        return False
    try:
        p.relative_to(".")
    except ValueError:
        return False
    return ".." not in p.parts


class GameManager:
    """Gère le catalogue de jeux et leur état (installé, non installé, etc.)."""

    __slots__ = ("config", "_catalog", "_games", "_index", "_states", "_new_game_ids",
                 "_download_counts", "_asset_digests", "_digests_lower",
                 "_asset_sizes", "_sizes_lower")

    def __init__(self, config: Config) -> None:
        self.config = config
        self._catalog = load_catalog()
        self._games = self._catalog.games
        self._index: dict[str, GameData] = {g.id: g for g in self._games}
        self._states: dict[str, GameState] = {
            g.id: self._detect_state(g) for g in self._games
        }
        # Jeux apparus via un reload de catalogue pendant la session (badge « NOUVEAU »)
        self._new_game_ids: set[str] = set()
        # Compteurs de téléchargement GitHub (toutes versions cumulées), remplis
        # en arrière-plan par l'UpdateChecker — vide tant que le fetch n'a pas abouti.
        self._download_counts: dict[str, int] = {}
        # URL d'asset → empreinte SHA-256 publiée par GitHub, remplies en
        # arrière-plan par l'UpdateChecker (vide tant que le fetch n'a pas abouti).
        self._asset_digests: dict[str, str] = {}
        self._digests_lower: dict[str, str] = {}
        # URL d'asset → taille réelle en octets, même provenance et même réserve :
        # vide tant que l'API n'a pas répondu, auquel cas on retombe sur le
        # `size_mb` du catalogue.
        self._asset_sizes: dict[str, int] = {}
        self._sizes_lower: dict[str, int] = {}
        self._backfill_missing_versions()
        log.info("Catalogue chargé : %d jeux (v%s)", len(self._games), self._catalog.catalog_version)

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    def reload_catalog(self, catalog: Catalog) -> None:
        """Recharge le catalogue (ex: après un update distant). Préserve les états."""
        old_states = dict(self._states)
        self._catalog = catalog
        self._games = catalog.games
        self._index = {g.id: g for g in self._games}
        self._states = {}
        for g in self._games:
            if g.id in old_states:
                self._states[g.id] = old_states[g.id]
            else:
                self._states[g.id] = self._detect_state(g)
                if self._states[g.id] == GameState.NOT_INSTALLED:
                    self._new_game_ids.add(g.id)
                    log.info("Nouveau jeu disponible : %s", g.name)
        self._backfill_missing_versions()
        log.info("Catalogue rechargé : %d jeux (v%s)", len(self._games), catalog.catalog_version)

    def is_new(self, game_id: str) -> bool:
        """True si le jeu est apparu via un reload de catalogue et n'a pas encore été vu."""
        return game_id in self._new_game_ids

    def mark_seen(self, game_id: str) -> None:
        """Retire le badge « NOUVEAU » d'un jeu (l'utilisateur l'a sélectionné)."""
        self._new_game_ids.discard(game_id)

    def refresh_states(self) -> None:
        """Re-détecte l'état de tous les jeux sur le disque.

        Nécessaire après un changement d'install_path : les états en mémoire
        pointent sinon vers l'ancien dossier. Préserve les états transitoires
        (téléchargement/installation en cours) pour ne pas casser une opération.
        """
        for g in self._games:
            if self._states.get(g.id) in (GameState.DOWNLOADING, GameState.INSTALLING):
                continue
            self._states[g.id] = self._detect_state(g)
        self._backfill_missing_versions()
        log.info("États re-détectés (%d jeux)", len(self._games))

    def _backfill_missing_versions(self) -> None:
        """Enregistre une version pour les jeux INSTALLÉS sans version connue.

        Un jeu détecté sur le disque sans entrée dans `installed_versions`
        (dossier déjà présent lors d'un changement d'install_path, config
        réinitialisée…) ne recevrait JAMAIS de notification de mise à jour :
        `has_update` exige une version connue. Convention optimiste identique
        à l'import « J'ai déjà ce jeu » : version recommandée du moment —
        « Vérifier / réparer » couvre le doute. Modif en mémoire seulement
        (persistée au prochain save naturel de la config ; idempotent au boot).
        """
        for g in self._games:
            if (self._states.get(g.id) == GameState.INSTALLED
                    and g.id not in self.config.installed_versions):
                self.config.installed_versions[g.id] = g.recommended_version
                log.info("Version inconnue pour %s (installé) — considérée v%s",
                         g.id, g.recommended_version)

    def redetect_state(self, game_id: str) -> None:
        """Force la re-détection disque d'un seul jeu (après annulation/erreur d'opération).

        Contrairement à un set NOT_INSTALLED aveugle, ceci préserve un jeu encore
        installé quand un téléchargement de mise à jour/réparation échoue.
        """
        game = self._index.get(game_id)
        if game is not None:
            self._states[game_id] = self._detect_state(game)

    def _detect_state(self, game: GameData) -> GameState:
        """Détecte l'état d'un jeu en vérifiant le disque."""
        if not _is_safe_relative(game.executable):
            log.warning("Chemin executable suspect ignoré : %s", game.executable)
            return GameState.NOT_INSTALLED
        exe_path = self.config.install_path / game.executable
        try:
            exe_path.resolve().relative_to(self.config.install_path.resolve())
        except ValueError:
            log.warning("Path traversal détecté dans _detect_state : %s", exe_path)
            return GameState.NOT_INSTALLED
        if exe_path.exists():
            return GameState.INSTALLED
        return GameState.NOT_INSTALLED

    def get_game_by_id(self, game_id: str) -> GameData | None:
        return self._index.get(game_id)

    def get_games(self) -> list[GameEntry]:
        """Retourne la liste des jeux enrichis avec leur état."""
        return [
            GameEntry(game=game, state=self._states[game.id])
            for game in self._games
        ]

    def get_game_path(self, game_id: str) -> Path | None:
        """Retourne le chemin racine du jeu."""
        game = self._index.get(game_id)
        if game is None:
            return None
        if not _is_safe_relative(game.executable):
            return None
        return self.config.install_path / Path(game.executable).parts[0]

    def get_state(self, game_id: str) -> GameState:
        return self._states.get(game_id, GameState.NOT_INSTALLED)

    def is_installed(self, game_id: str) -> bool:
        return self._states.get(game_id) == GameState.INSTALLED

    def installed_version(self, game_id: str) -> str | None:
        """Retourne la version installée d'un jeu, ou None."""
        return self.config.installed_versions.get(game_id)

    def has_update(self, game_id: str) -> bool:
        """Vérifie si une mise à jour est disponible pour un jeu installé.

        La règle elle-même vit dans `version_utils.update_disponible` : elle
        était dupliquée ici et dans l'UpdateChecker, en comparaison de chaînes.
        """
        if not self.is_installed(game_id):
            return False
        game = self._index.get(game_id)
        if game is None:
            return False
        return update_disponible(self.installed_version(game_id), game.recommended_version)

    def set_game_state(self, game_id: str, state: GameState) -> None:
        if game_id not in self._index:
            log.warning("Jeu inconnu : %s", game_id)
            return
        self._states[game_id] = state
        log.info("État de %s → %s", game_id, state)

    def launch_game(self, game_id: str, confirmer=None) -> subprocess.Popen | None:
        """Lance le .exe du jeu en processus détaché.

        `confirmer` est le rappel de prévenance avant écriture registre (cf.
        `apply_game_language`) : il n'est appelé que s'il y a réellement une
        écriture à faire, donc au premier lancement et après un changement.
        """
        game = self._index.get(game_id)
        if game is None:
            log.warning("Impossible de lancer un jeu inconnu : %s", game_id)
            return None
        if not _is_safe_relative(game.executable):
            log.warning("Chemin executable non sûr : %s", game.executable)
            return None
        exe_path = self.config.install_path / game.executable
        try:
            exe_path.resolve().relative_to(self.config.install_path.resolve())
        except ValueError:
            log.warning("Path traversal détecté : %s", exe_path)
            return None
        if not exe_path.exists():
            log.warning("Exécutable introuvable : %s", exe_path)
            return None

        # Socle commun + ce que le catalogue déclare pour CE jeu (ex. HP7 et
        # son Visual C++ 2005). L'identifiant manquant remonte dans le message
        # d'erreur : c'est lui qui permet à l'UI d'ouvrir la bonne page.
        manquants = prerequis_manquants(("vcredist_x86", *game.requires))
        if manquants:
            raise RuntimeError(f"prerequis_manquant:{manquants[0]}")

        # Langue du jeu AVANT tout le reste : c'est la seule étape qui peut
        # demander une élévation, et l'utilisateur doit voir l'invite UAC juste
        # après son clic, pas après trois secondes de patches silencieux. Un
        # échec (UAC refusé) ne bloque PAS le lancement : le jeu démarrera dans
        # la langue déjà en place, ce qui vaut mieux que de ne pas démarrer.
        if not self.apply_game_language(game, confirmer=confirmer):
            log.warning("Langue non appliquée pour %s — lancement quand même", game_id)

        # Pré-lancement (cf. src/core/pre_launch.py)
        unblock_game_dlls(exe_path.parent)
        delete_pre_launch_files(game, self.config)
        create_pre_launch_files(game, self.config)
        apply_ini_patches(game, self.config)

        log.info("Lancement de %s (%s)", game.name, exe_path)
        popen_kwargs: dict = {"cwd": str(exe_path.parent)}
        # `sys.platform == "win32"` et non `platform.system()` : c'est la
        # convention de tout le reste du projet (16 autres sites), et le
        # portage Linux impose que le test soit repérable d'un seul motif.
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            popen_kwargs["start_new_session"] = True
        return subprocess.Popen([str(exe_path)], **popen_kwargs)

    def apply_pre_launch_patches(self, game: GameData) -> None:
        """Façade rétro-compat — délègue à pre_launch.apply_ini_patches."""
        apply_ini_patches(game, self.config)

    # ──────────────────── Langue de jeu ────────────────────

    def langues_disponibles(self, game: GameData) -> tuple:
        """Langues que CETTE installation sait réellement faire.

        Le registre ne fait que SÉLECTIONNER une langue ; les fichiers, eux,
        viennent du disque d'origine. Un jeu installé en français n'a que les
        fichiers français, et basculer la clé sur l'anglais ne donnerait pas un
        jeu anglais (confirmé par deux guides communautaires : « you also have
        to copy the language file from the DVD to your installation path »).
        Proposer une langue que l'installation ne sait pas faire serait donc
        promettre quelque chose de faux.

        Une langue sans `requires_file` est toujours proposée : le contrôle est
        une option du catalogue, pas une obligation.
        """
        lr = game.language_registry
        if lr is None:
            return ()
        racine = self.config.install_path
        gardees = []
        for langue in lr.languages:
            if not langue.requires_file:
                gardees.append(langue)
                continue
            chemin = racine / langue.requires_file.replace("\\", "/")
            try:
                if chemin.exists():
                    gardees.append(langue)
            except OSError:
                pass
        return tuple(gardees)

    def detect_game_language(self, game: GameData) -> str | None:
        """Langue actuellement POSÉE dans le registre, None si indéterminable.

        La lecture est gratuite (aucun privilège) et c'est la seule source qui
        dise la vérité : le jeu peut avoir été installé par son installeur
        d'origine, ou l'utilisateur avoir changé la clé à la main.
        """
        lr = game.language_registry
        if lr is None:
            return None
        noms = {nom for langue in lr.languages for nom, _ in langue.values}
        actuel = registre.lire_valeurs(lr.root, lr.key, sorted(noms), lr.view)
        if not actuel:
            return None
        for langue in lr.languages:
            if all(actuel.get(nom) == val for nom, val in langue.values):
                return langue.code
        return None

    def game_language(self, game: GameData) -> str | None:
        """Code de la langue de CE jeu, None s'il n'en propose pas.

        Trois sources, dans l'ordre :
        1. le choix EXPLICITE de l'utilisateur, s'il est encore proposé ;
        2. ce que le registre porte RÉELLEMENT — sans quoi la ligne méta
           annoncerait une langue que le jeu n'a pas, et le lancement voudrait
           « corriger » le registre (donc demander une élévation) alors que
           l'utilisateur n'a rien demandé ;
        3. la langue de l'interface si le jeu la propose, sinon la première du
           catalogue. Surtout PAS la langue système : l'utilisateur a déjà dit
           sa langue à l'onboarding, et de toute façon aucun défaut figé ne peut
           convenir tant qu'il n'est pas modifiable.
        """
        lr = game.language_registry
        # Sans registre atteignable (Linux), aucune langue n'est « celle du
        # jeu » : rien ne lit ni n'écrit ce réglage ici. Retourner None éteint
        # le sélecteur de la ligne méta plutôt que d'afficher un choix sans
        # effet — un réglage qui ne règle rien est pire que pas de réglage.
        if not registre.disponible():
            return None
        if lr is None or not lr.languages:
            return None
        # Le choix et la détection portent sur TOUTES les langues déclarées :
        # si le registre annonce l'allemand, on l'affiche, même si les fichiers
        # allemands ne sont pas là — mieux vaut dire la vérité que la masquer.
        # Seul le DÉFAUT se restreint à ce que l'installation sait faire.
        choisi = self.config.game_language.get(game.id)
        if choisi and lr.get(choisi) is not None:
            return choisi
        detecte = self.detect_game_language(game)
        if detecte is not None:
            return detecte
        possibles = self.langues_disponibles(game) or lr.languages
        interface = get_language()
        if any(lg.code == interface for lg in possibles):
            return interface
        return possibles[0].code

    def set_game_language(self, game_id: str, code: str) -> None:
        """Enregistre le choix de langue d'un jeu (persisté en config)."""
        game = self._index.get(game_id)
        if game is None or game.language_registry is None:
            return
        if game.language_registry.get(code) is None:
            log.warning("Langue %r non proposée par %s — ignorée", code, game_id)
            return
        self.config.game_language[game_id] = code
        self.config.save()
        log.info("Langue de %s : %s", game_id, code)

    def valeurs_registre(self, game: GameData, code: str | None = None) -> dict:
        """Tout ce qui doit être posé dans la clé du jeu, langue comprise.

        Les valeurs communes (« Install Dir ») et celles de la langue vont dans
        la MÊME clé : les écrire ensemble, c'est un seul .reg et une seule
        invite UAC au lieu de deux à la suite. La langue passe en dernier —
        elle est plus spécifique, elle gagne en cas de collision de nom.
        """
        lr = game.language_registry
        if lr is None:
            return {}
        valeurs = {nom: substitute_vars(v, game, self.config) if isinstance(v, str) else v
                   for nom, v in lr.common}
        code = code or self.game_language(game)
        langue = lr.get(code) if code else None
        if langue is not None:
            valeurs.update(langue.as_dict)
        return valeurs

    def apply_game_language(self, game: GameData, code: str | None = None,
                            confirmer=None) -> bool:
        """Écrit une langue dans le registre. True s'il n'y a rien à faire.

        `code` permet d'appliquer AVANT de persister : si l'écriture échoue (UAC
        refusé), on ne veut pas garder en config un choix que le registre n'a
        pas pris — sinon la fiche annoncerait une langue que le jeu n'a pas, et
        chaque lancement redemanderait l'élévation. Sans `code`, on applique ce
        que `game_language` résout.

        Ne demande une élévation que si les valeurs DIFFÈRENT réellement : le
        cas courant est qu'elles sont déjà bonnes, et une invite UAC à chaque
        lancement serait pire que le problème qu'on règle.

        `confirmer(ruche, cle, valeurs)` est transmis tel quel : c'est l'UI qui
        prévient, et seulement quand il y a vraiment quelque chose à écrire.
        """
        lr = game.language_registry
        if lr is None:
            return True
        # Hors Windows il n'y a rien à écrire — et surtout pas d'avertissement
        # à journaliser À CHAQUE lancement pour une opération qu'on n'a pas
        # tentée. `launch_game` traite False comme un échec réel : ce n'en est
        # pas un.
        if not registre.disponible():
            return True
        valeurs = self.valeurs_registre(game, code)
        if not valeurs:
            return True
        return registre.ecrire_valeurs(lr.root, lr.key, valeurs, lr.view,
                                       confirmer=confirmer)

    # ──────────────────── Stats de jeu ────────────────────

    def add_playtime(self, game_id: str, seconds: int) -> None:
        """Cumule le temps d'une session et date la dernière partie (persisté en config)."""
        if game_id not in self._index or seconds <= 0:
            return
        self.config.playtime_seconds[game_id] = (
            self.config.playtime_seconds.get(game_id, 0) + int(seconds)
        )
        self.config.last_played[game_id] = date.today().isoformat()
        self.config.save()
        log.info("Temps de jeu de %s : +%d s (total %d s)",
                 game_id, seconds, self.config.playtime_seconds[game_id])

    def get_playtime(self, game_id: str) -> int:
        """Temps de jeu cumulé en secondes (0 si jamais joué)."""
        return self.config.playtime_seconds.get(game_id, 0)

    def last_played(self, game_id: str) -> str | None:
        """Date ISO de la dernière session, ou None."""
        return self.config.last_played.get(game_id)

    def free_space_mb(self) -> int | None:
        """Mo libres sur le disque du dossier d'installation, None si illisible.

        None signifie « je ne sais pas » et doit toujours désactiver la
        vérification plutôt que la faire échouer : un disque non interrogeable
        (chemin absent, lecteur réseau déconnecté) ne prouve pas qu'il manque
        de la place.
        """
        try:
            return int(shutil.disk_usage(self.config.install_path).free // (1024 * 1024))
        except OSError:
            return None

    def set_download_counts(self, counts: dict[str, int]) -> None:
        """Reçoit les compteurs ⬇ agrégés par l'UpdateChecker (thread principal)."""
        self._download_counts = dict(counts)

    def download_count(self, game_id: str) -> int:
        """Téléchargements GitHub cumulés (0 si inconnu / fetch non abouti)."""
        return self._download_counts.get(game_id, 0)

    def set_asset_digests(self, digests: dict[str, str]) -> None:
        """Reçoit les empreintes publiées par GitHub (thread principal).

        Construit au passage un index insensible à la casse : le catalogue peut
        référencer « hp6.7z.001 » alors que l'asset s'appelle « HP6.7z.001 ».
        GitHub sert les deux formes (vérifié : même taille, même contenu), mais
        son API ne publie que la forme canonique — sans cet index, ces versions
        perdraient leur vérification d'intégrité sans que rien ne le signale.
        """
        self._asset_digests = dict(digests)
        lower: dict[str, str] = {}
        ambigus: set[str] = set()
        for url, digest in self._asset_digests.items():
            cle = url.lower()
            if cle in lower and lower[cle] != digest:
                ambigus.add(cle)
            lower[cle] = digest
        for cle in ambigus:
            # Deux assets ne différant que par la casse : impossible de trancher.
            # Mieux vaut ne pas vérifier que vérifier contre la mauvaise empreinte.
            log.warning("Empreintes ambiguës (casse) pour %s — ignorées", cle)
            del lower[cle]
        self._digests_lower = lower

    def set_asset_sizes(self, sizes: dict[str, int]) -> None:
        """Reçoit les tailles réelles publiées par GitHub (thread principal).

        Même index insensible à la casse que les empreintes, et pour la même
        raison : le catalogue écrit « hp5.7z.001 » là où l'asset s'appelle
        « HP5.7z.001 ». Une ambiguïté de casse est ignorée plutôt que devinée —
        une taille fausse ferait promettre au bouton un poids qui n'est pas le
        bon, ce qui est exactement le défaut qu'on répare.
        """
        self._asset_sizes = dict(sizes)
        lower: dict[str, int] = {}
        ambigus: set[str] = set()
        for url, taille in self._asset_sizes.items():
            cle = url.lower()
            if cle in lower and lower[cle] != taille:
                ambigus.add(cle)
            lower[cle] = taille
        for cle in ambigus:
            log.warning("Tailles ambiguës (casse) pour %s — ignorées", cle)
            lower.pop(cle, None)
        self._sizes_lower = lower

    def _size_for(self, url: str | None) -> int:
        """Taille publiée pour cette URL, en octets (0 si inconnue)."""
        if not url:
            return 0
        return self._asset_sizes.get(url) or self._sizes_lower.get(url.lower(), 0)

    def archive_size_mb(self, version: GameVersion) -> int:
        """Poids RÉEL du téléchargement, en Mo — 0 si GitHub ne l'a pas dit.

        À ne pas confondre avec `version.size_mb`, qui est la taille du jeu une
        fois INSTALLÉ (mesuré : de 1,77 à 2,30 fois le téléchargement réel). Le
        bouton, le garde-fou de taille du téléchargeur et le calcul d'espace
        disque veulent ce chiffre-ci ; l'espace disque veut les deux.

        Multi-parts : **tout ou rien**. Une somme partielle annoncerait un poids
        plus petit que la réalité, ce qui est pire que de ne rien annoncer — le
        garde-fou du téléchargeur couperait alors un téléchargement sain.
        """
        if version.download_parts:
            tailles = [self._size_for(url) for url in version.download_parts]
            return round(sum(tailles) / 1024 / 1024) if all(tailles) else 0
        octets = self._size_for(version.download_url)
        return round(octets / 1024 / 1024) if octets else 0

    def _digest_for(self, url: str | None) -> str:
        """Empreinte publiée pour cette URL ("" si inconnue)."""
        if not url:
            return ""
        return self._asset_digests.get(url) or self._digests_lower.get(url.lower(), "")

    def expected_hashes(self, version: GameVersion) -> tuple[str | None, list[str]]:
        """Empreintes à vérifier pour une version : (sha256 simple, sha256 des parts).

        Deux sources possibles, dans cet ordre :

        1. Le **catalogue** (`sha256` / `sha256_parts`) — attestation explicite,
           seule option pour une archive hébergée ailleurs que sur GitHub.
        2. Les **empreintes publiées par GitHub**, récupérées sans requête
           supplémentaire par l'UpdateChecker. Elles évitent d'avoir à recopier
           64 caractères à la main à chaque release, oubli qui laisserait la
           vérification dormante.

        Retourne (None, []) si aucune source n'est disponible : la vérification
        est alors sautée, comme avant — jamais un échec de téléchargement.
        """
        if version.download_parts:
            catalogue = list(version.sha256_parts)
            if len(catalogue) == len(version.download_parts) and all(catalogue):
                return None, catalogue
            depuis_github = [self._digest_for(url) for url in version.download_parts]
            # Tout ou rien : une liste trouée décalerait les empreintes d'un cran
            # par rapport aux parts et ferait échouer une archive pourtant saine.
            if all(depuis_github):
                return None, depuis_github
            return None, []

        if version.sha256:
            attendu = self._digest_for(version.download_url)
            if attendu and attendu != version.sha256.lower():
                log.warning(
                    "Empreinte du catalogue (%s…) différente de celle publiée par "
                    "GitHub (%s…) pour %s — le catalogue fait foi",
                    version.sha256[:12], attendu[:12], version.download_url)
            return version.sha256, []

        return self._digest_for(version.download_url) or None, []

    def last_played_game_id(self) -> str | None:
        """Id du jeu joué le plus récemment (None si aucune session enregistrée).

        Les dates ISO se comparent lexicographiquement ; les ids absents du
        catalogue courant sont ignorés (jeu retiré).
        """
        dates = {
            gid: day for gid, day in self.config.last_played.items()
            if gid in self._index
        }
        if not dates:
            return None
        return max(dates.items(), key=lambda kv: kv[1])[0]

    def save_installed_version(self, game_id: str, version: str | None = None) -> None:
        """Sauvegarde la version du jeu installé dans la config."""
        game = self._index.get(game_id)
        if game is None:
            return
        ver = version or game.recommended_version
        self.config.installed_versions[game_id] = ver
        self.config.save()

    def uninstall_game(self, game_id: str) -> bool:
        """Supprime le dossier du jeu. Retourne True si succès."""
        game_path = self.get_game_path(game_id)
        game = self._index.get(game_id)
        if game is None or game_path is None or not game_path.exists():
            log.warning("Rien à désinstaller pour %s (chemin: %s)", game_id, game_path)
            return False
        try:
            game_path.resolve().relative_to(self.config.install_path.resolve())
        except ValueError:
            log.error("Path traversal détecté lors de la désinstallation : %s", game_path)
            return False

        log.info("Désinstallation de %s — suppression de : %s", game.name, game_path)
        try:
            def _force_remove_readonly(_func, path, _exc_info):
                """Retire le flag read-only et réessaie la suppression."""
                Path(path).chmod(stat.S_IWRITE)
                _func(path)
            shutil.rmtree(game_path, onexc=_force_remove_readonly)
        except OSError as exc:
            log.error("Échec de la suppression de %s : %s", game_path, exc)
            return False
        self._states[game_id] = GameState.NOT_INSTALLED
        self.config.installed_versions.pop(game_id, None)
        self.config.save()
        log.info("Désinstallation terminée : %s (%s supprimé)", game_id, game_path)
        return True

"""Gestionnaire de catalogue + état des jeux + lancement de processus."""

import logging
import shutil
import stat
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta
from enum import StrEnum, auto
from pathlib import Path
from typing import NamedTuple

from src.core import captures, compat, manette
from src.core.chemins import chemin_relatif_sur
from src.core import game_language as langue
from src.core import copies_sauvegardes, resolution_jeu, stats
from src.core.config import Config
from src.core.game_data import Catalog, GameData, GameVersion, load_catalog
from src.core.pre_launch import (
    besoin_de_documents,
    documents_inutilisable,
    apply_ini_patches,
    create_pre_launch_files,
    restaurer_configs_manquantes,
    delete_pre_launch_files,
    env_de_lancement,
    unblock_game_dlls,
)
from src.core.system_checks import prerequis_manquants
from src.core.version_utils import update_disponible

log = logging.getLogger(__name__)

# ERROR_ELEVATION_REQUIRED : CreateProcess refuse un exe qui exige l'administrateur.
ERREUR_ELEVATION = 740

# Au-delà, l'archive n'attend plus que son installation : ce n'est plus une
# reprise. Un seul seuil pour le bouton et la vignette (règle 98).
REPRISE_SEUIL = 0.99


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
        # Remplis en arrière-plan par l'UpdateChecker, vides tant que l'API
        # GitHub n'a pas répondu : téléchargements cumulés, empreintes SHA-256
        # et tailles réelles par URL d'asset (sinon `size_mb` du catalogue).
        self._download_counts: dict[str, int] = {}
        self._asset_digests: dict[str, str] = {}
        self._digests_lower: dict[str, str] = {}
        self._asset_sizes: dict[str, int] = {}
        self._sizes_lower: dict[str, int] = {}
        self._backfill_missing_versions()
        # Gèle les cumuls d'avant le journal des sessions : cet historique ne
        # se reconstruit pas.
        stats.amorcer(self.config.playtime_seconds)
        # Rattrape une partie dont le launcher n'a pas vu la fin (zone de
        # notification, mise à jour, plantage). Après `amorcer`.
        stats.recuperer_session_interrompue()
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

        Sans elle, `has_update` ne les notifierait jamais. Convention optimiste
        (version recommandée du moment), comme l'import « J'ai déjà ce jeu ».
        En mémoire seulement ; idempotent.
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
        if not chemin_relatif_sur(game.executable):
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
        if not chemin_relatif_sur(game.executable):
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
        """Vérifie si une mise à jour est disponible pour un jeu installé
        (règle unique : `version_utils.update_disponible`)."""
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

    def launch_game(self, game_id: str, confirmer=None, avertir=None,
                    ignorer_prerequis: bool = False) -> subprocess.Popen | None:
        """Lance le .exe du jeu en processus détaché.

        Sous Linux, par umu-run ou wine dans le préfixe partagé (`compat.py`).
        `ignorer_prerequis` : « Lancer quand même » après un échec de
        winetricks — Wine suffit parfois, c'est à l'utilisateur d'en décider.

        `confirmer` : prévenance avant écriture registre, appelée seulement
        s'il y a une écriture à faire (règle 69).

        `avertir()` : l'écriture était NÉCESSAIRE et a échoué. Le lancement
        continue, mais on le dit (HP7b refuse de démarrer avec `Locale=fr_FR`,
        sans rien expliquer).
        """
        game = self._index.get(game_id)
        if game is None:
            log.warning("Impossible de lancer un jeu inconnu : %s", game_id)
            return None
        if not chemin_relatif_sur(game.executable):
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

        # Sous Linux, sans lanceur de compatibilité rien de la suite n'a de
        # sens : le dire avant d'écrire dans un préfixe que personne ne lira.
        lanceur = None
        if sys.platform != "win32":
            lanceur = compat.lanceur()
            if lanceur is None:
                # Peut-être installé depuis (le message le propose) : rechercher.
                compat.oublier()
                lanceur = compat.lanceur()
            if lanceur is None:
                raise RuntimeError("compat_absent")

        # Socle commun + `requires` du jeu. L'identifiant manquant remonte
        # pour que l'UI ouvre la bonne page (ou l'installe dans le préfixe).
        manquants = ([] if ignorer_prerequis
                     else prerequis_manquants(("vcredist_x86", *game.requires)))
        if manquants:
            raise RuntimeError(f"prerequis_manquant:{manquants[0]}")

        # HP1-HP3 vivent dans Documents ; sans accès, ils plantent sur un
        # « General protection fault » que rien ne relie au coupable. Le dire avant.
        if besoin_de_documents(game):
            docs = documents_inutilisable()
            if docs is not None:
                raise RuntimeError(f"documents_inutilisable:{docs}")

        # Langue d'abord : seule étape qui peut demander l'UAC, à montrer juste
        # après le clic. Un refus ne bloque pas le lancement.
        if game.language_registry is not None \
                and not self.apply_game_language(game, confirmer=confirmer):
            log.warning("Langue non appliquée pour %s — lancement quand même", game_id)
            if avertir is not None:
                avertir()

        # Pré-lancement (cf. src/core/pre_launch.py)
        unblock_game_dlls(exe_path.parent)
        delete_pre_launch_files(game, self.config)
        create_pre_launch_files(game, self.config)
        # Avant les patchs : ils sautent un fichier absent, et le moteur le
        # régénérerait depuis Default.ini, assistant de configuration compris.
        restaurer_configs_manquantes(game, self.config)
        apply_ini_patches(game, self.config)
        # Taille de fenêtre APRÈS la restauration, qui recopierait le modèle
        # (1024×768 pour HP2) ; écrite à chaque fois, raison dans le module.
        resolution_jeu.appliquer(game, self.config, resolution_jeu.place_pour(game, self.config))
        # Langue par FICHIERS (HP1) APRÈS la restauration, qui recopierait un
        # HP.ini français par-dessus.
        if game.langue_par_fichiers \
                and not self.apply_game_language(game):
            log.warning("Langue non appliquée pour %s — lancement quand même", game_id)
            if avertir is not None:
                avertir()
        # Le correctif PC écrit ses captures directement hors du dossier du jeu.
        captures.preparer(game, self.config.install_path)
        # Et la couleur de la maison, que son xinput1_3.dll repose sur la manette.
        manette.preparer((self.config.install_path / game.executable).parent,
                         self.config.theme if self.config.couleur_manette else None)

        # Les sauvegardes telles qu'elles sont AVANT la partie
        # (`copies_sauvegardes`). Sur un fil : la toute première fois, HP3 en a
        # 25 Mo à compresser, et le clic sur JOUER ne doit pas attendre. Le jeu
        # met plusieurs secondes à charger ; une sauvegarde réécrite pendant la
        # copie est de toute façon détectée et sa copie jetée.
        if self.config.copies_sauvegardes and game.sauvegardes is not None:
            threading.Thread(target=copies_sauvegardes.avant_partie,
                             args=(game.id, game.sauvegardes), daemon=True,
                             name=f"copies-{game.id}").start()

        log.info("Lancement de %s (%s)", game.name, exe_path)
        popen_kwargs: dict = {"cwd": str(exe_path.parent)}
        if sys.platform != "win32":
            return self._lancer_sous_wine(game, exe_path, lanceur, popen_kwargs)
        popen_kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        # Couche DPI (règle 104) : sans elle, HP7 s'ouvrait en 3200×1800 sur
        # un écran 2560×1440 à l'échelle. None : le jeu hérite du nôtre.
        popen_kwargs["env"] = env_de_lancement(game.dpi_aware)
        # Chemin absolu validé au parsing du catalogue. Aucun shell.
        try:
            return subprocess.Popen([str(exe_path)], **popen_kwargs)  # nosec B603
        except OSError as exc:
            # 740 : « Exécuter en tant qu'administrateur » coché sur l'exe.
            # Le dire, pas « Impossible de lancer ».
            if getattr(exc, "winerror", None) == ERREUR_ELEVATION:
                raise RuntimeError(f"elevation_requise:{exe_path}") from exc
            raise

    @staticmethod
    def _lancer_sous_wine(game: GameData, exe_path: Path, lanceur,
                          popen_kwargs: dict) -> subprocess.Popen:
        """Lance le jeu par umu-run ou wine, dans le préfixe partagé.

        `dpi_aware` est ignoré (couche Windows). `dll_overrides` part en
        `WINEDLLOVERRIDES`. La sortie de Wine va dans
        `_Launcher/logs/wine-<jeu>.log`, réécrit à chaque lancement.
        """
        pfx = compat.prefixe(lanceur.famille)
        popen_kwargs["start_new_session"] = True
        popen_kwargs["env"] = compat.environnement(lanceur, pfx, game.dll_overrides,
                                                   ips_max=game.max_fps)
        commande = compat.commande_jeu(lanceur, exe_path)
        journal = compat.journal_du_jeu(game.id)
        log.info("Lancement sous %s (%s) : préfixe %s, surcharges %s, plafond %s, journal %s",
                 lanceur.famille, lanceur.executable, pfx,
                 ",".join(game.dll_overrides) or "aucune",
                 f"{game.max_fps} ips" if game.max_fps else "aucun", journal)
        try:
            journal.parent.mkdir(parents=True, exist_ok=True)
            sortie = open(journal, "wb")
        except OSError as exc:
            log.warning("Journal Wine impossible (%s) : sortie ignorée", exc)
            sortie = None
        try:
            # Lanceur trouvé par chemin ABSOLU (`compat._trouver`), exe validé au
            # parsing du catalogue ; liste d'arguments, aucun shell.
            return subprocess.Popen(  # nosec B603
                commande, stdin=subprocess.DEVNULL,
                stdout=sortie if sortie is not None else subprocess.DEVNULL,
                stderr=subprocess.STDOUT, **popen_kwargs)
        finally:
            # Le processus a sa propre copie du descripteur : la nôtre se ferme.
            if sortie is not None:
                sortie.close()

    # ──────────────────── Langue de jeu ────────────────────
    # Façades : les règles vivent dans `core/game_language.py`.

    def langues_disponibles(self, game: GameData) -> tuple:
        """Langues que cette installation sait réellement faire (fichiers présents)."""
        return langue.langues_disponibles(game, self.config)


    def game_language(self, game: GameData) -> str | None:
        """Langue de ce jeu : choix explicite → registre → interface → catalogue."""
        return langue.resoudre(game, self.config)

    def set_game_language(self, game_id: str, code: str) -> None:
        """Enregistre le choix de langue d'un jeu (persisté en config)."""
        langue.memoriser(self._index.get(game_id), code, self.config)

    def valeurs_registre(self, game: GameData, code: str | None = None) -> dict:
        """Tout ce qui doit être posé dans la clé du jeu, langue comprise."""
        return langue.valeurs_registre(game, self.config, code)

    def apply_game_language(self, game: GameData, code: str | None = None,
                            confirmer=None) -> bool:
        """Écrit la langue dans le registre. True s'il n'y a rien à faire."""
        return langue.appliquer(game, self.config, code, confirmer)

    # ──────────────────── Stats de jeu ────────────────────

    def add_playtime(self, game_id: str, seconds: int,
                     debut: datetime | None = None, code: int | None = None,
                     arret: bool = False) -> bool:
        """Consigne ce qu'un lancement a donné : une partie, ou une tentative.

        **Rend True si c'était une vraie partie** : le seuil est arbitré ici
        seulement, et l'affichage en a besoin (pas de « bon jeu » à un jeu qui
        n'a pas démarré). Trop court, c'est une TENTATIVE, signature d'un jeu
        qui refuse de démarrer. `arret` : le jeu a écrit un arrêt fatal dans son
        journal (`config_cassee`) — sa boîte d'erreur le garde en vie tant
        qu'on la regarde, d'où un seuil plus haut (`DUREE_MINIMALE_APRES_ARRET`).

        Cumuls en config = source rapide (fiche, cap Ko-fi) ; le journal
        (`stats.py`) garde le détail. `debut` : heure RELEVÉE au lancement,
        nécessaire au rattrapage d'une partie interrompue.
        """
        if game_id not in self._index or seconds < 0:
            return False
        debut = debut or (datetime.now() - timedelta(seconds=int(seconds)))
        seuil = stats.DUREE_MINIMALE_APRES_ARRET if arret else stats.DUREE_MINIMALE
        if seconds < seuil:
            stats.enregistrer_tentative(game_id, debut, int(seconds), code)
            log.info("Lancement sans partie : %s (%d s, code %s%s)", game_id, seconds, code,
                     ", arrêt fatal au journal" if arret else "")
            return False
        self.config.playtime_seconds[game_id] = (
            self.config.playtime_seconds.get(game_id, 0) + int(seconds)
        )
        self.config.last_played[game_id] = date.today().isoformat()
        self.config.save()
        stats.enregistrer_session(game_id, debut, int(seconds))
        log.info("Temps de jeu de %s : +%d s (total %d s)",
                 game_id, seconds, self.config.playtime_seconds[game_id])
        return True

    def get_playtime(self, game_id: str) -> int:
        """Temps de jeu cumulé en secondes (0 si jamais joué)."""
        return self.config.playtime_seconds.get(game_id, 0)

    def last_played(self, game_id: str) -> str | None:
        """Date ISO de la dernière session, ou None."""
        return self.config.last_played.get(game_id)

    def free_space_mb(self) -> int | None:
        """Mo libres sur le disque du dossier d'installation, None si illisible.

        None = « je ne sais pas » : désactive la vérification, ne la fait
        jamais échouer.
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

        Index insensible à la casse en plus : le catalogue écrit « hp6.7z.001 »,
        l'API ne publie que « HP6.7z.001 », et ces versions perdaient sinon
        leur vérification sans bruit.
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

        Même index insensible à la casse que les empreintes ; une ambiguïté
        est ignorée plutôt que devinée.
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

        Pas `version.size_mb`, la taille INSTALLÉE (1,77 à 2,30 fois plus,
        règle 86). Multi-parts : tout ou rien — une somme partielle ferait
        couper un téléchargement sain par le garde-fou de taille.
        """
        if version.download_parts:
            tailles = [self._size_for(url) for url in version.download_parts]
            return round(sum(tailles) / 1024 / 1024) if all(tailles) else 0
        octets = self._size_for(version.download_url)
        return round(octets / 1024 / 1024) if octets else 0

    def octets_deja_telecharges(self, game_id: str, version: GameVersion) -> int:
        """Ce qui attend déjà dans le cache pour cette version, en octets.

        Sert à DIRE que la reprise existe (sinon on croit avoir tout perdu à
        80 % et on abandonne). Compté au disque : le fait survit à la fermeture.
        Le préfixe couvre fichier unique et volumes (`.7z.001.part`).
        """
        dossier = self.config.cache_path
        if not dossier.is_dir():
            return 0
        prefixe = self.chemin_archive(game_id, version).name
        total = 0
        for fichier in dossier.glob(prefixe + "*"):
            try:
                total += fichier.stat().st_size
            except OSError:
                continue        # supprimé entre le glob et le stat : il ne compte pas
        return total

    def reprise(self, game: GameData) -> tuple[float, float] | None:
        """Téléchargement INTERROMPU qui attend dans le cache.

        Rend `(part reçue de 0 à 1, Mo restants)`, ou None s'il n'y a rien à
        reprendre. Calcul unique pour le bouton ET la vignette (règle 98).
        """
        version = game.current_download
        if version is None:
            return None
        # Poids RÉEL publié par GitHub, sinon la taille installée du catalogue.
        poids = self.archive_size_mb(version) or version.size_mb
        if not poids:
            return None
        deja_mo = self.octets_deja_telecharges(game.id, version) / 1_048_576
        if not 0 < deja_mo < poids * REPRISE_SEUIL:
            return None
        return deja_mo / poids, poids - deja_mo

    def chemin_archive(self, game_id: str, version: GameVersion) -> Path:
        """Ou atterrit l'archive de cette version dans le cache.

        SOURCE UNIQUE du nom (téléchargement, résidus, reprise). Il porte la
        VERSION : deux releases de HP5 publient le même `hp5.7z.001`, et une
        part restée en cache s'installait sous l'autre numéro (règle 83).
        """
        return self.config.cache_path / f"{game_id}_v{version.version}.7z"

    def _digest_for(self, url: str | None) -> str:
        """Empreinte publiée pour cette URL ("" si inconnue)."""
        if not url:
            return ""
        return self._asset_digests.get(url) or self._digests_lower.get(url.lower(), "")

    def expected_hashes(self, version: GameVersion) -> tuple[str | None, list[str]]:
        """Empreintes à vérifier pour une version : (sha256 simple, sha256 des parts).

        Le catalogue d'abord (seule option hors GitHub), puis les empreintes
        publiées par GitHub (règle 75). (None, []) sans source : vérification
        sautée, jamais un échec.
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

    # ──────────────────── Bandes-annonces ────────────────────

    def trailers(self) -> tuple:
        """Bandes-annonces déclarées par le catalogue (vide s'il n'en déclare pas)."""
        return self._catalog.trailers

    def trailer_hash(self, trailer) -> str | None:
        """Empreinte à vérifier pour cette bande-annonce, ou None.

        Mêmes sources et même ordre que `expected_hashes`.
        """
        return trailer.sha256 or self._digest_for(trailer.url) or None

    def trailer_size_mb(self, trailer) -> int:
        """Poids réel de la bande-annonce en Mo, sinon celui du catalogue.

        Même chiffre pour le garde-fou du téléchargeur et le libellé du bouton.
        """
        octets = self._size_for(trailer.url)
        return round(octets / 1024 / 1024) if octets else trailer.size_mb

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

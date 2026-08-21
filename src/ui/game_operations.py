"""Contrôleur des opérations de jeu — téléchargement, installation, mise à jour."""

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.downloader import Downloader
from src.core.game_data import GameData, GameVersion
from src.core.game_manager import GameManager, GameState
from src.core.i18n import tr
from src.core.installer import Installer
from src.core.system_checks import needed_space_mb
from src.core.thread_utils import arreter_a_la_fermeture
from src.ui.speed_tracker import SpeedTracker

log = logging.getLogger(__name__)


def _supprimer_residus(dest: Path) -> int:
    """Efface les fichiers de travail d'un téléchargement abandonné. Retourne le nombre.

    Tout ce qui commence par le nom de la destination SUIVI D'UN POINT lui
    appartient : « .part » pour un fichier unique, « .001 » / « .002 » et leurs
    « .part » pour un multi-volumes. L'archive complète elle-même (`dest`,
    sans point ajouté) n'est pas visée : elle n'existe qu'après un
    téléchargement réussi, et l'installateur a sa propre règle pour la retirer.
    """
    efface = 0
    for residu in dest.parent.glob(dest.name + ".*"):
        try:
            residu.unlink()
            efface += 1
        except OSError:
            # Encore verrouillé par un thread zombie sous Windows. Sans gravité :
            # le prochain téléchargement de cette version le réécrira.
            log.debug("Résidu encore verrouillé, laissé en place : %s", residu)
    if efface:
        log.info("%d fichier(s) de travail supprimé(s) pour %s", efface, dest.name)
    return efface


class GameOperations(QObject):
    """Orchestre le téléchargement et l'installation des jeux.

    Gère le cycle : download → install → post-install patches.
    Communique avec la vue via des signaux Qt.
    """

    # Progression téléchargement : (octets téléchargés, octets total, vitesse bytes/s, eta secondes)
    download_progress = pyqtSignal(int, int, float, float)
    # Progression installation : pourcentage 0-100
    install_progress = pyqtSignal(int)
    # Info multi-parts : (part courante, total)
    part_info = pyqtSignal(int, int)
    # Opération terminée avec succès
    operation_finished = pyqtSignal(object)  # GameData
    # Erreur pendant l'opération
    operation_error = pyqtSignal(str, str)  # (titre, message)
    # État d'un jeu a changé (pour rafraîchir l'UI)
    state_changed = pyqtSignal()
    # Message de statut
    status_message = pyqtSignal(str)
    # Phase de l'opération en cours : "download" | "verify" | "install"
    phase_changed = pyqtSignal(str)

    def __init__(self, manager: GameManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._downloader: Downloader | None = None
        self._installer: Installer | None = None
        self._speed_tracker = SpeedTracker()
        self._target_version: GameVersion | None = None
        self._active_game: GameData | None = None
        # True si la version installée doit être désinstallée APRÈS le téléchargement
        # (jamais avant : un échec réseau ne doit pas laisser l'utilisateur sans jeu).
        self._uninstall_first = False
        # Downloaders annulés dont le thread n'a pas fini dans le délai
        # (read réseau bloquant) — gardés vivants jusqu'à leur fin réelle.
        self._zombies: list[Downloader] = []
        self._phase = ""  # phase courante (dédupliquée avant émission)

    def _set_phase(self, phase: str) -> None:
        if phase != self._phase:
            self._phase = phase
            self.phase_changed.emit(phase)

    @property
    def is_busy(self) -> bool:
        """True si un téléchargement ou une installation est en cours."""
        return self._downloader is not None or self._installer is not None

    @property
    def active_game(self) -> GameData | None:
        return self._active_game

    # ──────────────────── Téléchargement ────────────────────

    def check_disk_space(self, version: GameVersion) -> int | None:
        """Vérifie l'espace disque. Retourne les Mo libres si insuffisant, None si OK."""
        free_mb = self._manager.free_space_mb()
        if free_mb is None:
            return None  # disque non interrogeable → pas de blocage
        besoin = needed_space_mb(version.size_mb,
                                 self._manager.archive_size_mb(version))
        return free_mb if free_mb < besoin else None

    def download(self, game: GameData, version: GameVersion, *,
                 uninstall_first: bool = False) -> None:
        """Lance le téléchargement d'une version de jeu.

        `uninstall_first=True` (switch de version) : la version installée n'est
        supprimée qu'une fois le téléchargement terminé et vérifié.
        """
        if self.is_busy:
            self.status_message.emit(tr("Un téléchargement ou installation est déjà en cours."))
            return
        if not version.is_available:
            # Point de passage unique de download / switch_version / repair :
            # aucun chemin ne doit lancer un Downloader sans source, sous peine
            # du message d'erreur générique qui accuse la connexion réseau.
            log.warning("Version %s de %s sans source de téléchargement", version.version, game.id)
            self.status_message.emit(
                tr("{} n'est pas encore téléchargeable — les fichiers arrivent bientôt.")
                .format(game.name)
            )
            return

        self._target_version = version
        self._active_game = game
        self._uninstall_first = uninstall_first
        self._manager.set_game_state(game.id, GameState.DOWNLOADING)
        self._speed_tracker.reset()
        self.state_changed.emit()
        self.status_message.emit(tr("Téléchargement de {} v{}…").format(game.name, version.version))

        archive_name = f"{game.id}_v{version.version}.7z"
        dest = self._manager.config.cache_path / archive_name
        # Empreintes : celles du catalogue si renseignées, sinon celles publiées
        # par GitHub (récupérées sans requête dédiée). Vide → vérification sautée.
        sha256, sha256_parts = self._manager.expected_hashes(version)
        if not sha256 and not sha256_parts:
            log.info("Aucune empreinte disponible pour %s v%s — vérification sautée",
                     game.id, version.version)
        self._downloader = Downloader(
            url=version.download_url, destination=dest,
            parts=version.download_parts,
            # Poids RÉEL de l'archive quand GitHub l'a publié : le garde-fou
            # du téléchargeur (×1,5) vise une archive, or `size_mb` est la
            # taille installée — la tolérance valait donc ×3 dans les faits.
            expected_size_mb=self._manager.archive_size_mb(version) or version.size_mb,
            expected_sha256=sha256,
            expected_sha256_parts=sha256_parts,
            parent=self,
        )
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.download_finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)
        self._downloader.verifying.connect(self._on_verifying)
        if version.download_parts:
            self._downloader.part_info.connect(self._on_part_info)
        self._set_phase("download")
        self._downloader.start()

    def cancel_download(self) -> None:
        """Annule le téléchargement en cours."""
        dl = self._downloader
        self._downloader = None
        dest: Path | None = None
        if dl is not None:
            dest = dl.destination
            self._disconnect_downloader(dl)
            dl.cancel()
            # Attendre l'arrêt réel du thread : sans ça, un re-téléchargement
            # immédiat rouvre le même .part pendant que l'ancien thread écrit
            # encore → PermissionError (verrou de fichier Windows).
            if dl.wait(3000):
                dl.deleteLater()
            else:
                # Thread bloqué sur un read réseau (timeout jusqu'à 120 s) :
                # nettoyage différé via le QThread.finished natif.
                log.warning("Downloader encore actif après annulation — nettoyage différé")
                self._zombies.append(dl)
                dl.finished.connect(lambda: self._reap_zombie(dl))
        # Nettoyer TOUT ce que ce téléchargement avait semé : le « .part » d'un
        # fichier unique, mais aussi les volumes d'un multi-parts et leur propre
        # « .part ». L'ancien code ne supprimait que `dest.with_suffix(".part")`,
        # un fichier qui n'existe JAMAIS dans le chemin multi-parts : annuler
        # HP5 après la première part laissait 2 Go dans le cache, définitivement
        # et sans que rien ne les montre.
        if dest is not None:
            _supprimer_residus(dest)
        game = self._active_game
        self._active_game = None
        self._target_version = None
        self._uninstall_first = False
        self._phase = ""
        if game is not None:
            # Re-détecter plutôt que forcer NOT_INSTALLED : pour une mise à jour /
            # réparation annulée, l'ancienne version est toujours installée.
            self._manager.redetect_state(game.id)
        self.state_changed.emit()
        self.status_message.emit(tr("Téléchargement annulé."))

    def cancel_all(self) -> None:
        """Annule toute opération en cours (appelé à la fermeture).

        L'attente n'est PAS facultative et son résultat n'est PAS jetable : un
        thread encore vivant est détruit avec cet objet, ce qui abandonne le
        processus sans un mot. `arreter_a_la_fermeture` borne l'affaire — voir
        `src.core.thread_utils` pour le pourquoi de `terminate()`.

        Les zombies aussi : ils sont déparentés, donc c'est le vidage de la
        liste qui lâche la dernière référence Python, et le thread mourrait
        alors exactement de la même façon.
        """
        if self._downloader is not None:
            self._downloader.cancel()
            arreter_a_la_fermeture(self._downloader, "Téléchargement")
        if self._installer is not None:
            self._installer.cancel()
            arreter_a_la_fermeture(self._installer, "Installation")
        for z in self._zombies:
            arreter_a_la_fermeture(z, "Téléchargement annulé")
        self._zombies.clear()

    def _reap_zombie(self, dl: Downloader) -> None:
        """Détruit un downloader annulé une fois son thread réellement terminé."""
        if dl in self._zombies:
            self._zombies.remove(dl)
        dl.deleteLater()

    def _disconnect_downloader(self, dl: Downloader) -> None:
        """Disconnect symétrique des signaux du downloader."""
        try:
            dl.progress.disconnect(self._on_download_progress)
            dl.download_finished.disconnect(self._on_download_finished)
            dl.error.disconnect(self._on_download_error)
            dl.verifying.disconnect(self._on_verifying)
        except TypeError:
            pass
        try:
            dl.part_info.disconnect(self._on_part_info)
        except TypeError:
            pass

    def _disconnect_installer(self, inst: Installer) -> None:
        """Disconnect symétrique des signaux de l'installer."""
        try:
            inst.progress.disconnect(self._on_install_progress)
            inst.finalizing.disconnect(self._on_finalizing)
            inst.install_finished.disconnect(self._on_install_finished)
            inst.error.disconnect(self._on_install_error)
        except TypeError:
            pass

    # ──────────────────── Installation ────────────────────

    def install(self, game: GameData, archive_path: Path, *, delete_archive: bool = True) -> None:
        """Lance l'installation d'un jeu depuis une archive."""
        self._active_game = game
        self._manager.set_game_state(game.id, GameState.INSTALLING)
        self.state_changed.emit()

        dest = self._manager.config.install_path
        config_files = [
            (cf.source, cf.destination)
            for cf in game.post_install.config_files
        ]
        game_dir = Path(game.executable).parts[0] if game.executable else None
        self._installer = Installer(
            archive_path, dest,
            registry_entries=list(game.post_install.registry),
            config_files=config_files,
            game_dir=game_dir,
            delete_archive=delete_archive, parent=self,
        )
        self._installer.progress.connect(self._on_install_progress)
        self._installer.finalizing.connect(self._on_finalizing)
        self._installer.install_finished.connect(self._on_install_finished)
        self._installer.error.connect(self._on_install_error)
        self._set_phase("install")
        self._installer.start()

    # ──────────────────── Version switch ────────────────────

    def switch_version(self, game: GameData, version: GameVersion) -> None:
        """Télécharge la nouvelle version, PUIS désinstalle l'actuelle.

        L'ordre est volontaire : un téléchargement échoué/annulé ne doit jamais
        laisser l'utilisateur sans aucune version installée.
        """
        if self.is_busy:
            self.status_message.emit(tr("Un téléchargement ou installation est déjà en cours."))
            return
        self.download(game, version, uninstall_first=self._manager.is_installed(game.id))

    def repair(self, game: GameData) -> None:
        """Re-télécharge l'archive (vérifiée par SHA-256 si dispo) et réinstalle par-dessus."""
        if self.is_busy:
            self.status_message.emit(tr("Un téléchargement ou installation est déjà en cours."))
            return
        installed = self._manager.installed_version(game.id)
        ver = (game.get_version(installed) if installed else None) or game.current_download
        if ver is None:
            self.status_message.emit(tr("Aucune version disponible."))
            return
        self.status_message.emit(tr("Vérification de {}…").format(game.name))
        self.download(game, ver)

    # ──────────────────── Callbacks téléchargement ────────────────────

    def _on_verifying(self) -> None:
        """Le downloader vérifie l'empreinte d'un fichier complet (part en cache)."""
        self._set_phase("verify")
        self.status_message.emit(tr("Vérification de l'archive…"))

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            return
        # Le stream a (re)pris → retour en phase téléchargement après une vérification
        self._set_phase("download")
        self._speed_tracker.update(downloaded)
        if not self._speed_tracker.should_update_ui():
            return
        self.download_progress.emit(
            downloaded, total,
            self._speed_tracker.speed,
            self._speed_tracker.eta(downloaded, total),
        )

    def _on_download_finished(self, archive_path_str: str) -> None:
        if self._downloader is not None:
            self._disconnect_downloader(self._downloader)
        self._downloader = None
        # Mémoriser la vitesse observée : elle sert à annoncer une durée AVANT
        # le clic sur les téléchargements suivants (voir estimate_duration).
        # `speed` est une PROPRIÉTÉ : l'appeler levait « 'float' object is not
        # callable » à chaque téléchargement réussi, donc AVANT `install()` —
        # aucun jeu ne pouvait plus s'installer et l'utilisateur recevait un
        # rapport de crash à 100 %. Voir tests/test_game_operations.py.
        observed = self._speed_tracker.speed
        if observed > 0:
            self._manager.config.last_download_speed = observed
            self._manager.config.save()
        game = self._active_game
        if game is None:
            return
        # Switch de version : l'ancienne installation n'est supprimée que maintenant,
        # le téléchargement de la nouvelle étant terminé et vérifié.
        if self._uninstall_first:
            self._uninstall_first = False
            self._manager.uninstall_game(game.id)  # install() repasse l'état à INSTALLING juste après
        self.status_message.emit(tr("Installation de {}…").format(game.name))
        self.install(game, Path(archive_path_str),
                     delete_archive=self._manager.config.delete_archives)

    def _on_download_error(self, message: str) -> None:
        if self._downloader is not None:
            self._disconnect_downloader(self._downloader)
        self._downloader = None
        game = self._active_game
        self._active_game = None
        self._target_version = None
        self._uninstall_first = False
        self._phase = ""
        if game is not None:
            # Re-détecter : une mise à jour/réparation échouée laisse l'ancienne
            # version installée (la désinstallation n'a lieu qu'après téléchargement).
            self._manager.redetect_state(game.id)
        self.state_changed.emit()
        self.status_message.emit(tr("Erreur : {}").format(message))
        self.operation_error.emit(
            tr("Échec du téléchargement"),
            tr("Le téléchargement a échoué.\nVérifiez votre connexion internet et réessayez."),
        )

    def _on_part_info(self, current: int, total: int) -> None:
        self.part_info.emit(current, total)

    # ──────────────────── Callbacks installation ────────────────────

    def _on_install_progress(self, pct: int) -> None:
        self.install_progress.emit(pct)

    def _on_finalizing(self) -> None:
        """Extraction finie, travail post-extraction en cours."""
        self._set_phase("finalize")
        self.status_message.emit(tr("Finalisation de l'installation…"))

    def _on_install_finished(self, _path: str) -> None:
        if self._installer is not None:
            self._disconnect_installer(self._installer)
        self._installer = None
        self._phase = ""
        game = self._active_game
        self._active_game = None
        if game is None:
            return

        exe_path = self._manager.config.install_path / game.executable
        if not exe_path.exists():
            log.warning("Exécutable introuvable après extraction : %s", exe_path)
            self._manager.set_game_state(game.id, GameState.NOT_INSTALLED)
            self.state_changed.emit()
            self.status_message.emit(tr("Installation incomplète."))
            self.operation_error.emit(
                tr("Installation incomplète"),
                tr("L'installation semble incomplète : l'exécutable du jeu est introuvable.\nL'archive est peut-être corrompue."),
            )
            return

        # NB : pas d'apply_pre_launch_patches ici — les .ini live dans Documents
        # et n'existent souvent pas encore à ce stade. Ils seront patchés au lancement.
        self._manager.set_game_state(game.id, GameState.INSTALLED)
        target_ver = self._target_version
        self._target_version = None
        self._manager.save_installed_version(game.id, target_ver.version if target_ver else None)
        self.state_changed.emit()
        self.status_message.emit(tr("{} installé avec succès !").format(game.name))
        self.operation_finished.emit(game)

    def _on_install_error(self, message: str) -> None:
        if self._installer is not None:
            self._disconnect_installer(self._installer)
        self._installer = None
        self._phase = ""
        game = self._active_game
        self._active_game = None
        self._target_version = None
        self._uninstall_first = False
        if game is not None:
            self._manager.redetect_state(game.id)
        self.state_changed.emit()
        self.status_message.emit(tr("Erreur d'installation : {}").format(message))
        self.operation_error.emit(
            tr("Échec de l'installation"),
            tr("L'installation a échoué.\nL'archive est peut-être corrompue. Réessayez le téléchargement."),
        )

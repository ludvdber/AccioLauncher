"""Cycle de vie des vérifications de mise à jour, et téléchargement de l'exe.

Extrait de `main_window.py`, qui portait la création des `UpdateChecker`, leur
arrêt propre, la re-tentative hors ligne, l'état de la mise à jour du launcher
et le téléchargement de son exe — soit deux cents lignes qui ne touchaient aucun
widget.

Le partage avec la fenêtre suit une règle simple : **ici, rien qui se voie**.
Le dispatcher fait tourner des threads et émet des signaux ; c'est `MainWindow`
qui décide ce que ça affiche (bandeau, toast, statut, dialogue). Un
`QMessageBox` posé depuis ce module aurait ramené la fenêtre dans le fichier
qu'on vient d'en sortir.

Trois précautions non négociables sont conservées telles quelles :

- **Aucun `QThread` n'est remplacé pendant qu'il tourne** — il resterait enfant
  de la fenêtre et mourrait avec elle (« QThread: Destroyed while thread is
  still running », abandon du process, « le launcher plante quand on le ferme »).
- **Un checker encore bloqué sur un read réseau est déparenté**, pas détruit :
  il survit à la fenêtre et se nettoie sur son `finished` natif.
- **La re-tentative hors ligne est ré-armée à CHAQUE échec**, pas seulement à la
  transition — sinon un seul essai serait fait, et rebrancher son câble
  laisserait « Télécharger » grisé jusqu'au prochain démarrage.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.core.downloader import Downloader
from src.core.formatting import format_progress_line
from src.core.game_manager import GameManager
from src.core.i18n import tr
from src.core.self_update import apply_update_and_restart, can_self_update
from src.core.thread_utils import arreter_a_la_fermeture
from src.core.updater import UpdateChecker
from src.ui.speed_tracker import SpeedTracker
from src.ui.utils import open_url

log = logging.getLogger(__name__)

# Délai avant de re-tester le réseau quand plus rien ne répond. Assez court pour
# qu'un câble rebranché se voie tout de suite, assez long pour ne pas marteler
# l'API GitHub — et de toute façon sans coût quand on est réellement hors ligne
# (les requêtes échouent au premier DNS).
OFFLINE_RETRY_MS = 45_000

# Checkers encore actifs à la fermeture : déparentés de la fenêtre et gardés
# vivants ici jusqu'à leur fin réelle. Même contrat que GameOperations._zombies.
_orphaned_checkers: list[UpdateChecker] = []


def _reap_checker(checker: UpdateChecker) -> None:
    """Libère un checker orphelin une fois son thread réellement terminé."""
    if checker in _orphaned_checkers:
        _orphaned_checkers.remove(checker)
    checker.deleteLater()


class UpdateDispatcher(QObject):
    """Possède les `UpdateChecker` et le téléchargement de la mise à jour."""

    # ── Résultats des vérifications ──
    catalog_updated = pyqtSignal(object)          # Catalog distant plus récent
    launcher_update = pyqtSignal(str, str, str, str)  # version, url, asset, sha256
    update_counts = pyqtSignal(int)               # nb de jeux à mettre à jour
    download_counts = pyqtSignal(dict)            # compteurs ⬇ de GitHub
    asset_sizes = pyqtSignal(dict)                # tailles réelles des archives
    network_status = pyqtSignal(bool)

    # ── Téléchargement de l'exe de mise à jour ──
    launcher_message = pyqtSignal(str)   # texte prêt à poser dans le bandeau
    launcher_busy = pyqtSignal(bool)     # bouton du bandeau à griser
    launcher_ready = pyqtSignal()        # exe en place : la fenêtre doit fermer

    def __init__(self, manager: GameManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._checker: UpdateChecker | None = None
        self._extra_checkers: list[UpdateChecker] = []

        # État de la mise à jour du launcher, tel que l'a annoncé GitHub.
        self.version: str = ""
        self.url: str = ""
        self.asset_url: str = ""
        self.asset_sha256: str = ""

        self._download: Downloader | None = None
        self._speed = SpeedTracker()

        self._offline_retry = QTimer(self)
        self._offline_retry.setSingleShot(True)
        self._offline_retry.timeout.connect(self.start)

    # ──────────────────── Vérifications ────────────────────

    def _games_asset_urls(self) -> dict[str, list[list[str]]]:
        """Snapshot game_id → versions → URLs d'assets (compteur ⬇, thread-safe)."""
        return {
            entry.game.id: [
                [v.download_url or ""] + list(v.download_parts or [])
                for v in entry.game.versions
            ]
            for entry in self._manager.get_games()
        }

    def _new_checker(self, *, forced: bool) -> UpdateChecker:
        catalog = self._manager.catalog
        return UpdateChecker(
            catalog_url=catalog.catalog_url,
            # Version « 0 » → force le fetch, quel que soit ce qu'on a déjà.
            current_catalog_version="0" if forced else catalog.catalog_version,
            installed_versions=self._manager.config.installed_versions,
            games_asset_urls=self._games_asset_urls(),
            parent=self,
        )

    def start(self) -> None:
        """Lance la vérification de fond.

        Toujours lancée : sans réseau, ou si GitHub répond mal, chaque étape
        échoue proprement et le launcher garde ce qu'il a déjà — le catalogue
        embarqué ou le dernier téléchargé (`load_catalog` prend le plus récent
        des deux). Il n'y a donc rien à gagner à ne pas essayer, et un réglage
        « ne pas vérifier » ne faisait que priver l'utilisateur des empreintes
        SHA-256 qui vérifient ses téléchargements.
        """
        if self._checker is not None:
            self.shutdown_checker(self._checker)
        self._checker = self._new_checker(forced=False)
        self._checker.catalog_updated.connect(self.catalog_updated)
        self._checker.launcher_update.connect(self.launcher_update)
        self._checker.update_counts.connect(self.update_counts)
        self._checker.download_counts.connect(self._on_download_counts)
        self._checker.asset_digests.connect(self._on_asset_digests)
        self._checker.asset_sizes.connect(self._on_asset_sizes)
        self._checker.network_status.connect(self.network_status)
        self._checker.start()

    def forced_checker(self) -> UpdateChecker:
        """Crée et câble un checker forcé, puis le RETOURNE — sans le démarrer.

        L'appelant y branche ses propres slots (`catalog_updated`,
        `launcher_update`, retour dans le dialogue des Paramètres) avant de le
        lancer : la durée de vie de ce dialogue ne regarde pas ce module. Le
        retrait de la liste des checkers en cours est déjà branché ici.
        """
        checker = self._new_checker(forced=True)
        self._extra_checkers.append(checker)
        checker.update_counts.connect(self.update_counts)
        checker.download_counts.connect(self._on_download_counts)
        checker.asset_digests.connect(self._on_asset_digests)
        checker.asset_sizes.connect(self._on_asset_sizes)
        checker.network_status.connect(self.network_status)
        checker.finished.connect(lambda: self._forget(checker))
        return checker

    def _on_asset_digests(self, digests: dict) -> None:
        """Empreintes SHA-256 publiées par GitHub, pour vérifier les archives.

        Reçues dans la même réponse que les compteurs ⬇ : aucune requête
        supplémentaire. Voir `GameManager.expected_hashes`.

        Ce détour par une méthode du dispatcher n'est pas décoratif : brancher
        `checker.asset_digests` directement sur `manager.set_asset_digests`
        lève `SystemError` à la connexion. PyQt garde une référence FAIBLE vers
        le receveur d'une méthode liée, et `GameManager` déclare `__slots__`
        sans `__weakref__` — il n'est donc pas référençable faiblement. Le
        symptôme n'apparaît qu'au premier vrai câblage, jamais à l'import.
        """
        self._manager.set_asset_digests(digests)

    def _on_asset_sizes(self, sizes: dict) -> None:
        """Tailles réelles des archives, reçues dans la même réponse que le reste.

        Le manager d'abord, la fenêtre ensuite : le bouton « TÉLÉCHARGER » porte
        le poids et doit se refaire une fois le vrai chiffre connu. Même détour
        obligatoire que pour les empreintes — `GameManager` n'est pas
        référençable faiblement, une connexion directe lèverait `SystemError`.
        """
        self._manager.set_asset_sizes(sizes)
        self.asset_sizes.emit(sizes)

    def _on_download_counts(self, counts: dict) -> None:
        """Le manager d'abord, la fenêtre ensuite : elle rafraîchit la fiche.

        Même raison que ci-dessus pour ne pas viser le manager directement.
        """
        self._manager.set_download_counts(counts)
        self.download_counts.emit(counts)

    def _forget(self, checker: UpdateChecker) -> None:
        if checker in self._extra_checkers:
            self._extra_checkers.remove(checker)

    def schedule_retry(self, online: bool) -> None:
        """Re-teste le réseau tant que rien ne répond. Voir le module."""
        if online:
            self._offline_retry.stop()
        else:
            self._offline_retry.start(OFFLINE_RETRY_MS)

    # ──────────────────── Mise à jour du launcher ────────────────────

    def remember(self, version: str, url: str, asset_url: str, asset_sha256: str) -> None:
        """Retient ce que GitHub a annoncé, pour le clic qui viendra peut-être."""
        self.version = version
        self.url = url
        self.asset_url = asset_url
        self.asset_sha256 = asset_sha256

    @property
    def can_install_itself(self) -> bool:
        """La mise à jour peut-elle s'installer sans passer par le navigateur ?"""
        return bool(self.asset_url) and can_self_update()

    def download(self) -> None:
        """Auto-update en un clic si possible, sinon ouverture de la page release."""
        if self._download is not None:
            return
        if not self.can_install_itself:
            if self.url:
                open_url(self.url)
            return
        dest = self._manager.config.cache_path / f"AccioLauncher_v{self.version}.exe"
        dest.unlink(missing_ok=True)
        self.launcher_busy.emit(True)
        self._speed.reset()
        self.launcher_message.emit(tr("Téléchargement de la mise à jour…"))
        # L'empreinte vient de l'API GitHub (cf. UpdateChecker._check_launcher).
        # Vide → téléchargement non vérifié, comme avant : on ne bloque pas une
        # mise à jour parce que GitHub n'a pas publié de digest.
        self._download = Downloader(
            url=self.asset_url, destination=dest,
            expected_sha256=self.asset_sha256 or None,
            parent=self,
        )
        self._download.progress.connect(self._on_progress)
        self._download.download_finished.connect(self._on_finished)
        self._download.error.connect(self._on_error)
        self._download.start()

    def _on_progress(self, downloaded: int, total: int) -> None:
        """Pourcentage, volume, VITESSE et temps restant — même ligne que les jeux.

        Un simple pourcentage ne dit pas si le téléchargement avance ou s'il est
        bloqué. `format_progress_line` est la source unique de cette ligne dans
        tout le projet ; la réécrire ici la ferait diverger.
        """
        if total <= 0:
            return
        self._speed.update(downloaded)
        if not self._speed.should_update_ui() and downloaded < total:
            return
        ligne = format_progress_line(downloaded, total, self._speed.speed,
                                     self._speed.eta(downloaded, total))
        self.launcher_message.emit(f"{tr('Téléchargement de la mise à jour…')} {ligne}")

    def _on_finished(self, path_str: str) -> None:
        self._download = None
        self.launcher_busy.emit(False)
        if apply_update_and_restart(Path(path_str)):
            self.launcher_message.emit(tr("Redémarrage…"))
            log.info("Fermeture pour mise à jour vers v%s", self.version)
            self.launcher_ready.emit()
        elif self.url:
            # Mode dev / échec du script : retomber sur la page release.
            open_url(self.url)

    def _on_error(self, message: str) -> None:
        log.warning("Échec du téléchargement de la mise à jour : %s", message)
        self._download = None
        self.launcher_busy.emit(False)
        self.launcher_message.emit(
            tr("Échec du téléchargement — ouverture de la page de release"))
        if self.url:
            open_url(self.url)

    # ──────────────────── Extinction ────────────────────

    @staticmethod
    def shutdown_checker(checker: UpdateChecker) -> None:
        """Arrête un `UpdateChecker` sans jamais le détruire pendant qu'il tourne.

        Demande l'interruption (honorée entre les étapes réseau de `run()`),
        attend, et si le thread est encore bloqué sur une requête en vol, le
        déparente pour qu'il survive à la destruction de la fenêtre — son
        `finished` natif s'occupe du nettoyage.
        """
        if not checker.isRunning():
            return
        checker.requestInterruption()
        if checker.wait(3000):
            return
        log.warning("UpdateChecker encore actif à la fermeture — nettoyage différé")
        checker.setParent(None)
        _orphaned_checkers.append(checker)
        checker.finished.connect(lambda: _reap_checker(checker))

    def shutdown(self) -> None:
        """À appeler au `closeEvent` : arrête tout, dans le bon ordre.

        Le timer d'abord, sinon il ressusciterait un checker pendant qu'on
        attend justement la fin des threads.
        """
        self._offline_retry.stop()
        if self._checker is not None:
            self.shutdown_checker(self._checker)
        for checker in list(self._extra_checkers):
            self.shutdown_checker(checker)
        self._extra_checkers.clear()
        if self._download is not None:
            # Le résultat de l'attente n'est PAS jetable : ce downloader est
            # enfant du dispatcher, donc un thread encore vivant serait détruit
            # avec la fenêtre — abandon du processus, sans message. Les checkers
            # au-dessus s'en sortent par le déparentage parce qu'ils peuvent
            # survivre à la fenêtre ; un téléchargement en cours, non.
            self._download.cancel()
            arreter_a_la_fermeture(self._download, "Mise à jour du launcher")
            self._download = None

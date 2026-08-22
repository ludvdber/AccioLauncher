"""Téléchargement des bandes-annonces, une par une, en arrière-plan.

Séparé de `GameOperations` volontairement : une bande-annonce ne s'installe
pas, ne change pas l'état d'un jeu et ne doit jamais occuper la barre de
téléchargement — qui affiche un parcours « 1/4 · Téléchargement → … →
4/4 · Finalisation » qui n'a aucun sens ici. Elle a donc sa propre surface,
dans les Paramètres, et un toast quand c'est fini.
"""

import logging

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.core import trailers as store
from src.core.downloader import Downloader
from src.core.game_data import Trailer
from src.core.i18n import tr
from src.core.thread_utils import arreter_a_la_fermeture

log = logging.getLogger(__name__)

# Un téléchargement de jeu passe AVANT : au premier lancement, quelqu'un qui
# accepte les bandes-annonces va aussi lancer un jeu de 4 Go dans la minute, et
# se partager la bande passante ralentirait précisément ce qu'il attend. On
# repasse plus tard plutôt que d'entrer en concurrence.
_ATTENTE_MS = 30_000
# Reprise au demarrage : la fenetre d'abord, la connexion ensuite.
_DELAI_RATTRAPAGE_MS = 4_000


class TrailerStore(QObject):
    """Fait venir les bandes-annonces manquantes, dans l'ordre du catalogue."""

    # (faites, total, octets_de_la_courante, octets_total_de_la_courante)
    progress = pyqtSignal(int, int, int, int)
    # (téléchargées, échouées) — nommé, jamais `finished` (cf. QThread)
    job_finished = pyqtSignal(int, int)
    state_changed = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, manager, ops, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._ops = ops
        self._file: list[Trailer] = []
        self._courante: Trailer | None = None
        self._downloader: Downloader | None = None
        self._zombies: list[Downloader] = []
        self._faites = 0
        self._echecs = 0
        self._total = 0
        self._attente = QTimer(self)
        self._attente.setSingleShot(True)
        self._attente.timeout.connect(self._suivante)

    # ──────────────────── État ────────────────────

    @property
    def is_busy(self) -> bool:
        return self._downloader is not None or self._attente.isActive()

    @property
    def restantes(self) -> int:
        return len(self._file) + (1 if self._courante is not None else 0)

    # ──────────────────── Cycle de vie ────────────────────

    def start(self, trailers) -> None:
        """Met en file les bandes-annonces absentes et démarre.

        Fait le ménage des versions périmées AVANT de télécharger : c'est le
        moment où l'on sait ce que le catalogue attend, et le seul où l'espace
        libéré profite au téléchargement qui suit.
        """
        if self.is_busy:
            return
        perimes = store.fichiers_perimes(trailers)
        if perimes:
            n, octets = store.supprimer(perimes)
            log.info("Bandes-annonces périmées supprimées : %d (%d octets)", n, octets)
        self._file = store.manquantes(trailers)
        self._total = len(self._file)
        self._faites = 0
        self._echecs = 0
        if not self._file:
            self.job_finished.emit(0, 0)
            return
        self.state_changed.emit()
        self._suivante()

    def cancel(self) -> None:
        """Arrête le téléchargement en cours et vide la file."""
        self._attente.stop()
        self._file.clear()
        dl = self._downloader
        self._downloader = None
        self._courante = None
        if dl is not None:
            self._deconnecter(dl)
            dl.cancel()
            if dl.wait(3000):
                dl.deleteLater()
            else:
                # Bloqué sur un read réseau : nettoyage différé par le
                # QThread.finished natif, comme dans GameOperations.
                log.warning("Téléchargement de bande-annonce encore actif — nettoyage différé")
                self._zombies.append(dl)
                dl.finished.connect(lambda: self._reap(dl))
        self.state_changed.emit()

    def shutdown(self) -> None:
        """Extinction : un thread laissé vivant serait détruit avec son parent,
        ce qui abandonne le processus sans un mot (0xC0000409)."""
        self._attente.stop()
        if self._downloader is not None:
            self._downloader.cancel()
            arreter_a_la_fermeture(self._downloader, "Bande-annonce")
        for z in self._zombies:
            arreter_a_la_fermeture(z, "Bande-annonce annulée")
        self._zombies.clear()

    def armer_rattrapage(self, config) -> None:
        """Programme la reprise d'un téléchargement laissé en plan.

        C'est tout l'intérêt d'avoir PERSISTÉ le choix (`trailers_optin`) plutôt
        que de le traiter comme une réponse jetable : une fermeture ou une
        coupure réseau au milieu laissait sinon trois vidéos sur huit,
        définitivement, sans que rien à l'écran ne relie l'une à l'autre.

        Différé : au premier démarrage on veut la fenêtre à l'écran avant
        d'ouvrir une connexion.
        """
        if not config.trailers_optin:
            return
        QTimer.singleShot(_DELAI_RATTRAPAGE_MS, self._rattraper)

    def rattraper_apres_catalogue(self, config) -> None:
        """Le catalogue vient de changer : une bande-annonce a pu être
        ajoutée ou révisée.

        Sans ce rappel il fallait DEUX lancements pour la voir arriver —
        un pour recevoir le catalogue, un pour le rattrapage du démarrage
        — et entre les deux la fiche du jeu perdait sa vidéo : `present()`
        cherche déjà le nom de la NOUVELLE version. Ici la fenêtre est
        debout, donc pas de délai : on part tout de suite.
        """
        if config.trailers_optin:
            self._rattraper()

    def _rattraper(self) -> None:
        liste = self._manager.trailers()
        if liste:
            self.start(liste)

    # ──────────────────── Enchaînement ────────────────────

    def _suivante(self) -> None:
        if not self._file:
            self._courante = None
            self.state_changed.emit()
            self._annoncer_la_fin()
            self.job_finished.emit(self._faites, self._echecs)
            return
        # Un jeu qui se télécharge passe devant : on repasse plus tard.
        if self._ops is not None and self._ops.is_busy:
            self._attente.start(_ATTENTE_MS)
            return

        trailer = self._file.pop(0)
        self._courante = trailer
        dest = store.chemin_local(trailer)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._downloader = Downloader(
            url=trailer.url, destination=dest,
            expected_size_mb=self._manager.trailer_size_mb(trailer),
            expected_sha256=self._manager.trailer_hash(trailer),
            parent=self,
        )
        self._downloader.progress.connect(self._on_progress)
        self._downloader.download_finished.connect(self._on_finished)
        self._downloader.error.connect(self._on_error)
        self._downloader.start()
        self.state_changed.emit()

    def _on_progress(self, octets: int, total: int) -> None:
        self.progress.emit(self._faites, self._total, octets, total)

    def _on_finished(self, _chemin: str) -> None:
        self._faites += 1
        self._liberer()
        self._suivante()

    def _on_error(self, message: str) -> None:
        jeu = self._courante.game_id if self._courante is not None else "?"
        log.warning("Bande-annonce %s non téléchargée : %s", jeu, message)
        self._echecs += 1
        self._liberer()
        # On continue : une bande-annonce qui manque n'est pas une raison
        # d'abandonner les sept autres.
        self._suivante()

    def _liberer(self) -> None:
        dl = self._downloader
        self._downloader = None
        self._courante = None
        if dl is not None:
            self._deconnecter(dl)
            dl.deleteLater()

    def _reap(self, dl: Downloader) -> None:
        if dl in self._zombies:
            self._zombies.remove(dl)
        dl.deleteLater()

    def _deconnecter(self, dl: Downloader) -> None:
        """Disconnect symétrique — sinon un signal en vol touche un objet mort."""
        try:
            dl.progress.disconnect(self._on_progress)
            dl.download_finished.disconnect(self._on_finished)
            dl.error.disconnect(self._on_error)
        except TypeError:
            pass

    def _annoncer_la_fin(self) -> None:
        """Un toast, pas un modal : rien à décider, et un échec n'en est pas
        vraiment un — une bande-annonce qui manque laisse un fond fixe, pas un
        launcher cassé. Il se dit donc sans alarmer."""
        if self._faites == 0 and self._echecs == 0:
            return
        if self._echecs:
            self.status_message.emit(
                tr("Bandes-annonces : {ok} téléchargées, {echecs} indisponibles.")
                .format(ok=self._faites, echecs=self._echecs))
        else:
            self.status_message.emit(tr("Bandes-annonces téléchargées."))

    # ──────────────────── Suppression ────────────────────

    def supprimer_tout(self) -> int:
        """Efface les bandes-annonces du disque. Retourne les octets libérés."""
        self.cancel()
        _, octets = store.supprimer_tout()
        self.state_changed.emit()
        self.status_message.emit(tr("Bandes-annonces supprimées."))
        return octets

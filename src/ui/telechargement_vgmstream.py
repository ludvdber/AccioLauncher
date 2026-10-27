"""Le téléchargement de vgmstream à la première écoute de HP5 ou HP6 (1.3.1, 2026-10-28).

Il pesait 4,3 Mo dans l'exe pour les seuls joueurs de ces deux jeux. La page
Musique annonce son poids et le fait venir sur un clic ; le zip officiel est
vérifié puis posé par `vgmstream.installer`. Possédé par la `Mediatheque`
(qui vit autant que la fenêtre) : fermer la page n'arrête pas un
téléchargement commencé, et la page rouverte en voit l'avancement.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from src.core import vgmstream
from src.core.downloader import Downloader
from src.core.thread_utils import arreter_a_la_fermeture, liberer_apres_fin

log = logging.getLogger(__name__)


class TelechargementVgmstream(QObject):
    """Fait venir vgmstream, une fois ; les pages ne font que l'écouter."""

    # Pour cent, 0 à 100.
    progression = pyqtSignal(int)
    # Nommé, jamais `finished` (cf. QThread) : True si vgmstream est posé.
    termine = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dl: Downloader | None = None
        self._zip: Path | None = None
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    @property
    def en_cours(self) -> bool:
        return self._dl is not None

    def lancer(self) -> None:
        if self._dl is not None or not vgmstream.a_telecharger():
            return
        self._zip = vgmstream.dossier_installe().with_name("vgmstream-win64.zip")
        try:
            self._zip.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("vgmstream : dossier %s non créé : %s", self._zip.parent, exc)
            self.termine.emit(False)
            return
        self._dl = Downloader(url=vgmstream.URL, destination=self._zip, expected_size_mb=5,
                              expected_sha256=vgmstream.EMPREINTE_ZIP, parent=self)
        self._dl.progress.connect(self._on_progress)
        self._dl.download_finished.connect(self._on_fini)
        self._dl.error.connect(self._on_erreur)
        self._dl.start()
        self.progression.emit(0)

    def _on_progress(self, octets: int, total: int) -> None:
        total = total or vgmstream.TAILLE_ZIP
        self.progression.emit(max(0, min(100, octets * 100 // total)))

    def _on_fini(self, chemin: str) -> None:
        self._liberer()
        ok = vgmstream.installer(Path(chemin))
        self._effacer_zip()
        self.termine.emit(ok)

    def _on_erreur(self, message: str, _echec=None) -> None:
        log.warning("vgmstream non téléchargé : %s", message)
        self._liberer()
        self._effacer_zip()
        self.termine.emit(False)

    def _effacer_zip(self) -> None:
        if self._zip is not None:
            try:
                self._zip.unlink(missing_ok=True)   # notre propre téléchargement
            except OSError:
                pass

    def _liberer(self) -> None:
        dl, self._dl = self._dl, None
        if dl is None:
            return
        try:
            dl.progress.disconnect(self._on_progress)
            dl.download_finished.disconnect(self._on_fini)
            dl.error.disconnect(self._on_erreur)
        except TypeError:
            pass
        liberer_apres_fin(dl)

    def shutdown(self) -> None:
        """À la fermeture : un thread laissé vivant serait détruit avec son parent."""
        if self._dl is not None:
            self._dl.cancel()
            arreter_a_la_fermeture(self._dl, "vgmstream")

"""Orchestrateur QThread d'installation : extraction → post-install → cleanup."""

import logging
import shutil
import threading
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.extractors import extract_7z, extract_zip
from src.core.post_install import apply_config_files, apply_registry, unblock_extracted

log = logging.getLogger(__name__)


class Installer(QThread):
    """Extrait une archive et installe un jeu en arrière-plan."""

    progress = pyqtSignal(int)         # pourcentage 0-100
    # Extraction terminée, travail post-extraction en cours (déblocage NTFS,
    # copie des configs, suppression de l'archive). Sans ce signal la barre
    # restait à 100 % sans rien dire pendant des dizaines de secondes sur un
    # jeu de plusieurs Go, et l'utilisateur concluait à un blocage.
    finalizing = pyqtSignal()
    # NB : pas `finished` — ça masquerait le signal natif QThread.finished.
    install_finished = pyqtSignal(str)  # chemin du dossier d'installation
    error = pyqtSignal(str)             # message d'erreur

    def __init__(
        self,
        archive_path: Path,
        destination: Path,
        registry_entries: list[str] | None = None,
        config_files: list[tuple[str, str]] | None = None,
        game_dir: str | None = None,
        delete_archive: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.archive_path = archive_path
        self.destination = destination
        self.registry_entries = registry_entries or []
        self.config_files = config_files or []
        self.game_dir = game_dir
        self.delete_archive = delete_archive
        self._cancel_event = threading.Event()
        # DEUX listes, et c'est le fond du sujet : elles répondaient à la même
        # question (« quels dossiers l'extraction a-t-elle produits ? ») alors
        # qu'elles servent deux buts opposés.
        #
        # `_extracted_dirs` = ce qu'il faut DÉBLOQUER (Zone.Identifier). Doit
        # inclure le dossier du jeu même s'il existait déjà, sinon une
        # réparation ou une mise à jour ne débloquait plus rien du tout
        # (mesuré : 0 fichier sur 3), et UE1 repartait en « Can't find file
        # for package » sur les DLL fraîchement extraites.
        #
        # `_created_dirs` = ce qu'il est permis de SUPPRIMER en cas
        # d'annulation. Uniquement les dossiers qui n'existaient pas avant :
        # nettoyer le dossier du jeu sur une réparation annulée détruirait
        # l'installation que l'utilisateur avait déjà.
        self._extracted_dirs: list[Path] = []
        self._created_dirs: list[Path] = []

    @property
    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        """Demande l'arrêt de l'extraction."""
        self._cancel_event.set()
        log.info("Annulation de l'installation demandée")

    def run(self) -> None:
        """Boucle principale : extraction → post-install → nettoyage."""
        log.debug("Installation démarrée : archive=%s, destination=%s",
                  self.archive_path, self.destination)
        try:
            self.destination.mkdir(parents=True, exist_ok=True)
            existing_dirs = set(p.name for p in self.destination.iterdir() if p.is_dir())

            suffix = self.archive_path.suffix.lower()
            if suffix == ".001":
                suffix = Path(self.archive_path.stem).suffix.lower()

            match suffix:
                case ".7z":
                    extract_7z(self.archive_path, self.destination,
                               self.progress.emit, lambda: self._cancelled)
                case ".zip":
                    extract_zip(self.archive_path, self.destination,
                                self.progress.emit, lambda: self._cancelled)
                case _:
                    self.error.emit(f"Format d'archive non supporté : {suffix}")
                    return

            apres = set(p.name for p in self.destination.iterdir() if p.is_dir())
            new_dirs = apres - existing_dirs
            self._created_dirs = [self.destination / d for d in new_dirs]
            # Le dossier du jeu s'ajoute au déblocage même s'il préexistait :
            # c'est le cas d'une réparation ou d'une mise à jour, où l'archive
            # dépose des fichiers neufs — donc marqués par Windows — dans un
            # dossier que la différence d'inventaire ne voit pas apparaître.
            a_debloquer = set(new_dirs)
            if self.game_dir and self.game_dir in apres:
                a_debloquer.add(self.game_dir)
            self._extracted_dirs = [self.destination / d for d in a_debloquer]
            log.debug("Dossiers à débloquer : %s | créés par cette extraction : %s",
                      [str(d) for d in self._extracted_dirs],
                      [str(d) for d in self._created_dirs])

            if self._cancelled:
                self._cleanup()
                return

            self.finalizing.emit()
            count = unblock_extracted(self._extracted_dirs)
            if count > 0:
                log.info("%d fichier(s) débloqué(s) (Zone.Identifier supprimé)", count)
            apply_registry(self.registry_entries)
            apply_config_files(self.destination, self.game_dir, self.config_files)

            if self.delete_archive:
                self._delete_archive()

            log.info("Installation terminée : %s", self.destination)
            self.install_finished.emit(str(self.destination))

        except Exception as exc:
            log.exception("Erreur pendant l'installation")
            # NE PAS cleanup en cas d'erreur d'extraction — laisser les fichiers pour debug
            self.error.emit(f"Erreur d'installation : {exc}")

    def _delete_archive(self) -> None:
        """Supprime l'archive — toutes les parts pour une archive multi-volumes (.001)."""
        targets = [self.archive_path]
        if self.archive_path.suffix == ".001":
            # « jeu.7z.001 » → supprimer jeu.7z.001, .002, … (toutes les parts du set)
            stem = self.archive_path.name[: -len(".001")]
            targets = sorted(self.archive_path.parent.glob(stem + ".[0-9][0-9][0-9]"))
        for target in targets:
            try:
                target.unlink(missing_ok=True)
                log.info("Archive supprimée : %s", target)
            except PermissionError:
                log.warning("Impossible de supprimer l'archive (fichier verrouillé) : %s", target)

    def _cleanup(self) -> None:
        """Nettoie UNIQUEMENT les dossiers CRÉÉS par cette extraction.

        Deux protections : on ne supprime jamais `self.destination` (le dossier
        d'installation racine), et on ne touche jamais un dossier qui existait
        avant — annuler une réparation ne doit pas emporter l'installation que
        l'utilisateur avait déjà.
        """
        if not self._created_dirs:
            log.debug("Rien à nettoyer (aucun dossier créé par cette extraction)")
            return
        for d in self._created_dirs:
            if not d.exists():
                continue
            if d.resolve() == self.destination.resolve():
                log.critical("REFUS de supprimer le dossier d'installation racine : %s", d)
                continue
            try:
                shutil.rmtree(d)
                log.info("Fichiers partiels nettoyés : %s", d)
            except OSError as exc:
                log.error("Échec du nettoyage de %s : %s", d, exc)

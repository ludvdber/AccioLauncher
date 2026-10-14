"""Worker QThread pour scanner la taille des jeux installés en arrière-plan."""

import os
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class DiskScanWorker(QThread):
    """Calcule la taille totale d'une liste de dossiers de jeux.

    Reçoit un snapshot de chemins (préparé sur le thread principal) pour rester thread-safe.
    """
    # « qlonglong » et non `int` : côté Qt, un `int` fait 32 bits, et le total
    # d'une bibliothèque de jeux dépasse 4 Gio. 13,04 Go arrivaient en
    # 154,5 Mo — le modulo 2³² exact (mesuré le 2026-09-24).
    result = pyqtSignal(int, "qlonglong")  # (count, total_bytes)

    def __init__(self, game_paths: list[Path], parent=None) -> None:
        super().__init__(parent)
        self._game_paths = game_paths

    def run(self) -> None:
        count = len(self._game_paths)
        total_bytes = 0
        # `os.scandir` et non `rglob` + `stat` : sous Windows, la taille vient
        # avec l'entrée de dossier, sans appel système par fichier. Mesuré le
        # 2026-10-14 sur les 8 jeux de Ludo (2 040 fichiers, 25,9 Go) : 10 ms
        # contre 150, à disque chaud. Ce fil tenait le verrou de Python
        # pendant que la page des Paramètres se construisait : l'ouverture
        # « freezait » (Ludo).
        pile = [str(p) for p in self._game_paths if p.exists()]
        while pile:
            try:
                with os.scandir(pile.pop()) as entrees:
                    for entree in entrees:
                        # Interruption coopérative : permet à done() d'attendre
                        # la fin du thread sans risquer un wait() infini.
                        if self.isInterruptionRequested():
                            return
                        if entree.is_dir(follow_symlinks=False):
                            pile.append(entree.path)
                        elif entree.is_file(follow_symlinks=False):
                            total_bytes += entree.stat(follow_symlinks=False).st_size
            except OSError:
                pass
        self.result.emit(count, total_bytes)

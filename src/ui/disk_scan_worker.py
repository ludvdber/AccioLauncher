"""Worker QThread pour scanner la taille des jeux installés en arrière-plan."""

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
        for game_path in self._game_paths:
            if not game_path.exists():
                continue
            try:
                for f in game_path.rglob("*"):
                    # Interruption coopérative : permet à closeEvent d'attendre
                    # la fin du thread sans risquer un wait() infini.
                    if self.isInterruptionRequested():
                        return
                    if f.is_file():
                        total_bytes += f.stat().st_size
            except OSError:
                pass
        self.result.emit(count, total_bytes)

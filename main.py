import logging
import sys

from PyQt6.QtWidgets import QApplication

from src.core.config import CONFIG_FILE_PATH, DEFAULT_INSTALL_PATH

LOG_DIR = DEFAULT_INSTALL_PATH
LOG_FILE = LOG_DIR / "accio_launcher.log"


def _setup_logging() -> None:
    """Configure le logging : DEBUG dans le fichier, INFO dans la console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    # Console — INFO
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Fichier — DEBUG
    file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def main():
    _setup_logging()

    app = QApplication(sys.argv)

    # Import après QApplication pour que les widgets soient disponibles
    from src.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

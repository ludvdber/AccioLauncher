import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from src.core.config import DEFAULT_INSTALL_PATH

LOG_DIR = DEFAULT_INSTALL_PATH
LOG_FILE = LOG_DIR / "accio_launcher.log"


def _setup_logging() -> None:
    """Configure le logging : DEBUG dans le fichier, INFO dans la console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def _create_splash() -> QSplashScreen:
    """Crée un splash screen avec le logo Accio Launcher."""
    from PyQt6.QtCore import QRect
    from src.ui.fonts import load_fonts, cinzel_decorative, cinzel

    load_fonts()

    W, H = 480, 260
    pix = QPixmap(W, H)
    pix.fill(QColor("#060611"))

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # ⚡ centré en haut
    p.setPen(QColor("#d4a017"))
    p.setFont(QFont("Segoe UI Emoji", 36))
    p.drawText(QRect(0, 25, W, 50), Qt.AlignmentFlag.AlignCenter, "\u26a1")

    # "Accio Launcher" en Cinzel Decorative
    p.setFont(cinzel_decorative(36))
    p.drawText(QRect(0, 85, W, 50), Qt.AlignmentFlag.AlignCenter, "Accio Launcher")

    # Ligne décorative dorée
    p.setPen(QPen(QColor(212, 160, 23, 80), 1.0))
    y_line = 145
    margin = 120
    p.drawLine(margin, y_line, W - margin, y_line)

    # Sous-titre
    p.setPen(QColor("#8a8aaa"))
    p.setFont(cinzel(11))
    p.drawText(QRect(0, 155, W, 30), Qt.AlignmentFlag.AlignCenter, "CHARGEMENT\u2026")

    # Bordure dorée fine
    p.setPen(QPen(QColor(212, 160, 23, 40), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(0, 0, W - 1, H - 1)

    p.end()

    splash = QSplashScreen(pix)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    return splash


def main():
    _setup_logging()

    app = QApplication(sys.argv)

    splash = _create_splash()
    splash.show()
    app.processEvents()

    from src.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

import logging
import logging.handlers
import sys
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from src.core.config import ASSETS_DIR, DEFAULT_INSTALL_PATH

LOG_DIR = DEFAULT_INSTALL_PATH
LOG_FILE = LOG_DIR / "accio_launcher.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 Mo
LOG_BACKUP_COUNT = 3


def _setup_logging() -> None:
    """Configure le logging : DEBUG dans le fichier (rotation), INFO dans la console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        str(LOG_FILE), encoding="utf-8",
        maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
    )
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
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Logo centré en haut
    logo_path = str(ASSETS_DIR / "accio_launcher.png")
    logo = QPixmap(logo_path)
    if not logo.isNull():
        logo_size = 64
        logo_scaled = logo.scaled(logo_size, logo_size,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        logo_x = (W - logo_scaled.width()) // 2
        p.drawPixmap(logo_x, 15, logo_scaled)

    # "Accio Launcher" en Cinzel Decorative
    p.setPen(QColor("#d4a017"))
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
    try:
        _setup_logging()
    except OSError as exc:
        print(f"Impossible d'initialiser le logging : {exc}", file=sys.stderr)

    log = logging.getLogger(__name__)

    try:
        app = QApplication(sys.argv)

        splash = _create_splash()
        splash.show()
        app.processEvents()

        from src.ui.main_window import MainWindow

        window = MainWindow()
        window.show()
        splash.finish(window)
        sys.exit(app.exec())

    except Exception as exc:
        log.critical("Erreur fatale au démarrage : %s", exc, exc_info=True)
        # Tenter d'afficher une boîte de dialogue si QApplication existe
        try:
            app_instance = QApplication.instance()
            if app_instance:
                QMessageBox.critical(
                    None, "Erreur fatale",
                    f"Accio Launcher n'a pas pu démarrer.\n\n{exc}",
                )
        except Exception:
            pass
        print(f"Erreur fatale : {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

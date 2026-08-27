import logging
import logging.handlers
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from src.core.config import DEFAULT_LANGUAGE, LOG_DIR, migrer_arborescence

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

    # httpcore déverse tous les en-têtes HTTP en DEBUG — il remplirait à lui
    # seul la rotation de 5 Mo ; httpx garde sa ligne INFO « HTTP Request: … ».
    logging.getLogger("httpcore").setLevel(logging.INFO)


def _create_splash():
    """Écran de démarrage de marque (cf. src/ui/splash.py).

    Les polices sont chargées ici parce que le splash est le tout premier
    élément peint : sans elles, son libellé d'état partirait en repli système.
    """
    from src.ui.fonts import load_fonts
    from src.ui.splash import AccioSplash

    load_fonts()
    return AccioSplash()


def main():
    # AVANT le logging : le journal s'ouvre dans `_Launcher/logs/`, et un
    # `RotatingFileHandler` qui tient l'ancien fichier ouvert empêcherait de le
    # déplacer. Avant `Config.exists()` aussi, sinon un `config.json` resté à
    # l'ancien emplacement passerait pour absent et l'assistant de premier
    # lancement rouvrirait chez quelqu'un qui a déjà huit jeux installés.
    try:
        _deplaces = migrer_arborescence()
    except OSError as exc:
        print(f"Migration de l'arborescence impossible : {exc}", file=sys.stderr)
        _deplaces = []

    try:
        _setup_logging()
    except OSError as exc:
        print(f"Impossible d'initialiser le logging : {exc}", file=sys.stderr)

    log = logging.getLogger(__name__)
    if _deplaces:
        log.info("Arborescence rangée dans %s : %s",
                 LOG_DIR.parent.name, ", ".join(_deplaces))

    # Identité applicative explicite : groupement taskbar, icône et
    # notifications corrects (sinon Windows regroupe sous "python.exe" en dev).
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ASTeam.AccioLauncher")
        except (AttributeError, OSError):
            pass

    try:
        app = QApplication(sys.argv)

        # La langue doit être active AVANT le premier texte affiché : le splash
        # apparaît bien avant MainWindow, qui appelait jusqu'ici set_language.
        from src.core.config import Config as _Config
        from src.core.i18n import set_language, tr
        set_language(_Config.load().langue if _Config.exists() else DEFAULT_LANGUAGE)

        # L'anneau de focus doré ne doit apparaître qu'au clavier. Posé ici,
        # le filtre couvre aussi l'assistant de premier lancement.
        from src.ui.focus_visible import install as install_focus_clavier
        install_focus_clavier(app)

        # Rapport de crash en un clic : les exceptions non gérées dans les slots
        # affichent un dialogue copiable au lieu de tuer le process en silence.
        from src.ui.crash_dialog import install_excepthook
        install_excepthook()

        # Instance unique : un second lancement active la fenêtre existante et quitte.
        from src.ui.single_instance import SingleInstance
        guard = SingleInstance()
        if not guard.try_acquire():
            sys.exit(0)

        splash = _create_splash()
        splash.show()
        # Les états annoncés correspondent à de VRAIES étapes : rien n'est
        # simulé, et la progression n'avance que quand quelque chose a
        # réellement été fait.
        splash.set_statut(tr("Initialisation"), 0.10)
        app.processEvents()

        from src.ui.main_window import MainWindow
        from src.core.config import Config

        splash.set_statut(tr("Chargement des ressources"), 0.45)
        app.processEvents()

        # Vérifier si c'est le premier lancement AVANT de créer MainWindow
        # pour cacher le splash qui bloquerait les dialogues de bienvenue.
        if not Config.exists():
            splash.close()

        splash.set_statut(tr("Préparation de la bibliothèque"), 0.75)
        window = MainWindow()
        guard.activate_requested.connect(window.bring_to_front)

        # `window.show()` déclenche la première mise en page ET le premier rendu
        # complet de l'interface : 304 ms mesurées, la deuxième étape la plus
        # coûteuse du démarrage. Elle se déroulait sous le libellé « Prêt », qui
        # promettait donc la fin alors qu'il restait un tiers de seconde. Elle a
        # maintenant son propre libellé, et « Prêt » ne s'affiche qu'une fois la
        # fenêtre réellement prête.
        splash.set_statut(tr("Ouverture de la fenêtre"), 0.92)
        window.show()
        # Un démarrage de plus. Compté ICI et non à la construction de
        # MainWindow : la suite de tests en construit des dizaines, et aucune
        # n'est un lancement du launcher.
        from src.core import stats as _stats
        _stats.enregistrer_demarrage()
        splash.set_statut(tr("Prêt"), 1.0)
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

# Accio Launcher — Copyright (c) 2026 ASTeam — https://acciolauncher.be/
# GNU GPL v3 uniquement, avec des termes additionnels (article 7) qui valent pour
# tous les fichiers du dépôt : voir LICENSE et ADDITIONAL-TERMS.md.
import logging
import logging.handlers
import os
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from src.core.config import DEFAULT_LANGUAGE, LOG_DIR, migrer_arborescence

LOG_FILE = LOG_DIR / "accio_launcher.log"
# Identifiant de l'application sous Linux : nom du `.desktop` de l'AppImage
# (sans l'extension), et `app_id` de la fenêtre sous Wayland.
DESKTOP_ID = "be.acciolauncher.AccioLauncher"
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
    # INFO dans l'exe, DEBUG depuis les sources. Le journal de l'exe est celui
    # qu'on demande sur le Discord : en DEBUG, il racontait surtout le décor
    # (une ligne par bouton reconstruit, une par perte de focus). Pour un cas
    # difficile, ACCIO_JOURNAL=debug rend le détail sans republier.
    detaille = (not getattr(sys, "frozen", False)
                or os.environ.get("ACCIO_JOURNAL", "").lower() == "debug")
    file_handler.setLevel(logging.DEBUG if detaille else logging.INFO)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # En-tête de session : la version et le système. Hors ligne, la version
    # n'apparaissait JAMAIS dans le journal (seule la vérification des mises à
    # jour l'écrivait) — c'est pourtant la première question qu'on pose.
    from src.core.diagnostic import identite
    # ASCII : la console Windows est en cp1252 et refusait les filets « ─ ».
    root.info("===== %s =====", identite())
    if sys.platform != "win32":
        # Sous Linux, la seconde question est « avec quoi le jeu tourne-t-il ? ».
        from src.core.diagnostic import ligne_compatibilite
        try:
            root.info("%s", ligne_compatibilite())
        except Exception as exc:  # une ligne de journal n'empêche jamais de démarrer
            root.warning("Préfixe Wine illisible : %s", exc)

    # httpcore déverse tous les en-têtes HTTP en DEBUG — il remplirait à lui
    # seul la rotation de 5 Mo ; httpx garde sa ligne INFO « HTTP Request: … ».
    logging.getLogger("httpcore").setLevel(logging.INFO)


def _create_splash(faits_du_jour: bool):
    """Écran de démarrage de marque (cf. src/ui/splash.py).

    Les polices sont chargées ici parce que le splash est le tout premier
    élément peint : sans elles, son libellé d'état partirait en repli système.
    Le fait du jour est celui de la barre du bas, et se coupe avec elle.
    """
    from src.core import almanach
    from src.core.i18n import tr
    from src.ui.fonts import load_fonts
    from src.ui.splash import AccioSplash

    load_fonts()
    fait = almanach.fait_du_jour() if faits_du_jour else ""
    return AccioSplash(fait=tr(fait) if fait else "")


# Variables par lesquelles l'utilisateur règle lui-même l'échelle de Qt : une
# seule posée, et le launcher n'y touche pas.
_ECHELLE_DE_L_UTILISATEUR = ("QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS",
                             "QT_ENABLE_HIGHDPI_SCALING")


def _plafonner_echelle(environ=None, mesurer=None) -> str | None:
    """Windows : pose `QT_SCALE_FACTOR` si la fenêtre minimale déborde de l'écran.

    À 175 % sur un 1920×1080, la zone de travail fait 1097×569 pixels
    logiques ; `setMinimumSize(980, 660)` passait outre le plafond de
    `geometrie_d_ouverture`, et la fenêtre s'ouvrait 91 px plus haute que
    l'écran (constat du 2026-11-12). Le facteur ramène l'échelle juste assez
    pour que 980×660 y tienne (`window_chrome.echelle_plafonnee`). À poser
    AVANT `QApplication`, qui ne relit plus la variable ensuite. Rend la
    valeur posée, ou None. Rien sous Linux : appelé derrière `sys.platform`.
    """
    environ = os.environ if environ is None else environ
    if any(environ.get(nom) for nom in _ECHELLE_DE_L_UTILISATEUR):
        return None
    if mesurer is None:
        from src.core.win_utils import zone_de_travail_principale as mesurer
    zone = mesurer()
    if zone is None:
        return None
    from src.ui.window_chrome import echelle_plafonnee
    facteur = echelle_plafonnee(*zone)
    if facteur is None:
        return None
    environ["QT_SCALE_FACTOR"] = valeur = f"{facteur:.3f}"
    return valeur


def _sortir(code: int):
    """Quitte SANS finalisation de l'interpréteur, dès que `QApplication` existe.

    Pendant celle-ci, sip détruit les objets C++ restants dans un ordre qu'il ne
    maîtrise pas : mesuré le 2026-09-18, violation d'accès dans
    `sip.cp314-win_amd64.pyd` (offset 0x10726, aucune frame Python) à 2
    fermetures sur 8 depuis les sources, et 5 fois dans le journal Windows
    depuis le 30 août, exe publié compris. Invisible, la fenêtre est déjà
    fermée, mais c'est un plantage à chaque fois. Le second lancement et
    l'erreur au démarrage passaient encore par `sys.exit` (audit du 2026-11-02).
    Rien n'est perdu à sauter cette étape : la config et les stats sont écrites
    dans `closeEvent`, les threads y sont arrêtés, le journal est vidé ici, et
    le dossier temporaire de l'exe est nettoyé par le processus parent de
    PyInstaller.
    """
    logging.shutdown()
    for flux in (sys.stdout, sys.stderr):
        if flux is not None:
            flux.flush()
    os._exit(code)


def main():
    # Tout premier : les modules du launcher importés ensuite se chargent à leur
    # premier usage (Python 3.15), et les modules d'extension Qt sont créés
    # maintenant, avant tout objet Qt (règle 5).
    from src.ui.imports_paresseux import activer as activer_imports_paresseux
    _paresseux = activer_imports_paresseux()

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
    log.info("Imports paresseux : %s", "actifs" if _paresseux else "absents de cet interpréteur")
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
        # Une échelle Windows élevée sur un petit écran : la fenêtre minimale
        # déborderait. La mesure n'empêche jamais de démarrer.
        try:
            _echelle = _plafonner_echelle()
        except Exception as exc:
            log.warning("Échelle de l'écran illisible : %s", exc)
            _echelle = None
        if _echelle:
            log.info("Échelle plafonnée à %s : 980×660 ne tenait pas dans l'écran principal",
                     _echelle)
    else:
        # Dans l'AppImage : ce que Qt lancera (xdg-open, le navigateur) ne doit
        # pas hériter des bibliothèques embarquées. Voir `compat`.
        from src.core.compat import assainir_environnement
        assainir_environnement()
        # Bandes-annonces : le son jouait, l'image restait celle du jeu (Ludo,
        # Bazzite, Intel UHD, 2026-09-30). Le FFmpeg de Qt décode en MATÉRIEL
        # (VAAPI) : l'image reste dans la carte graphique, et sans rendu GPU
        # pour la recevoir, `QVideoFrame.toImage()` la rend vide. Une valeur
        # VIDE coupe le décodage matériel ; une valeur de l'utilisateur reste la sienne.
        os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")

    try:
        app = QApplication(sys.argv)
        if sys.platform != "win32":
            # L'équivalent de l'AppUserModelID : sous Wayland, c'est CE nom qui
            # relie la fenêtre à son `.desktop`, donc à son icône et à son nom
            # dans le dock (`setWindowIcon` y est ignoré). Même identifiant
            # que le `.desktop` de l'AppImage.
            app.setDesktopFileName(DESKTOP_ID)
        # Icône de TOUTE l'application, pas seulement de MainWindow :
        # l'assistant de premier lancement s'ouvre avant elle et portait
        # l'icône générique de Windows — la toute première fenêtre qu'on voit.
        from src.ui.utils import icone_application
        app.setWindowIcon(icone_application())
        # Écrans et mise à l'échelle : trois défauts de ce projet n'existaient
        # qu'à 125 % (trait du carrousel, icônes rognées, fenêtre de HP7).
        from src.core.diagnostic import ecran
        log.info("Écrans : %s", " ; ".join(
            ecran(e.size().width(), e.size().height(), e.devicePixelRatio())
            for e in app.screens()))

        # La langue doit être active AVANT le premier texte affiché : le splash
        # apparaît bien avant MainWindow, qui appelait jusqu'ici set_language.
        from src.core.config import Config as _Config
        from src.core.i18n import set_language
        # Lue UNE fois pour tout le démarrage : config.json était lu cinq fois avant la
        # première fenêtre (banc de rapidité, 2026-11-13). Rien ne l'écrit d'ici là.
        _cfg = _Config.load() if _Config.exists() else None
        set_language(_cfg.langue if _cfg is not None else DEFAULT_LANGUAGE)

        # L'anneau de focus doré ne doit apparaître qu'au clavier. Posé ici,
        # le filtre couvre aussi l'assistant de premier lancement.
        from src.ui.focus_visible import install as install_focus_clavier
        install_focus_clavier(app)

        # La manette rejoue ses appuis comme des touches : posée ici, elle
        # pilote aussi l'assistant de premier lancement.
        from src.ui import manette_nav
        manette_nav.install(
            app, _cfg.navigation_manette if _cfg is not None else True)

        # Rapport de crash en un clic : les exceptions non gérées dans les slots
        # affichent un dialogue copiable au lieu de tuer le process en silence.
        from src.ui.crash_dialog import install_excepthook
        install_excepthook()

        # Instance unique : un second lancement active la fenêtre existante et quitte.
        from src.ui.single_instance import SingleInstance
        from src.core import liste_saut
        # « Jouer à … » de l'icône Windows : le jeu demandé, relayé s'il y a déjà une fenêtre.
        jouer = liste_saut.id_demande(sys.argv)
        guard = SingleInstance()
        if not guard.try_acquire(jouer=jouer):
            _sortir(0)

        splash = _create_splash(_cfg.faits_du_jour if _cfg is not None else True)
        splash.show()
        # Les étapes affichées sont annoncées par le code qui les fait
        # (`src/core/demarrage.py`) : rien n'est simulé, et la ligne n'avance
        # que quand quelque chose commence réellement.
        app.processEvents()

        from src.core import demarrage
        from src.ui.main_window import MainWindow
        from src.ui.onboarding import OnboardingAnnule

        # Vérifier si c'est le premier lancement AVANT de créer MainWindow
        # pour cacher le splash qui bloquerait les dialogues de bienvenue.
        # Même chose pour la version courte de l'assistant, montrée une fois à
        # ceux qui avaient le launcher avant le Choixpeau.
        from src.core.assistant import etapes_a_rattraper
        if _cfg is None:
            splash.close()
        else:
            if etapes_a_rattraper(_cfg.etapes_assistant, _cfg.theme, _cfg.trailers_optin):
                splash.close()

        try:
            window = MainWindow()
        except OnboardingAnnule:
            # L'assistant a été fermé sans aboutir. On n'écrit AUCUNE config et
            # on ne démarre pas : la croix doit reporter l'installation, pas la
            # sauter. Avant, des défauts étaient enregistrés, donc le launcher
            # s'ouvrait ET `Config.exists()` devenait vrai — l'assistant ne
            # revenait jamais (Ludo, 2026-09-23).
            log.info("Premier lancement abandonné — aucune configuration écrite")
            splash.close()
            # Le Choixpeau a pu colorer la manette : elle resterait allumée.
            from src.core import manette
            if manette.allumee_par_nous():
                manette.eteindre()
            _sortir(0)
        guard.activate_requested.connect(window.bring_to_front)
        from src.ui import question_reprise, raccourci_jouer
        raccourci_jouer.brancher(window, guard)
        question_reprise.brancher(window)

        # `window.show()` déclenche la première mise en page ET le premier rendu
        # complet de l'interface : 304 ms mesurées, la deuxième étape la plus
        # coûteuse du démarrage. Elle se déroulait sous le libellé « Prêt », qui
        # promettait donc la fin alors qu'il restait un tiers de seconde. Elle a
        # maintenant sa propre étape, et l'écran se ferme sans « Prêt » : la
        # fenêtre qui apparaît le dit mieux (règle 107).
        demarrage.annoncer(demarrage.FENETRE)
        window.show()
        # Un démarrage de plus. Compté ICI et non à la construction de
        # MainWindow : la suite de tests en construit des dizaines, et aucune
        # n'est un lancement du launcher.
        from src.core import stats as _stats
        _stats.enregistrer_demarrage()
        splash.finish(window)
        if jouer:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: raccourci_jouer.jouer_demande(window, jouer))
        _sortir(app.exec())

    except Exception as exc:
        log.critical("Erreur fatale au démarrage : %s", exc, exc_info=True)
        try:
            afficher_erreur_fatale(exc)
        except Exception:
            # Le démarrage a DÉJÀ échoué et c'est journalisé en critique :
            # l'échec de la boîte ne change pas l'issue, mais il dit que
            # l'utilisateur n'a rien vu à l'écran. Un `pass` le taisait.
            log.warning("Boîte d'erreur fatale impossible à afficher",
                        exc_info=True)
        print(f"Erreur fatale : {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        _sortir(1)


def afficher_erreur_fatale(exc: BaseException, fabrique=QMessageBox) -> bool:
    """La boîte d'un démarrage raté. Rend False quand rien ne peut s'afficher.

    Elle était en français en dur, par le raccourci `QMessageBox.critical`
    (règle 116), et ne disait pas où trouver le journal : la seule chose dont
    l'aide sur le Discord a besoin (audit du 2026-10-07, ACT-005). La langue
    est celle de la config si elle a eu le temps d'être posée, le français
    sinon — `tr` ne lève jamais.
    """
    if QApplication.instance() is None:
        return False
    from PyQt6.QtCore import Qt

    from src.core.i18n import tr
    boite = fabrique()
    boite.setWindowTitle("Accio Launcher")
    boite.setIcon(QMessageBox.Icon.Critical)
    boite.setTextFormat(Qt.TextFormat.PlainText)
    boite.setText(tr("Accio Launcher n'a pas pu démarrer."))
    boite.setInformativeText(tr(
        "Le détail est dans le journal :\n{}\n\nJoignez ce fichier à votre "
        "message sur le Discord.").format(LOG_FILE))
    boite.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    boite.setDetailedText(f"{type(exc).__name__}: {exc}")
    boite.addButton(tr("Fermer"), QMessageBox.ButtonRole.AcceptRole)
    boite.exec()
    return True


if __name__ == "__main__":
    main()

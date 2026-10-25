"""Rapport de crash en un clic — excepthook global + dialogue de signalement.

Une exception non gérée dans un slot Qt tuerait l'application sans un mot.
`install_excepthook()` (appelé par main.py après la création du QApplication)
loggue l'erreur puis affiche un dialogue : « Copier le rapport », « Ouvrir le
Discord » ou « Ouvrir une issue GitHub » pré-remplie. Aucun envoi automatique —
l'utilisateur voit exactement ce qui part.
"""

import logging
import sys
import traceback
import urllib.parse

from src.core.config import APP_VERSION
# `scrub_user_paths` vit désormais dans `diagnostic` (le bouton « Copier les
# informations de diagnostic » en a besoin aussi) ; réexporté ici pour les
# appelants existants.
from src.core.diagnostic import identite, scrub_user_paths

log = logging.getLogger(__name__)

_ISSUES_URL = "https://github.com/ludvdber/AccioLauncher/issues/new"
_LOG_TAIL_LINES = 40
# Les URLs ont une longueur max pratique (~2000) — le corps d'issue est tronqué,
# le rapport complet passe par « Copier le rapport ».
_MAX_ISSUE_BODY = 1500


def _read_log_tail() -> str:
    """Dernières lignes du log applicatif (vide si introuvable)."""
    from src.core.config import LOG_DIR

    log_file = LOG_DIR / "accio_launcher.log"
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-_LOG_TAIL_LINES:])
    except OSError:
        return ""


def build_crash_report(exc_text: str, log_tail: str = "") -> str:
    """Assemble le rapport (version, OS, traceback, queue de log), chemins anonymisés."""
    parts = [
        identite(),
        "",
        "── Erreur ──",
        exc_text.rstrip(),
    ]
    if log_tail:
        parts += ["", f"── Log (dernières {_LOG_TAIL_LINES} lignes) ──", log_tail.rstrip()]
    return scrub_user_paths("\n".join(parts))


def github_issue_url(report: str) -> str:
    """URL d'issue GitHub pré-remplie (corps tronqué pour rester une URL valide)."""
    body = report[:_MAX_ISSUE_BODY]
    if len(report) > _MAX_ISSUE_BODY:
        body += "\n\n[rapport tronqué — coller la version complète depuis le presse-papiers]"
    title = f"[Crash] Accio Launcher v{APP_VERSION}"
    return (f"{_ISSUES_URL}?title={urllib.parse.quote(title)}"
            f"&body={urllib.parse.quote(f'```\n{body}\n```')}")


def construire_dialogue(report: str):
    """Le dialogue de plantage, prêt à être `exec()`uté.

    Séparé de `_show_crash_dialog` pour être construit dans un test sans le
    modal bloquant.

    Deux rangées, parce que ce sont deux questions différentes. En haut :
    obtenir de l'aide. Le texte disait « à coller sur le Discord » sans donner
    le lien, et le seul bouton de sortie était une issue GitHub — que la
    plupart des joueurs ne savent pas ouvrir, faute de compte. En bas : que
    faire du launcher. Les cinq boutons sur une seule rangée élargissaient le
    dialogue bien au-delà de sa largeur minimale.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
    )

    from src.core.i18n import tr
    from src.core.liens import DISCORD_URL
    from src.ui.composants import feuille_de_style, police, texte
    from src.ui.icon_button import pixmap_icone
    from src.ui.theme import themed
    from src.ui.utils import open_url

    # Refait le 2026-10-09 sur les composants : le titre dit ce qui s'est passé,
    # puis le rapport et les boutons. L'encadré vert « Vos jeux et vos
    # sauvegardes ne sont pas touchés » a été retiré le 2026-10-24 (Ludo : « ça
    # n'a pas de sens ») : il disait un état normal, ce que le launcher s'interdit.
    dlg = QDialog()
    dlg.setWindowTitle(tr("Accio Launcher — Erreur inattendue"))
    dlg.setMinimumSize(560, 460)
    dlg.setStyleSheet(themed(
        "QDialog { background: #0d0d1a; }"
        "QPlainTextEdit { background: #060611; color: #b0b0c8; border: 1px solid #1a2744;"
        " border-radius: 8px; font-family: Consolas, monospace; font-size: 11px; padding: 6px; }"
        # Le bouton Discord garde son nom (les tests le cherchent) : style secondaire.
        "QPushButton#crashDiscord { min-height: 34px; max-height: 34px; padding: 0 16px;"
        " border-radius: 7px; color: #d9d6e8; background: rgba(255, 255, 255, 0.03);"
        " border: 1px solid rgba(255, 255, 255, 0.14); }"
        "QPushButton#crashDiscord:hover { border-color: #d6a72c; }"
        "QPushButton#crashDiscord[focusClavier=\"true\"]:focus { border: 2px solid #d6a72c; padding: 0 15px; }"
    ) + feuille_de_style())
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(28, 24, 28, 22)
    layout.setSpacing(0)

    tete = QHBoxLayout()
    tete.setSpacing(14)
    icone = QLabel()
    icone.setStyleSheet("background: transparent;")
    icone.setPixmap(pixmap_icone("attention", 26, QColor("#e0584f")))
    tete.addWidget(icone)
    titre = texte(tr("Le launcher a rencontré une erreur"), 17, "#f4f2f8", retour=True)
    titre.setFont(police(17, gras=True))
    tete.addWidget(titre, stretch=1)
    layout.addLayout(tete)
    layout.addSpacing(12)
    layout.addWidget(texte(tr(
        "Copiez le rapport et collez-le sur le Discord pour obtenir de l'aide, "
        "ou ouvrez une issue GitHub pré-remplie."), 14, "#d9d6e8", retour=True))
    layout.addSpacing(14)

    text = QPlainTextEdit(report)
    text.setReadOnly(True)
    layout.addWidget(text, stretch=1)
    layout.addSpacing(16)

    def _bouton(libelle: str, nom: str = "secondaire") -> QPushButton:
        btn = QPushButton(libelle)
        btn.setObjectName(nom)
        btn.setFont(police(13, gras=True))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        return btn

    # Rangée 1 : obtenir de l'aide.
    aide = QHBoxLayout()
    aide.setSpacing(10)
    btn_copy = _bouton(tr("Copier le rapport"), "principal")

    def _copy() -> None:
        QApplication.clipboard().setText(report)
        btn_copy.setText(tr("Rapport copié"))

    btn_copy.clicked.connect(_copy)
    aide.addWidget(btn_copy)

    btn_discord = _bouton(tr("Ouvrir le Discord"), "crashDiscord")
    btn_discord.clicked.connect(lambda: open_url(DISCORD_URL))
    aide.addWidget(btn_discord)

    btn_issue = _bouton(tr("Ouvrir une issue GitHub"))
    btn_issue.clicked.connect(lambda: open_url(github_issue_url(report)))
    aide.addWidget(btn_issue)
    aide.addStretch()
    layout.addLayout(aide)
    layout.addSpacing(10)

    # Rangée 2 : que faire du launcher.
    buttons = QHBoxLayout()
    buttons.setSpacing(10)
    buttons.addStretch()
    btn_close = _bouton(tr("Fermer"))
    btn_close.clicked.connect(dlg.accept)
    buttons.addWidget(btn_close)

    btn_restart = _bouton(tr("Redémarrer le launcher"))

    def _restart() -> None:
        from src.core.self_update import relaunch_after_exit

        if relaunch_after_exit():
            # Après un crash, l'état du process n'est plus fiable : sortie franche,
            # le .bat détaché relance une instance propre.
            import os
            os._exit(1)
        dlg.accept()

    btn_restart.clicked.connect(_restart)
    buttons.addWidget(btn_restart)
    layout.addLayout(buttons)
    return dlg


def _show_crash_dialog(report: str) -> None:
    construire_dialogue(report).exec()


# Un seul dialogue de crash dans la vie du process (voir _hook).
_dialog_shown = False
# Vrai pendant l'exec() du dialogue : une exception levée par le dialogue
# lui-même ne doit pas rouvrir un dialogue.
_in_hook = False


def reset_crash_state() -> None:
    """Réarme le dialogue (tests uniquement — jamais appelé en production)."""
    global _dialog_shown, _in_hook
    _dialog_shown = False
    _in_hook = False


def install_excepthook() -> None:
    """Route les exceptions non gérées vers le log + le dialogue de rapport.

    PyQt6 appelle sys.excepthook pour les exceptions levées dans les slots puis
    abandonne le process — ce hook donne à l'utilisateur le temps de copier le
    rapport avant. KeyboardInterrupt garde le comportement standard.

    Le dialogue n'est montré QU'UNE FOIS. Les exceptions les plus probables
    viennent de slots rappelés en boucle (paintEvent, tick du Ticker à ~30 FPS,
    progression de téléchargement) : sans ce garde, chaque répétition empilait
    une modale de plus, jusqu'à ce que l'utilisateur doive tuer le process —
    sans jamais pouvoir copier le rapport, ce qui est pourtant tout l'objet de
    la fonctionnalité. Les exceptions suivantes restent journalisées.
    """
    def _hook(exc_type, exc_value, exc_tb) -> None:
        global _dialog_shown, _in_hook

        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        exc_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.critical("Exception non gérée :\n%s", exc_text)

        if _in_hook:
            # Exception levée PENDANT l'affichage du dialogue : log seul.
            log.error("Exception pendant l'affichage du rapport de crash — dialogue non rouvert")
            return
        if _dialog_shown:
            log.warning("Dialogue de crash déjà affiché — exception journalisée seulement")
            return

        _in_hook = True
        try:
            report = build_crash_report(exc_text, _read_log_tail())
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is not None:
                _dialog_shown = True
                _show_crash_dialog(report)
        except Exception:  # le handler de crash ne doit jamais crasher
            log.exception("Échec de l'affichage du rapport de crash")
        finally:
            _in_hook = False

    sys.excepthook = _hook

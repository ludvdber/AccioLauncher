"""Rapport de crash en un clic — excepthook global + dialogue de signalement.

Une exception non gérée dans un slot Qt tuerait l'application sans un mot.
`install_excepthook()` (appelé par main.py après la création du QApplication)
loggue l'erreur puis affiche un dialogue : « Copier le rapport » (pour le
Discord) ou « Ouvrir une issue GitHub » pré-remplie. Aucun envoi automatique —
l'utilisateur voit exactement ce qui part.
"""

import logging
import sys
import traceback
import urllib.parse
from pathlib import Path

from src.core.config import APP_VERSION

log = logging.getLogger(__name__)

_ISSUES_URL = "https://github.com/ludvdber/AccioLauncher/issues/new"
_LOG_TAIL_LINES = 40
# Les URLs ont une longueur max pratique (~2000) — le corps d'issue est tronqué,
# le rapport complet passe par « Copier le rapport ».
_MAX_ISSUE_BODY = 1500


def scrub_user_paths(text: str) -> str:
    """Remplace le dossier personnel par ~ (ne pas exposer le nom d'utilisateur)."""
    home = str(Path.home())
    for variant in (home, home.replace("\\", "/"), home.replace("\\", "\\\\")):
        text = text.replace(variant, "~")
    return text


def _read_log_tail() -> str:
    """Dernières lignes du log applicatif (vide si introuvable)."""
    from src.core.config import DEFAULT_INSTALL_PATH

    log_file = DEFAULT_INSTALL_PATH / "accio_launcher.log"
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-_LOG_TAIL_LINES:])
    except OSError:
        return ""


def build_crash_report(exc_text: str, log_tail: str = "") -> str:
    """Assemble le rapport (version, OS, traceback, queue de log), chemins anonymisés."""
    parts = [
        f"Accio Launcher v{APP_VERSION}",
        f"Python {sys.version.split()[0]} — {sys.platform}",
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
    # Pas de backslash dans une f-string : SyntaxError en Python 3.10/3.11
    # (le projet garde la compat 3.10+ dans ses conventions).
    fenced = "```\n" + body + "\n```"
    return (f"{_ISSUES_URL}?title={urllib.parse.quote(title)}"
            f"&body={urllib.parse.quote(fenced)}")


def _show_crash_dialog(report: str) -> None:
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
        QPushButton, QVBoxLayout,
    )

    from src.core.i18n import tr
    from src.ui.theme import themed
    from src.ui.utils import open_url

    dlg = QDialog()
    dlg.setWindowTitle(tr("Accio Launcher — Erreur inattendue"))
    dlg.setMinimumSize(560, 420)
    dlg.setStyleSheet(themed(
        "QDialog { background: #0d0d1a; }"
        "QLabel { color: #eaeaea; font-size: 13px; }"
        "QPlainTextEdit { background: #060611; color: #b0b0c8; border: 1px solid #1a2744;"
        " border-radius: 6px; font-family: Consolas, monospace; font-size: 11px; }"
        "QPushButton { background: #16213e; color: #eaeaea; border: 1px solid #2c3e6b;"
        " border-radius: 6px; padding: 8px 16px; font-size: 13px; }"
        "QPushButton:hover { border-color: #d4a017; color: #e8c547; }"
    ))
    layout = QVBoxLayout(dlg)

    intro = QLabel(tr("Une erreur inattendue s'est produite. Tu peux copier le rapport "
                      "(à coller sur le Discord) ou ouvrir une issue GitHub pré-remplie."))
    intro.setWordWrap(True)
    layout.addWidget(intro)

    text = QPlainTextEdit(report)
    text.setReadOnly(True)
    layout.addWidget(text, stretch=1)

    buttons = QHBoxLayout()
    btn_copy = QPushButton(tr("Copier le rapport"))

    def _copy() -> None:
        QApplication.clipboard().setText(report)
        btn_copy.setText(tr("Copié ✓"))

    btn_copy.clicked.connect(_copy)
    buttons.addWidget(btn_copy)

    btn_issue = QPushButton(tr("Ouvrir une issue GitHub"))
    btn_issue.clicked.connect(lambda: open_url(github_issue_url(report)))
    buttons.addWidget(btn_issue)

    buttons.addStretch()

    btn_restart = QPushButton(tr("Redémarrer le launcher"))

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

    btn_close = QPushButton(tr("Fermer"))
    btn_close.clicked.connect(dlg.accept)
    buttons.addWidget(btn_close)
    layout.addLayout(buttons)

    dlg.exec()


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

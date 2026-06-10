"""Handlers utilisateur de GameDetailView (download / play / uninstall / update / etc.)

Extraits dans un module séparé pour garder la vue sous 300 lignes. Chaque fonction
prend la vue en premier argument et utilise ses signaux + sous-systèmes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFileDialog, QMenu, QMessageBox

from src.core.formatting import format_size
from src.core.game_data import GameVersion
from src.core.game_manager import GameState
from src.ui.utils import open_url
from src.ui.versions_dialog import VersionsDialog

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView

log = logging.getLogger(__name__)

_VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x86.exe"


def on_download(view: "GameDetailView", version: GameVersion | None = None) -> None:
    if view.game is None:
        return
    if view._ops.is_busy:
        active = view._ops.active_game
        if active and active.id != view.game.id:
            QMessageBox.information(
                view, "Téléchargement déjà en cours",
                f"Un téléchargement est déjà en cours pour {active.name}.\n\n"
                "Veuillez attendre la fin avant d'en lancer un autre.",
            )
        else:
            view.status_message.emit("Téléchargement déjà en cours pour ce jeu.")
        return
    ver = version or view.game.current_download
    if ver is None:
        view.status_message.emit("Aucune version disponible.")
        return
    free_mb = view._ops.check_disk_space(ver)
    if free_mb is not None:
        QMessageBox.warning(
            view, "Espace disque insuffisant",
            f"Il faut environ {format_size(ver.size_mb * 2)} d'espace libre.\n"
            f"Actuellement {format_size(free_mb)} disponibles.",
        )
        return
    view._ops.download(view.game, ver)
    view._refresh()


def on_cancel_download(view: "GameDetailView") -> None:
    view._ops.cancel_download()
    view._refresh()


def on_play(view: "GameDetailView") -> None:
    if view.game is None:
        return
    view._stop_video()
    try:
        proc = view.manager.launch_game(view.game.id)
    except RuntimeError as exc:
        if "vcredist_x86_missing" in str(exc):
            reply = QMessageBox.warning(
                view, "Visual C++ manquant",
                "Le Visual C++ Redistributable x86 (2015-2022) n'est pas installé.\n"
                "Il est nécessaire pour lancer les jeux.\n\n"
                "Voulez-vous ouvrir la page de téléchargement ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                open_url(_VC_REDIST_URL)
        else:
            log.error("Erreur au lancement : %s", exc)
            view.status_message.emit("Impossible de lancer le jeu.")
        return
    except OSError as exc:
        log.error("Impossible de lancer %s : %s", view.game.name, exc)
        view.status_message.emit("Impossible de lancer le jeu.")
        return
    if proc is not None:
        view.status_message.emit(f"Lancement de {view.game.name}…")
        view.game_launched.emit(proc, view.game.name)
    else:
        view.status_message.emit("Impossible de lancer le jeu.")


def on_uninstall(view: "GameDetailView") -> None:
    if view.game is None:
        return
    reply = QMessageBox.question(
        view, "Confirmer la désinstallation",
        f"Voulez-vous vraiment désinstaller {view.game.name} ?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return
    has_config = bool(view.game.post_install.config_files)
    view.manager.uninstall_game(view.game.id)
    view._refresh()
    view.state_changed.emit()
    if has_config:
        QMessageBox.information(
            view, "Sauvegardes conservées",
            "Les sauvegardes et la configuration dans Mes Documents ont été conservées.",
        )
    view.status_message.emit(f"{view.game.name} désinstallé.")


def on_update_clicked(view: "GameDetailView") -> None:
    if view.game is None:
        return
    ver = view.game.get_version(view.game.recommended_version)
    if ver is None:
        return
    installed = view.manager.installed_version(view.game.id) or "?"
    changes = "\n".join(f"• {c}" for c in ver.changes)
    reply = QMessageBox.question(
        view, "Mise à jour disponible",
        f"Mettre à jour de v{installed} vers v{ver.version} ?\n\n"
        f"Changements :\n{changes}\n\n"
        f"La version actuelle sera supprimée avant l'installation.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        view._ops.switch_version(view.game, ver)


def on_switch_version(view: "GameDetailView", game_id: str, version: str) -> None:
    if view.game is None or view.game.id != game_id:
        return
    ver = view.game.get_version(version)
    if ver is not None:
        view._ops.switch_version(view.game, ver)


def on_versions_clicked(view: "GameDetailView") -> None:
    if view.game is None:
        return
    dlg = VersionsDialog(view.game, view.manager, view)
    dlg.switch_to_version.connect(lambda gid, ver: on_switch_version(view, gid, ver))
    dlg.exec()


def on_install_local(view: "GameDetailView") -> None:
    if view.game is None or view._ops.is_busy:
        return
    path, _ = QFileDialog.getOpenFileName(
        view, "Sélectionner une archive de jeu", "", "Archives (*.7z *.zip)",
    )
    if not path:
        return
    view.status_message.emit(f"Installation de {view.game.name} depuis un fichier local…")
    view._ops.install(view.game, Path(path), delete_archive=False)
    view._refresh()


def show_context_menu(view: "GameDetailView", pos) -> None:
    if view.game is None:
        return
    menu = QMenu(view)
    act_versions = QAction("Gérer les versions", view)
    act_versions.triggered.connect(lambda: on_versions_clicked(view))
    menu.addAction(act_versions)
    if view.manager.get_state(view.game.id) == GameState.NOT_INSTALLED:
        act_local = QAction("Installer depuis un fichier local…", view)
        act_local.triggered.connect(lambda: on_install_local(view))
        menu.addAction(act_local)
    menu.exec(view.mapToGlobal(pos))


def trigger_primary_action(view: "GameDetailView") -> None:
    if view.game is None:
        return
    match view.manager.get_state(view.game.id):
        case GameState.NOT_INSTALLED:
            on_download(view)
        case GameState.INSTALLED:
            on_play(view)

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
from src.core.game_data import GameData, GameVersion
from src.core.i18n import tr
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
                view, tr("Téléchargement déjà en cours"),
                tr("Un téléchargement est déjà en cours pour {}.\n\nVeuillez attendre la fin avant d'en lancer un autre.").format(active.name),
            )
        else:
            view.status_message.emit(tr("Téléchargement déjà en cours pour ce jeu."))
        return
    ver = version or view.game.current_download
    if ver is None:
        view.status_message.emit(tr("Aucune version disponible."))
        return
    free_mb = view._ops.check_disk_space(ver)
    if free_mb is not None:
        QMessageBox.warning(
            view, tr("Espace disque insuffisant"),
            tr("Il faut environ {} d'espace libre.\nActuellement {} disponibles.").format(
                format_size(ver.size_mb * 2), format_size(free_mb)),
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
                view, tr("Visual C++ manquant"),
                tr("Le Visual C++ Redistributable x86 (2015-2022) n'est pas installé.\nIl est nécessaire pour lancer les jeux.\n\nVoulez-vous ouvrir la page de téléchargement ?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                open_url(_VC_REDIST_URL)
        else:
            log.error("Erreur au lancement : %s", exc)
            view.status_message.emit(tr("Impossible de lancer le jeu."))
        return
    except OSError as exc:
        log.error("Impossible de lancer %s : %s", view.game.name, exc)
        view.status_message.emit(tr("Impossible de lancer le jeu."))
        return
    if proc is not None:
        view.status_message.emit(tr("Lancement de {}…").format(view.game.name))
        view.game_launched.emit(proc, view.game.name, view.game.id)
    else:
        view.status_message.emit(tr("Impossible de lancer le jeu."))


def on_uninstall(view: "GameDetailView") -> None:
    if view.game is None:
        return
    reply = QMessageBox.question(
        view, tr("Confirmer la désinstallation"),
        tr("Voulez-vous vraiment désinstaller {} ?").format(view.game.name),
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
            view, tr("Sauvegardes conservées"),
            tr("Les sauvegardes et la configuration dans Mes Documents ont été conservées."),
        )
    view.status_message.emit(tr("{} désinstallé.").format(view.game.name))


def on_update_clicked(view: "GameDetailView") -> None:
    if view.game is None:
        return
    ver = view.game.get_version(view.game.recommended_version)
    if ver is None:
        return
    installed = view.manager.installed_version(view.game.id) or "?"
    changes = "\n".join(f"• {c}" for c in ver.changes)
    reply = QMessageBox.question(
        view, tr("Mise à jour disponible"),
        tr("Mettre à jour de v{} vers v{} ?\n\nChangements :\n{}\n\nLa version actuelle sera remplacée une fois le téléchargement terminé.").format(
            installed, ver.version, changes),
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


def on_repair(view: "GameDetailView") -> None:
    """Vérifie / répare un jeu installé : re-téléchargement (SHA-256 si dispo) + réinstallation."""
    if view.game is None or view._ops.is_busy:
        return
    reply = QMessageBox.question(
        view, tr("Vérifier / réparer les fichiers"),
        tr("L'archive de {} va être re-téléchargée (avec vérification d'intégrité quand elle est disponible) puis réinstallée par-dessus les fichiers existants.\n\nLes sauvegardes et la configuration ne sont pas touchées.\n\nContinuer ?").format(view.game.name),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        view._ops.repair(view.game)
        view._refresh()


def find_import_error(game: GameData, source: Path, install_path: Path) -> str | None:
    """Valide un dossier d'installation existant à importer.

    Retourne un message d'erreur utilisateur, ou None si l'import est possible.
    Fonction pure (testable sans Qt).
    """
    parts = Path(game.executable).parts
    if len(parts) < 2:
        return tr("Ce jeu ne supporte pas l'import d'une installation existante.")
    rel_exe = Path(*parts[1:])  # ex: System/HP.exe (sans le dossier racine du jeu)
    if not (source / rel_exe).exists():
        return tr("L'exécutable attendu est introuvable :\n{}\n\nChoisissez le dossier du jeu qui contient « {} ».").format(source / rel_exe, rel_exe)
    dest = install_path / parts[0]
    if dest.exists():
        return tr("Un dossier existe déjà à l'emplacement cible :\n{}\n\nDésinstallez d'abord la copie existante.").format(dest)
    if source.resolve().drive.lower() != install_path.resolve().drive.lower():
        return tr("Le dossier est sur un autre disque que le dossier d'installation.\nDéplacez-le manuellement, ou changez le dossier d'installation dans les Paramètres.")
    return None


def on_import_existing(view: "GameDetailView") -> None:
    """« J'ai déjà ce jeu » — déplace une installation existante dans le launcher."""
    if view.game is None or view._ops.is_busy:
        return
    game = view.game
    chosen = QFileDialog.getExistingDirectory(
        view, tr("Localiser l'installation de {}").format(game.name), str(Path.home()),
    )
    if not chosen:
        return
    source = Path(chosen)
    error = find_import_error(game, source, view.manager.config.install_path)
    if error is not None:
        QMessageBox.warning(view, tr("Import impossible"), error)
        return
    dest = view.manager.config.install_path / Path(game.executable).parts[0]
    reply = QMessageBox.question(
        view, tr("Importer ce jeu"),
        tr("Le dossier va être déplacé :\n\n{}\n→ {}\n\nLe jeu sera marqué en version {} (version réelle inconnue — utilisez « Vérifier / réparer » en cas de doute).\n\nContinuer ?").format(
            source, dest, game.recommended_version),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)  # même disque (validé) → rename instantané
    except OSError as exc:
        log.error("Import de %s impossible : %s", source, exc)
        QMessageBox.warning(view, tr("Import impossible"), tr("Déplacement impossible :\n{}").format(exc))
        return
    view.manager.redetect_state(game.id)
    view.manager.save_installed_version(game.id)
    view._refresh()
    view.state_changed.emit()
    view.status_message.emit(tr("{} importé avec succès !").format(game.name))
    log.info("Installation importée : %s → %s", source, dest)


def on_install_local(view: "GameDetailView") -> None:
    if view.game is None or view._ops.is_busy:
        return
    path, _ = QFileDialog.getOpenFileName(
        view, tr("Sélectionner une archive de jeu"), "", "Archives (*.7z *.zip)",
    )
    if not path:
        return
    view.status_message.emit(tr("Installation de {} depuis un fichier local…").format(view.game.name))
    view._ops.install(view.game, Path(path), delete_archive=False)
    view._refresh()


def show_context_menu(view: "GameDetailView", pos) -> None:
    if view.game is None:
        return
    menu = QMenu(view)
    act_versions = QAction(tr("Gérer les versions"), view)
    act_versions.triggered.connect(lambda: on_versions_clicked(view))
    menu.addAction(act_versions)
    state = view.manager.get_state(view.game.id)
    if state == GameState.NOT_INSTALLED:
        act_local = QAction(tr("Installer depuis un fichier local…"), view)
        act_local.triggered.connect(lambda: on_install_local(view))
        menu.addAction(act_local)
        act_import = QAction(tr("J'ai déjà ce jeu — localiser l'installation…"), view)
        act_import.triggered.connect(lambda: on_import_existing(view))
        menu.addAction(act_import)
    elif state == GameState.INSTALLED:
        act_repair = QAction(tr("Vérifier / réparer les fichiers"), view)
        act_repair.triggered.connect(lambda: on_repair(view))
        menu.addAction(act_repair)
    menu.exec(view.mapToGlobal(pos))


def trigger_primary_action(view: "GameDetailView") -> None:
    if view.game is None:
        return
    match view.manager.get_state(view.game.id):
        case GameState.NOT_INSTALLED:
            on_download(view)
        case GameState.INSTALLED:
            on_play(view)

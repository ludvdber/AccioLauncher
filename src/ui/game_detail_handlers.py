"""Handlers utilisateur de GameDetailView (download / play / uninstall / update / etc.)

Extraits dans un module séparé pour garder la vue sous 300 lignes. Chaque fonction
prend la vue en premier argument et utilise ses signaux + sous-systèmes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox

from src.core.formatting import format_size
from src.core.game_data import GameData, GameVersion
from src.core.i18n import tr
from src.core.game_manager import GameState
from src.core.system_checks import PREREQUIS, VCREDIST_URL, needed_space_mb
from src.ui.utils import open_url
from src.ui.versions_dialog import VersionsDialog

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView

log = logging.getLogger(__name__)


def _boite(icone, view, titre: str, texte: str, boutons=None, defaut=None):
    """QMessageBox en texte BRUT, pour tout message portant un nom de jeu.

    Les messages de ce module interpolent `game.name`, qui vient du CATALOGUE —
    donc de l'extérieur, et modifiable à distance sans republier l'exécutable.
    Or `QMessageBox` est en `AutoText` : Qt renifle le contenu et bascule en
    rich text dès qu'il ressemble à du HTML, si bien qu'un nom de jeu contenant
    `<img src="http://…">` déclencherait une requête réseau à l'ouverture du
    dialogue. Un point de passage unique vaut mieux que huit rappels à ne pas
    oublier au prochain dialogue ajouté.
    """
    boite = QMessageBox(view)
    boite.setIcon(icone)
    boite.setWindowTitle(titre)
    boite.setTextFormat(Qt.TextFormat.PlainText)
    boite.setText(texte)
    if boutons is not None:
        boite.setStandardButtons(boutons)
    if defaut is not None:
        boite.setDefaultButton(defaut)
    return boite.exec()


def confirmer_registre(view: "GameDetailView", nom_jeu: str):
    """Fabrique le rappel de prévenance affiché avant une écriture registre.

    On ne touche pas au registre de quelqu'un sans le lui dire, et on lui dit
    QUOI : le nom des valeurs, leur contenu et la clé visée. Sous HKLM, Windows
    enchaîne sur une invite UAC — l'annoncer est la moitié utile du message,
    car une autorisation qui surgit sans raison connue se refuse, et le jeu ne
    démarre pas.

    Le rappel n'est appelé que lorsqu'il y a réellement quelque chose à écrire
    (`game_registry.ecrire_valeurs` compare d'abord) : au deuxième lancement,
    personne n'est dérangé. C'est ce qui permet de prévenir TOUJOURS sans que
    ça devienne un nag.
    """
    def demander(ruche: str, cle: str, valeurs: dict) -> bool:
        detail = "\n".join(f"    {nom} = {valeur}" for nom, valeur in valeurs.items())
        morceaux = [
            tr("{jeu} enregistre ses réglages dans le registre de Windows.\n\n"
               "Le launcher va écrire ceci dans {cle} :\n\n{valeurs}").format(
                   jeu=nom_jeu, cle=f"{ruche}\\{cle}", valeurs=detail),
            tr("Sans cette écriture, le jeu risque de ne pas démarrer."),
        ]
        if ruche == "HKLM":
            morceaux.append(tr("Windows va ensuite demander une autorisation "
                               "administrateur."))
        morceaux.append(tr("Continuer ?"))
        return _boite(
            QMessageBox.Icon.Question, view, tr("Réglage du jeu"),
            "\n\n".join(morceaux),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) == QMessageBox.StandardButton.Yes
    return demander


def nom_prerequis(identifiant: str) -> str:
    """Nom lisible d'un prérequis, pour un message adressé à l'utilisateur.

    Le catalogue manipule des identifiants (`vcredist2005_x86`) ; personne ne
    doit lire ça dans une boîte de dialogue.
    """
    noms = {
        "vcredist_x86": tr("Le composant Visual C++ Redistributable x86 (2015-2022)"),
        "vcredist2005_x86": tr("Le composant Visual C++ 2005 Redistributable x86"),
        "vcredist2008_x86": tr("Le composant Visual C++ 2008 Redistributable x86"),
    }
    return noms.get(identifiant, tr("Un composant Windows requis"))


def on_download(view: "GameDetailView", version: GameVersion | None = None) -> None:
    if view.game is None:
        return
    if view._ops.is_busy:
        active = view._ops.active_game
        if active and active.id != view.game.id:
            # Toast et non dialogue : il n'y a aucune décision à prendre, et la
            # barre de téléchargement en bas montre déjà ce qui occupe le poste.
            view.notify.emit(
                tr("Téléchargement déjà en cours pour {} — un seul à la fois.")
                .format(active.name))
        else:
            view.status_message.emit(tr("Téléchargement déjà en cours pour ce jeu."))
        return
    ver = version or view.game.current_download
    if ver is None:
        view.status_message.emit(tr("Aucune version disponible."))
        return
    if not ver.is_available:
        # Garde de dernier recours : le bouton est déjà remplacé par « Bientôt
        # disponible », mais la touche Entrée et le menu contextuel passent ici
        # aussi. Sans ça, l'utilisateur recevait « Vérifiez votre connexion ».
        view.status_message.emit(
            tr("{} n'est pas encore téléchargeable — les fichiers arrivent bientôt.")
            .format(view.game.name)
        )
        return
    # Re-vérification au clic : le bandeau d'avertissement du panneau d'actions
    # a pu être calculé il y a plusieurs minutes, et de la place a pu être
    # libérée entre-temps. C'est ce test-ci qui fait foi.
    free_mb = view._ops.check_disk_space(ver)
    if free_mb is not None:
        view.notify.emit(
            tr("Espace insuffisant : {} libres, il en faut environ {}.").format(
                format_size(free_mb),
                format_size(needed_space_mb(
                    ver.size_mb, view.manager.archive_size_mb(ver)))))
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
        proc = view.manager.launch_game(
            view.game.id, confirmer=confirmer_registre(view, view.game.name))
    except RuntimeError as exc:
        if str(exc).startswith("prerequis_manquant:"):
            manquant = str(exc).split(":", 1)[1]
            reply = _boite(QMessageBox.Icon.Warning,
                view, tr("Composant Windows manquant"),
                tr("{} n'est pas installé sur ce PC.\nCe jeu ne peut pas démarrer sans lui.\n\n"
                   "Voulez-vous ouvrir la page de téléchargement ?").format(
                       nom_prerequis(manquant)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                open_url(PREREQUIS.get(manquant, (None, VCREDIST_URL))[1])
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
    reply = _boite(QMessageBox.Icon.Question,
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
        view.notify.emit(
            tr("Les sauvegardes et la configuration dans Mes Documents ont été conservées."))
    view.status_message.emit(tr("{} désinstallé.").format(view.game.name))


def on_update_clicked(view: "GameDetailView") -> None:
    if view.game is None:
        return
    ver = view.game.get_version(view.game.recommended_version)
    if ver is None:
        return
    installed = view.manager.installed_version(view.game.id) or "?"
    changes = "\n".join(f"• {c}" for c in ver.changes)
    reply = _boite(QMessageBox.Icon.Question,
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
    reply = _boite(QMessageBox.Icon.Question,
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
        _boite(QMessageBox.Icon.Warning, view, tr("Import impossible"), error)
        return
    dest = view.manager.config.install_path / Path(game.executable).parts[0]
    reply = _boite(QMessageBox.Icon.Question,
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
        _boite(QMessageBox.Icon.Warning, view, tr("Import impossible"), tr("Déplacement impossible :\n{}").format(exc))
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


def on_language_clicked(view: "GameDetailView") -> None:
    """Menu de choix de la langue du jeu, posé sous le segment de la ligne méta.

    Le choix est écrit dans le registre TOUT DE SUITE, pas au prochain
    lancement : l'écriture peut demander une élévation (HP7 lit sa langue sous
    HKLM), et une invite UAC est compréhensible juste après un clic délibéré,
    beaucoup moins trois écrans plus tard au moment de jouer. Le lancement
    revérifie de toute façon, et n'élève que si ça a réellement bougé.
    """
    game = view.game
    if game is None or game.language_registry is None:
        return
    courant = view.manager.game_language(game)
    # Seules les langues que l'installation sait RÉELLEMENT faire. Une langue
    # dont les fichiers ne sont pas là donnerait un jeu cassé, pas un jeu
    # traduit. Si le catalogue ne déclare aucun contrôle, tout est proposé.
    proposables = view.manager.langues_disponibles(game)
    if len(proposables) < 2 and courant is not None:
        # Rien à choisir : ne pas ouvrir un menu à une seule entrée grisée.
        view.notify.emit(tr("Ce jeu n'est installé que dans une seule langue."))
        return
    menu = QMenu(view)
    for langue in proposables:
        action = QAction(langue.label, view)
        action.setCheckable(True)
        action.setChecked(langue.code == courant)
        action.triggered.connect(
            lambda _checked=False, code=langue.code: _appliquer_langue(view, code))
        menu.addAction(action)
    menu.exec(view.ancre_langue() or QCursor.pos())


def _appliquer_langue(view: "GameDetailView", code: str) -> None:
    """Enregistre le choix, l'écrit dans le registre, rafraîchit la fiche."""
    game = view.game
    if game is None or code == view.manager.game_language(game):
        return
    if game.language_registry is None:
        return
    # Appliquer D'ABORD, persister ENSUITE. Enregistrer un choix que le registre
    # n'a pas pris ferait annoncer à la fiche une langue que le jeu n'a pas, et
    # surtout : chaque lancement redemanderait l'élévation pour « corriger » un
    # écart que l'utilisateur a déjà refusé de corriger une fois.
    #
    # L'écriture peut demander une élévation, puis attendre que regedit ait
    # réellement pris : quelques secondes pendant lesquelles la fenêtre ne
    # répond pas. Sans curseur d'attente, ça ressemble à un plantage.
    # Le rappel de prévenance est un DIALOGUE, pas une opération longue : on
    # rend le curseur normal le temps de la question, sinon on lit un message
    # et on clique un bouton avec un sablier sous la souris — la fenêtre a
    # l'air figée au moment précis où elle attend une réponse.
    demander = confirmer_registre(view, game.name)
    accepte = True

    def confirmer(ruche, cle, valeurs):
        nonlocal accepte
        QApplication.restoreOverrideCursor()
        try:
            accepte = demander(ruche, cle, valeurs)
        finally:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        return accepte

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        pose = view.manager.apply_game_language(game, code, confirmer=confirmer)
    finally:
        QApplication.restoreOverrideCursor()
    if not accepte:
        # Refus délibéré : rien à signaler, l'utilisateur sait ce qu'il a fait.
        # Un modal d'erreur ici reprocherait à quelqu'un d'avoir répondu non.
        return
    if pose:
        view.manager.set_game_language(game.id, code)
        langue = game.language_registry.get(code)
        etiquette = langue.label if langue is not None else code
        view.notify.emit(tr("Langue du jeu : {}").format(etiquette))
    else:
        # Échec = UAC refusé, ou le registre n'a pas pris. Une vraie erreur,
        # donc un modal : le choix est enregistré mais SANS effet, et un toast
        # qui s'efface laisserait l'utilisateur croire que c'est fait.
        _boite(QMessageBox.Icon.Warning,
            view, tr("Langue du jeu"),
            tr("La langue n'a pas pu être écrite dans le registre.\n\n"
               "Ce réglage demande une autorisation administrateur. Le jeu "
               "démarrera dans la langue actuellement en place."))
    view.set_game(game)


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

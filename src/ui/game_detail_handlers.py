"""Handlers utilisateur de GameDetailView (download / play / uninstall / update / etc.)

Extraits dans un module séparé pour garder la vue sous 300 lignes. Chaque fonction
prend la vue en premier argument et utilise ses signaux + sous-systèmes.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox

from src.core.formatting import format_size
from src.core.game_data import GameData, GameVersion
from src.core.i18n import tr
from src.core import compat
from src.core import preparation_wine as preparation
from src.core.game_manager import GameState
from src.core.liens import GUIDE_LINUX_URL
from src.core.system_checks import (
    PREREQUIS, VCREDIST_URL, VERBES_WINETRICKS, needed_space_mb, prerequis_manquants,
)
from src.ui.preparateur_wine import noms_des_verbes
from src.ui.utils import open_local_path, open_url
from src.ui.game_settings_dialog import GameSettingsDialog
from src.ui.versions_dialog import VersionsDialog

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView

log = logging.getLogger(__name__)


def _boite(icone, view, titre: str, texte: str, choix=(), defaut: int = 0) -> int:
    """QMessageBox en texte BRUT et aux boutons NOMMÉS.

    Deux règles tenues au même endroit, parce qu'elles se sont toutes les deux
    payées ici.

    ① **Texte brut.** Les messages de ce module interpolent `game.name`, qui
    vient du CATALOGUE — donc de l'extérieur, et modifiable à distance sans
    republier l'exécutable. Or `QMessageBox` est en `AutoText` : Qt renifle le
    contenu et bascule en rich text dès qu'il ressemble à du HTML, si bien
    qu'un nom de jeu contenant du balisage serait INTERPRÉTÉ.

    ② **Jamais de boutons standard.** `StandardButton.Yes` / `.No` ne sont pas
    traduits par `tr()` mais par les fichiers `qtbase_<langue>.qm` de Qt —
    que le build ÉCARTE volontairement (`_keep()` dans `accio_launcher.spec`).
    Résultat mesuré : un launcher réglé en français affichait « Yes » et
    « No ». Deux systèmes de traduction pour une même fenêtre, dont un que
    `tests/test_i18n.py` ne voit pas et qu'un traducteur bénévole ne peut pas
    corriger. Les libellés passent donc par `choix`, déjà traduits.

    Et un bouton se lit mieux quand il DIT ce qu'il fait : « Désinstaller »
    répond à la question tout seul, là où « Oui » oblige à relire l'intitulé —
    même raison qui fait nommer la perte dans la confirmation de fermeture.

    `choix` va du plus engageant au plus neutre ; le dernier est le retrait,
    donc celui qu'Échap déclenche. Retourne l'INDEX du bouton cliqué, ou -1 si
    la boîte a été fermée autrement (croix, Alt+F4) — jamais 0 par défaut, ce
    qui reviendrait à consentir à la place de quelqu'un qui n'a rien répondu.
    Sans `choix`, la boîte est un simple constat et ne porte qu'un congé.
    """
    boite = QMessageBox(view)
    boite.setIcon(icone)
    boite.setWindowTitle(titre)
    boite.setTextFormat(Qt.TextFormat.PlainText)
    boite.setText(texte)
    if not choix:
        boite.addButton(tr("Fermer"), QMessageBox.ButtonRole.AcceptRole)
        boite.exec()
        return -1
    boutons = [
        boite.addButton(libelle, QMessageBox.ButtonRole.AcceptRole if i == 0
                        else QMessageBox.ButtonRole.RejectRole)
        for i, libelle in enumerate(choix)
    ]
    boite.setDefaultButton(boutons[defaut])
    boite.exec()
    clique = boite.clickedButton()
    return next((i for i, b in enumerate(boutons) if b is clique), -1)


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

    `ecarts` porte la valeur qui est DÉJÀ en place pour chaque entrée qu'on
    s'apprête à écraser. On l'affiche : « le launcher va écrire ceci » ne dit
    pas qu'on remplace un réglage existant, et c'est pourtant le cas normal —
    l'installeur EA laisse un `Install Dir` et un `Locale` à lui. Quelqu'un qui
    voit ce qu'il perd peut refuser en connaissance de cause ; sans ça,
    autoriser revient à signer sans lire.
    """
    def demander(ruche: str, cle: str, valeurs: dict, ecarts: dict | None = None) -> bool:
        ecarts = ecarts or {}
        lignes = []
        for nom, valeur in valeurs.items():
            lignes.append(f"    {nom} = {valeur}")
            actuel = ecarts.get(nom, (None, None))[0]
            # Rien à annoncer si la valeur n'existait pas : on ne remplace
            # alors rien du tout, et « remplace : (rien) » est du bruit.
            # L'indentation reste dans le code : une clé de traduction qui
            # commence par huit espaces est un piège à traducteur.
            if actuel is not None:
                lignes.append("        " + tr("remplace : {}").format(actuel))
        detail = "\n".join(lignes)
        # Sous Linux, le registre est celui du préfixe Wine : le dire, pour
        # que personne ne croie qu'on touche à quoi que ce soit du système.
        if sys.platform == "win32":
            intro = tr("{jeu} enregistre ses réglages dans le registre de Windows.\n\n"
                       "Le launcher va écrire ceci dans {cle} :\n\n{valeurs}")
        else:
            intro = tr("{jeu} enregistre ses réglages dans le registre de Wine, "
                       "celui du préfixe du launcher.\n\n"
                       "Le launcher va écrire ceci dans {cle} :\n\n{valeurs}")
        morceaux = [
            intro.format(jeu=nom_jeu, cle=f"{ruche}\\{cle}", valeurs=detail),
            tr("Sans cette écriture, le jeu risque de ne pas démarrer."),
        ]
        # Pas d'UAC sous Wine : l'annoncer ferait attendre une fenêtre qui ne
        # viendra pas.
        if ruche == "HKLM" and sys.platform == "win32":
            morceaux.append(tr("Windows va ensuite demander une autorisation "
                               "administrateur."))
        morceaux.append(tr("Continuer ?"))
        return _boite(
            QMessageBox.Icon.Question, view, tr("Réglage du jeu"),
            "\n\n".join(morceaux),
            (tr("Écrire et lancer"), tr("Annuler")),
        ) == 0
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


def on_play(view: "GameDetailView", ignorer_prerequis: bool = False) -> None:
    if view.game is None:
        return
    if view.preparation_en_cours:
        # Deux winetricks dans le même préfixe se marcheraient dessus, et le
        # jeu partirait sans ce qu'on est justement en train d'installer.
        view.notify.emit(tr("Préparation de Wine en cours — patientez un instant."))
        return
    view._stop_video()
    demander = confirmer_registre(view, view.game.name)
    accepte = True

    def confirmer(ruche, cle, valeurs, ecarts=None):
        nonlocal accepte
        accepte = demander(ruche, cle, valeurs, ecarts)
        return accepte

    def avertir() -> None:
        # Un REFUS n'a rien à signaler : l'utilisateur vient de répondre non,
        # le lui répéter serait le lui reprocher. Un ÉCHEC, si — le jeu part
        # avec un réglage que le launcher n'a pas pu corriger, et sans ce mot
        # personne ne fera le lien entre l'invite et le jeu qui se ferme.
        if accepte:
            view.notify.emit(
                tr("Le réglage n'a pas pu être écrit — le jeu démarre "
                   "avec sa configuration actuelle."))

    # Passé seulement quand il sert : les tests remplacent `launch_game`
    # par des doublures qui ne connaissent pas ce paramètre.
    options = {"ignorer_prerequis": True} if ignorer_prerequis else {}
    try:
        proc = view.manager.launch_game(
            view.game.id, confirmer=confirmer, avertir=avertir, **options)
    except RuntimeError as exc:
        if str(exc) == "compat_absent":
            signaler_compat_absent(view)
        elif str(exc).startswith("prerequis_manquant:") and sys.platform != "win32":
            proposer_preparation(view, view.game, puis_jouer=True)
        elif str(exc).startswith("prerequis_manquant:"):
            manquant = str(exc).split(":", 1)[1]
            reply = _boite(QMessageBox.Icon.Warning,
                view, tr("Composant Windows manquant"),
                tr("{} n'est pas installé sur ce PC.\nCe jeu ne peut pas démarrer sans lui.\n\n"
                   "Voulez-vous ouvrir la page de téléchargement ?").format(
                       nom_prerequis(manquant)),
                (tr("Ouvrir la page"), tr("Plus tard")),
            )
            if reply == 0:
                open_url(PREREQUIS.get(manquant, (None, VCREDIST_URL))[1])
        elif str(exc).startswith("documents_inutilisable:") and sys.platform != "win32":
            _boite(QMessageBox.Icon.Critical, view,
                   tr("Dossier Documents inaccessible"),
                   tr("Ce jeu enregistre sa configuration et ses sauvegardes dans :\n\n{}\n\n"
                      "Ce dossier du préfixe Wine refuse l'écriture, donc le jeu ne peut pas "
                      "démarrer.\n\nVérifiez qu'il reste de la place sur le disque, et que "
                      "le dossier « _Launcher » d'Accio Launcher vous appartient bien.")
                   .format(str(exc).split(":", 1)[1]))
        elif str(exc).startswith("documents_inutilisable:"):
            _boite(QMessageBox.Icon.Critical, view,
                   tr("Dossier Documents inaccessible"),
                   tr("Ce jeu enregistre sa configuration et ses sauvegardes dans :\n\n{}\n\nWindows refuse d'y écrire, donc le jeu ne peut pas démarrer.\n\nC'est en général une protection : dans Sécurité Windows → Protection contre les rançongiciels, désactivez « Accès contrôlé aux dossiers » ou autorisez Accio Launcher. Un antivirus tiers peut faire la même chose. Si ce dossier a été déplacé ou supprimé, rétablissez-le par clic droit sur Documents → Propriétés → Emplacement.").format(str(exc).split(":", 1)[1]))
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


def signaler_compat_absent(view: "GameDetailView") -> None:
    """Ni umu-run ni wine : dire QUOI installer, jamais un échec muet.

    Sur Bazzite, umu-launcher fait partie de l'image (relevé dans son
    `Containerfile`) : s'il manque, c'est une image ancienne ou modifiée, et
    la mise à jour du système le ramène. Ailleurs, le paquet de la
    distribution. La détection est refaite au clic suivant sur JOUER : pas
    besoin de redémarrer le launcher.
    """
    reponse = _boite(
        QMessageBox.Icon.Warning, view, tr("Wine introuvable"),
        tr("Accio Launcher lance ces jeux Windows avec umu-launcher (recommandé) "
           "ou Wine. Aucun des deux n'est installé.\n\n"
           "Sur Bazzite, umu-launcher fait partie du système : mettez Bazzite à "
           "jour (« ujust update ») puis redémarrez. Sur une autre distribution, "
           "installez le paquet umu-launcher, ou Wine avec le support 32 bits.\n\n"
           "Cliquez ensuite à nouveau sur JOUER : le launcher les cherchera de "
           "nouveau."),
        (tr("Ouvrir le guide"), tr("Fermer")))
    if reponse == 0:
        open_url(GUIDE_LINUX_URL)


def proposer_preparation(view: "GameDetailView", game: GameData | None,
                         puis_jouer: bool) -> None:
    """Propose de préparer Wine pour ce jeu : préfixe, puis composants.

    Une QUESTION, pas une initiative : winetricks télécharge chez Microsoft,
    et umu peut télécharger Proton la première fois. On dit ce qui va se
    passer, on laisse décider, et on ne le fait que sur un clic.
    """
    if game is None:
        return
    if view.preparation_en_cours:
        view.notify.emit(tr("Préparation de Wine en cours — patientez un instant."))
        return
    manquants = prerequis_manquants(("vcredist_x86", *game.requires))
    verbes = [VERBES_WINETRICKS[m] for m in manquants if m in VERBES_WINETRICKS]
    etapes = []
    if not compat.pret(compat.prefixe()):
        etapes.append("• " + tr("créer le préfixe Wine du launcher"))
    if verbes:
        etapes.append("• " + tr("y installer {}").format(noms_des_verbes(verbes)))
    if not etapes:
        return
    reponse = _boite(
        QMessageBox.Icon.Question, view, tr("Préparer Wine"),
        tr("Avant de lancer {jeu}, le launcher doit préparer Wine :\n\n{etapes}\n\n"
           "Les composants Visual C++ sont téléchargés depuis Microsoft par "
           "winetricks. Avec umu, la première préparation télécharge aussi Proton "
           "(plusieurs centaines de Mo). Comptez quelques minutes ; le launcher "
           "reste utilisable pendant ce temps.").format(
               jeu=game.name, etapes="\n".join(etapes)),
        (tr("Préparer et lancer") if puis_jouer else tr("Préparer"), tr("Plus tard")))
    if reponse == 0:
        view.preparer_wine(game, verbes, puis_jouer)


def apres_preparation(view: "GameDetailView", game_id: str, reussie: bool,
                      raison: str, puis_jouer: bool) -> None:
    """La préparation est finie : lancer, prévenir, ou expliquer l'échec.

    Un échec n'est pas une impasse quand le préfixe existe : les composants
    INTÉGRÉS à Wine suffisent parfois, et c'est à l'utilisateur d'essayer —
    d'où « Lancer quand même ». Sans préfixe, rien ne peut démarrer.
    """
    game = view.manager.get_game_by_id(game_id)
    if game is None or raison == preparation.ANNULEE:
        return
    affiche = view.game is not None and view.game.id == game_id
    if reussie:
        if puis_jouer and affiche:
            on_play(view)
        else:
            view.notify.emit(tr("Wine est prêt : {} peut être lancé.").format(game.name))
        return
    journal = str(view.journal_preparation)
    if raison == preparation.PREFIXE:
        _boite(QMessageBox.Icon.Critical, view, tr("Préparer Wine"),
               tr("Le préfixe Wine n'a pas pu être créé.\n\nCe qu'ont dit umu ou Wine "
                  "est dans :\n{}").format(journal))
        return
    if raison == preparation.WINETRICKS_ABSENT:
        texte = tr("winetricks est introuvable : les composants Visual C++ ne peuvent "
                   "pas être installés dans Wine.\n\nInstallez winetricks (il fait "
                   "partie de Bazzite) ou umu-launcher. Le jeu peut aussi démarrer "
                   "sans eux : les composants intégrés à Wine suffisent parfois.")
    else:
        texte = tr("L'installation des composants Visual C++ dans Wine a échoué.\n\n"
                   "Ce qu'a dit winetricks est dans :\n{}\n\nLe jeu peut tout de même "
                   "démarrer : les composants intégrés à Wine suffisent parfois.").format(
                       journal)
    if not affiche:
        _boite(QMessageBox.Icon.Warning, view, tr("Préparer Wine"), texte)
        return
    reponse = _boite(QMessageBox.Icon.Warning, view, tr("Préparer Wine"), texte,
                     (tr("Lancer quand même"), tr("Fermer")), 1)
    if reponse == 0:
        on_play(view, ignorer_prerequis=True)


def on_uninstall(view: "GameDetailView") -> None:
    if view.game is None:
        return
    reply = _boite(QMessageBox.Icon.Question,
        view, tr("Confirmer la désinstallation"),
        tr("Voulez-vous vraiment désinstaller {} ?").format(view.game.name),
        (tr("Désinstaller"), tr("Annuler")), 1,
    )
    if reply != 0:
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
        (tr("Mettre à jour"), tr("Plus tard")), 1,
    )
    if reply == 0:
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
        (tr("Vérifier et réparer"), tr("Annuler")), 1,
    )
    if reply == 0:
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
        (tr("Déplacer et importer"), tr("Annuler")), 1,
    )
    if reply != 0:
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


def on_game_settings(view: "GameDetailView") -> None:
    """Ouvre la fenêtre de réglages du jeu (engrenage à côté des boutons).

    Une FENÊTRE et pas un menu : les réglages d'un jeu vont s'étoffer
    (résolution, qualité, mode fenêtré), et un menu qui grandit devient une
    liste à dérouler. Une fenêtre a des rubriques, de la place pour expliquer,
    et sait montrer ce qui n'est pas encore livré — ce que la rubrique
    « Affichage », verrouillée, fait exprès.
    """
    game = view.game
    if game is None:
        return
    dlg = GameSettingsDialog(
        game, view.manager,
        appliquer_langue=lambda code: _appliquer_langue(view, code),
        actions=_actions_fichiers(view, game),
        parent=view)
    dlg.exec()


def _actions_fichiers(view: "GameDetailView", game: GameData):
    """Ce que la fenêtre de réglages propose sous « Fichiers du jeu ».

    « Gérer les versions » et « Vérifier / réparer » n'étaient atteignables
    qu'au CLIC DROIT — le défaut qu'on vient de corriger pour la langue, à
    l'identique. Réparer n'a de sens que sur un jeu installé ; l'ouverture du
    dossier non plus, et proposer d'ouvrir un dossier qui n'existe pas serait
    une erreur de plus à expliquer.
    """
    actions = [(tr("Gérer les versions"), lambda: on_versions_clicked(view))]
    if view.manager.get_state(game.id) == GameState.INSTALLED:
        actions.append((tr("Vérifier / réparer les fichiers"),
                        lambda: on_repair(view)))
        actions.append((tr("Ouvrir le dossier du jeu"),
                        lambda: _ouvrir_dossier_du_jeu(view, game)))
    return actions


def _ouvrir_dossier_du_jeu(view: "GameDetailView", game: GameData) -> None:
    """Ouvre le dossier où le jeu est RÉELLEMENT installé.

    Le dossier de l'exécutable, pas la racine d'installation : depuis que HP7
    range ses fichiers dans un sous-dossier `pc`, les deux ont divergé, et
    c'est celui qui contient le jeu qu'on veut voir.
    """
    dossier = (view.manager.config.install_path
               / Path(game.executable.replace(chr(92), "/")).parent)
    if not dossier.is_dir():
        view.notify.emit(tr("Dossier introuvable — le jeu a peut-être été déplacé."))
        return
    open_local_path(str(dossier))


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


def _appliquer_langue(view: "GameDetailView", code: str) -> bool:
    """Enregistre le choix, l'écrit dans le registre, rafraîchit la fiche.

    Rend True si le registre porte RÉELLEMENT la nouvelle langue. La fenêtre
    de réglages s'en sert pour remettre son bouton radio sur ce qui est vrai :
    laisser la sélection sur un choix refusé afficherait une langue que le jeu
    n'a pas.
    """
    game = view.game
    if game is None or code == view.manager.game_language(game):
        return False
    if game.language_registry is None:
        return False
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

    def confirmer(ruche, cle, valeurs, ecarts=None):
        nonlocal accepte
        QApplication.restoreOverrideCursor()
        try:
            accepte = demander(ruche, cle, valeurs, ecarts)
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
        return False
    if pose:
        view.manager.set_game_language(game.id, code)
        langue = game.language_registry.get(code)
        etiquette = langue.label if langue is not None else code
        view.notify.emit(tr("Langue du jeu : {}").format(etiquette))
        view.set_game(game)
        return True
    else:
        # Échec = UAC refusé, ou le registre n'a pas pris. Une vraie erreur,
        # donc un modal : le choix est enregistré mais SANS effet, et un toast
        # qui s'efface laisserait l'utilisateur croire que c'est fait.
        if sys.platform == "win32":
            texte = tr("La langue n'a pas pu être écrite dans le registre.\n\n"
                       "Ce réglage demande une autorisation administrateur. Le jeu "
                       "démarrera dans la langue actuellement en place.")
        else:
            texte = tr("La langue n'a pas pu être écrite dans le registre de Wine.\n\n"
                       "Le jeu démarrera dans la langue actuellement en place. Le "
                       "journal du launcher dit ce qui s'est passé.")
        _boite(QMessageBox.Icon.Warning, view, tr("Langue du jeu"), texte)
    view.set_game(game)
    return False


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

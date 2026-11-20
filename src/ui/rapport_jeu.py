"""« Rapport du jeu », dans la rubrique Fichiers des réglages d'un jeu (Ludo, 2026-11-20, après #40).

Le rapport global (Paramètres → À propos) existait, mais personne ne le trouvait depuis le jeu qui pose souci, et il ne
disait ni les réglages en place ni les parties d'avant. Celui-ci ne parle que du jeu : en-tête (launcher, système,
matériel, écrans, version du jeu), réglages actuels, journaux de la dernière partie, puis des lancements gardés
(`core/journaux_jeux`). Posé sur le Bureau et dans le presse-papiers comme fichier : un Ctrl+V le joint sur Discord
ou dans une issue GitHub.
"""
import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtGui import QGuiApplication

from src.core import diagnostic, journaux_jeux
from src.core.game_data import GameData
from src.core.i18n import tr
from src.ui.reglages_rubriques import ActionFichier

log = logging.getLogger(__name__)


def nom_du_fichier(game: GameData) -> str:
    # Nom FIXE par jeu : chaque copie remplace la précédente, rien ne s'accumule sur le Bureau.
    return f"Accio Launcher - {game.id} - rapport.txt"


def entete(game: GameData, version: str | None) -> list[str]:
    ecrans = [diagnostic.ecran(e.size().width(), e.size().height(), e.devicePixelRatio())
              for e in QGuiApplication.screens()]
    return [f"Rapport de {game.name} ({game.id}) · version du jeu {version or '?'}",
            datetime.now().strftime("%Y-%m-%d %H:%M"), diagnostic.identite(), *diagnostic.materiel(),
            *(f"Écran : {e}" for e in ecrans)]


def enregistrer(view, game: GameData) -> Path | None:
    from src.ui.about_page import dossier_du_rapport
    tete = entete(game, view.manager.installed_version(game.id))
    chemin = dossier_du_rapport() / nom_du_fichier(game)
    try:
        chemin.write_text(journaux_jeux.rapport(game, view.manager.config, tete), encoding="utf-8")
    except OSError as exc:
        log.warning("Rapport de %s non écrit (%s) : %s", game.id, chemin, exc)
        return None
    return chemin


def copier(view, game: GameData) -> None:
    from src.ui.about_page import presse_papiers
    chemin = enregistrer(view, game)
    if chemin is None:
        view.notify.emit(tr("Le rapport n'a pas pu être écrit sur le Bureau."))
        return
    QGuiApplication.clipboard().setMimeData(presse_papiers("\n".join(entete(game, None)[:1]), chemin))
    view.notify.emit(tr("Rapport de {} copié : un Ctrl+V le joint sur Discord ou GitHub. "
                        "Il est aussi sur votre Bureau.").format(game.name))


def action(view, game: GameData) -> ActionFichier:
    return ActionFichier(tr("Rapport du jeu"), lambda: copier(view, game),
                         tr("Les réglages en place et les journaux des derniers lancements, "
                            "prêts à joindre à une demande d'aide."), tr("Copier"))

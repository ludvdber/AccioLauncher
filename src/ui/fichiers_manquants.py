"""Dire au joueur quels fichiers essentiels manquent à son jeu, et quoi faire.

À part de `game_detail_handlers` (plafond de lignes) : la vérification vit
dans `src.core.fichiers_essentiels`, ici seulement la boîte. Appelé par
« Vérifier / réparer les fichiers » et après un lancement raté, jamais avant
de lancer : un mod qui remplace un fichier ne doit rien bloquer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from src.core import fichiers_essentiels
from src.core.game_data import GameData
from src.core.i18n import tr
from src.ui.utils import open_local_path

if TYPE_CHECKING:
    from src.ui.game_detail import GameDetailView

log = logging.getLogger(__name__)

# Au-delà, la boîte ne tiendrait plus à l'écran ; le nombre dit le reste.
_MANQUANTS_AFFICHES = 8


def constat_complet(game: GameData) -> str:
    """Le paragraphe « rien ne manque », seulement si le catalogue a une liste.

    Sans elle, seul l'exécutable a été regardé : « tout est là » mentirait.
    """
    if not game.fichiers_essentiels:
        return ""
    return tr("Les fichiers essentiels de {} sont tous là.").format(game.name) + "\n\n"


def signaler_fichiers_manquants(view: "GameDetailView", game: GameData) -> bool:
    """Dit quels fichiers essentiels manquent, et propose d'y remédier.

    Rend True si une boîte a été montrée (il en manquait), False sinon : à
    l'appelant de poursuivre. Les noms seuls, pas les chemins : c'est ce que
    montre la quarantaine d'un antivirus, et ce que le joueur cherchera.
    """
    # Ici et pas en tête : `game_detail_handlers` importe ce module.
    from src.ui import game_detail_handlers as h

    absents = fichiers_essentiels.manquants(game, Path(view.manager.config.install_path))
    if not absents:
        return False
    log.warning("%s : fichier(s) essentiel(s) absent(s) : %s", game.id, ", ".join(absents))
    noms = [f"• {Path(f).name}" for f in absents[:_MANQUANTS_AFFICHES]]
    if len(absents) > _MANQUANTS_AFFICHES:
        noms.append(tr("… et {} autres").format(len(absents) - _MANQUANTS_AFFICHES))
    choix = h._boite(QMessageBox.Icon.Warning,
        view, tr("Il manque des fichiers à {}").format(game.name),
        tr("Ces fichiers du jeu ne sont plus dans son dossier :\n{}\n\n"
           "Le plus souvent, c'est l'antivirus qui les a mis en quarantaine. Restaurez-les "
           "depuis son historique, puis ajoutez le dossier des jeux à ses exclusions : "
           "sinon il les retirera encore.\n\n"
           "« Retélécharger le jeu » réinstalle tous ses fichiers par-dessus. "
           "Les sauvegardes ne sont pas touchées.").format("\n".join(noms)),
        (tr("Retélécharger le jeu"), tr("Ouvrir le dossier du jeu"), tr("Fermer")), 2,
    )
    if choix == 0:
        # Re-gardé : la boîte a pu rester ouverte pendant qu'autre chose démarrait.
        if not view._ops.is_busy and not h._preparation_bloque(view):
            view._ops.repair(game)
            view._refresh()
    elif choix == 1:
        ouvrir_dossier_du_jeu(view, game)
    return True


def ouvrir_dossier_du_jeu(view: "GameDetailView", game: GameData) -> None:
    """Ouvre le dossier où le jeu est RÉELLEMENT installé.

    Le dossier de l'exécutable, pas la racine d'installation : depuis que HP7
    range ses fichiers dans un sous-dossier `pc`, les deux ont divergé, et
    c'est celui qui contient le jeu qu'on veut voir. Ici depuis le 2026-10-09 :
    la boîte des fichiers manquants y renvoie, et l'hôte touchait son plafond.
    """
    dossier = (view.manager.config.install_path
               / Path(game.executable.replace(chr(92), "/")).parent)
    if not dossier.is_dir():
        view.notify.emit(tr("Dossier introuvable — le jeu a peut-être été déplacé."))
        return
    open_local_path(str(dossier))

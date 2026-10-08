"""Les fichiers sans lesquels un jeu installé ne démarre pas sont-ils encore là ?

Né d'un rapport du 2026-10-09 : l'antivirus d'un joueur avait retiré
`d3d11drv.dll` de HP2 APRÈS une installation réussie. Le jeu s'arrêtait sur
« Assertion failed: RenDev », le launcher y voyait une configuration abîmée,
et la remettre quatre fois n'y changeait rien.

La liste vient du catalogue (`GameData.fichiers_essentiels`, plus
l'exécutable). On ne regarde que la PRÉSENCE : un mod qui remplace un fichier
n'est pas une panne, et un fichier en plus n'en est jamais une. Vérifié sur
demande (« Vérifier / réparer les fichiers ») et après un lancement raté,
jamais avant de lancer.
"""

import os
from pathlib import Path

from src.core.game_data import GameData


def _present(racine: Path, relatif: str) -> bool:
    """`relatif` existe-t-il sous `racine`, casse ignorée ? Pure.

    Windows l'ignore déjà ; sous Linux, un jeu Windows écrit `System` dans son
    catalogue et `system` sur le disque sans que rien ne casse sous Wine — il
    ne faut pas l'annoncer manquant pour autant.
    """
    courant = racine
    for nom in relatif.replace("\\", "/").split("/"):
        if nom in ("", "."):
            continue
        exact = courant / nom
        if exact.exists():
            courant = exact
            continue
        try:
            voisins = os.listdir(courant)
        except OSError:
            return False
        trouve = next((v for v in voisins if v.casefold() == nom.casefold()), None)
        if trouve is None:
            return False
        courant = courant / trouve
    return courant.is_file()


def manquants(game: GameData, install_path: Path) -> list[str]:
    """Les fichiers essentiels absents, dans l'ordre du catalogue. Pure.

    L'exécutable d'abord : sans lui, rien d'autre n'a de sens.
    """
    attendus = [game.executable.replace("\\", "/")]
    attendus += [f for f in game.fichiers_essentiels if f.casefold() != attendus[0].casefold()]
    return [f for f in attendus if not _present(Path(install_path), f)]

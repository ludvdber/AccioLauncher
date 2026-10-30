"""La difficulté propre au jeu, réglée depuis le launcher.

Demande de Ludo (2026-10-30), pour la 1.3.1 en bêta : HP2 a une difficulté
dans son menu Options (Facile / Moyen / Difficile, `User.ini`
`[Engine.PlayerPawn] Difficulty`), livrée en Facile, et que presque personne
n'y a vue. Ce qu'elle change, lu dans le code du jeu (atelier,
`notes/doc/hp2/SANTE_DEGATS.md` § 7) : dégâts reçus × 1,2 / 2 / 3, sorts
ennemis × 1 / 2 / 3, Basilic plus dur ; pas VU en jeu.

**Le fichier du jeu fait foi**, rien n'est gardé dans la config du launcher :
le menu du jeu et le launcher montrent toujours la même chose. Écrit au CHOIX,
jamais au lancement (sinon le launcher défairait le choix fait dans le jeu).
Le jeu relit le fichier à son démarrage : un choix fait pendant une partie
compte au prochain lancement.
"""

from src.core.catalogue_blocs import Difficulte, IniPatch
from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import ecrire_cle_ini, lire_cle_ini

# Le nom de chaque cran, du plus facile au plus difficile (clés tr()).
NIVEAUX = ("Facile", "Moyen", "Difficile")


def _patch(spec: Difficulte, valeur: str = "") -> IniPatch:
    return IniPatch(file=spec.file, section=spec.section, key=spec.key, value=valeur)


def lire(game: GameData, config: Config) -> int | None:
    """Le cran posé (0 facile, 1 moyen, 2 difficile) ; None sans bloc au catalogue.

    Une clé absente ou une valeur inconnue se lit « Facile » : c'est ce que fait
    le moteur (premier élément de son énumération). La casse est ignorée, comme
    par le moteur.
    """
    spec = game.difficulte
    if spec is None:
        return None
    posee = (lire_cle_ini(_patch(spec), game, config) or "").casefold()
    for rang, valeur in enumerate(spec.values):
        if valeur.casefold() == posee:
            return rang
    return 0


def ecrire(game: GameData, config: Config, rang: int) -> bool:
    """Pose le cran `rang` dans le fichier du jeu. True si c'est fait.

    False sans bloc, pour un cran hors de 0..2, ou si le fichier manque ou ne
    s'écrit pas (`ecrire_cle_ini` ne crée jamais l'ini : c'est le jeu qui l'écrit).
    """
    spec = game.difficulte
    if spec is None or not 0 <= rang < len(spec.values):
        return False
    return ecrire_cle_ini(_patch(spec, spec.values[rang]), game, config)

"""L'incrustation du correctif (compteur F10, mesure F11) sous Wine.

Le correctif de HP4 à HP7b ne dessine pas son incrustation sous Wine
(`[Accio.Overlay] DrawUnderWine=0`, depuis sa 2.2.0) : son premier dessin de
texte figeait le GPU Intel pour de bon. La cause est dans le pilote (voir
`compat.OPTION_DXVK_SANS_GEL`), et le lanceur l'écarte par `DXVK_CONFIG` à chaque
lancement. Quand l'environnement du lancement porte ce remède, le lanceur
autorise donc le dessin ; sinon il le coupe. Sans cela, « Compteur d'images » et
« Panneau de performances » des réglages ne montraient rien sous Linux, et F10
non plus.

Vérifié sur Bazzite le 2026-11-11 (Intel UHD, Mesa 26.2.6, GE-Proton10-34) :
gel à chaque fois sans le remède, aucun sur 6 parties de 10 minutes avec.

Seul le `d3d9.ini` porte cette clé ; un ini qui ne l'a pas (correctif plus
ancien, HP1 à HP3) n'est pas touché.
"""

import logging
from collections.abc import Mapping
from pathlib import Path

from src.core import compat, reglages_correctif

log = logging.getLogger(__name__)

SECTION = "Accio.Overlay"
CLE = "DrawUnderWine"


def suivre(dossier_exe: Path, env: Mapping[str, str]) -> bool:
    """Au lancement sous Wine : `DrawUnderWine` suit le remède de l'environnement.

    Rend True si l'ini a été écrit. Ne lève pas : le jeu démarre quand même,
    avec l'incrustation dans l'état où elle était.
    """
    ini = reglages_correctif.chemin_ini(dossier_exe)
    if reglages_correctif.valeur_posee(ini, SECTION, CLE) is None:
        return False
    voulu = "1" if compat.dxvk_sans_gel(env) else "0"
    try:
        ecrit = reglages_correctif.poser_valeur(ini, SECTION, CLE, voulu)
    except (OSError, ValueError):
        log.warning("Incrustation : %s non posé dans %s", CLE, ini, exc_info=True)
        return False
    if ecrit:
        log.info("Incrustation du correctif sous Wine : %s=%s dans %s", CLE, voulu, ini)
    return ecrit

"""La qualité du rendu Direct3D 11 de HP1 et HP2 : Maximale, Équilibrée, Légère.

Constat du 2026-11-18 (un joueur sur PC portable) : HP1 et HP2 à 5 images/s en
plein écran, 15 en fenêtré, les autres jeux fluides, rien ne change en baissant
les options du jeu. Leur rendu D3D11 est installé au MAXIMUM dans
`[D3D11Drv.D3D11RenderDevice]` (MSAA 8, occlusion ambiante, réflexions, HDR,
parallaxe, éclairage volumétrique, distance illimitée), et le menu du jeu
n'atteint aucune de ces clés.

Le choix vit dans la config du launcher (`Config.qualite_rendu`, id → niveau)
et s'écrit au LANCEMENT, jeu fermé, clé par clé dans l'ini du joueur
(`pre_launch.ecrire_cles_ini` : sections et clés sans casse, toute autre ligne
intacte). Sans choix, rien n'est écrit : l'ini reste celui de l'installation.
Chaque niveau pose TOUTES ses clés, si bien que revenir à « Maximale » remet
exactement l'installation.
"""

from src.core.catalogue_blocs import IniPatch
from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import ecrire_cles_ini

SECTION = "D3D11Drv.D3D11RenderDevice"

MAXIMALE = "maximale"
EQUILIBREE = "equilibree"
LEGERE = "legere"
NIVEAUX = (MAXIMALE, EQUILIBREE, LEGERE)

# Maximale = les valeurs livrées par l'installation (HP.ini de HP1, Game.ini de HP2).
_VALEURS: dict[str, dict[str, str]] = {
    MAXIMALE: {"Antialiasing": "8", "ASSAO": "True", "SSR": "True", "HDR": "True",
               "ParallaxOcclusionMapping": "True", "VolumetricLighting": "True",
               "UnlimitedViewDistance": "True"},
    EQUILIBREE: {"Antialiasing": "4", "ASSAO": "True", "SSR": "False", "HDR": "True",
                 "ParallaxOcclusionMapping": "False", "VolumetricLighting": "True",
                 "UnlimitedViewDistance": "False"},
    LEGERE: {"Antialiasing": "0", "ASSAO": "False", "SSR": "False", "HDR": "False",
             "ParallaxOcclusionMapping": "False", "VolumetricLighting": "False",
             "UnlimitedViewDistance": "False"},
}


def valeurs(niveau: str) -> dict[str, str]:
    """Les clés que pose `niveau` (copie) ; KeyError pour un niveau inconnu."""
    return dict(_VALEURS[niveau])


def _patch_d3d11(game: GameData) -> IniPatch | None:
    """Le patch du catalogue qui règle le rendu D3D11 du jeu : il dit QUEL fichier
    porte la section. Aucun : le jeu ne rend pas par D3D11Drv (HP3 à HP8)."""
    if game.pre_launch is None:
        return None
    return next((p for p in game.pre_launch.ini_patches
                 if p.section.casefold() == SECTION.casefold()), None)


def gere(game: GameData) -> bool:
    return _patch_d3d11(game) is not None


def choisi(game: GameData, config: Config) -> str:
    """Le niveau choisi pour ce jeu ; Maximale sans choix (l'installation)."""
    niveau = config.qualite_rendu.get(game.id, "")
    return niveau if niveau in NIVEAUX else MAXIMALE


def appliquer(game: GameData, config: Config) -> bool:
    """Écrit le niveau choisi dans l'ini du jeu. True si quelque chose a été écrit."""
    niveau = config.qualite_rendu.get(game.id, "")
    patch = _patch_d3d11(game)
    if niveau not in NIVEAUX or patch is None:
        return False
    return ecrire_cles_ini(patch.file, SECTION, _VALEURS[niveau], game, config)

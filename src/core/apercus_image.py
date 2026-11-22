"""Les aperçus avant/après des réglages de la page Image (décision de Ludo du 2026-11-12, point 4).

Deux images par réglage et par jeu, tirées de paires prises EN JEU (même partie, même vue, un seul
réglage changé) : la valeur Accio livrée et une autre valeur, sur la fenêtre 640 × 360 de la capture
2560 × 1440 où l'effet se voit le plus, pixels d'origine. Fabriquées par l'atelier
(`apercus_image.py`), rangées dans `assets/apercus_image/<jeu>/<ident>_accio.jpg` et `_autre.jpg`,
décrites par `index.json` : `{jeu: {ident: {"autre": libellé de l'autre valeur (clé tr()), …}}}`.

Seuls HP5 et HP6 en ont (2026-11-22) : les paires de HP4 sont noyées par la lumière de la forêt,
celles de HP1-HP3, HP7 et HP8 ne sont pas prises. Un réglage sans aperçu n'en montre aucun.
Aucune fonction ne lève.
"""

from dataclasses import dataclass
from pathlib import Path

from src.core import json_garde
from src.core.config import ASSETS_DIR

DOSSIER = ASSETS_DIR / "apercus_image"

# Les noms que peut porter l'autre valeur (clés tr(), traduites) : un libellé hors de cette liste
# ne s'afficherait qu'en français, l'aperçu n'est pas montré.
LIBELLES = ("Coupé", "Coupés", "Allumé", "Aucune", "D'origine", "Maximale", "Pack HD", "Filtrage ×4", "MSAA ×4", "×1,5")


@dataclass(frozen=True, slots=True)
class Apercu:
    accio: Path       # la valeur Accio livrée
    autre: Path       # l'autre valeur
    libelle: str      # le nom de l'autre valeur (clé tr())


def apercu(jeu: str, ident: str, dossier: Path = DOSSIER) -> Apercu | None:
    """L'aperçu du réglage `ident` dans le jeu `jeu` ; None s'il n'y en a pas ou s'il manque un fichier."""
    try:
        index = json_garde.lire(dossier / "index.json")
    except (OSError, ValueError):
        return None
    fiche = index.get(jeu, {}).get(ident) if isinstance(index, dict) else None
    if not isinstance(fiche, dict) or (libelle := fiche.get("autre")) not in LIBELLES or not isinstance(libelle, str):
        return None
    accio, autre = dossier / jeu / f"{ident}_accio.jpg", dossier / jeu / f"{ident}_autre.jpg"
    if not (accio.is_file() and autre.is_file()):
        return None
    return Apercu(accio, autre, libelle)

"""Saisons décoratives — palette et mouvement des particules selon la date.

`config.season` vaut "auto" (selon la date), "aucune", "halloween" ou "noel".
Le changement depuis Paramètres est appliqué EN DIRECT (les particules sont
re-semées), contrairement au thème qui demande un redémarrage.
"""

from datetime import date

# Ordre d'affichage dans Paramètres ; "auto" est résolu via current_season().
SEASONS = ("auto", "aucune", "halloween", "noel")


def current_season(today: date | None = None) -> str:
    """Saison décorative en cours : octobre → halloween, déc. + début janv. → noel."""
    today = today or date.today()
    if today.month == 10:
        return "halloween"
    if today.month == 12 or (today.month == 1 and today.day <= 6):
        return "noel"
    return "aucune"


def resolve(config_value: str, today: date | None = None) -> str:
    """Traduit la valeur de config en saison effective ("auto" → date du jour)."""
    if config_value == "auto":
        return current_season(today)
    return config_value if config_value in SEASONS else "aucune"

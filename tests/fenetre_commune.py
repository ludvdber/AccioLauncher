"""Ce que partagent les tests qui pilotent une vraie MainWindow (sortis de
`test_integration_smoke.py` le 2026-10-14). Les fixtures `make_window*`
vivent dans `conftest.py`."""

from src.core.game_data import load_catalog

_CATALOG = load_catalog()
_IDS = [g.id for g in _CATALOG.games]


def _libelles_du_layout(panel) -> list[str]:
    """Textes des widgets réellement dans le layout d'actions.

    Pas findChildren : `clear_layout` passe par deleteLater(), donc les boutons
    de la fiche précédente restent enfants un tour de boucle de plus.
    """
    layout = panel._action_layout
    textes = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and hasattr(w, "text"):
            textes.append(w.text())
    return textes


_LANG_BLOCK = {
    "root": "HKLM",
    "view": 32,
    "key": chr(92).join(["SOFTWARE", "Electronic Arts", "Jeu"]),
    "languages": {
        "fr": {"label": "Français", "values": {"Language": "French", "Locale": "fr_FR"}},
        "en": {"label": "English", "values": {"Language": "English", "Locale": "en_US"}},
        "de": {"label": "Deutsch", "values": {"Language": "German", "Locale": "de_DE"}},
    },
}

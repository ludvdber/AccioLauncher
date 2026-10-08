"""Plafonds de lignes des deux plus gros fichiers de l'interface (ACT-009).

Même patron que le plafond de `main_window.py` (`test_update_dispatcher.py`) : le test ne dit pas que ces fichiers
sont BIEN découpés, il rend leur croissance visible, donc délibérée. Le plafond se relève en le DISANT dans le
commentaire de la ligne, jamais en silence — sinon il devient un compteur.
"""
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]

PLAFONDS = {
    # Mesuré le 2026-10-08 : 884 lignes.
    "src/ui/game_settings_dialog.py": 890,
    # Mesuré le 2026-10-08 : 1097 lignes.
    "src/ui/game_detail_handlers.py": 1100,
}


@pytest.mark.parametrize("fichier", sorted(PLAFONDS))
def test_le_fichier_n_a_pas_regrossi(fichier):
    lignes = len((RACINE / fichier).read_text(encoding="utf-8").splitlines())
    assert lignes <= PLAFONDS[fichier], (
        f"{fichier} a regrossi : {lignes} lignes pour un plafond de {PLAFONDS[fichier]}. "
        "Sortir du code dans un module à part, ou relever le plafond en disant pourquoi.")

"""Configuration pytest globale.

Force le platform Qt à offscreen pour les CI sans display, et fournit
des fixtures réutilisables pour les tests UI.
"""

import os

# Doit être posé AVANT tout import PyQt6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest


@pytest.fixture(autouse=True)
def _config_hors_du_vrai_dossier(tmp_path, monkeypatch):
    """Aucun test n'écrit dans le config.json RÉEL de l'utilisateur.

    `Config.save()` vise `src.core.config.CONFIG_FILE_PATH`. Un test — ou un
    script de mise au point — qui construit une Config et la sauve avant d'avoir
    redirigé ce chemin écrase le fichier réel : dossier d'installation, versions
    installées, temps de jeu. C'est arrivé le 2026-08-18 et les statistiques de
    jeu ont été perdues. Cette garde rend l'accident impossible depuis les tests.
    """
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH",
                        tmp_path / "config_test.json")
    yield

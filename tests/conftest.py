"""Configuration pytest globale.

Force le platform Qt à offscreen pour les CI sans display, et fournit
des fixtures réutilisables pour les tests UI.
"""

import os

# Doit être posé AVANT tout import PyQt6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# Charger les modules d'extension Qt MAINTENANT, à la collecte, alors qu'il
# n'existe encore aucun objet Qt ni QApplication.
#
# `QtNetwork` n'était importé que tardivement, à l'intérieur d'un test ou d'un
# fixture. Créer un module d'extension C au milieu d'une session — donc pendant
# que le ramasse-miettes peut passer sur des objets Qt vivants — a provoqué un
# « Windows fatal exception: access violation » pendant un build, dans
# `enum.py` au moment de la création du module. Le plantage est ALÉATOIRE :
# il dépend du moment où le GC se déclenche, et il fait échouer un build au
# hasard. Importer tôt supprime la fenêtre de tir.
from PyQt6 import QtNetwork  # noqa: F401,E402
import pytest  # noqa: E402


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


@pytest.fixture(autouse=True)
def _jamais_d_elevation_uac(monkeypatch):
    """Aucun test ne doit pouvoir faire apparaître une invite UAC.

    `game_registry._ecrire_eleve` appelle `ShellExecuteW(..., "runas", ...)`,
    qui ouvre une fenêtre de consentement Windows et **bloque jusqu'à ce qu'un
    humain clique**. Dans une suite de tests, cela veut dire : une exécution
    qui ne se termine jamais, en CI comme sur le poste de développement, avec
    une boîte de dialogue système au milieu de l'écran.

    Un oubli de bouchon dans UN seul test suffirait. La garde est donc posée
    ici, pour tous : un test qui veut exercer ce chemin doit le remplacer
    explicitement, jamais l'atteindre par accident. Même esprit que la garde
    sur le vrai `config.json` ci-dessus.
    """
    def _interdit(*_a, **_k):
        raise AssertionError(
            "Un test a tenté une écriture registre ÉLEVÉE (invite UAC). "
            "Bouchonner `game_registry.ecrire_valeurs` dans le test.")

    monkeypatch.setattr("src.core.game_registry._ecrire_eleve", _interdit)
    yield

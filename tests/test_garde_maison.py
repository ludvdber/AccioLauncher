"""La suite ne peut pas viser le vrai dossier de la personne qui la lance."""

from pathlib import Path

from src.core import config, stats


def test_les_chemins_du_launcher_sont_ceux_de_la_suite():
    """Y compris hors des gardes par test : une écriture différée a remplacé le vrai config.json."""
    for chemin in (config.DEFAULT_INSTALL_PATH, config.LAUNCHER_DATA_PATH, Path.home()):
        assert "accio_tests_" in str(chemin), chemin


def test_le_journal_des_sessions_aussi():
    assert stats.JOURNAL_NAME == "sessions.json"
    assert "accio_tests_" in str(config.LAUNCHER_DATA_PATH / stats.JOURNAL_NAME)

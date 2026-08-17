"""Tests pour src/core/post_install.py — validation des destinations de config (pur)."""

from pathlib import Path

from src.core.post_install import (
    _FORBIDDEN_DEST_SUFFIXES,
    allowed_config_roots,
    config_dest_error,
)


def _roots(tmp_path: Path) -> list[Path]:
    return [tmp_path / "Documents", tmp_path / "Saved Games"]


class TestConfigDestError:
    def test_documents_accepte(self, tmp_path):
        dest = tmp_path / "Documents" / "Harry Potter" / "HP.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is None

    def test_saved_games_accepte(self, tmp_path):
        dest = tmp_path / "Saved Games" / "HP3" / "save.dat"
        assert config_dest_error(dest, _roots(tmp_path)) is None

    def test_hors_racines_refuse(self, tmp_path):
        """Le home entier n'est PAS une destination valide — seulement Documents."""
        dest = tmp_path / "AppData" / "Roaming" / "quelquechose.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_dossier_demarrage_refuse(self, tmp_path):
        """Régression sécurité : le dossier Démarrage est sous le home mais hors
        Documents — un catalogue empoisonné ne doit pas pouvoir y déposer un fichier."""
        dest = (tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows"
                / "Start Menu" / "Programs" / "Startup" / "evil.bat")
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_traversal_depuis_documents_refuse(self, tmp_path):
        dest = tmp_path / "Documents" / ".." / "AppData" / "x.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_extension_executable_refusee(self, tmp_path):
        """Même DANS Documents, une extension exécutable est refusée."""
        for suffix in (".exe", ".bat", ".lnk", ".dll", ".ps1"):
            dest = tmp_path / "Documents" / "Harry Potter" / f"payload{suffix}"
            reason = config_dest_error(dest, _roots(tmp_path))
            assert reason is not None, f"{suffix} aurait dû être refusé"
            assert "exécutable" in reason

    def test_extension_insensible_a_la_casse(self, tmp_path):
        dest = tmp_path / "Documents" / "HP" / "payload.ExE"
        assert config_dest_error(dest, _roots(tmp_path)) is not None

    def test_ini_reste_accepte(self, tmp_path):
        dest = tmp_path / "Documents" / "HP" / "User.ini"
        assert config_dest_error(dest, _roots(tmp_path)) is None


class TestAllowedConfigRoots:
    def test_documents_en_premier(self):
        roots = allowed_config_roots()
        assert len(roots) == 2
        assert roots[0].name.lower() in ("documents", "mes documents")

    def test_home_nu_pas_dans_les_racines(self):
        """Le home lui-même ne doit jamais être une racine autorisée."""
        assert Path.home().resolve() not in [r.resolve() for r in allowed_config_roots()]


class TestForbiddenSuffixes:
    def test_couvre_les_vecteurs_classiques(self):
        for suffix in (".exe", ".bat", ".cmd", ".ps1", ".vbs", ".lnk", ".dll", ".reg"):
            assert suffix in _FORBIDDEN_DEST_SUFFIXES

    def test_ini_non_interdit(self):
        assert ".ini" not in _FORBIDDEN_DEST_SUFFIXES

"""Tests pour src/core/win_utils.py"""

import sys

import pytest
from unittest.mock import patch

from src.core.win_utils import remove_zone_identifier


class TestRemoveZoneIdentifier:
    def test_non_existing_root(self, tmp_path):
        result = remove_zone_identifier(tmp_path / "does_not_exist")
        assert result == 0

    def test_empty_dir(self, tmp_path):
        assert remove_zone_identifier(tmp_path) == 0

    def test_non_windows_returns_zero(self, tmp_path):
        (tmp_path / "test.dll").write_text("fake")
        with patch.object(sys, "platform", "linux"):
            assert remove_zone_identifier(tmp_path) == 0

    def test_does_not_crash_on_files_without_zone_identifier(self, tmp_path):
        # Sur Windows réel, les fichiers locaux n'ont pas de Zone.Identifier ;
        # la fonction tente le os.remove et catch OSError silencieusement.
        (tmp_path / "test.dll").write_text("fake")
        (tmp_path / "test.exe").write_text("fake")
        # Ne doit pas crasher (sous Windows OS error attrapée, sous Linux short-circuit)
        result = remove_zone_identifier(tmp_path)
        assert isinstance(result, int)

    def test_pattern_filter(self, tmp_path):
        (tmp_path / "a.dll").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        # Pattern restreint : seuls les .dll seraient itérés
        # On ne peut pas tester l'effet réel sans un vrai NTFS, mais l'API
        # ne doit pas crasher avec un pattern custom.
        result = remove_zone_identifier(tmp_path, pattern="*.dll")
        assert isinstance(result, int)

    def test_subdirectories_traversed(self, tmp_path):
        sub = tmp_path / "sub" / "nested"
        sub.mkdir(parents=True)
        (sub / "deep.dll").write_text("x")
        result = remove_zone_identifier(tmp_path)
        assert isinstance(result, int)


class TestNomsCommencantPar:
    """La recherche par motif qui remplace le parcours de WinSxS (90 ms → 0,2)."""

    def test_casse_ignoree_et_seulement_le_debut(self, tmp_path):
        from src.core.win_utils import noms_commencant_par
        (tmp_path / "X86_Microsoft.VC80.CRT_abc_8.0").mkdir()
        (tmp_path / "x86_microsoft.vc90.crt_abc_9.0").mkdir()
        (tmp_path / "autre_x86_microsoft.vc80.crt_abc").mkdir()
        assert noms_commencant_par(tmp_path, "x86_microsoft.vc80.crt_abc_") == [
            "X86_Microsoft.VC80.CRT_abc_8.0"]

    def test_rien_ou_dossier_absent(self, tmp_path):
        from src.core.win_utils import noms_commencant_par
        assert noms_commencant_par(tmp_path, "x86_") == []
        assert noms_commencant_par(tmp_path / "absent", "x86_") == []

    def test_repli_quand_le_systeme_refuse(self, tmp_path, monkeypatch):
        """L'appel système qui échoue ne doit rien cacher : on parcourt."""
        from src.core import win_utils

        def refus(*_a):
            raise OSError("refusé")
        monkeypatch.setattr(win_utils, "_noms_par_le_systeme", refus)
        (tmp_path / "x86_a").mkdir()
        assert win_utils.noms_commencant_par(tmp_path, "X86_") == ["x86_a"]

    def test_le_motif_n_est_jamais_un_joker(self, tmp_path):
        """Un « * » dans le début n'élargit pas la recherche."""
        from src.core.win_utils import noms_commencant_par
        (tmp_path / "abc").mkdir()
        assert noms_commencant_par(tmp_path, "a*") == []


class TestHabillerFenetre:
    """Coins arrondis et trait natifs de Windows 11 (fenêtre sans cadre)."""

    def test_colorref_est_bgr(self):
        from src.core.win_utils import couleur_dwm
        assert couleur_dwm(0x1A, 0x27, 0x44) == 0x44271A

    def test_hors_windows_rien(self, monkeypatch):
        import src.core.win_utils as wu
        monkeypatch.setattr(wu.sys, "platform", "linux")
        assert wu.habiller_fenetre(1234, (0, 0, 0)) is False


@pytest.mark.skipif(sys.platform != "win32", reason="registre et DWM : Windows seulement")
class TestAppelsReelsWindows:
    """Lecture seule : ces appels n'avaient jamais été exécutés par la suite."""

    def test_couches_d_un_exe_inconnu(self, tmp_path):
        from src.core import win_utils
        assert win_utils.couches_de_compatibilite(tmp_path / "personne.exe") == {}

    def test_habiller_une_fenetre_inexistante_rend_faux(self):
        from src.core import win_utils
        assert win_utils.habiller_fenetre(0, (214, 167, 44)) is False

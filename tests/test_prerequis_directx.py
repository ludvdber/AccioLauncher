"""Runtime DirectX de juin 2010 : les DLL que Windows ne livre pas.

Relevé dans les binaires le 2026-09-26 : HP5/HP6 importent xinput1_3.dll, les
Reliques d3dx9_37.dll et xinput1_3.dll, le wrapper d3d9 de HP4 à HP7b
d3dx9_43.dll. Sur un Windows neuf, ces jeux s'arrêtaient sur « xinput1_3.dll est
introuvable » sans que le launcher ait rien dit.
"""

import pytest

from src.core import system_checks
from src.core.system_checks import (
    DIRECTX9_URL, DLL_DIRECTX9, PREREQUIS, VERBES_WINETRICKS, dll_x86_presente,
    prerequis_manquants,
)


@pytest.fixture(autouse=True)
def _caches_vides():
    system_checks.invalidate_vcredist_cache()
    yield
    system_checks.invalidate_vcredist_cache()


@pytest.fixture
def windows(monkeypatch, tmp_path):
    """Un faux Windows 64 bits : SysWOW64 vide, dans tmp_path."""
    monkeypatch.setattr(system_checks.sys, "platform", "win32")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    (tmp_path / "SysWOW64").mkdir()
    (tmp_path / "System32").mkdir()
    return tmp_path


class TestDetection:
    def test_pure(self, tmp_path):
        assert dll_x86_presente(tmp_path, "xinput1_3") is False
        (tmp_path / "xinput1_3.dll").write_bytes(b"MZ")
        assert dll_x86_presente(tmp_path, "xinput1_3") is True

    def test_une_dll_absente_est_signalee_seule(self, windows):
        for nom in ("d3dx9_43", "d3dx9_37"):
            (windows / "SysWOW64" / f"{nom}.dll").write_bytes(b"MZ")
        assert prerequis_manquants(DLL_DIRECTX9) == ["xinput1_3"]

    def test_les_dll_64_bits_ne_comptent_pas(self, windows):
        """Le launcher est 64 bits, le jeu 32 : une DLL de System32 lui est inutile."""
        (windows / "System32" / "xinput1_3.dll").write_bytes(b"MZ")
        assert prerequis_manquants(("xinput1_3",)) == ["xinput1_3"]

    def test_windows_32_bits_sans_syswow64(self, windows):
        (windows / "SysWOW64").rmdir()
        (windows / "System32" / "xinput1_3.dll").write_bytes(b"MZ")
        assert prerequis_manquants(("xinput1_3",)) == []

    def test_le_retour_dans_la_fenetre_oublie_le_resultat(self, windows):
        """Installer le runtime puis revenir : le bandeau ne doit pas rester."""
        assert prerequis_manquants(("d3dx9_43",)) == ["d3dx9_43"]
        (windows / "SysWOW64" / "d3dx9_43.dll").write_bytes(b"MZ")
        assert prerequis_manquants(("d3dx9_43",)) == ["d3dx9_43"]   # mémorisé
        system_checks.invalidate_vcredist_cache()
        assert prerequis_manquants(("d3dx9_43",)) == []

    def test_sous_linux_wine_a_les_siennes(self, monkeypatch):
        monkeypatch.setattr(system_checks.sys, "platform", "linux")
        assert prerequis_manquants(DLL_DIRECTX9) == []


class TestDeclaration:
    def test_une_seule_page_pour_les_trois(self):
        """Le même installeur de Microsoft pose les trois DLL."""
        assert {PREREQUIS[nom][1] for nom in DLL_DIRECTX9} == {DIRECTX9_URL}
        assert DIRECTX9_URL.startswith("https://")

    def test_chaque_identifiant_a_son_verbe(self):
        assert set(DLL_DIRECTX9) <= set(VERBES_WINETRICKS)
    # Ce que le catalogue embarqué déclare : tests/test_catalogue_embarque.py.


class TestLibelles:
    def test_le_bandeau_nomme_la_dll(self):
        from src.ui.alert_banner import _NOMS_COURTS
        assert "xinput1_3.dll" in _NOMS_COURTS["xinput1_3"]

    def test_le_dialogue_nomme_la_dll(self):
        from src.ui.game_detail_handlers import nom_prerequis
        assert "d3dx9_37.dll" in nom_prerequis("d3dx9_37")

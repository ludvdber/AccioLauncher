"""Le compilateur d'effets de juin 2010 et Visual C++ 2010 (HP1, HP2).

`d3d11drv.dll` importe `d3dx11_43.dll`, `d3dcompiler_43.dll`, `msvcr100.dll` et
`msvcp100.dll`, et compile `ASSAO.fx` à chaque démarrage. Sous Wine (Bazzite,
2026-09-30), HP1 s'arrêtait sur « Error compiling effects file » puis
« Initializing Direct3D failed » : il faut les deux DLL NATIVES dans le préfixe
— chacune seule échoue —, alors que les msvcr100/msvcp100 de Wine suffisent.

`sys.platform` est simulé dans les deux sens : ces tests tournent partout.
"""
import json
import sys
from pathlib import Path

import pytest

from src.core import compat, system_checks
from src.core.system_checks import (
    DIRECTX9_URL, DLL_COMPILATEUR, PREREQUIS, VCREDIST_2010_URL, VERBES_WINETRICKS,
    dll_native_dans_le_prefixe, prerequis_manquants,
)

B = chr(92)
NATIVE = b"MZ" + bytes(0x3E) + b"This program cannot be run" + bytes(16)
INTERNE = b"MZ" + bytes(0x3E) + b"Wine builtin DLL" + bytes(16)


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


@pytest.fixture
def linux(monkeypatch):
    """Le préfixe de `conftest._linux_pret_a_jouer`, sans aucun verbe."""
    monkeypatch.setattr(sys, "platform", "linux")
    pfx = compat.prefixe("wine")
    (pfx / "winetricks.log").write_text("vcrun2022\n", encoding="utf-8")
    system_checks.invalidate_vcredist_cache()
    return pfx


def _poser_dll(pfx: Path, nom: str, contenu: bytes = NATIVE, dossier: str = "syswow64") -> None:
    systeme = pfx / "drive_c" / "windows" / dossier
    systeme.mkdir(parents=True, exist_ok=True)
    (systeme / f"{nom}.dll").write_bytes(contenu)


def _surcharger(pfx: Path, **valeurs: str) -> None:
    lignes = "".join(f'"{nom}"="{v}"\n' for nom, v in valeurs.items())
    (pfx / "user.reg").write_text(
        "WINE REGISTRY Version 2\n\n#arch=win64\n\n"
        f"[Software{B}{B}Wine{B}{B}DllOverrides] 1\n{lignes}\n", encoding="utf-8")


class TestSousWindows:
    def test_les_deux_dll_dans_syswow64(self, windows):
        assert prerequis_manquants(DLL_COMPILATEUR) == list(DLL_COMPILATEUR)
        for nom in DLL_COMPILATEUR:
            (windows / "SysWOW64" / f"{nom}.dll").write_bytes(b"MZ")
        system_checks.invalidate_vcredist_cache()
        assert prerequis_manquants(DLL_COMPILATEUR) == []

    def test_visual_cpp_2010_sans_winsxs(self, windows):
        """Ses DLL vont dans le dossier système : il faut les DEUX."""
        (windows / "SysWOW64" / "msvcr100.dll").write_bytes(b"MZ")
        assert prerequis_manquants(("vcredist2010_x86",)) == ["vcredist2010_x86"]
        (windows / "SysWOW64" / "msvcp100.dll").write_bytes(b"MZ")
        system_checks.invalidate_vcredist_cache()
        assert prerequis_manquants(("vcredist2010_x86",)) == []

    def test_le_retour_dans_la_fenetre_oublie_le_resultat(self, windows):
        assert prerequis_manquants(("d3dx11_43",)) == ["d3dx11_43"]
        (windows / "SysWOW64" / "d3dx11_43.dll").write_bytes(b"MZ")
        assert prerequis_manquants(("d3dx11_43",)) == ["d3dx11_43"]   # mémorisé
        system_checks.invalidate_vcredist_cache()
        assert prerequis_manquants(("d3dx11_43",)) == []


class TestSousLinux:
    def test_un_prefixe_neuf_n_a_pas_le_compilateur(self, linux):
        """Contrairement aux DLL de `DLL_DIRECTX9`, celles de Wine ne suffisent pas."""
        assert prerequis_manquants(DLL_COMPILATEUR) == list(DLL_COMPILATEUR)

    def test_le_journal_de_winetricks_suffit(self, linux):
        (linux / "winetricks.log").write_text("vcrun2022\nd3dx11_43\nd3dcompiler_43\n",
                                              encoding="utf-8")
        assert prerequis_manquants(DLL_COMPILATEUR) == []

    def test_visual_cpp_2010_de_wine_suffit(self, linux):
        assert prerequis_manquants(("vcredist2010_x86",)) == []

    def test_une_dll_native_posee_a_la_main_avec_sa_surcharge(self, linux):
        _poser_dll(linux, "d3dx11_43")
        _surcharger(linux, **{"*d3dx11_43": "native"})
        assert prerequis_manquants(("d3dx11_43",)) == []

    def test_sans_surcharge_wine_charge_la_sienne(self, linux):
        _poser_dll(linux, "d3dx11_43")
        assert prerequis_manquants(("d3dx11_43",)) == ["d3dx11_43"]

    def test_une_surcharge_builtin_ne_compte_pas(self, linux):
        _poser_dll(linux, "d3dcompiler_43")
        _surcharger(linux, d3dcompiler_43="builtin,native")
        assert prerequis_manquants(("d3dcompiler_43",)) == ["d3dcompiler_43"]

    def test_la_dll_interne_de_wine_ne_compte_pas(self, linux):
        """Wine range ses propres DLL au même endroit, sous le même nom."""
        _poser_dll(linux, "d3dcompiler_43", INTERNE)
        _surcharger(linux, **{"*d3dcompiler_43": "native"})
        assert prerequis_manquants(("d3dcompiler_43",)) == ["d3dcompiler_43"]

    def test_un_prefixe_32_bits_range_tout_dans_system32(self, linux):
        (linux / "system.reg").write_text("WINE REGISTRY Version 2\n\n#arch=win32\n",
                                          encoding="utf-8")
        _poser_dll(linux, "d3dx11_43", dossier="system32")
        _surcharger(linux, d3dx11_43="native,builtin")
        assert dll_native_dans_le_prefixe(linux, "d3dx11_43") is True

    def test_sans_lanceur_l_absence_de_wine_est_signalee_ailleurs(self, linux, sans_lanceur):
        assert prerequis_manquants(DLL_COMPILATEUR) == []


class TestDeclaration:
    def test_chaque_identifiant_a_son_verbe(self):
        assert set(DLL_COMPILATEUR) <= set(VERBES_WINETRICKS)
        assert VERBES_WINETRICKS["vcredist2010_x86"] == "vcrun2010"

    def test_les_pages_d_aide(self):
        assert {PREREQUIS[nom][1] for nom in DLL_COMPILATEUR} == {DIRECTX9_URL}
        assert VCREDIST_2010_URL.startswith("https://www.microsoft.com/")

    def test_le_catalogue_embarque_declare_ce_que_charge_d3d11drv(self):
        catalogue = json.loads((Path(__file__).resolve().parents[1] / "src/data/games.json")
                               .read_text(encoding="utf-8"))
        requis = {g["id"]: set(g.get("requires", [])) for g in catalogue["games"]}
        for jeu in ("hp1", "hp2"):
            assert {"d3dx11_43", "d3dcompiler_43", "vcredist2010_x86"} <= requis[jeu], jeu
        # HP5 et HP6 importent msvcr80.dll.
        for jeu in ("hp5", "hp6"):
            assert "vcredist2005_x86" in requis[jeu], jeu


class TestLibelles:
    def test_le_bandeau_nomme_la_dll_sans_dire_directx_9(self):
        from src.ui.alert_banner import _NOMS_COURTS
        assert "d3dcompiler_43.dll" in _NOMS_COURTS["d3dcompiler_43"]
        assert "DirectX 9" not in _NOMS_COURTS["d3dcompiler_43"]

    def test_le_dialogue_nomme_la_dll(self):
        from src.ui.game_detail_handlers import nom_prerequis
        assert "d3dx11_43.dll" in nom_prerequis("d3dx11_43")
        assert "2010" in nom_prerequis("vcredist2010_x86")

    def test_la_barre_de_preparation_nomme_les_verbes(self):
        from src.ui.preparateur_wine import noms_des_verbes
        assert noms_des_verbes(["d3dx11_43", "vcrun2010"]) == (
            "DirectX (d3dx11_43), Visual C++ 2010")

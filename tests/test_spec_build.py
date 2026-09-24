"""Ce que le build garde et ce qu'il écarte (`accio_launcher.spec`).

Le filtre `_keep` ne s'exerce QUE dans l'exe : toute la suite tourne depuis
les sources, où Qt trouve ses plugins dans site-packages. Un filtre trop
gourmand — `"imageformats" in chemin` au lieu d'une liste — laisserait donc
la suite verte et livrerait un launcher sans une seule image. Ces tests
tiennent les DEUX sens : ce qui est mort sort, ce qui sert reste.
"""

import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
SPEC = RACINE / "accio_launcher.spec"


def _arbre():
    return ast.parse(SPEC.read_text(encoding="utf-8"))


def _charger_filtre():
    """Extrait `_JAMAIS_ATTEINTS` et `_keep` du spec, sans l'exécuter.

    Le spec lance l'analyse PyInstaller à son niveau module : on n'en compile
    que les deux définitions utiles.
    """
    utiles = [n for n in _arbre().body
              if (isinstance(n, ast.FunctionDef) and n.name == "_keep")
              or (isinstance(n, ast.Assign)
                  and any(isinstance(c, ast.Name) and c.id == "_JAMAIS_ATTEINTS"
                          for c in n.targets))]
    assert len(utiles) == 2, "le spec a perdu _keep ou _JAMAIS_ATTEINTS"
    espace: dict = {}
    exec(compile(ast.Module(body=utiles, type_ignores=[]), str(SPEC), "exec"),
         espace)
    return espace["_keep"]


_keep = _charger_filtre()


def _garde(chemin_windows: str) -> bool:
    """La décision du filtre, vérifiée sous les DEUX conventions de séparateur."""
    windows = _keep((chemin_windows, "", "BINARY"))
    posix = _keep((chemin_windows.replace("\\", "/"), "", "BINARY"))
    assert windows == posix, f"le séparateur change la décision : {chemin_windows}"
    return windows


class TestCeQuiEstMortSort:

    @pytest.mark.parametrize("chemin", [
        r"PyQt6\Qt6\bin\opengl32sw.dll",
        r"PyQt6\Qt6\plugins\imageformats\qtiff.dll",
        r"PyQt6\Qt6\plugins\imageformats\qwebp.dll",
        r"PyQt6\Qt6\plugins\imageformats\qpdf.dll",
        r"PyQt6\Qt6\plugins\tls\qopensslbackend.dll",
        r"PyQt6\Qt6\plugins\tls\qschannelbackend.dll",
        r"PyQt6\Qt6\plugins\platforms\qoffscreen.dll",
        r"PyQt6\Qt6\plugins\generic\qtuiotouchplugin.dll",
        r"PyQt6\Qt6\translations\qtbase_fr.qm",
        r"assets\videos\hp1_video.mp4",
    ])
    def test_ecarte(self, chemin):
        assert not _garde(chemin)


class TestCeQuiSertReste:
    """La contre-épreuve : sans elle, un filtre qui retire TOUT passerait."""

    @pytest.mark.parametrize("chemin", [
        r"PyQt6\Qt6\bin\Qt6Core.dll",
        r"PyQt6\Qt6\bin\Qt6Gui.dll",
        r"PyQt6\Qt6\bin\Qt6Svg.dll",
        r"PyQt6\Qt6\bin\Qt6Network.dll",
        r"PyQt6\Qt6\bin\Qt6Multimedia.dll",
        r"PyQt6\Qt6\bin\avcodec-61.dll",
        r"PyQt6\Qt6\plugins\platforms\qwindows.dll",
        r"PyQt6\Qt6\plugins\styles\qmodernwindowsstyle.dll",
        r"PyQt6\Qt6\plugins\multimedia\ffmpegmediaplugin.dll",
        r"PyQt6\Qt6\plugins\iconengines\qsvgicon.dll",
        r"libssl-3.dll",
        r"libcrypto-3.dll",
        r"assets\backgrounds\hp1_bg.jpg",
        r"data\i18n\en.json",
    ])
    def test_garde(self, chemin):
        assert _garde(chemin)

    def test_chaque_format_d_asset_garde_son_decodeur(self):
        """Ajouter un asset .webp doit échouer ICI, pas chez l'utilisateur.

        Deux listes qu'aucun calcul ne reliait : les extensions des assets et
        les décodeurs gardés. Un .webp ajouté sans retirer `qwebp.dll` de
        `_JAMAIS_ATTEINTS` s'afficherait depuis les sources et resterait
        invisible dans l'exe. PNG et BMP sont décodés par QtGui lui-même.
        """
        decodeur = {".jpg": "qjpeg", ".jpeg": "qjpeg", ".ico": "qico",
                    ".svg": "qsvg", ".gif": "qgif", ".webp": "qwebp",
                    ".tif": "qtiff", ".tiff": "qtiff", ".tga": "qtga",
                    ".png": None, ".bmp": None}
        vus = {f.suffix.lower() for f in (RACINE / "assets").rglob("*")
               if f.is_file() and f.suffix.lower() in decodeur
               and "videos" not in f.parts}
        assert {".jpg", ".svg", ".ico"} <= vus, "le balayage des assets est vide"
        for extension in sorted(vus):
            plugin = decodeur[extension]
            if plugin:
                assert _garde(rf"PyQt6\Qt6\plugins\imageformats\{plugin}.dll"), (
                    f"des assets {extension} sont embarqués mais leur décodeur "
                    f"{plugin}.dll est écarté du build")


class TestLeBuildNeDependPasDuPoste:

    def test_brotli_est_exclu(self):
        """httpx importe brotli S'IL LE TROUVE.

        Il n'était dans l'exe que parce que py7zr, retiré du projet, restait
        installé sur le poste de build : l'exe local le portait, celui de la
        CI non.
        """
        appel = next(n for n in ast.walk(_arbre())
                     if isinstance(n, ast.Call)
                     and getattr(n.func, "id", "") == "Analysis")
        excludes = next(k.value for k in appel.keywords if k.arg == "excludes")
        assert "brotli" in ast.literal_eval(excludes)


class TestChaquePlateformeSonSeptZip:
    """Le 7-Zip de l'autre plateforme est du poids mort : 7z.exe ne tourne pas
    sous Linux, `7zzs` pas sous Windows. Et l'exe Windows doit rester ce qu'il
    était avant le portage."""

    @pytest.mark.parametrize("plateforme, garde, ecarte", [
        ("win32", [r"assets\7z\7z.exe", r"assets\7z\7z.dll", r"assets\7z\License.txt"],
         [r"assets\7z\linux\7zzs", r"assets\7z\linux\License.txt"]),
        ("linux", [r"assets\7z\linux\7zzs", r"assets\7z\linux\License.txt"],
         [r"assets\7z\7z.exe", r"assets\7z\7z.dll"]),
    ])
    def test_par_plateforme(self, monkeypatch, plateforme, garde, ecarte):
        import sys
        monkeypatch.setattr(sys, "platform", plateforme)
        for chemin in garde:
            assert _garde(chemin), f"{plateforme} doit garder {chemin}"
        for chemin in ecarte:
            assert not _garde(chemin), f"{plateforme} doit écarter {chemin}"

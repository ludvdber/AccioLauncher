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
    fonctions = {"_keep", "_qml_utile"}
    constantes = {"_JAMAIS_ATTEINTS", "_QML_GARDES", "_QML_RACINE_QTQUICK", "_DLL_QUICK_INUTILES"}
    utiles = [n for n in _arbre().body
              if (isinstance(n, ast.FunctionDef) and n.name in fonctions)
              or (isinstance(n, ast.Assign)
                  and any(isinstance(c, ast.Name) and c.id in constantes
                          for c in n.targets))]
    assert len(utiles) == len(fonctions) + len(constantes), "le spec a perdu une pièce du filtre"
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
        # Qt Quick : tout ce que le fond de l'accueil n'importe pas (2026-11-01).
        r"PyQt6\Qt6\qml\QtQuick3D\Physics\qquick3dphysicsplugin.dll",
        r"PyQt6\Qt6\qml\QtQuick\Controls\qtquickcontrols2plugin.dll",
        r"PyQt6\Qt6\qml\QtWebSockets\qmlwebsocketsplugin.dll",
        r"PyQt6\Qt6\bin\Qt6Quick3DRuntimeRender.dll",
        r"PyQt6\Qt6\bin\Qt6QuickControls2Material.dll",
        r"PyQt6\Qt6\bin\Qt6ShaderTools.dll",
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
        # Les modèles 3D des Collections sur la carte graphique (2026-10-31).
        r"PyQt6\Qt6\bin\Qt6OpenGL.dll",
        r"PyQt6\QtOpenGL.pyd",
        r"PyQt6\Qt6\bin\avcodec-61.dll",
        r"PyQt6\Qt6\plugins\platforms\qwindows.dll",
        r"PyQt6\Qt6\plugins\styles\qmodernwindowsstyle.dll",
        r"PyQt6\Qt6\plugins\multimedia\ffmpegmediaplugin.dll",
        r"PyQt6\Qt6\plugins\iconengines\qsvgicon.dll",
        r"libssl-3.dll",
        r"libcrypto-3.dll",
        r"assets\backgrounds\hp1_bg.jpg",
        r"data\i18n\en.json",
        # Le fond de l'accueil sur la carte graphique (`assets/qml/FondAccueil.qml`).
        r"assets\qml\FondAccueil.qml",
        r"PyQt6\Qt6\bin\Qt6Quick.dll",
        r"PyQt6\Qt6\bin\Qt6Qml.dll",
        r"PyQt6\Qt6\bin\Qt6QuickWidgets.dll",
        r"PyQt6\Qt6\bin\Qt6MultimediaQuick.dll",
        r"PyQt6\Qt6\qml\QtQuick\qmldir",
        r"PyQt6\Qt6\qml\QtQuick\qtquick2plugin.dll",
        r"PyQt6\Qt6\qml\QtQml\qmldir",
        r"PyQt6\Qt6\qml\QtMultimedia\quickmultimediaplugin.dll",
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
                assert _garde(f"PyQt6/Qt6/plugins/imageformats/lib{plugin}.so"), (
                    f"des assets {extension} sont embarqués mais leur décodeur "
                    f"lib{plugin}.so est écarté de l'AppImage")


class TestLesGreffonsLinux:
    """Les mêmes deux sens pour l'AppImage : ce qui est mort sort, ce qui sert
    reste. Une AppImage sans `libqxcb` ne démarre pas en mode Jeu (XWayland) ;
    sans `libqwayland` ni `libxdg-shell`, pas sous KDE Wayland."""

    @pytest.mark.parametrize("chemin", [
        "PyQt6/Qt6/plugins/platformthemes/libqgtk3.so",
        "PyQt6/Qt6/plugins/platforms/libqoffscreen.so",
        "PyQt6/Qt6/plugins/platforms/libqminimal.so",
        "PyQt6/Qt6/plugins/platforms/libqeglfs.so",
        "PyQt6/Qt6/plugins/platforms/libqlinuxfb.so",
        "PyQt6/Qt6/plugins/platforms/libqvnc.so",
        "PyQt6/Qt6/plugins/imageformats/libqwebp.so",
        "PyQt6/Qt6/plugins/imageformats/libqpdf.so",
        "PyQt6/Qt6/plugins/tls/libqopensslbackend.so",
        "PyQt6/Qt6/plugins/networkinformation/libqnetworkmanager.so",
        "PyQt6/Qt6/plugins/generic/libqevdevmouseplugin.so",
    ])
    def test_ecarte(self, chemin):
        assert not _garde(chemin)

    @pytest.mark.parametrize("chemin", [
        "PyQt6/Qt6/plugins/platforms/libqxcb.so",
        "PyQt6/Qt6/plugins/platforms/libqwayland.so",
        "PyQt6/Qt6/plugins/wayland-shell-integration/libxdg-shell.so",
        "PyQt6/Qt6/plugins/wayland-decoration-client/libbradient.so",
        "PyQt6/Qt6/plugins/wayland-graphics-integration-client/libqt-plugin-wayland-egl.so",
        "PyQt6/Qt6/plugins/xcbglintegrations/libqxcb-glx-integration.so",
        # Touches mortes et composition : les accents d'un chemin de dossier.
        "PyQt6/Qt6/plugins/platforminputcontexts/libcomposeplatforminputcontextplugin.so",
        "PyQt6/Qt6/plugins/platforminputcontexts/libibusplatforminputcontextplugin.so",
        "PyQt6/Qt6/plugins/platformthemes/libqxdgdesktopportal.so",
        "PyQt6/Qt6/plugins/multimedia/libffmpegmediaplugin.so",
        "PyQt6/Qt6/plugins/iconengines/libqsvgicon.so",
        "PyQt6/Qt6/lib/libQt6XcbQpa.so.6",
        "PyQt6/Qt6/lib/libQt6WaylandClient.so.6",
    ])
    def test_garde(self, chemin):
        assert _garde(chemin)


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

    def test_linux_epure_ses_binaires_windows_inchange(self):
        """Le Python d'`actions/setup-python` livre libpython AVEC ses symboles
        de débogage (33 Mo, 7 une fois épurée) : sans `strip`, l'AppImage de la
        release pesait 77 Mo, contre 62 construite depuis un Python de
        distribution. L'exe Windows, lui, ne change pas."""
        branche = next(n for n in _arbre().body
                       if isinstance(n, ast.If)
                       and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "EXE"
                               for c in ast.walk(n)))

        def strip(noeuds, nom):
            appels = [c for n in noeuds for c in ast.walk(n)
                      if isinstance(c, ast.Call) and getattr(c.func, "id", "") == nom]
            assert appels, f"aucun appel {nom}"
            return {ast.literal_eval(k.value) for c in appels for k in c.keywords
                    if k.arg == "strip"}

        assert "linux" in ast.unparse(branche.test)
        assert strip(branche.body, "EXE") == {True}
        assert strip(branche.body, "COLLECT") == {True}
        assert strip(branche.orelse, "EXE") == {False}


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

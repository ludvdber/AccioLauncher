"""Le build Linux : AppImage, `build.sh`, et le workflow de release commun.

Comme pour l'exe Windows, rien de tout cela ne s'exerce depuis les sources :
la suite tourne sans jamais construire d'AppImage. Un défaut ici ne se
verrait qu'une fois la release publiée — chez quelqu'un dont le launcher ne
démarre pas. Ces tests tiennent donc ce qui RELIE les morceaux entre eux :
l'identifiant de bureau, les noms de fichiers que l'auto-mise à jour
reconnaît, l'élagage des bibliothèques, et le brouillon unique.
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
LINUX = RACINE / "build" / "linux"


def _module(nom: str):
    spec = importlib.util.spec_from_file_location(f"_accio_build_{nom}", LINUX / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dependances = _module("dependances")
appimage = _module("appimage")


# ─────────────────────────── Élagage des bibliothèques ───────────────────────────

def _lecteur(besoins: dict[str, list[str]]):
    """Un faux `objdump` : les NEEDED de chaque SOURCE."""
    return lambda source: besoins.get(source, [])


class TestElagage:
    """Une bibliothèque de la machine de build n'est gardée que si quelque
    chose y MÈNE : aucune liste de noms à tenir, c'est le calcul qui décide."""

    BINAIRES = [
        ("PyQt6/QtGui.abi3.so", "s/QtGui", "EXTENSION"),
        ("PyQt6/Qt6/lib/libQt6Gui.so.6", "s/libQt6Gui", "BINARY"),
        ("PyQt6/Qt6/plugins/platforms/libqxcb.so", "s/qxcb", "BINARY"),
        ("libQt6Gui.so.6", "PyQt6/Qt6/lib/libQt6Gui.so.6", "SYMLINK"),
        ("libpython3.14.so.1.0", "s/libpython", "BINARY"),
        ("libxkbcommon.so.0", "s/xkb", "BINARY"),
        ("libxcb-cursor.so.0", "s/xcbcursor", "BINARY"),
        ("libgtk-3.so.0", "s/gtk", "BINARY"),       # plus personne n'y mène
        ("libcairo.so.2", "s/cairo", "BINARY"),     # ... ni à ce qu'elle tirait
        ("libstdc++.so.6", "s/stdcxx", "BINARY"),   # fournie par la machine
        ("libz.so.1", "s/z", "BINARY"),
    ]
    BESOINS = {
        "s/QtGui": ["libQt6Gui.so.6", "libstdc++.so.6"],
        "s/libQt6Gui": ["libxkbcommon.so.0", "libfontconfig.so.1", "libz.so.1"],
        "s/qxcb": ["libQt6Gui.so.6", "libxcb-cursor.so.0"],
        "s/gtk": ["libcairo.so.2"],
    }

    def _elaguer(self):
        gardes, retires = dependances.elaguer(self.BINAIRES, _lecteur(self.BESOINS))
        return {e[0] for e in gardes}, {e[0] for e in retires}

    def test_ce_qui_sert_reste(self):
        gardes, _ = self._elaguer()
        assert {"libxkbcommon.so.0", "libxcb-cursor.so.0", "PyQt6/Qt6/lib/libQt6Gui.so.6",
                "PyQt6/Qt6/plugins/platforms/libqxcb.so"} <= gardes

    def test_la_pile_gtk_part_avec_son_greffon(self):
        _, retires = self._elaguer()
        assert {"libgtk-3.so.0", "libcairo.so.2"} <= retires

    def test_ce_que_la_machine_fournit_part(self):
        """`libstdc++` de 22.04 passerait AVANT celle de la machine, dont les
        pilotes Mesa ont besoin."""
        _, retires = self._elaguer()
        assert {"libstdc++.so.6", "libz.so.1"} <= retires

    def test_libpython_et_les_liens_restent(self):
        """Le chargeur de PyInstaller ouvre libpython lui-même : aucun NEEDED
        n'y mène, et elle est pourtant indispensable."""
        gardes, _ = self._elaguer()
        assert "libpython3.14.so.1.0" in gardes
        assert "libQt6Gui.so.6" in gardes

    def test_rien_de_pyqt_n_est_elague(self):
        """Élaguer les greffons est le rôle de `_keep` (spec) : ici, seules les
        bibliothèques de la MACHINE de build sont en jeu."""
        binaires = [("PyQt6/Qt6/lib/libQt6Quick.so.6", "s/quick", "BINARY")]
        gardes, retires = dependances.elaguer(binaires, _lecteur({}))
        assert gardes == binaires and retires == []

    def test_la_liste_d_exclusion_porte_les_pieges_connus(self):
        for nom in ("libstdc++.so.6", "libgcc_s.so.1", "libfontconfig.so.1",
                    "libfreetype.so.6", "libGL.so.1", "libEGL.so.1", "libX11.so.6",
                    "libwayland-client.so.0", "libwayland-cursor.so.0"):
            assert nom in dependances.FOURNI_PAR_LA_MACHINE


class TestVerificationDuDossier:
    """Avant d'emballer : une dépendance absente, c'est « Could not load the Qt
    platform plugin xcb » chez quelqu'un d'autre."""

    @staticmethod
    def _elf(chemin: Path) -> Path:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"\x7fELF" + bytes(12))
        return chemin

    def test_un_dossier_sain(self, tmp_path):
        qxcb = self._elf(tmp_path / "_internal/PyQt6/Qt6/plugins/platforms/libqxcb.so")
        self._elf(tmp_path / "_internal/libxcb-cursor.so.0")
        lire = _lecteur({str(qxcb): ["libxcb-cursor.so.0", "libc.so.6", "libX11.so.6"]})
        assert dependances.verifier_dossier(tmp_path, lire) == []

    def test_une_dependance_manquante(self, tmp_path):
        qxcb = self._elf(tmp_path / "_internal/PyQt6/Qt6/plugins/platforms/libqxcb.so")
        lire = _lecteur({str(qxcb): ["libxcb-cursor.so.0"]})
        defauts = dependances.verifier_dossier(tmp_path, lire)
        assert len(defauts) == 1 and "libxcb-cursor.so.0" in defauts[0]
        assert "libqxcb.so" in defauts[0]

    def test_une_bibliotheque_de_la_machine_embarquee(self, tmp_path):
        self._elf(tmp_path / "_internal/libstdc++.so.6")
        defauts = dependances.verifier_dossier(tmp_path, _lecteur({}))
        assert defauts and "libstdc++.so.6" in defauts[0]

    def test_le_dossier_sain_a_bien_ete_lu(self, tmp_path):
        """Contre-épreuve du cas sain : sans elle, un lecteur jamais appelé
        (ou appelé avec la mauvaise clé) le ferait passer à vide."""
        qxcb = self._elf(tmp_path / "libqxcb.so")
        lus = []
        dependances.verifier_dossier(tmp_path, lambda p: lus.append(p) or [])
        assert lus == [str(qxcb)]

    def test_un_fichier_qui_n_est_pas_elf_n_est_pas_lu(self, tmp_path):
        (tmp_path / "games.json").write_text("{}")
        lus = []
        dependances.verifier_dossier(tmp_path, lambda p: lus.append(p) or [])
        assert lus == []


# ─────────────────────────── L'AppImage ───────────────────────────

BUREAU = LINUX / f"{appimage.IDENTIFIANT}.desktop"


def _entrees_bureau() -> dict[str, str]:
    texte = BUREAU.read_text(encoding="utf-8")
    return dict(ligne.split("=", 1) for ligne in texte.splitlines() if "=" in ligne)


class TestIdentiteDeBureau:
    """Sous Wayland, c'est l'`app_id` qui relie la fenêtre à son `.desktop`, et
    le `.desktop` à son icône : trois noms qui doivent n'en faire qu'un."""

    def test_un_seul_identifiant(self):
        import main
        assert appimage.IDENTIFIANT == main.DESKTOP_ID
        assert BUREAU.is_file()
        assert _entrees_bureau()["Icon"] == main.DESKTOP_ID

    def test_la_classe_x11_est_le_nom_de_l_executable(self):
        """Sous X11, Qt prend le nom de l'exécutable pour `WM_CLASS` (relevé
        sous Xvfb sur l'AppImage : « AccioLauncher », « AccioLauncher »)."""
        spec = (RACINE / "accio_launcher.spec").read_text(encoding="utf-8")
        assert 'name="AccioLauncher"' in spec
        assert _entrees_bureau()["StartupWMClass"] == "AccioLauncher"

    def test_un_jeu_sans_terminal(self):
        entrees = _entrees_bureau()
        assert entrees["Type"] == "Application" and entrees["Terminal"] == "false"
        assert "Game" in entrees["Categories"].split(";")

    def test_traduit_dans_les_langues_du_launcher(self):
        entrees = _entrees_bureau()
        assert "Comment[fr]" in entrees and "Comment[es]" in entrees


class TestNomDuFichierPublie:
    def test_l_auto_mise_a_jour_le_reconnait(self):
        """Le nom que produit le build est celui que le vérificateur choisit
        sur une machine x86_64 — et pas sur une machine ARM."""
        from src.core.updater import asset_de_la_plateforme
        release = [{"name": "AccioLauncher.exe", "browser_download_url": "https://g/e"},
                   {"name": appimage.SORTIE, "browser_download_url": "https://g/a"},
                   {"name": appimage.SORTIE + ".sigstore.json",
                    "browser_download_url": "https://g/s"}]
        assert asset_de_la_plateforme(release, "linux", "x86_64")["name"] == appimage.SORTIE
        assert asset_de_la_plateforme(release, "linux", "aarch64") is None

    def test_sans_numero_de_version(self):
        """L'auto-mise à jour remplace le fichier sur place : un nom portant
        la version mentirait dès la première mise à jour."""
        assert not re.search(r"\d+\.\d+", appimage.SORTIE)


class TestPointDEntree:
    def test_apprun_lance_le_dossier_gele(self):
        texte = (LINUX / "AppRun").read_bytes()
        assert texte.startswith(b"#!/bin/sh\n")
        assert b"\r" not in texte, "un shebang suivi de CRLF ne s'exécute pas"
        assert b'exec "$ICI/usr/lib/AccioLauncher/AccioLauncher" "$@"' in texte

    @pytest.mark.skipif(sys.platform == "win32", reason="bit exécutable POSIX")
    def test_executables(self):
        import os
        for fichier in (LINUX / "AppRun", RACINE / "build.sh"):
            assert os.access(fichier, os.X_OK), fichier


class TestOutilsEpingles:
    """appimagetool et le runtime sont épinglés par VERSION et par EMPREINTE,
    comme les actions de la CI : un build ne change pas parce qu'un
    « continuous » a bougé en amont."""

    @pytest.mark.parametrize("url, sha", [appimage.APPIMAGETOOL, appimage.RUNTIME])
    def test_version_figee(self, url, sha):
        assert url.startswith("https://github.com/AppImage/")
        assert "/continuous/" not in url
        assert re.fullmatch(r"[0-9a-f]{64}", sha)

    def test_le_cache_evite_le_telechargement(self, tmp_path, monkeypatch):
        contenu = b"outil"
        sha = appimage.hashlib.sha256(contenu).hexdigest()
        cible = tmp_path / "1.0" / "outil"
        cible.parent.mkdir()
        cible.write_bytes(contenu)
        monkeypatch.setattr(appimage.urllib.request, "urlopen",
                            lambda *a, **k: pytest.fail("téléchargé malgré le cache"))
        assert appimage.outil("https://x/download/1.0/outil", sha, tmp_path) == cible

    def test_une_empreinte_fausse_est_refusee(self, tmp_path, monkeypatch):
        import io

        class _Reponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(appimage.urllib.request, "urlopen",
                            lambda *a, **k: _Reponse(b"remplace en route"))
        with pytest.raises(SystemExit, match="Empreinte inattendue"):
            appimage.outil("https://x/download/1.0/outil", "0" * 64, tmp_path)
        assert not list((tmp_path / "1.0").iterdir()), "un fichier refusé est resté"


class TestIcones:
    def test_chaque_taille_dessinee_telle_quelle(self, tmp_path):
        """Aucune taille recalculée : l'.ico en porte sept, ajustées à la main."""
        pytest.importorskip("PIL")
        from PIL import Image
        (tmp_path / "AppDir").mkdir()
        appimage.icones(RACINE / "assets" / "accio_launcher.ico", tmp_path / "AppDir")
        hicolor = tmp_path / "AppDir/usr/share/icons/hicolor"
        tailles = sorted(int(d.name.split("x")[0]) for d in hicolor.iterdir())
        assert tailles == [16, 24, 32, 48, 64, 128, 256]
        with Image.open(tmp_path / "AppDir" / f"{appimage.IDENTIFIANT}.png") as racine:
            assert racine.size == (256, 256)

    def test_les_documents_de_licence_existent(self):
        for nom in appimage.DOCUMENTS:
            assert (RACINE / nom).is_file(), nom


# ─────────────────────────── build.sh ───────────────────────────

class TestBuildSh:
    TEXTE = (RACINE / "build.sh").read_bytes().decode("utf-8")

    def test_fins_de_ligne_unix(self):
        assert "\r" not in self.TEXTE

    def test_s_arrete_au_premier_echec(self):
        assert self.TEXTE.startswith("#!/bin/sh\n")
        assert "\nset -eu\n" in self.TEXTE

    def test_les_six_etapes_dans_l_ordre(self):
        """Le même chemin que build.bat, plus l'AppImage."""
        etapes = re.findall(r'echo "\[(\d)/6\] ([^"]+)"', self.TEXTE)
        assert [int(n) for n, _ in etapes] == [1, 2, 3, 4, 5, 6]
        ordre = [self.TEXTE.index(m) for m in (
            "build/create_icon.py", "ruff check", "pytest", "tools/audit_geometrie.py",
            "PyInstaller accio_launcher.spec", "build/linux/appimage.py")]
        assert ordre == sorted(ordre)

    def test_gitattributes_garde_les_fins_de_ligne(self):
        attributs = (RACINE / ".gitattributes").read_text(encoding="utf-8")
        assert "*.sh   text eol=lf" in attributs
        assert "build/linux/AppRun  text eol=lf" in attributs


# ─────────────────────────── Workflow de release ───────────────────────────

RELEASE = (RACINE / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def _job(nom: str) -> str:
    """Le texte d'un job, jusqu'au suivant."""
    m = re.search(rf"^  {nom}:\n(.*?)(?=^  [a-z_-]+:\n|\Z)", RELEASE, re.MULTILINE | re.DOTALL)
    assert m, f"job {nom} absent"
    return m.group(1)


class TestWorkflowDeRelease:
    def test_deux_builds_un_seul_brouillon(self):
        """Tout ou rien : le brouillon attend les DEUX builds."""
        assert "needs: [version, windows, linux]" in _job("brouillon")
        assert "gh release create" in _job("brouillon")
        assert "gh release create" not in _job("windows") + _job("linux")

    def test_rien_n_est_publie_automatiquement(self):
        assert "--draft" in _job("brouillon")
        # Un seul déclencheur, à la main : pas de `push`, `release` ni `schedule`.
        declencheurs = re.search(r"^on:\n(.*?)^permissions:", RELEASE,
                                 re.MULTILINE | re.DOTALL).group(1)
        assert re.findall(r"^  (\w+):", declencheurs, re.MULTILINE) == ["workflow_dispatch"]

    def test_les_quatre_fichiers_dans_le_brouillon(self):
        brouillon = _job("brouillon")
        for fichier in ('"$exe"', '"$exe.sigstore.json"', '"$appimage"',
                        '"$appimage.sigstore.json"'):
            assert fichier in brouillon
        assert "dist/AccioLauncher-x86_64.AppImage" in brouillon
        assert appimage.SORTIE in _job("linux")

    def test_chaque_binaire_a_son_attestation(self):
        assert "subject-path: dist/AccioLauncher.exe" in _job("windows")
        assert f"subject-path: dist/{appimage.SORTIE}" in _job("linux")

    def test_la_glibc_la_plus_ancienne_raisonnable(self):
        """Une AppImage exige la glibc de SA machine de build."""
        assert "runs-on: ubuntu-22.04" in _job("linux")

    def test_le_build_linux_passe_par_build_sh(self):
        assert "run: ./build.sh" in _job("linux")
        assert "libxcb-cursor0" in _job("linux")

    def test_windows_passe_toujours_par_build_bat(self):
        assert "cmd /c build.bat" in _job("windows")
        assert "runs-on: windows-latest" in _job("windows")

    def test_toutes_les_actions_epinglees_par_empreinte(self):
        for ligne in re.findall(r"uses:\s*(\S+)", RELEASE):
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ligne), ligne

    def test_aucune_expression_dans_un_script(self):
        """Une valeur interpolée dans `run:` est une injection de script en
        puissance : tout passe par `env:`."""
        blocs = re.findall(r"run: \|\n((?:\s{10,}.*\n)+)", RELEASE)
        blocs += re.findall(r"run: (?!\|)(.*)", RELEASE)
        assert blocs
        for bloc in blocs:
            assert "${{" not in bloc, bloc

    def test_les_notes_portent_les_deux_empreintes(self):
        notes = (RACINE / ".github" / "release-notes.md").read_text(encoding="utf-8")
        for marque in ("{SHA256}", "{SHA256_LINUX}", "{TAG}"):
            assert marque in notes
        assert "{SHA256_LINUX}" in _job("brouillon")
        # Après le trait : la boîte de mise à jour du launcher ne l'affiche pas.
        affiche, _, reste = notes.partition("\n---\n")
        assert "AppImage" not in affiche and "AppImage" in reste

"""Le Flatpak d'Accio Launcher (build/flatpak/) : ce qui relie les morceaux.

Le manifeste emballe le MÊME dossier gelé que l'AppImage ; les jeux, eux, se
lancent par umu-run ou wine de l'HÔTE, à travers deux scripts : le point
d'entrée `accio-launcher` (qui pose les relais) et le relais `accio-hote`
(qui appelle `flatpak-spawn --host`). Rien de cela ne s'exerce depuis les
sources : ces tests tiennent les permissions (les plus étroites qui marchent,
relevées le 2026-11-18, docs/linux/FLATPAK.md), l'identifiant, et le
comportement du relais avec un FAUX flatpak-spawn.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
FLATPAK = RACINE / "build" / "flatpak"
MANIFESTE = FLATPAK / "be.acciolauncher.AccioLauncher.json"
POSIX = pytest.mark.skipif(sys.platform == "win32", reason="scripts /bin/sh : Linux")


def _manifeste() -> dict:
    return json.loads(MANIFESTE.read_text(encoding="utf-8"))


def _preparer():
    spec = importlib.util.spec_from_file_location("_accio_flatpak_preparer", FLATPAK / "preparer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestIdentite:
    def test_l_identifiant_est_celui_du_bureau_et_de_wayland(self):
        """L'id Flatpak = le `.desktop` = l'`app_id` Wayland (`main.DESKTOP_ID`)."""
        import main
        assert _manifeste()["id"] == main.DESKTOP_ID
        assert (RACINE / "build" / "linux" / f"{main.DESKTOP_ID}.desktop").is_file()

    def test_metainfo(self):
        racine = ET.parse(FLATPAK / "be.acciolauncher.AccioLauncher.metainfo.xml").getroot()
        assert racine.findtext("id") == _manifeste()["id"]
        assert racine.findtext("project_license") == "GPL-3.0-only"
        assert racine.find("launchable").text == "be.acciolauncher.AccioLauncher.desktop"
        # La version n'est PAS écrite ici : preparer.py la prend dans pyproject.toml.
        assert racine.find("releases/release").get("version") == "@VERSION@"

    def test_runtime_freedesktop_sans_python_ni_qt_du_runtime(self):
        """Le dossier gelé porte son Python 3.15 et son Qt : le runtime n'a que
        Python 3.13 (relevé : 3.13.18 dans 25.08), et le projet exige 3.15."""
        m = _manifeste()
        assert (m["runtime"], m["runtime-version"]) == ("org.freedesktop.Platform", "25.08")
        assert m["command"] == "accio-launcher"


class TestPermissions:
    """Les permissions les plus étroites qui marchent. Une permission en plus se
    justifie dans docs/linux/FLATPAK.md, ou ce test la refuse."""

    ATTENDUES = {
        "--share=ipc", "--share=network",
        "--socket=wayland", "--socket=fallback-x11", "--socket=pulseaudio",
        "--device=all",                                          # manette : /dev/input, hidraw
        "--filesystem=~/Games/AccioLauncher:create",             # jeux, _Launcher, préfixes
        "--filesystem=xdg-data/Steam/compatibilitytools.d:ro",   # GE-Proton, lecture seule
        "--filesystem=xdg-data/umu:ro",                          # runtime d'umu installé ?
        "--filesystem=xdg-pictures/Accio Launcher:create",       # captures
        "--filesystem=xdg-music/Accio:create",                   # musiques exportées
        "--filesystem=xdg-run/discord-ipc-0",                    # Discord natif
        "--filesystem=xdg-run/app/com.discordapp.Discord:create",  # Discord Flatpak
        "--talk-name=org.freedesktop.Flatpak",                   # flatpak-spawn --host
        "--talk-name=org.kde.StatusNotifierWatcher",             # zone de notification
    }

    def test_exactement_celles_ci(self):
        assert set(_manifeste()["finish-args"]) == self.ATTENDUES

    def test_jamais_tout_le_dossier_personnel_ni_le_systeme(self):
        for permission in _manifeste()["finish-args"]:
            assert permission not in {"--filesystem=home", "--filesystem=host",
                                      "--filesystem=host-os", "--filesystem=~/Games"}
            assert not permission.startswith("--filesystem=xdg-data/Steam:")


class TestManifeste:
    def test_installe_les_deux_scripts_et_corrige_exec(self):
        module = _manifeste()["modules"][0]
        commandes = "\n".join(module["build-commands"])
        assert "/app/bin/accio-launcher" in commandes and "/app/bin/accio-hote" in commandes
        assert "--set-key=Exec --set-value=accio-launcher" in commandes
        chemins = {s["path"] for s in module["sources"]}
        assert chemins == {"accio-launcher", "accio-hote", "AccioLauncher-linux-x86_64.tar.gz"}
        for chemin in chemins - {"AccioLauncher-linux-x86_64.tar.gz"}:
            assert (FLATPAK / chemin).is_file()

    @POSIX
    def test_scripts_shell_valides(self):
        for nom in ("accio-launcher", "accio-hote", "construire.sh"):
            assert subprocess.run(["/bin/sh", "-n", str(FLATPAK / nom)], check=False).returncode == 0
            if nom != "construire.sh":
                assert os.access(FLATPAK / nom, os.X_OK), nom

    def test_l_archive_n_est_pas_suivie(self):
        texte = (RACINE / ".gitignore").read_text(encoding="utf-8")
        assert "build/flatpak/AccioLauncher-linux-x86_64.tar.gz" in texte
        assert "build/flatpak-travail/" in texte


@POSIX
class TestRelaisVersLHote:
    """`accio-hote` avec un FAUX flatpak-spawn qui écrit ses arguments."""

    @pytest.fixture
    def relais(self, tmp_path):
        outils = tmp_path / "outils"
        outils.mkdir()
        faux = outils / "flatpak-spawn"
        faux.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done > "$SORTIE"\n'
                        'echo "LD=${LD_LIBRARY_PATH:-absent}" >> "$SORTIE"\nexit 7\n', encoding="utf-8")
        faux.chmod(0o755)
        dossier_relais = tmp_path / "accio-hote"
        dossier_relais.mkdir()
        lien = dossier_relais / "umu-run"
        lien.symlink_to(FLATPAK / "accio-hote")
        sortie = tmp_path / "sortie.txt"
        env = {"PATH": f"{outils}:/usr/bin:/bin", "SORTIE": str(sortie), "HOME": str(tmp_path),
               "ACCIO_RELAIS_HOTE": str(dossier_relais)}
        return lien, env, sortie, tmp_path

    def _lancer(self, relais, extra):
        lien, env, sortie, dossier = relais
        code = subprocess.run([str(lien), "/jeux/HP1/System/HP.exe", "-arg avec espace"],
                              env={**env, **extra}, cwd=dossier, check=False).returncode
        return code, sortie.read_text(encoding="utf-8").splitlines()

    def test_appelle_l_hote_sous_son_nom_dans_le_dossier_courant(self, relais):
        code, lignes = self._lancer(relais, {})
        assert code == 7                                    # code de retour relayé
        assert lignes[0] == "--host"
        assert lignes[1] == f"--directory={relais[3]}"
        assert lignes[-4:-1] == ["umu-run", "/jeux/HP1/System/HP.exe", "-arg avec espace"]
        assert "--watch-bus" not in lignes                 # le jeu survit au launcher, comme l'AppImage

    def test_transmet_les_variables_des_jeux_et_rien_d_autre(self, relais):
        _, lignes = self._lancer(relais, {
            "WINEPREFIX": "/p", "GAMEID": "umu-default", "ACCIO_LAUNCH": "1",
            "DXVK_CONFIG": "d3d9.ffUbershaderVS = False", "WINEDLLOVERRIDES": "winmm=n,b",
            "PROTONPATH": "/proton", "UMU_RUNTIME_UPDATE": "0",
            "SECRET": "non", "LD_LIBRARY_PATH": "/app/lib/AccioLauncher/_internal"})
        envs = {ligne for ligne in lignes if ligne.startswith("--env=")}
        assert envs == {"--env=WINEPREFIX=/p", "--env=GAMEID=umu-default", "--env=ACCIO_LAUNCH=1",
                        "--env=DXVK_CONFIG=d3d9.ffUbershaderVS = False",
                        "--env=WINEDLLOVERRIDES=winmm=n,b", "--env=PROTONPATH=/proton",
                        "--env=UMU_RUNTIME_UPDATE=0"}

    def test_retire_le_ld_library_path_du_dossier_gele(self, relais):
        """Hérité, flatpak-spawn chargeait la GLib de PyInstaller : « undefined
        symbol: g_sort_array », code 127 (essai du 2026-11-18)."""
        _, lignes = self._lancer(relais, {"LD_LIBRARY_PATH": "/app/lib/AccioLauncher/_internal"})
        assert lignes[-1] == "LD=absent"

    def test_wine_qui_designe_un_relais_devient_son_nom(self, relais):
        """`compat.environnement` pose WINE = chemin du relais pour winetricks :
        l'hôte ne connaît pas ce chemin, il retrouve wine par son nom."""
        _, lignes = self._lancer(relais, {"WINE": f"{relais[1]['ACCIO_RELAIS_HOTE']}/wine"})
        assert "--env=WINE=wine" in lignes


class TestArchive:
    def test_reproductible_et_complete(self, tmp_path):
        """Deux passes, même empreinte ; dossier gelé, .desktop, icônes, licences."""
        pytest.importorskip("PIL")
        preparer = _preparer()
        gele = tmp_path / "AccioLauncher"
        (gele / "_internal").mkdir(parents=True)
        (gele / "AccioLauncher").write_bytes(b"\x7fELF")
        (gele / "AccioLauncher").chmod(0o755)
        (gele / "_internal" / "a.so").write_bytes(b"x")
        un, deux = tmp_path / "1.tar.gz", tmp_path / "2.tar.gz"
        assert preparer.ecrire(gele, un) == preparer.ecrire(gele, deux)
        with tarfile.open(un) as tar:
            noms = set(tar.getnames())
            if sys.platform != "win32":
                assert tar.getmember("AccioLauncher/AccioLauncher").mode == 0o755
        assert "share/applications/be.acciolauncher.AccioLauncher.desktop" in noms
        assert "share/icons/hicolor/256x256/apps/be.acciolauncher.AccioLauncher.png" in noms
        assert "share/doc/accio-launcher/LICENSE" in noms
        with tarfile.open(un) as tar:
            meta = tar.extractfile("share/metainfo/be.acciolauncher.AccioLauncher.metainfo.xml").read()
        import tomllib
        version = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        release = ET.fromstring(meta).find("releases/release")
        assert release.get("version") == version
        assert len(release.get("date")) == 10 and "@" not in meta.decode("utf-8")

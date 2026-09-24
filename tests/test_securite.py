"""Ce que Bandit vérifie en CI (`security.yml`), gardé aussi dans la suite locale.

`build.bat` ne lance pas Bandit : sans ces tests, une régression ne se verrait
qu'après le push. Ils gardent surtout ce que la configuration de Bandit
AFFIRME — `.bandit` écarte deux règles pour de bonnes raisons, et ces raisons
doivent rester vraies :

- aucun programme n'est lancé par son seul nom (B607). Sous Windows, il serait
  cherché d'abord dans le dossier de l'exe appelant, donc là où l'utilisateur
  a enregistré AccioLauncher.exe — souvent Téléchargements ;
- `random` ne sert qu'aux effets visuels (B311, écarté globalement) ;
- aucune exception n'est avalée sans trace (B110).
"""

import ast
import configparser
import sys
from pathlib import Path

import pytest

import src.core.self_update as self_update
from src.core import extractors
from src.core.win_utils import commande_systeme

_RACINE = Path(__file__).resolve().parents[1]
_SOURCES = [*(_RACINE / "src").rglob("*.py"), *(_RACINE / "tools").rglob("*.py"),
            *(_RACINE / "build").glob("*.py"), _RACINE / "main.py"]
_APPELS_PROCESSUS = {"run", "Popen", "call", "check_call", "check_output"}


def _arbres():
    for fichier in _SOURCES:
        yield fichier.relative_to(_RACINE).as_posix(), ast.parse(
            fichier.read_text(encoding="utf-8"))


class TestAucunProgrammeLanceParSonSeulNom:
    def test_balayage_du_code(self):
        """`subprocess.run(["tasklist", …])` : le nom seul, sans chemin."""
        fautifs = []
        for nom, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if not (isinstance(noeud, ast.Call)
                        and isinstance(noeud.func, ast.Attribute)
                        and noeud.func.attr in _APPELS_PROCESSUS
                        and isinstance(noeud.func.value, ast.Name)
                        and noeud.func.value.id == "subprocess"
                        and noeud.args
                        and isinstance(noeud.args[0], ast.List)
                        and noeud.args[0].elts):
                    continue
                premier = noeud.args[0].elts[0]
                if (isinstance(premier, ast.Constant) and isinstance(premier.value, str)
                        and "/" not in premier.value and "\\" not in premier.value):
                    fautifs.append(f"{nom}:{noeud.lineno} « {premier.value} »")
        assert not fautifs, (
            "programme lancé par son seul nom — passer par "
            f"win_utils.commande_systeme : {fautifs}")

    @pytest.mark.skipif(sys.platform != "win32", reason="System32 : Windows uniquement")
    @pytest.mark.parametrize("programme", ["tasklist.exe", "cmd.exe", "find.exe", "PING.EXE"])
    def test_chemin_absolu_et_reel(self, programme):
        chemin = Path(commande_systeme(programme))
        assert chemin.is_absolute()
        assert chemin.is_file(), f"{chemin} n'existe pas"
        assert chemin.parent.name.lower() == "system32"

    @pytest.mark.skipif(sys.platform != "win32", reason="tasklist : Windows uniquement")
    def test_la_detection_d_un_jeu_marche_toujours(self):
        """Le vrai `tasklist.exe`, appelé par son chemin : il voit bien le
        processus qui fait tourner cette suite, et pas un nom inventé."""
        from src.ui.process_monitor import ProcessMonitor
        assert ProcessMonitor._is_exe_running(Path(sys.executable).name)
        assert not ProcessMonitor._is_exe_running("accio_nexiste_pas_4242.exe")

    def test_hors_windows_le_nom_est_rendu_tel_quel(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert commande_systeme("tasklist.exe") == "tasklist.exe"


class TestLeScriptDeRelance:
    """Le .bat de relance appelait `tasklist`, `find` et `ping` par leur nom :
    cmd les cherche dans le dossier courant avant System32."""

    @pytest.mark.skipif(sys.platform != "win32", reason=".bat Windows uniquement")
    def test_outils_par_chemin_systeme(self, tmp_path, monkeypatch):
        import os

        capture: dict = {}
        bat = tmp_path / "t.bat"

        def faux_popen(args, **kwargs):
            capture["args"] = args
            capture["env"] = kwargs.get("env")
            capture["bat"] = bat.read_text(encoding="ascii")
            return object()

        monkeypatch.setattr(self_update.subprocess, "Popen", faux_popen)
        monkeypatch.setattr(self_update.tempfile, "mkstemp",
                            lambda **kw: (os.open(str(bat), os.O_RDWR | os.O_CREAT), str(bat)))
        assert self_update._spawn_after_exit_bat("echo x\r\n", prefix="t_") is True

        assert Path(capture["args"][0]).is_absolute(), "cmd.exe par son seul nom"
        for outil in ("tasklist.exe", "find.exe", "PING.EXE"):
            assert f'"%ACCIO_SYS%\\{outil}"' in capture["bat"], outil
        assert Path(capture["env"]["ACCIO_SYS"]).is_dir()


class TestSeptZip:
    def test_hors_windows_un_chemin_absolu_du_path(self, monkeypatch, tmp_path):
        """Sans 7-Zip embarqué : l'officiel (`7zz`) d'abord, par chemin absolu."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(extractors, "Path", _PathSansEmbarque)
        monkeypatch.setattr(extractors.shutil, "which", lambda nom: f"/usr/bin/{nom}")
        assert extractors.find_7z_exe() == "/usr/bin/7zz"

    def test_hors_windows_p7zip_en_repli(self, monkeypatch):
        """Bazzite a p7zip (`7z`, `7za`) dans son image, pas `7zz`."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(extractors, "Path", _PathSansEmbarque)
        monkeypatch.setattr(extractors.shutil, "which",
                            lambda nom: "/usr/bin/7za" if nom == "7za" else None)
        assert extractors.find_7z_exe() == "/usr/bin/7za"

    def test_hors_windows_l_embarque_passe_d_abord(self, monkeypatch):
        """Le 7-Zip officiel pour Linux, livré avec le launcher comme 7z.exe."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(extractors.shutil, "which", lambda nom: pytest.fail("PATH"))
        trouve = extractors.find_7z_exe()
        if sys.platform != "win32":     # le bit exécutable n'existe que sous POSIX
            assert trouve.endswith("7zzs")

    def test_sous_windows_jamais_de_repli_par_le_nom(self, monkeypatch):
        """Sans exe embarqué ni 7-Zip installé : None, pas « 7z »."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(extractors, "Path", _PathSansEmbarque)
        assert extractors.find_7z_exe() is None


class _PathSansEmbarque(type(Path())):
    """Un `Path` pour lequel aucun 7z.exe n'existe, ni embarqué ni installé."""

    def exists(self, *a, **k):  # noqa: D401
        return False

    def is_file(self, *a, **k):  # noqa: D401
        return False


class TestRandomSeulementDecoratif:
    """`.bandit` écarte B311 pour TOUT le dépôt : ce test l'empêche de
    couvrir demain un tirage qui, lui, compterait (jeton, nom de fichier)."""

    _DECORATIFS = {"src/ui/particles.py", "src/ui/carousel.py",
                   "build/create_social_preview.py"}

    def test_seuls_les_effets_visuels_importent_random(self):
        importeurs = set()
        for nom, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import) and any(a.name == "random" for a in noeud.names):
                    importeurs.add(nom)
                if isinstance(noeud, ast.ImportFrom) and noeud.module == "random":
                    importeurs.add(nom)
        assert importeurs <= self._DECORATIFS, (
            f"random importé hors des effets visuels : {importeurs - self._DECORATIFS} "
            "— pour un tirage qui compte, `secrets`")


class TestAucuneExceptionAvaleeSansTrace:
    def test_pas_de_except_exception_pass(self):
        fautifs = []
        for nom, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if (isinstance(noeud, ast.ExceptHandler)
                        and (noeud.type is None
                             or (isinstance(noeud.type, ast.Name)
                                 and noeud.type.id in {"Exception", "BaseException"}))
                        and all(isinstance(i, ast.Pass) for i in noeud.body)):
                    fautifs.append(f"{nom}:{noeud.lineno}")
        assert not fautifs, f"exception avalée sans trace (Bandit B110) : {fautifs}"


class TestConfigurationBandit:
    def test_seulement_deux_regles_ecartees(self):
        """Écarter une règle de plus doit être une décision, pas un oubli :
        ce test oblige à la justifier ici ET dans `.bandit`."""
        ini = configparser.ConfigParser()
        ini.read(_RACINE / ".bandit", encoding="utf-8")
        skips = {s.strip() for s in ini["bandit"]["skips"].split(",")}
        assert skips == {"B311", "B404"}

"""Ce que les règles de sécurité vérifient en CI (`security.yml`, `ruff --select S`
depuis le 2026-10-31, bandit avant), gardé aussi dans la suite locale.

`build.bat` ne lance pas ces règles : sans ces tests, une régression ne se
verrait qu'après le push. Ils gardent surtout ce que la commande de la CI
AFFIRME : elle écarte S311 pour une bonne raison, et cette raison doit rester
vraie :

- aucun programme n'est lancé par son seul nom (B607). Sous Windows, il serait
  cherché d'abord dans le dossier de l'exe appelant, donc là où l'utilisateur
  a enregistré AccioLauncher.exe — souvent Téléchargements ;
- `random` ne sert qu'aux effets visuels (B311, écarté globalement) ;
- aucune exception n'est avalée sans trace (B110).
"""

import ast
import os
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

    def test_shellexecute_par_chemin(self):
        """`ShellExecuteW(…, "regedit.exe", …)` : le nom seul, lancé ÉLEVÉ."""
        fautifs = []
        for nom, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if (isinstance(noeud, ast.Call)
                        and isinstance(noeud.func, ast.Attribute)
                        and noeud.func.attr == "ShellExecuteW"
                        and len(noeud.args) > 2
                        and isinstance(noeud.args[2], ast.Constant)):
                    fautifs.append(f"{nom}:{noeud.lineno} « {noeud.args[2].value} »")
        assert not fautifs, f"ShellExecuteW sur un nom écrit en dur : {fautifs}"

    @pytest.mark.skipif(sys.platform != "win32", reason="C:\\Windows : Windows uniquement")
    def test_regedit_existe_au_chemin_utilise(self):
        from src.core.win_utils import dossier_windows
        assert (Path(dossier_windows()) / "regedit.exe").is_file()

    @pytest.mark.skipif(sys.platform != "win32", reason="System32 : Windows uniquement")
    @pytest.mark.parametrize("programme", ["tasklist.exe", "cmd.exe", "find.exe", "PING.EXE"])
    def test_chemin_absolu_et_reel(self, programme):
        chemin = Path(commande_systeme(programme))
        assert chemin.is_absolute()
        assert chemin.is_file(), f"{chemin} n'existe pas"
        assert chemin.parent.name.lower() == "system32"

    @pytest.mark.skipif(sys.platform != "win32", reason="tasklist : Windows uniquement")
    def test_la_detection_d_un_jeu_marche_toujours(self, monkeypatch):
        """Le vrai `tasklist.exe`, appelé par son chemin : il voit bien le
        processus qui fait tourner cette suite, et pas un nom inventé.

        Délai porté à 60 s : sous `-n auto`, `tasklist` a dépassé 5 s
        (2026-11-01), et ce test-ci vérifie la détection, pas la vitesse."""
        from src.ui import process_monitor
        from src.ui.process_monitor import ProcessMonitor
        monkeypatch.setattr(process_monitor, "_TASKLIST_DELAI_S", 60)
        assert ProcessMonitor._is_exe_running(Path(sys.executable).name) is True
        assert ProcessMonitor._is_exe_running("accio_nexiste_pas_4242.exe") is False

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
        # `abspath` : ce test tourne AUSSI sous Windows, où il rend D:\usr\bin\7zz.
        assert extractors.find_7z_exe() == os.path.abspath("/usr/bin/7zz")

    def test_hors_windows_p7zip_en_repli(self, monkeypatch):
        """Bazzite a p7zip (`7z`, `7za`) dans son image, pas `7zz`."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(extractors, "Path", _PathSansEmbarque)
        monkeypatch.setattr(extractors.shutil, "which",
                            lambda nom: "/usr/bin/7za" if nom == "7za" else None)
        assert extractors.find_7z_exe() == os.path.abspath("/usr/bin/7za")

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

    def test_la_barriere_lit_les_vrais_noms_accentues(self, tmp_path):
        """Le vrai 7-Zip : lue dans la page de la console, la liste rendait
        « Ph‚nix » pour « Phénix », et la barrière contrôlait d'autres noms
        que ceux écrits sur le disque."""
        import subprocess
        exe = extractors.find_7z_exe()
        if exe is None:
            pytest.skip("aucun 7-Zip sur cette machine")
        nom = "L'Ordre du Phénix — Édition"
        (tmp_path / "src" / nom).mkdir(parents=True)
        (tmp_path / "src" / nom / "Système.ini").write_text("x", encoding="utf-8")
        archive = tmp_path / "essai.7z"
        subprocess.run([exe, "a", str(archive), str(tmp_path / "src" / nom)],
                       capture_output=True, check=True, timeout=60)
        entrees = extractors.list_7z_entries(archive, exe)
        assert extractors.premiers_niveaux(entrees) == {nom}
        assert any(e.endswith("Système.ini") for e in entrees)


class _PathSansEmbarque(type(Path())):
    """Un `Path` pour lequel aucun 7z.exe n'existe, ni embarqué ni installé."""

    def exists(self, *a, **k):  # noqa: D401
        return False

    def is_file(self, *a, **k):  # noqa: D401
        return False


class TestRandomSeulementDecoratif:
    """`security.yml` écarte S311 (ex-B311) pour TOUT le dépôt : ce test l'empêche de
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


class TestReglesDeSecuriteEnCI:
    def test_une_seule_regle_ecartee(self):
        """Écarter une règle de plus doit être une décision, pas un oubli :
        ce test oblige à la justifier ici ET dans le commentaire du workflow."""
        workflow = (_RACINE / ".github/workflows/security.yml").read_text(encoding="utf-8")
        commandes = [ligne.strip() for ligne in workflow.splitlines()
                     if "ruff check" in ligne and "--select S" in ligne]
        assert commandes == ["run: ruff check --select S --ignore S311 --extend-exclude tests,fuzz "
                             "--output-format github ."]
        assert "bandit -r" not in workflow

    def test_security_yml_en_python_315(self):
        """PEP 810 (`lazy import`) n'est lisible qu'à partir de la 3.15."""
        workflow = (_RACINE / ".github/workflows/security.yml").read_text(encoding="utf-8")
        assert 'python-version: "3.15"' in workflow

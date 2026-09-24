"""Tests pour src/core/self_update.py — le .bat de relance, prouvé par simulation.

Le bug du 2026-06-11 (« Redémarrer maintenant » ne relançait jamais) avait DEUX
causes, chacune verrouillée ici :
1. mode texte → \r\n devenait \r\r\n et cmd ne sortait jamais de la boucle :wait ;
2. DETACHED_PROCESS (pas de console du tout) bloquait le pipeline tasklist | find.

Troisième bug, découvert sur l'EXE GELÉ le 2026-06-12 (« Failed to load Python
DLL …\\_MEIxxxxxx\\python314.dll ») : le .bat héritait des variables _PYI_* du
bootloader PyInstaller, donc l'exe relancé se croyait enfant onefile de
l'instance morte et cherchait ses DLL dans son dossier temporaire supprimé.
"""

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import src.core.self_update as self_update

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _attendre_contenu(marqueur: Path, delai: float = 20.0) -> str:
    """Attend que le .bat ait ÉCRIT, pas seulement OUVERT, son marqueur.

    `marqueur.exists()` devient vrai dès que `cmd` ouvre le fichier pour la
    redirection `>`, c'est-à-dire AVANT que l'`echo` n'y dépose quoi que ce
    soit. Une boucle qui s'arrête à l'existence lit donc une chaîne vide une
    fois de temps en temps — CI Windows 3.14, 2026-09-23 : « env inattendu :
    '' ». La lecture peut aussi échouer franchement tant que `cmd` tient le
    fichier ouvert (partage refusé sous Windows), d'où le `except OSError`.

    Un test qui rate une fois sur dix est pire que pas de test : `build.bat`
    s'arrête au premier échec, et on apprend à le relancer sans le lire.
    """
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        try:
            contenu = marqueur.read_text(encoding="ascii", errors="replace")
        except OSError:
            contenu = ""
        if contenu.strip():
            return contenu
        time.sleep(0.2)
    return ""


class TestBatContent:
    @pytest.mark.skipif(sys.platform != "win32",
                        reason="constantes CREATE_NO_WINDOW Windows uniquement")
    def test_no_double_carriage_returns(self, tmp_path, monkeypatch):
        """Régression \r\r\n : le contenu écrit sur disque doit être en CRLF strict."""
        import os

        captured: dict = {}
        bat_file = tmp_path / "t.bat"

        def fake_popen(*args, **kwargs):
            captured["bat"] = bat_file.read_bytes()
            return object()

        def fake_mkstemp(**kw):
            return os.open(str(bat_file), os.O_RDWR | os.O_CREAT), str(bat_file)

        monkeypatch.setattr(self_update.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(self_update.tempfile, "mkstemp", fake_mkstemp)
        assert self_update._spawn_after_exit_bat("echo x\r\n", prefix="t_") is True
        content = captured["bat"]
        assert b"\r\r" not in content, "CRLF doublés — cmd ne sortira jamais de :wait"
        assert b":wait\r\n" in content

    def test_no_detached_process_flag(self):
        """Régression : DETACHED_PROCESS (console absente) bloque tasklist | find."""
        import inspect
        src = inspect.getsource(self_update._spawn_after_exit_bat)
        assert "DETACHED_PROCESS" not in src
        assert "CREATE_NO_WINDOW" in src


class TestCleanPyinstallerEnv:
    def test_strips_bootloader_state_and_sets_reset(self, monkeypatch):
        """Régression « Failed to load Python DLL » : l'env transmis au .bat ne
        doit contenir AUCUNE variable du bootloader PyInstaller."""
        monkeypatch.setenv("_PYI_ARCHIVE_FILE", r"C:\fake\AccioLauncher.exe")
        monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "1")
        monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\fake")
        monkeypatch.setenv("_MEIPASS2", r"C:\fake\_MEI000000")
        monkeypatch.setenv("ACCIO_UNRELATED", "garde-moi")

        env = self_update._clean_pyinstaller_env()
        assert not any(k.startswith("_PYI_") for k in env)
        assert "_MEIPASS2" not in env
        assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
        assert env["ACCIO_UNRELATED"] == "garde-moi"

    @pytest.mark.skipif(sys.platform != "win32",
                        reason="constantes CREATE_NO_WINDOW Windows uniquement")
    def test_spawn_passes_cleaned_env_to_popen(self, tmp_path, monkeypatch):
        import os

        captured: dict = {}
        bat_file = tmp_path / "t.bat"

        def fake_popen(*args, **kwargs):
            captured["env"] = kwargs.get("env")
            return object()

        def fake_mkstemp(**kw):
            return os.open(str(bat_file), os.O_RDWR | os.O_CREAT), str(bat_file)

        monkeypatch.setenv("_PYI_ARCHIVE_FILE", r"C:\fake\AccioLauncher.exe")
        monkeypatch.setattr(self_update.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(self_update.tempfile, "mkstemp", fake_mkstemp)
        assert self_update._spawn_after_exit_bat("echo x\r\n", prefix="t_") is True
        env = captured["env"]
        assert env is not None, "Popen sans env= : le .bat hérite des _PYI_*"
        assert "_PYI_ARCHIVE_FILE" not in env
        assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


@pytest.mark.skipif(sys.platform != "win32", reason=".bat Windows uniquement")
class TestBatEndToEnd:
    def test_bat_waits_parent_death_then_runs_body(self, tmp_path):
        """Simulation réelle : un process enfant spawn le .bat (via le VRAI code)
        puis meurt ; le .bat doit alors exécuter le corps (écrire un marqueur)."""
        marker = tmp_path / "marker.txt"
        child = tmp_path / "child.py"
        child.write_text(textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(_REPO_ROOT)!r})
            from src.core.self_update import _spawn_after_exit_bat
            body = 'echo done > "' + {str(marker)!r} + '"' + '\\r\\n'
            ok = _spawn_after_exit_bat(body, prefix="accio_pytest_")
            time.sleep(0.5)  # le .bat doit nous voir vivant au moins un tour
            sys.exit(0 if ok else 1)
        """), encoding="utf-8")

        proc = subprocess.run([sys.executable, str(child)], timeout=30,
                              capture_output=True)
        assert proc.returncode == 0, proc.stderr.decode(errors="replace")

        assert _attendre_contenu(marker),             "le .bat n'a pas exécuté le corps après la mort du parent"

    def test_bat_does_not_leak_pyinstaller_env(self, tmp_path):
        """Simulation réelle du restart d'un exe gelé : le parent est pollué par
        les variables du bootloader (_PYI_*) ; le corps du .bat fait écho à la
        variable — si elle fuit, le marqueur contient le faux chemin et l'exe
        relancé chercherait ses DLL dans un _MEI mort."""
        marker = tmp_path / "env_marker.txt"
        child = tmp_path / "child_env.py"
        child.write_text(textwrap.dedent(f"""
            import os, sys, time
            sys.path.insert(0, {str(_REPO_ROOT)!r})
            os.environ["_PYI_ARCHIVE_FILE"] = r"C:\\fake\\AccioLauncher.exe"
            os.environ["_PYI_PARENT_PROCESS_LEVEL"] = "1"
            from src.core.self_update import _spawn_after_exit_bat
            body = ('echo [%_PYI_ARCHIVE_FILE%][%PYINSTALLER_RESET_ENVIRONMENT%]'
                    ' > "' + {str(marker)!r} + '"' + '\\r\\n')
            ok = _spawn_after_exit_bat(body, prefix="accio_pytest_env_")
            time.sleep(0.5)
            sys.exit(0 if ok else 1)
        """), encoding="utf-8")

        proc = subprocess.run([sys.executable, str(child)], timeout=30,
                              capture_output=True)
        assert proc.returncode == 0, proc.stderr.decode(errors="replace")

        content = _attendre_contenu(marker)
        assert content, "le .bat n'a pas tourné"
        # Dans un .bat, une variable absente s'étend en vide → "[][1]" attendu.
        assert "AccioLauncher.exe" not in content, f"fuite _PYI_* : {content!r}"
        assert "[][1]" in content, f"env inattendu : {content!r}"


def _remplacement_sous_verrou(tmp_path: Path, corps: str) -> str:
    """Rejoue une mise à jour pendant que l'exe est encore VERROUILLÉ.

    Un processus « bootloader » garde la cible ouverte 3 s — ce que fait le
    bootloader PyInstaller en effaçant son `_MEI` après la mort de l'enfant
    Python. Pendant ce temps, l'« enfant » lance le VRAI .bat puis meurt
    aussitôt. Rend le contenu final de la cible, une fois le .bat passé.
    """
    cible = tmp_path / "AccioLauncher.exe"
    cible.write_text("ancien", encoding="ascii")
    neuf = tmp_path / "AccioLauncher_v9.exe"
    neuf.write_text("nouveau", encoding="ascii")
    marker = tmp_path / "fini.txt"

    # Python ouvre sans FILE_SHARE_DELETE : tant que le handle vit, `move`
    # vers ce nom est refusé, exactement comme sur l'image d'un exe en cours.
    verrou = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import time
        f = open({str(cible)!r}, "rb")
        print("pris", flush=True)
        time.sleep(3)
    """)], stdout=subprocess.PIPE)
    assert verrou.stdout.readline().strip() == b"pris"

    enfant = tmp_path / "enfant.py"
    corps_complet = corps + 'echo fini > "' + str(marker) + '"\r\n'
    variables = {"ACCIO_NOUVEL_EXE": str(neuf), "ACCIO_EXE": str(cible)}
    enfant.write_text("\n".join([
        "import sys",
        f"sys.path.insert(0, {str(_REPO_ROOT)!r})",
        "from src.core.self_update import _spawn_after_exit_bat",
        f"ok = _spawn_after_exit_bat({corps_complet!r}, prefix='accio_pytest_maj_',",
        f"                           variables={variables!r})",
        "sys.exit(0 if ok else 1)",
    ]), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(enfant)], timeout=30, capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")

    assert _attendre_contenu(marker, delai=60), "le .bat n'est jamais allé au bout"
    verrou.wait(timeout=10)
    return cible.read_text(encoding="ascii")


@pytest.mark.skipif(sys.platform != "win32", reason=".bat Windows uniquement")
class TestRemplacementSousVerrou:
    """Joueur, 2026-09-24 : « ça commence le dl, ça ferme le launcher, et ça
    remet le message la mise à jour est disponible ». Le nouvel exe était
    resté dans le cache : le remplacement avait été refusé, en silence."""

    def test_le_remplacement_attend_que_l_exe_soit_libere(self, tmp_path):
        assert _remplacement_sous_verrou(tmp_path, self_update._CORPS_REMPLACEMENT) == "nouveau"

    def test_contre_epreuve_l_ancien_move_unique_echouait(self, tmp_path):
        """Sans cette contre-épreuve, le test ci-dessus pourrait passer parce
        que le verrou ne verrouille rien."""
        ancien = 'move /y "%ACCIO_NOUVEL_EXE%" "%ACCIO_EXE%" >nul\r\n'
        assert _remplacement_sous_verrou(tmp_path, ancien) == "ancien"

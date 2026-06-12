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

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.5)
        assert marker.exists(), "le .bat n'a pas exécuté le corps après la mort du parent"

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

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.5)
        assert marker.exists(), "le .bat n'a pas tourné"
        content = marker.read_text(encoding="ascii", errors="replace")
        # Dans un .bat, une variable absente s'étend en vide → "[][1]" attendu.
        assert "AccioLauncher.exe" not in content, f"fuite _PYI_* : {content!r}"
        assert "[][1]" in content, f"env inattendu : {content!r}"

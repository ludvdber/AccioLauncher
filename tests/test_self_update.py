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


# ──────────────────── Linux : AppImage et relance ────────────────────

@pytest.fixture
def appimage(tmp_path, monkeypatch):
    """Une AppImage « qui tourne » : exe gelé, `$APPIMAGE` posé par le runtime."""
    cible = tmp_path / "Applications" / "AccioLauncher-x86_64.AppImage"
    cible.parent.mkdir()
    cible.write_bytes(b"ancienne")
    cible.chmod(0o755)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPIMAGE", str(cible))
    return cible


class TestAppImage:
    def test_la_cible_est_l_appimage_et_non_sys_executable(self, appimage):
        """Dans une AppImage, `sys.executable` vit dans un montage qui
        disparaît avec le processus : le relancer ne mènerait nulle part."""
        assert self_update.appimage_courante() == appimage
        assert self_update.can_self_update() is True

    def test_depuis_les_sources_pas_d_auto_remplacement(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.setenv("APPIMAGE", str(tmp_path / "x.AppImage"))
        assert self_update.appimage_courante() is None
        assert self_update.can_self_update() is False

    def test_un_dossier_en_lecture_seule_renvoie_a_la_page(self, appimage, monkeypatch):
        monkeypatch.setattr(self_update.os, "access", lambda chemin, mode: False)
        assert self_update.can_self_update() is False

    def test_appimage_disparue(self, appimage):
        appimage.unlink()
        assert self_update.can_self_update() is False

    def test_nom_du_telechargement(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert self_update.nom_du_telechargement("1.1.0") == "AccioLauncher_v1.1.0.AppImage"
        monkeypatch.setattr(sys, "platform", "win32")
        assert self_update.nom_du_telechargement("1.1.0") == "AccioLauncher_v1.1.0.exe"

    def test_remplacement_atomique_puis_relance(self, appimage, tmp_path, monkeypatch):
        nouvelle = tmp_path / "cache" / "AccioLauncher_v9.AppImage"
        nouvelle.parent.mkdir()
        nouvelle.write_bytes(b"nouvelle")
        relances = []
        monkeypatch.setattr(self_update, "_relancer_apres_la_fin",
                            lambda commande: relances.append(commande) or True)
        assert self_update.apply_update_and_restart(nouvelle) is True
        assert appimage.read_bytes() == b"nouvelle"
        assert appimage.stat().st_mode & 0o111, "l'AppImage doit rester exécutable"
        assert not nouvelle.exists(), "le téléchargement ne doit pas rester en cache"
        assert relances == [[str(appimage)]]
        assert not list(appimage.parent.glob(".*nouvelle")), "fichier temporaire laissé"

    def test_un_echec_laisse_l_ancienne_intacte(self, appimage, tmp_path, monkeypatch):
        monkeypatch.setattr(self_update, "_relancer_apres_la_fin", lambda c: pytest.fail("relancé"))
        assert self_update.apply_update_and_restart(tmp_path / "absente.AppImage") is False
        assert appimage.read_bytes() == b"ancienne"
        assert not list(appimage.parent.glob(".*nouvelle"))


class TestRelanceLinux:
    def _espion(self, monkeypatch):
        vus = {}

        def faux(args, **kwargs):
            vus["args"] = args
            vus.update(kwargs)
            return object()
        monkeypatch.setattr(self_update.subprocess, "Popen", faux)
        return vus

    def test_le_script_attend_la_mort_du_processus(self, monkeypatch):
        vus = self._espion(monkeypatch)
        assert self_update._relancer_apres_la_fin(["/opt/Accio.AppImage"]) is True
        assert vus["args"][:2] == ["/bin/sh", "-c"], "sh par son chemin absolu"
        assert vus["args"][3:] == ["accio-relance", "/opt/Accio.AppImage"]
        assert "/opt/Accio" not in vus["args"][2], "aucun chemin dans le corps du script"
        assert vus["env"]["ACCIO_PID"] == str(__import__("os").getpid())
        assert vus["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
        assert vus["start_new_session"] is True

    def test_depuis_les_sources_main_py_en_chemin_absolu(self, monkeypatch):
        """`sys.argv[0]` est relatif au dossier de lancement : on ne s'y fie plus."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delattr(sys, "frozen", raising=False)
        commandes = []
        monkeypatch.setattr(self_update, "_relancer_apres_la_fin",
                            lambda c: commandes.append(c) or True)
        assert self_update.relaunch_after_exit() is True
        assert commandes == [[sys.executable, str(_REPO_ROOT / "main.py")]]

    def test_depuis_l_appimage(self, appimage, monkeypatch):
        commandes = []
        monkeypatch.setattr(self_update, "_relancer_apres_la_fin",
                            lambda c: commandes.append(c) or True)
        assert self_update.relaunch_after_exit() is True
        assert commandes == [[str(appimage)]]

    @pytest.mark.skipif(sys.platform == "win32", reason="/bin/sh : Linux")
    def test_bout_en_bout_la_relance_attend_vraiment(self, tmp_path):
        """Un vrai processus programme sa relance puis meurt : la commande ne
        doit partir QU'APRÈS sa mort — c'est ce qui laisse l'instance unique
        libre pour le nouveau launcher."""
        marqueur = tmp_path / "relance.txt"
        enfant = textwrap.dedent(f"""
            import os, sys, time
            sys.path.insert(0, {str(_REPO_ROOT)!r})
            from src.core import self_update
            ecrire = "import os,time; open({str(marqueur)!r},'w').write(str(time.time()))"
            assert self_update._relancer_apres_la_fin([sys.executable, "-c", ecrire])
            time.sleep(1.5)
            print(time.time(), flush=True)
        """)
        fin = subprocess.run([sys.executable, "-c", enfant], capture_output=True,
                             text=True, timeout=30, check=True)
        mort = float(fin.stdout.strip())
        ecrit = _attendre_contenu(marqueur)
        assert ecrit, "la relance n'a jamais eu lieu"
        assert float(ecrit) >= mort, "la commande est partie AVANT la mort du processus"

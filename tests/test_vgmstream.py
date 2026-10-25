"""vgmstream : recherche de l'exécutable, conversion, et la musique de HP5 qui en dépend."""

import os
import subprocess
import sys

import pytest

from src.core import phonographe, vgmstream
from tests.test_archives_ea import _bigf, _flux, _mus


class _Fini:
    def __init__(self, code: int) -> None:
        self.returncode = code
        self.stderr = "erreur"


def _faux_run(code: int = 0, octets: bytes = b"RIFF" + b"\0" * 100):
    appels = []

    def run(args, **kwargs):
        appels.append(args)
        with open(args[2], "wb") as f:       # « -o <tmp> <source> »
            f.write(octets)
        return _Fini(code)
    return run, appels


@pytest.fixture
def faux_exe(tmp_path, monkeypatch):
    exe = tmp_path / "vgmstream-cli.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(vgmstream, "executable", lambda: exe)
    return exe


class TestExecutable:
    @pytest.mark.skipif(sys.platform != "win32", reason="l'exécutable n'est embarqué que sous Windows")
    def test_embarque_sous_windows(self):
        exe = vgmstream.executable()
        assert exe is not None and exe.name == "vgmstream-cli.exe", (
            "vgmstream absent : lancer `python build/vgmstream.py` (binaires non suivis par git)")
        assert (exe.parent / "License.txt").is_file()

    @pytest.mark.skipif(sys.platform != "win32", reason="l'exécutable n'est embarqué que sous Windows")
    def test_les_binaires_poses_sont_ceux_de_la_release(self):
        """Les octets embarqués sont ceux de la release r2117, pas une copie locale."""
        import importlib.util
        from pathlib import Path

        chemin = Path(__file__).resolve().parent.parent / "build" / "vgmstream.py"
        spec = importlib.util.spec_from_file_location("pose_vgmstream", chemin)
        assert spec is not None and spec.loader is not None
        pose = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pose)
        assert pose._a_poser() == []
        assert {p.name for p in pose.DOSSIER.glob("*.*")} - {"License.txt"} == set(pose.FICHIERS)

    def test_linux_prend_celui_du_systeme(self, monkeypatch):
        monkeypatch.setattr(vgmstream.sys, "platform", "linux")
        monkeypatch.setattr(vgmstream.shutil, "which", lambda nom: "/usr/bin/vgmstream-cli")
        assert vgmstream.executable() == vgmstream.Path(os.path.abspath("/usr/bin/vgmstream-cli"))
        monkeypatch.setattr(vgmstream.shutil, "which", lambda nom: None)
        assert vgmstream.executable() is None


class TestConvertir:
    def test_ecrit_puis_reutilise(self, tmp_path, faux_exe, monkeypatch):
        source = tmp_path / "a.asf"
        source.write_bytes(b"SCHl")
        run, appels = _faux_run()
        monkeypatch.setattr(vgmstream.subprocess, "run", run)
        cible = tmp_path / "cache" / "a.wav"
        assert vgmstream.convertir(source, cible) == cible
        assert cible.read_bytes()[:4] == b"RIFF"
        assert vgmstream.convertir(source, cible) == cible
        assert len(appels) == 1

    def test_echec_ne_laisse_rien(self, tmp_path, faux_exe, monkeypatch):
        source = tmp_path / "a.asf"
        source.write_bytes(b"SCHl")
        run, _ = _faux_run(code=1)
        monkeypatch.setattr(vgmstream.subprocess, "run", run)
        assert vgmstream.convertir(source, tmp_path / "a.wav") is None
        assert not (tmp_path / "a.wav").exists()
        assert not list(tmp_path.glob("*.accio-tmp*"))

    def test_delai_depasse(self, tmp_path, faux_exe, monkeypatch):
        source = tmp_path / "a.asf"
        source.write_bytes(b"SCHl")

        def trop_long(args, **kwargs):
            raise subprocess.TimeoutExpired(args, 60)
        monkeypatch.setattr(vgmstream.subprocess, "run", trop_long)
        assert vgmstream.convertir(source, tmp_path / "a.wav") is None
        assert not list(tmp_path.glob("*.accio-tmp*"))

    def test_sans_vgmstream(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vgmstream, "executable", lambda: None)
        source = tmp_path / "a.asf"
        source.write_bytes(b"SCHl")
        assert vgmstream.convertir(source, tmp_path / "a.wav") is None


class TestMusiqueHp5:
    def _jeu(self, tmp_path, monkeypatch):
        monkeypatch.setattr(phonographe, "SEUIL_MORCEAU", 200)
        jeu = tmp_path / "HP5"
        jeu.mkdir()
        (jeu / "music.big").write_bytes(_bigf({"audio/music/hog_music_stream.mus": _mus(_flux(500), _flux(400))}))
        return jeu

    def test_morceaux_convertis(self, tmp_path, faux_exe, monkeypatch):
        jeu = self._jeu(tmp_path, monkeypatch)
        run, _ = _faux_run()
        monkeypatch.setattr(vgmstream.subprocess, "run", run)
        pistes = phonographe.pistes("hp5", jeu)
        assert [p.identifiant for p in pistes] == ["hog_music_stream-1", "hog_music_stream-2"]
        lu = phonographe.fichier_lisible(pistes[0], tmp_path / "cache")
        assert lu is not None and lu.suffix == ".wav"

    def test_sans_vgmstream_pas_de_morceaux(self, tmp_path, monkeypatch):
        jeu = self._jeu(tmp_path, monkeypatch)
        monkeypatch.setattr(vgmstream, "executable", lambda: None)
        assert phonographe.pistes("hp5", jeu) == []

    def test_le_cache_reste_sous_son_plafond(self, tmp_path, monkeypatch):
        monkeypatch.setattr(phonographe, "_PLAFOND_WAV", 250)
        dossier = tmp_path / "hp5"
        dossier.mkdir()
        for i, nom in enumerate(("vieux", "moyen", "neuf")):
            f = dossier / f"{nom}.wav"
            f.write_bytes(b"\0" * 100)
            os.utime(f, (1000 + i, 1000 + i))
        phonographe._elaguer(dossier, dossier / "neuf.wav")
        assert sorted(p.stem for p in dossier.glob("*.wav")) == ["moyen", "neuf"]

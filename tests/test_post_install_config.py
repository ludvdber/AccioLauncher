"""Copie des fichiers de config vers Documents : une réinstallation les rafraîchit.

Le `User.ini` de HP2 est livré en lecture seule ; sa copie et son `.bak`
l'étaient aussi, et la réinstallation suivante échouait sur `PermissionError`
(journal de Ludo, 2026-08-22 et 2026-09-19).
"""

import os
import stat

import pytest

from src.core import post_install


@pytest.fixture
def jeu(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    monkeypatch.setattr(post_install, "get_documents_dir", lambda: docs)
    install = tmp_path / "Games"
    source = install / "HP2" / "config" / "User.ini"
    source.parent.mkdir(parents=True)
    return install, source, docs / "Harry Potter II" / "User.ini"


def _lecture_seule(chemin):
    chemin.chmod(stat.S_IREAD)


def _installer(install):
    post_install.apply_config_files(
        install, "HP2", [("config/User.ini", "~/Documents/Harry Potter II/User.ini")])


class TestConfigEnLectureSeule:
    def test_la_reinstallation_remplace_une_config_en_lecture_seule(self, jeu):
        install, source, dest = jeu
        source.write_text("v1")
        _lecture_seule(source)
        _installer(install)
        _installer(install)          # le .bak existe maintenant, en lecture seule
        source.chmod(stat.S_IWRITE | stat.S_IREAD)
        source.write_text("v2")
        _lecture_seule(source)

        _installer(install)

        assert dest.read_text() == "v2"
        assert dest.with_suffix(".ini.bak").read_text() == "v1"

    def test_l_attribut_de_l_archive_est_conserve(self, jeu):
        install, source, dest = jeu
        source.write_text("v1")
        _lecture_seule(source)
        _installer(install)
        assert not os.access(dest, os.W_OK)

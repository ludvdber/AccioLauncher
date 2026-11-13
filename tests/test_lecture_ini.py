"""Un ini lu UNE fois tant qu'il ne change pas (`src/core/lecture_ini.py`).

Audit du 2026-11-13 : une seule ouverture des réglages de HP6 lisait `d3d9.ini`
62 fois (75 sur un parcours). Mesure : le nombre de `read_bytes` réels.
Contre-épreuve : sur l'ancien `_lire`, ces comptes valent le nombre d'appels.
"""

import os
import time
from pathlib import Path

import pytest

from src.core import lecture_ini
from src.core import reglages_correctif as rc
from src.core.reglages_table import REGLAGES

INI = "[Accio.Window]\r\nWindowStyle=1\r\n[Accio.Graphics]\r\nSharpness=0.40\r\nVibrance=0.35\r\nFXAA=1\r\n"


@pytest.fixture
def lectures(monkeypatch):
    vus: list[str] = []
    vrai = Path.read_bytes

    def compter(self):
        vus.append(self.name)
        return vrai(self)
    monkeypatch.setattr(Path, "read_bytes", compter)
    return vus


@pytest.fixture
def ini(tmp_path, vieillir):
    chemin = tmp_path / "d3d9.ini"
    chemin.write_bytes(INI.encode("ascii"))
    vieillir(chemin)
    return chemin


def test_vingt_reglages_lus_une_seule_ouverture(ini, lectures):
    fxaa = REGLAGES["lissage"]
    for _ in range(20):
        assert rc.lire(ini, fxaa).valeur is True
    assert lectures == ["d3d9.ini"]


def test_ce_que_le_launcher_ecrit_se_relit_aussitot(ini, lectures, vieillir):
    fxaa = REGLAGES["lissage"]
    rc.lire(ini, fxaa)
    rc.ecrire(ini, fxaa, False)
    assert rc.lire(ini, fxaa).valeur is False
    vieillir(ini)                            # le joueur revient plus tard
    lectures.clear()
    for _ in range(5):
        assert rc.lire(ini, fxaa).valeur is False
    assert lectures == ["d3d9.ini"]


def test_reecrit_de_meme_taille_dans_le_meme_tic_est_relu(ini):
    """CI Windows, 2026-11-13 : « 1.5 » réécrit en « 2.0 » gardait date et taille, et se relisait 1.5."""
    etat = ini.stat()
    os.utime(ini, ns=(etat.st_atime_ns, time.time_ns()))
    assert "FXAA=1" in lecture_ini.lire_lignes(ini)[0]
    date = ini.stat().st_mtime_ns
    ini.write_bytes(INI.replace("FXAA=1", "FXAA=0").encode("ascii"))
    os.utime(ini, ns=(etat.st_atime_ns, date))          # même date, même taille
    assert "FXAA=0" in lecture_ini.lire_lignes(ini)[0]


def test_un_ini_change_a_la_main_est_relu(ini):
    fxaa = REGLAGES["lissage"]
    assert rc.lire(ini, fxaa).valeur is True
    ini.write_bytes(INI.replace("FXAA=1", "FXAA=0").encode("ascii"))
    etat = ini.stat()
    os.utime(ini, ns=(etat.st_atime_ns, etat.st_mtime_ns + 1_000_000_000))
    assert rc.lire(ini, fxaa).valeur is False


def test_les_lignes_rendues_sont_une_copie(ini):
    lignes, _ = lecture_ini.lire_lignes(ini)
    lignes.append("[Retouche]")
    assert "[Retouche]" not in lecture_ini.lire_lignes(ini)[0]


def test_la_copie_d_origine_se_compare_sans_relire(ini, lectures, vieillir):
    origine = rc.chemin_origine(ini)
    origine.write_bytes(ini.read_bytes())
    vieillir(origine)
    lectures.clear()
    for _ in range(5):
        assert rc.a_une_origine(ini) is False
    assert sorted(set(lectures)) == ["d3d9.ini", "d3d9.ini.origine"] and len(lectures) == 2


def test_le_cache_est_borne(tmp_path, vieillir):
    for n in range(lecture_ini._TAILLE + 5):
        f = tmp_path / f"{n}.ini"
        f.write_text("[A]\nB=1\n", encoding="utf-8")
        vieillir(f)
        lecture_ini.lire_lignes(f)
    assert len(lecture_ini._cache) <= lecture_ini._TAILLE


def test_fichier_absent_leve_oserror(tmp_path):
    with pytest.raises(OSError):
        lecture_ini.lire_lignes(tmp_path / "absent.ini")

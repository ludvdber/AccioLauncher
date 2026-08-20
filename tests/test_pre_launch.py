"""Patches INI de pré-lancement — et l'encodage des fichiers du MOTEUR.

Ces .ini ne nous appartiennent pas : UE1 les réécrit en ANSI à chaque session.
Les lire en UTF-8 strict levait `UnicodeDecodeError` dès que le chemin de
sauvegarde contenait un accent — donc pour tout utilisateur dont le profil
s'appelle « Frédéric ». Cette exception dérive de `ValueError`, pas d'`OSError` :
elle traversait le `except OSError` d'`apply_ini_patches`, puis `launch_game`,
puis `on_play` (qui ne rattrape que RuntimeError/OSError), et ressortait en
rapport de plantage au lieu d'un lancement de jeu.
"""

import sys

import pytest

from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import _INI_ENCODING, apply_ini_patches

B = chr(92)      # antislash, pour ne pas semer d'échappements dans le fichier
CRLF = "\r\n"

JEU = {
    "id": "hp1", "name": "HP1", "year": 2001, "description": "d",
    "developer": "dev", "executable": "HP1/System/HP.exe", "cover_image": "c.png",
    "pre_launch": {"ini_patches": [
        {"file": "%DOCUMENTS%" + B + "Harry Potter" + B + "HP.ini",
         "section": "FirstRun", "key": "Reconfig", "value": "0"},
    ]},
}


@pytest.fixture
def ini_ansi(tmp_path, monkeypatch):
    """Un HP.ini tel que le moteur l'écrit : ANSI, avec un profil accentué."""
    docs = tmp_path / "Documents"
    (docs / "Harry Potter").mkdir(parents=True)
    chemin = docs / "Harry Potter" / "HP.ini"
    contenu = (
        "[FirstRun]" + CRLF
        + "Reconfig=1" + CRLF
        + "[Core.System]" + CRLF
        + "SavePath=C:" + B + "Users" + B + "Frédéric"
        + B + "Documents" + B + "Harry Potter" + B + "Save" + CRLF
    )
    chemin.write_bytes(contenu.encode(_INI_ENCODING))
    monkeypatch.setattr("src.core.pre_launch.get_documents_dir", lambda: docs.resolve())
    return chemin, tmp_path


def _appliquer(tmp_path):
    apply_ini_patches(GameData.from_dict(JEU), Config(install_path=tmp_path / "jeux"))


class TestIniEcritParLeMoteur:
    def test_un_profil_accentue_ne_fait_plus_planter_le_lancement(self, ini_ansi):
        chemin, tmp_path = ini_ansi
        _appliquer(tmp_path)          # levait UnicodeDecodeError

    def test_le_patch_est_bien_applique(self, ini_ansi):
        chemin, tmp_path = ini_ansi
        _appliquer(tmp_path)
        assert "Reconfig=0" in chemin.read_text(encoding=_INI_ENCODING)

    def test_les_lignes_non_touchees_sont_intactes_a_l_octet(self, ini_ansi):
        """On ne doit pas abîmer une ligne qu'on se contente de recopier — et
        surtout pas réécrire en UTF-8 un fichier que le moteur relit en ANSI :
        il chercherait alors ses sauvegardes dans « FrÃ©dÃ©ric »."""
        chemin, tmp_path = ini_ansi
        lignes_avant = chemin.read_bytes().split(CRLF.encode("ascii"))
        _appliquer(tmp_path)
        lignes_apres = chemin.read_bytes().split(CRLF.encode("ascii"))

        save = [x for x in lignes_apres if x.startswith(b"SavePath=")]
        assert save, "la ligne SavePath a disparu"
        assert save[0] in lignes_avant, (
            "la ligne SavePath a été ré-encodée : le moteur ne la relira plus")

    def test_section_absente_ajoutee(self, ini_ansi):
        chemin, tmp_path = ini_ansi
        jeu = dict(JEU)
        jeu["pre_launch"] = {"ini_patches": [
            {"file": "%DOCUMENTS%" + B + "Harry Potter" + B + "HP.ini",
             "section": "NouvelleSection", "key": "Cle", "value": "Valeur"},
        ]}
        apply_ini_patches(GameData.from_dict(jeu),
                          Config(install_path=tmp_path / "jeux"))
        texte = chemin.read_text(encoding=_INI_ENCODING)
        assert "[NouvelleSection]" in texte
        assert "Cle=Valeur" in texte

    @pytest.mark.skipif(sys.platform != "win32", reason="page de codes ANSI Windows")
    def test_l_encodage_est_celui_du_moteur(self):
        assert _INI_ENCODING == "mbcs"

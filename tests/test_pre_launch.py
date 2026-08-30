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
from src.core.pre_launch import (
    _INI_ENCODING,
    apply_ini_patches,
    env_de_lancement,
)

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


class TestCoucheDpi:
    """La couche de compatibilité DPI donnée au jeu qu'on lance.

    Windows virtualise les programmes qui ne se déclarent pas conscients du
    DPI : sur un écran mis à l'échelle, il multiplie par le facteur d'échelle
    tout ce qu'ils demandent, fenêtre comprise. Mesuré le 2026-08-30 sur les
    DEUX parties de HP7, que leur wrapper `d3d9.dll` force en mode fenêtré :
    la fenêtre sortait à 3200×1800 sur un écran de 2560×1440 à 125 %, soit
    exactement le facteur d'échelle. Avec la couche : 2560×1440 à la position
    0,0. La résolution du jeu, elle, était bonne dans les deux cas — c'est ce
    qui rend le défaut si déroutant, et ce qui justifie de le corriger ici
    plutôt que de renvoyer l'utilisateur à ses réglages d'affichage.
    """

    def test_la_couche_est_posee_sur_un_environnement_vide(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert env_de_lancement(True, {}) == {"__COMPAT_LAYER": "HighDpiAware"}

    def test_un_jeu_qui_ne_le_declare_pas_ne_recoit_rien(self, monkeypatch):
        """La garde demandée par Ludo (2026-08-30) : seules les deux parties de
        HP7 posaient problème, et les six autres jeux ne doivent pas changer de
        comportement. None = `Popen` hérite, exactement comme avant."""
        monkeypatch.setattr(sys, "platform", "win32")
        assert env_de_lancement(False, {}) is None

    def test_une_couche_existante_est_conservee(self, monkeypatch):
        """`__COMPAT_LAYER` est une LISTE séparée par des espaces : quelqu'un
        qui a réglé `WINXPSP3` à la main pour un jeu récalcitrant ne doit pas
        la perdre parce qu'on lance ce jeu."""
        monkeypatch.setattr(sys, "platform", "win32")
        env = env_de_lancement(True, {"__COMPAT_LAYER": "WINXPSP3"})
        assert env["__COMPAT_LAYER"].split() == ["WINXPSP3", "HighDpiAware"]

    def test_pas_de_doublon_si_deja_posee(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        env = env_de_lancement(True, {"__COMPAT_LAYER": "HighDpiAware"})
        assert env["__COMPAT_LAYER"].split().count("HighDpiAware") == 1

    def test_la_casse_ne_cree_pas_de_doublon(self, monkeypatch):
        """Windows ne distingue pas la casse des noms de couches : ajouter
        « HighDpiAware » à côté de « highdpiaware » poserait deux fois la même
        chose, ce qui est au mieux du bruit."""
        monkeypatch.setattr(sys, "platform", "win32")
        env = env_de_lancement(True, {"__COMPAT_LAYER": "highdpiaware"})
        assert len(env["__COMPAT_LAYER"].split()) == 1

    def test_le_reste_de_l_environnement_est_transmis(self, monkeypatch):
        """On REMPLACE l'environnement du processus fils : tout oublier
        priverait le jeu de PATH, TEMP et du reste."""
        monkeypatch.setattr(sys, "platform", "win32")
        env = env_de_lancement(True, {"PATH": "/x", "TEMP": "/t"})
        assert env["PATH"] == "/x" and env["TEMP"] == "/t"

    def test_hors_windows_on_ne_touche_a_rien(self, monkeypatch):
        """None est exactement ce que `Popen(env=None)` attend — le jeu hérite
        du nôtre. La couche de compatibilité est une notion Windows ; sous
        Linux ces jeux tourneront sous Wine, qui a sa propre idée du DPI."""
        monkeypatch.setattr(sys, "platform", "linux")
        assert env_de_lancement(True, {}) is None

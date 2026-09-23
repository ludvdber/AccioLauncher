"""La configuration réglée d'un jeu revient quand elle a disparu.

Mesuré sur HP1 le 2026-09-24, avec l'exe : le dossier « Harry Potter » de
Documents vidé, sauvegardes gardées. Le launcher sautait ses sept patchs
faute de HP.ini (« Fichier INI introuvable, skip » sept fois au journal), le
moteur régénérait le fichier depuis Default.ini avec Reconfig=1, et le jeu
s'ouvrait sur son assistant de configuration — liste de cartes vidéo VIDE.
« Commencer ! » passait ; une liste vide, elle, se lit comme un jeu cassé.

Documents est redirigé vers tmp_path par la garde de conftest.
"""

import pytest

from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import (
    _INI_ENCODING,
    apply_ini_patches,
    restaurer_configs_manquantes,
)

B = chr(92)      # antislash, pour ne pas semer d'échappements dans le fichier
CRLF = "\r\n"
REGLEE = ("[FirstRun]" + CRLF + "Reconfig=1" + CRLF
          + "[WinDrv.WindowsClient]" + CRLF + "FullscreenViewportX=1920" + CRLF)

JEU = {
    "id": "hp1", "name": "HP1", "year": 2001, "description": "d",
    "developer": "dev", "executable": "HP1/System/HP.exe", "cover_image": "c.png",
    "post_install": {"config_files": [
        {"source": "config/HP.ini",
         "destination": "~/Documents/Harry Potter/HP.ini"},
        {"source": "config/User.ini",
         "destination": "~/Documents/Harry Potter/User.ini"},
    ]},
    "pre_launch": {"ini_patches": [
        {"file": "%DOCUMENTS%" + B + "Harry Potter" + B + "HP.ini",
         "section": "FirstRun", "key": "Reconfig", "value": "0"},
    ]},
}


@pytest.fixture
def poste(tmp_path):
    """Un jeu installé avec sa configuration livrée, et un profil Documents vide."""
    install = tmp_path / "jeux"
    livree = install / "HP1" / "config"
    livree.mkdir(parents=True)
    (livree / "HP.ini").write_bytes(REGLEE.encode(_INI_ENCODING))
    (livree / "User.ini").write_bytes(b"[Engine.Input]\r\nSpace=Jump\r\n")
    profil = tmp_path / "Documents" / "Harry Potter"
    return GameData.from_dict(JEU), Config(install_path=install), profil


class TestUneConfigDisparueRevient:

    def test_l_ini_revient_regle_puis_patche(self, poste):
        jeu, config, profil = poste
        restaurer_configs_manquantes(jeu, config)
        apply_ini_patches(jeu, config)
        texte = (profil / "HP.ini").read_text(encoding=_INI_ENCODING)
        assert "FullscreenViewportX=1920" in texte, "ce n'est pas la config réglée"
        assert "Reconfig=0" in texte, "les patchs ont encore sauté le fichier"

    def test_sans_restauration_les_patchs_ne_font_rien(self, poste):
        """Le défaut d'origine, gardé comme témoin : un patch saute un
        fichier absent, et c'est le moteur qui le recrée — mal."""
        jeu, config, profil = poste
        apply_ini_patches(jeu, config)
        assert not (profil / "HP.ini").exists()


class TestUneConfigPresenteAppartientAuJoueur:

    def test_une_config_modifiee_n_est_ni_reecrite_ni_doublee(self, poste):
        jeu, config, profil = poste
        profil.mkdir(parents=True)
        (profil / "HP.ini").write_bytes(b"[FirstRun]\r\nMaResolution=800x600\r\n")
        (profil / "User.ini").write_bytes(b"mes touches")
        avant = {f.name: f.read_bytes() for f in profil.iterdir()}
        restaurer_configs_manquantes(jeu, config)
        apres = {f.name: f.read_bytes() for f in profil.iterdir()}
        # Un `.bak` apparu compterait aussi : la copie de l'installation en
        # pose un dès qu'elle remplace quelque chose.
        assert apres == avant

    def test_seul_le_fichier_manquant_revient(self, poste):
        jeu, config, profil = poste
        profil.mkdir(parents=True)
        (profil / "HP.ini").write_bytes(b"du joueur")
        restaurer_configs_manquantes(jeu, config)
        assert (profil / "HP.ini").read_bytes() == b"du joueur"
        assert (profil / "User.ini").read_bytes().startswith(b"[Engine.Input]")


class TestRienNeBloqueLeLancement:

    def test_une_source_absente_ne_leve_rien(self, poste):
        jeu, config, profil = poste
        for fichier in (config.install_path / "HP1" / "config").iterdir():
            fichier.unlink()
        restaurer_configs_manquantes(jeu, config)
        assert not (profil / "HP.ini").exists()

    def test_un_jeu_sans_config_livree_n_ecrit_rien(self, tmp_path):
        jeu = GameData.from_dict({k: v for k, v in JEU.items()
                                  if k != "post_install"})
        restaurer_configs_manquantes(jeu, Config(install_path=tmp_path / "jeux"))
        assert not (tmp_path / "Documents").exists()

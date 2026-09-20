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


def _manager_avec_jeu(tmp_path, game_id: str):
    """Un manager dont le jeu demandé est installé pour de faux : l'exécutable
    existe, les prérequis sont réputés présents."""
    from unittest.mock import patch as _patch

    from src.core.config import Config
    from src.core.game_data import load_catalog
    from src.core.game_manager import GameManager

    catalogue = load_catalog()
    jeu = next(g for g in catalogue.games if g.id == game_id)
    exe = tmp_path / "jeux" / jeu.executable
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    config = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache")
    with _patch("src.core.game_manager.load_catalog", return_value=catalogue):
        manager = GameManager(config)
    return manager


class TestDossierDocumentsInutilisable:
    """Trois jeux sur huit écrivent dans Documents ; si Windows n'y donne pas
    accès, ils plantent à l'initialisation avec un message à eux.

    Cas réel du 2026-09-20 : HP1, HP2 et HP3 en échec (« General protection
    fault! History: appInit ») pendant que les cinq autres tournaient, et le
    journal du launcher portait déjà un `[WinError 2]` en créant le dossier.
    """

    def test_seuls_les_jeux_qui_y_ecrivent_sont_concernes(self):
        from src.core.game_data import load_catalog
        from src.core.pre_launch import besoin_de_documents
        besoin = {g.id: besoin_de_documents(g) for g in load_catalog().games}
        assert [gid for gid, b in besoin.items() if b] == ["hp1", "hp2", "hp3"]

    def test_un_documents_normal_ne_gene_personne(self, tmp_path, monkeypatch):
        from src.core import pre_launch
        monkeypatch.setattr(pre_launch, "get_documents_dir", lambda: tmp_path / "Docs")
        assert pre_launch.documents_inutilisable() is None
        assert (tmp_path / "Docs").is_dir()      # créé au besoin, comme le fera le jeu

    def test_un_documents_inaccessible_est_signale(self, tmp_path, monkeypatch):
        """La sonde ÉCRIT : `os.access` ment sous Windows, et un dossier qui
        existe peut refuser l'écriture."""
        from src.core import pre_launch
        fichier = tmp_path / "pas-un-dossier"
        fichier.write_text("x", encoding="utf-8")
        monkeypatch.setattr(pre_launch, "get_documents_dir", lambda: fichier / "Documents")
        assert pre_launch.documents_inutilisable() == fichier / "Documents"

    def test_le_lancement_refuse_avant_de_faire_planter_le_jeu(self, tmp_path, monkeypatch):
        from src.core import game_manager as gm
        manager = _manager_avec_jeu(tmp_path, "hp1")
        monkeypatch.setattr(gm, "documents_inutilisable", lambda: tmp_path / "Docs")
        lances = []
        monkeypatch.setattr(gm.subprocess, "Popen", lambda *a, **k: lances.append(a))
        with pytest.raises(RuntimeError) as erreur:
            manager.launch_game("hp1")
        assert str(erreur.value).startswith("documents_inutilisable:")
        assert str(tmp_path / "Docs") in str(erreur.value)
        assert not lances, "le jeu ne doit PAS être lancé"

    def test_un_jeu_qui_n_en_a_pas_besoin_se_lance(self, tmp_path, monkeypatch):
        """HP5 à HP7 écrivent dans AppData : un Documents cassé ne les regarde
        pas, et les bloquer serait inventer une panne."""
        from src.core import game_manager as gm
        manager = _manager_avec_jeu(tmp_path, "hp5")
        monkeypatch.setattr(gm, "documents_inutilisable", lambda: tmp_path / "Docs")
        monkeypatch.setattr(gm, "prerequis_manquants", lambda *a: [])
        lances = []
        monkeypatch.setattr(gm.subprocess, "Popen",
                            lambda *a, **k: lances.append(a) or object())
        manager.launch_game("hp5")
        assert lances, "HP5 doit démarrer"

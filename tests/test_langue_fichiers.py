"""Langue d'un jeu portée par ses FICHIERS (bloc `language_files`, HP1).

HP1 lit sa langue dans `Language=` de `HP.ini` ET de `System\\Default.ini`
(avec `Running.ini` présent, c'est Default.ini qui décide), et charge
l'écran `Help\\splash<langue>.bmp` au démarrage — que l'archive n'a qu'en
français. VU en jeu le 2026-09-26 : les deux clés plus un `splashint.bmp`
donnent HP1 en anglais ; sans le bmp, « Assertion failed: Bitmap.LoadFile ».
"""

import pytest

from src.core import game_language
from src.core.config import Config
from src.core.game_data import GameData
from src.core.pre_launch import _INI_ENCODING

B = chr(92)
CRLF = "\r\n"


def _cle(fichier, valeur):
    return {"file": fichier, "section": "Engine.Engine", "key": "Language", "value": valeur}


HP_INI = "%DOCUMENTS%" + B + "Harry Potter" + B + "HP.ini"
DEFAULT_INI = "%INSTALL_DIR%" + B + "System" + B + "Default.ini"

BLOC = {"languages": {
    "fr": {"label": "Français", "requires_file": "HP1/Sounds/AllDialog.fre_uax",
           "ini": [_cle(HP_INI, "fre"), _cle(DEFAULT_INI, "fre")]},
    "en": {"label": "English", "requires_file": "HP1/Sounds/AllDialog.uax",
           "ini": [_cle(HP_INI, "int"), _cle(DEFAULT_INI, "int")],
           "copy": [{"from": "HP1/Help/Splash0.bmp", "to": "HP1/Help/splashint.bmp"}]},
}}


def _jeu(bloc=BLOC, **extra):
    return GameData.from_dict({
        "id": "hp1", "name": "HP1", "year": 2001, "description": "d", "developer": "dev",
        "executable": "HP1/System/HP.exe", "cover_image": "c.png",
        "language_files": bloc, **extra})


def _ini(langue):
    return ("[URL]" + CRLF + "Protocol=unreal" + CRLF
            + "[Engine.Engine]" + CRLF + "GameRenderDevice=D3D11Drv.D3D11RenderDevice" + CRLF
            + "Language=" + langue + CRLF
            + "[Core.System]" + CRLF + "SavePath=..\\Save" + CRLF)


@pytest.fixture
def hp1(tmp_path, monkeypatch):
    """Une installation de HP1 en français, telle que l'archive la pose."""
    docs = (tmp_path / "Documents").resolve()
    jeux = (tmp_path / "Games").resolve()
    (docs / "Harry Potter").mkdir(parents=True)
    for rel in ("System", "Help", "Sounds"):
        (jeux / "HP1" / rel).mkdir(parents=True)
    (docs / "Harry Potter" / "HP.ini").write_bytes(_ini("fre").encode(_INI_ENCODING))
    (jeux / "HP1" / "System" / "Default.ini").write_bytes(_ini("fre").encode(_INI_ENCODING))
    (jeux / "HP1" / "Help" / "Splash0.bmp").write_bytes(b"BM-splash0")
    (jeux / "HP1" / "Help" / "splashfre.bmp").write_bytes(b"BM-fre")
    (jeux / "HP1" / "Sounds" / "AllDialog.fre_uax").write_bytes(b"fr")
    (jeux / "HP1" / "Sounds" / "AllDialog.uax").write_bytes(b"en")
    monkeypatch.setattr("src.core.pre_launch.get_documents_dir", lambda: docs)
    return _jeu(), Config(install_path=jeux), docs, jeux


def _langue_de(chemin):
    texte = chemin.read_bytes().decode(_INI_ENCODING)
    return next(ligne.split("=", 1)[1] for ligne in texte.split(CRLF) if ligne.startswith("Language="))


class TestCatalogue:
    def test_le_bloc_est_lu(self):
        jeu = _jeu()
        assert jeu.language_files is not None
        assert jeu.langues is jeu.language_files
        assert jeu.langues.codes == ("fr", "en")
        assert jeu.langues.get("en").copies == (("HP1/Help/Splash0.bmp", "HP1/Help/splashint.bmp"),)

    @pytest.mark.parametrize("modif", [
        lambda b: b["languages"]["en"]["ini"][0].update(value="int\r\n[Hack]"),     # une ligne de plus
        lambda b: b["languages"]["en"]["ini"][0].update(key="Lang]uage"),
        lambda b: b["languages"]["en"]["ini"][0].update(file="C:" + B + "Windows" + B + "win.ini"),
        lambda b: b["languages"]["en"]["ini"][0].update(file="%DOCUMENTS%" + B + ".." + B + "x.ini"),
        lambda b: b["languages"]["en"]["ini"][0].update(file="C:" + B + "x%DOCUMENTS%.ini"),
        lambda b: b["languages"]["en"]["copy"][0].update(to="../../evil.dll"),
        lambda b: b["languages"]["en"].update(requires_file="C:/x"),
        lambda b: b["languages"]["en"].update(ini=[]),
        lambda b: b["languages"].update({"../x": b["languages"]["en"]}),
    ])
    def test_un_bloc_douteux_est_ignore_en_entier(self, modif):
        import copy
        bloc = copy.deepcopy(BLOC)
        modif(bloc)
        assert _jeu(bloc).language_files is None

    def test_le_registre_l_emporte_s_il_est_declare(self):
        jeu = _jeu(language_registry={"root": "HKCU", "key": "Software\\X", "languages": {
            "fr": {"values": {"Language": "French"}}}})
        assert jeu.language_files is None
        assert jeu.langues is jeu.language_registry

    def test_greffe_d_un_registre_sur_un_jeu_a_fichiers(self, tmp_path):
        """Cas réel : un test greffait un registre sur HP1 (qui a ses fichiers).
        Tester `language_files` d'abord partait copier des fichiers absents,
        échouait, et ouvrait un modal que personne ne fermait — suite bloquée."""
        import dataclasses
        registre = _jeu(language_registry={"root": "HKCU", "key": "Software\\X", "languages": {
            "fr": {"values": {"Language": "French"}}}}).language_registry
        jeu = dataclasses.replace(_jeu(), language_registry=registre)
        assert not jeu.langue_par_fichiers
        assert jeu.langues is registre
        assert _jeu().langue_par_fichiers


class TestDetection:
    def test_l_installation_d_origine_est_en_francais(self, hp1):
        jeu, config, _, _ = hp1
        assert game_language.detecter(jeu, config) == "fr"
        assert game_language.resoudre(jeu, config) == "fr"

    def test_deux_fichiers_qui_divergent_ne_font_pas_une_langue(self, hp1):
        jeu, config, docs, _ = hp1
        (docs / "Harry Potter" / "HP.ini").write_bytes(_ini("int").encode(_INI_ENCODING))
        assert game_language.detecter(jeu, config) is None

    def test_ne_depend_pas_du_registre(self, hp1, monkeypatch):
        """Sous Linux sans préfixe prêt, le registre est injoignable : une
        langue portée par des fichiers doit rester réglable."""
        jeu, config, _, _ = hp1
        monkeypatch.setattr("src.core.game_language.registre.disponible", lambda: False)
        assert game_language.resoudre(jeu, config) == "fr"

    def test_les_deux_langues_sont_sur_le_disque(self, hp1):
        jeu, config, _, jeux = hp1
        assert [lg.code for lg in game_language.langues_disponibles(jeu, config)] == ["fr", "en"]
        (jeux / "HP1" / "Sounds" / "AllDialog.uax").unlink()
        assert [lg.code for lg in game_language.langues_disponibles(jeu, config)] == ["fr"]


class TestAppliquer:
    def test_l_anglais_pose_les_deux_cles_et_l_ecran_de_demarrage(self, hp1):
        jeu, config, docs, jeux = hp1
        assert game_language.appliquer(jeu, config, "en")
        assert _langue_de(docs / "Harry Potter" / "HP.ini") == "int"
        assert _langue_de(jeux / "HP1" / "System" / "Default.ini") == "int"
        assert (jeux / "HP1" / "Help" / "splashint.bmp").read_bytes() == b"BM-splash0"
        assert game_language.detecter(jeu, config) == "en"

    def test_le_reste_du_fichier_ne_bouge_pas(self, hp1):
        jeu, config, docs, _ = hp1
        game_language.appliquer(jeu, config, "en")
        assert (docs / "Harry Potter" / "HP.ini").read_bytes() == _ini("int").encode(_INI_ENCODING)

    def test_sans_ecran_de_demarrage_la_langue_n_est_pas_posee(self, hp1):
        """Le jeu s'arrêterait au démarrage : mieux vaut l'ancienne langue."""
        jeu, config, docs, jeux = hp1
        (jeux / "HP1" / "Help" / "Splash0.bmp").unlink()
        assert not game_language.appliquer(jeu, config, "en")
        assert _langue_de(docs / "Harry Potter" / "HP.ini") == "fre"
        assert _langue_de(jeux / "HP1" / "System" / "Default.ini") == "fre"

    def test_un_ecran_deja_present_n_est_pas_ecrase(self, hp1):
        jeu, config, _, jeux = hp1
        (jeux / "HP1" / "Help" / "splashint.bmp").write_bytes(b"BM-du-joueur")
        assert game_language.appliquer(jeu, config, "en")
        assert (jeux / "HP1" / "Help" / "splashint.bmp").read_bytes() == b"BM-du-joueur"

    def test_rien_n_est_reecrit_quand_c_est_deja_la_bonne_langue(self, hp1):
        jeu, config, docs, _ = hp1
        ini = docs / "Harry Potter" / "HP.ini"
        avant = ini.stat().st_mtime_ns
        assert game_language.appliquer(jeu, config, "fr")
        assert ini.stat().st_mtime_ns == avant

    def test_aucune_invite_n_est_demandee(self, hp1):
        jeu, config, _, _ = hp1

        def confirmer(*_a, **_k):
            raise AssertionError("une langue par fichiers ne touche pas au registre")
        assert game_language.appliquer(jeu, config, "en", confirmer=confirmer)

    def test_le_retour_au_francais(self, hp1):
        jeu, config, docs, jeux = hp1
        game_language.appliquer(jeu, config, "en")
        assert game_language.appliquer(jeu, config, "fr")
        assert _langue_de(docs / "Harry Potter" / "HP.ini") == "fre"
        assert _langue_de(jeux / "HP1" / "System" / "Default.ini") == "fre"


class TestAuLancement:
    def test_la_langue_passe_apres_la_restauration_d_un_ini_disparu(self, hp1, monkeypatch):
        """HP.ini effacé de Documents : le lancement le recopie depuis l'archive
        (en français). Posée AVANT, la langue choisie aurait été écrasée."""
        from unittest.mock import patch
        from src.core.game_data import Catalog
        from src.core.game_manager import GameManager
        _, config, docs, jeux = hp1
        jeu = _jeu(post_install={"config_files": [
            {"source": "config/HP.ini", "destination": "~/Documents/Harry Potter/HP.ini"}]})
        (jeux / "HP1" / "config").mkdir()
        (jeux / "HP1" / "config" / "HP.ini").write_bytes(_ini("fre").encode(_INI_ENCODING))
        (jeux / "HP1" / "System" / "HP.exe").write_bytes(b"")
        (docs / "Harry Potter" / "HP.ini").unlink()
        for module in ("src.core.post_install", "src.core.pre_launch"):
            monkeypatch.setattr(module + ".get_documents_dir", lambda: docs)
        monkeypatch.setattr("src.core.game_manager.prerequis_manquants", lambda _r: [])
        monkeypatch.setattr("src.core.game_manager.unblock_game_dlls", lambda _p: None)
        monkeypatch.setattr("src.core.game_manager.subprocess.Popen", lambda *a, **k: object())
        catalogue = Catalog(catalog_version="1.0", catalog_url="", games=(jeu,))
        with patch("src.core.config.CONFIG_FILE_PATH", jeux / "config.json"), \
                patch("src.core.game_manager.load_catalog", return_value=catalogue):
            m = GameManager(config)
            m.set_game_language("hp1", "en")
            avertis = []
            assert m.launch_game("hp1", avertir=lambda: avertis.append(1)) is not None
        assert _langue_de(docs / "Harry Potter" / "HP.ini") == "int"
        assert _langue_de(jeux / "HP1" / "System" / "Default.ini") == "int"
        assert (jeux / "HP1" / "Help" / "splashint.bmp").exists()
        assert avertis == []

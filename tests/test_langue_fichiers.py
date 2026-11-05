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

    def test_par_defaut_la_langue_du_launcher(self, hp1, monkeypatch):
        """L'archive porte le français : un launcher en anglais donnait quand
        même HP1 en français, et le joueur abandonnait (Ludo, 2026-11-03)."""
        jeu, config, _, _ = hp1
        monkeypatch.setattr("src.core.game_language.get_language", lambda: "en")
        assert game_language.detecter(jeu, config) == "fr"
        assert game_language.resoudre(jeu, config) == "en"

    def test_le_choix_du_joueur_gagne_sur_la_langue_du_launcher(self, hp1, monkeypatch):
        jeu, config, _, _ = hp1
        monkeypatch.setattr("src.core.game_language.get_language", lambda: "en")
        config.game_language["hp1"] = "fr"
        assert game_language.resoudre(jeu, config) == "fr"

    def test_une_langue_du_launcher_absente_du_disque_garde_ce_que_portent_les_fichiers(self, hp1, monkeypatch):
        """Launcher en espagnol, HP1 sans voix espagnoles : ce que les fichiers portent."""
        jeu, config, _, _ = hp1
        monkeypatch.setattr("src.core.game_language.get_language", lambda: "es")
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


class TestCatalogueEmbarque:
    """Les langues que le catalogue embarqué propose pour HP1 et HP2 (2026-11-03) :
    espagnol de l'édition US 2003 de HP1 ; anglais (`usa`) et espagnol (`spa`) du
    disque US de HP2. Chaque langue écrit le Documents ET le `default.ini` du jeu,
    et ne s'affiche que si ses voix sont dans l'archive."""

    @staticmethod
    def _bloc(jeu):
        import json

        from src.core.config import ASSETS_DIR
        catalogue = json.loads((ASSETS_DIR.parent / "src" / "data" / "games.json").read_text(encoding="utf-8"))
        return next(g for g in catalogue["games"] if g["id"] == jeu)["language_files"]["languages"]

    @pytest.mark.parametrize(("jeu", "attendu"), [
        ("hp1", {"fr": "fre", "en": "int", "es": "spa"}),
        ("hp2", {"fr": "fre", "en": "usa", "es": "spa"}),
    ])
    def test_trois_langues_dans_les_deux_fichiers(self, jeu, attendu):
        bloc = self._bloc(jeu)
        assert {code: {p["value"] for p in lg["ini"]} for code, lg in bloc.items()} == {
            code: {v} for code, v in attendu.items()}
        for lg in bloc.values():
            fichiers = [p["file"] for p in lg["ini"]]
            assert len(fichiers) == 2 and fichiers[0].startswith("%DOCUMENTS%")
            assert fichiers[1].startswith("%INSTALL_DIR%") and lg["requires_file"].startswith(jeu.upper() + "/Sounds/")


class TestHP3Langues:
    """Les onze langues de HP3, réunies depuis quatre éditions européennes du CD
    (2026-11-04). Le dossier de Documents de HP3 porte le titre TRADUIT : Core.dll
    lit `[Core.System] AppUserDir` dans Default.ini, livré « loc: … gametitle_1 ».
    Sans le figer, passer en anglais ouvrait « Harry Potter and the Prisoner of
    Azkaban » : ni la partie, ni les réglages (essai du 2026-11-04)."""

    ATTENDU = {"fr": "Fre", "en": "int", "es": "Spa", "de": "Ger", "it": "Ita", "pt": "Por",
               "pt-BR": "Bra", "nl": "Dut", "sv": "Swe", "da": "Dan", "no": "Nor"}

    @staticmethod
    def _jeu():
        import json

        from src.core.config import ASSETS_DIR
        catalogue = json.loads((ASSETS_DIR.parent / "src" / "data" / "games.json").read_text(encoding="utf-8"))
        return next(g for g in catalogue["games"] if g["id"] == "hp3")

    def test_invisible_pour_le_launcher_1_3_2(self):
        """La 1.3.2 lit `language_files` et écrit Default.ini sans lui rendre sa date :
        HP3 recréait alors les réglages du joueur, dès l'entrée `fr` (son `AppUserDir`)
        avec HP3 1.6. Les langues de HP3 vivent donc sous `language_files_v2`, que
        seule la 1.3.3 lit (2026-11-05)."""
        jeu = self._jeu()
        assert "language_files" not in jeu and "language_files_v2" in jeu
        assert GameData.from_dict(jeu).language_files is not None

    def test_v2_passe_avant_l_ancien_bloc(self):
        v2 = self._jeu()["language_files_v2"]
        ancien = {"languages": {"fr": v2["languages"]["fr"]}}
        game = GameData.from_dict({
            "id": "hp3", "name": "HP3", "year": 2004, "description": "d", "developer": "dev",
            "executable": "HP3/system/hppoa.exe", "cover_image": "c.png",
            "language_files": ancien, "language_files_v2": v2})
        assert game.language_files is not None and game.language_files.codes == tuple(self.ATTENDU)

    def test_onze_langues_et_leurs_voix(self):
        bloc = self._jeu()["language_files_v2"]["languages"]
        assert {code: lg["ini"][0]["value"] for code, lg in bloc.items()} == self.ATTENDU
        for code, lg in bloc.items():
            valeur = self.ATTENDU[code]
            voix = "alldialog.uax" if valeur == "int" else f"alldialog.{valeur.lower()}_uax"
            assert lg["requires_file"] == f"HP3/sounds/{voix}"

    def test_chaque_langue_garde_le_meme_dossier_de_documents(self):
        jeu = self._jeu()
        dossier = "Harry Potter et le prisonnier d'Azkaban"
        # Le dossier figé est celui où le launcher écrit la config et cherche les parties.
        assert all(dossier in p["file"] for p in jeu["pre_launch"]["ini_patches"])
        for lg in jeu["language_files_v2"]["languages"].values():
            par_cle = {(p["file"], p["section"], p["key"]): p["value"] for p in lg["ini"]}
            assert par_cle[("%INSTALL_DIR%\\system\\Default.ini", "Core.System", "AppUserDir")] == dossier
            assert par_cle[("%DOCUMENTS%\\" + dossier + "\\hppoa.ini", "Engine.Engine", "Language")] \
                == par_cle[("%INSTALL_DIR%\\system\\Default.ini", "Engine.Engine", "Language")]

    def test_le_bloc_se_lit(self):
        from src.core.catalogue_blocs import _parse_language_files
        lu = _parse_language_files(self._jeu()["language_files_v2"])
        assert lu is not None and lu.codes == tuple(self.ATTENDU)

    def test_appliquer_fige_le_dossier(self, tmp_path, monkeypatch):
        """De bout en bout sur un faux HP3 : l'anglais posé, `loc:` remplacé."""
        docs = (tmp_path / "docs").resolve()
        (docs / "Harry Potter et le prisonnier d'Azkaban").mkdir(parents=True)
        (docs / "Harry Potter et le prisonnier d'Azkaban" / "hppoa.ini").write_text(
            "[Engine.Engine]\r\nLanguage=Fre\r\n", encoding="cp1252", newline="")
        jeux = (tmp_path / "jeux").resolve()
        jeu_dir = jeux / "HP3"
        (jeu_dir / "system").mkdir(parents=True)
        (jeu_dir / "sounds").mkdir()
        (jeu_dir / "sounds" / "alldialog.uax").write_bytes(b"x")
        (jeu_dir / "system" / "Default.ini").write_text(
            "[Engine.Engine]\r\nLanguage=Fre\r\n[Core.System]\r\n"
            "AppUserDir=loc: SECTION=All KEY=gametitle_1 PACKAGE=HPMenu DEFAULT=HPPOA\r\n",
            encoding="cp1252", newline="")
        monkeypatch.setattr("src.core.pre_launch.get_documents_dir", lambda: docs)
        game = GameData.from_dict({
            "id": "hp3", "name": "HP3", "year": 2004, "description": "d", "developer": "dev",
            "executable": "HP3/system/hppoa.exe", "cover_image": "c.png",
            "language_files_v2": self._jeu()["language_files_v2"]})
        config = Config(install_path=jeux)
        assert [lg.code for lg in game_language.langues_disponibles(game, config)] == ["en"]
        assert game_language.appliquer(game, config, "en")
        defaut = (jeu_dir / "system" / "Default.ini").read_text(encoding="cp1252")
        assert "Language=int" in defaut and "AppUserDir=Harry Potter et le prisonnier d'Azkaban" in defaut
        assert "loc:" not in defaut
        assert game_language.detecter(game, config) == "en"

    def test_default_ini_garde_sa_date(self, tmp_path, monkeypatch):
        """HP3 recrée hppoa.ini et User.ini dès que Default.ini est plus récent que
        hppoa.ini (800×600, manette coupée, touches perdues ; VU le 2026-11-04) :
        poser la langue ne doit pas rajeunir Default.ini."""
        import os
        docs = (tmp_path / "docs").resolve()
        dossier = docs / "Harry Potter et le prisonnier d'Azkaban"
        dossier.mkdir(parents=True)
        (dossier / "hppoa.ini").write_text("[Engine.Engine]\r\nLanguage=Fre\r\n", encoding="cp1252", newline="")
        jeux = (tmp_path / "jeux").resolve()
        (jeux / "HP3" / "system").mkdir(parents=True)
        (jeux / "HP3" / "sounds").mkdir()
        (jeux / "HP3" / "sounds" / "alldialog.ger_uax").write_bytes(b"x")
        defaut = jeux / "HP3" / "system" / "Default.ini"
        defaut.write_text("[Engine.Engine]\r\nLanguage=Fre\r\n[Core.System]\r\nAppUserDir=loc: X\r\n",
                          encoding="cp1252", newline="")
        vieux = 1_760_000_000
        os.utime(defaut, (vieux, vieux))
        os.utime(dossier / "hppoa.ini", (vieux + 100, vieux + 100))
        monkeypatch.setattr("src.core.pre_launch.get_documents_dir", lambda: docs)
        game = GameData.from_dict({
            "id": "hp3", "name": "HP3", "year": 2004, "description": "d", "developer": "dev",
            "executable": "HP3/system/hppoa.exe", "cover_image": "c.png",
            "language_files_v2": self._jeu()["language_files_v2"]})
        assert game_language.appliquer(game, Config(install_path=jeux), "de")
        assert "Language=Ger" in defaut.read_text(encoding="cp1252")
        assert defaut.stat().st_mtime == vieux                       # contenu neuf, date d'avant
        assert (dossier / "hppoa.ini").stat().st_mtime > defaut.stat().st_mtime

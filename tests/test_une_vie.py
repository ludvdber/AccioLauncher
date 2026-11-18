"""Une seule vie (Réaliste, Impardonnable) : le dossier du mode, les clés du correctif, la partie
qui le joue, et ce que le joueur en voit (atelier, `notes/DIFFICULTE_1.4.md` § 6 et § 9 ; C4, C5)."""
import dataclasses
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import compteur_morts, sauvegardes, succes, une_vie
from src.core import difficulte_presets as dp
from src.core import reglages_correctif as rc
from src.core.game_data import load_catalog

_CATALOGUE = {g.id: g for g in load_catalog().games}

# Les lignes du correctif livré (`[Accio.Game]` de HP4 à HP6, valeurs d'origine).
INI = "\r\n".join([
    "; Accio Launcher - PC fix", "[Accio.Window]", "WindowStyle=0", "",
    "[Accio.Hardcore]", "DamageTaken=1", "DamageDealt=1", "EnemyReaction=1", "",
    "[Accio.Game]", "QuidditchDifficulty=0", "OneLife=0", "DeathCounter=0", "OneLifeSaves=", "",
]) + "\r\n"


def _racine(nom: str) -> Path:
    return sauvegardes.racines()[nom]


def _installer(tmp_path: Path, jeu: str, ini: str = INI) -> Path:
    """L'ini du nouveau correctif à côté de l'exe du jeu installé dans `tmp_path`."""
    game = _CATALOGUE[jeu]
    nom = {"hp1": "winmm.ini", "hp2": "winmm.ini", "hp3": "dinput8.ini"}.get(jeu, "d3d9.ini")
    chemin = tmp_path / Path(game.executable).parent / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(ini.encode("ascii"))
    return chemin


def _valeurs(chemin: Path) -> dict[str, str | None]:
    return {cle: rc.valeur_posee(chemin, une_vie.SECTION, cle)
            for cle in (une_vie.CLE_MODE, une_vie.CLE_COMPTEUR, une_vie.CLE_DOSSIER)}


class TestDossier:
    def test_un_dossier_par_jeu_nomme_save_unevie(self):
        docs, local = _racine("documents"), _racine("localappdata")
        assert une_vie.dossier(_CATALOGUE["hp1"]) == docs / "Harry Potter" / "Save_UneVie"
        assert une_vie.dossier(_CATALOGUE["hp2"]) == docs / "Harry Potter II" / "Save_UneVie" / "Slot7"
        for jeu in ("hp4", "hp5", "hp6"):
            assert une_vie.dossier(_CATALOGUE[jeu]) == local / "Save_UneVie" / jeu.upper()
        assert une_vie.dossier(_CATALOGUE["hp7a"]) is None, "HP7 et HP8 : de côté"

    def test_hp3_garde_le_meme_dossier_quand_le_jeu_cree_le_sien(self):
        """Le dossier du joueur suit la langue jouée : celui du mode, posé dans l'ini, ne bouge pas."""
        attendu = _racine("documents") / "Harry Potter et le prisonnier d'Azkaban" / "Save_UneVie"
        assert une_vie.dossier(_CATALOGUE["hp3"]) == attendu
        (_racine("documents") / "Harry Potter and the Prisoner of Azkaban" / "Save").mkdir(parents=True)
        assert une_vie.dossier(_CATALOGUE["hp3"]) == attendu

    @pytest.mark.parametrize("jeu", ["hp1", "hp2", "hp3", "hp4", "hp5", "hp6"])
    def test_les_parties_du_mode_ne_se_melent_pas_a_celles_du_joueur(self, jeu):
        """`sauvegardes.json` range une partie par chemin relatif : celui du mode ne peut pas être le sien."""
        game = _CATALOGUE[jeu]
        mode = une_vie.spec_du_mode(game)
        assert mode is not None
        nom = {"hp1": "Save0.usa", "hp2": "Slot7/Save0.usa", "hp3": "Save0.usa", "hp4": "HPGOF",
               "hp5": "HPOOTP", "hp6": "HPHBP0/HPHBP0"}[jeu]
        if jeu in ("hp4", "hp5", "hp6"):
            titre = {"hp4": "Harry Potter and the Goblet of Fire/HPGOF",
                     "hp5": "Harry Potter and the Order of the Phoenix/HPOOTP",
                     "hp6": "Harry Potter and the Half Blood Prince"}[jeu]
            dans_le_mode = une_vie.dossier(game) / "Electronic Arts" / titre / nom
            chez_le_joueur = _racine("localappdata") / "Electronic Arts" / titre / nom
        else:
            dans_le_mode = (une_vie.dossier(game).parent if jeu == "hp2" else une_vie.dossier(game)) / nom
            chez_le_joueur = sauvegardes.racines()["documents"] / Path(game.sauvegardes.dossiers[0].replace(
                "*", " and the Prisoner of ")) / ("Slot1/Save0.usa" if jeu == "hp2" else nom)
        for chemin in (dans_le_mode, chez_le_joueur):
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(b"\0" * 0x600)
        du_mode = set(sauvegardes.fichiers(une_vie.spec_du_mode(game)))
        du_joueur = set(sauvegardes.fichiers(game.sauvegardes))
        assert du_mode and du_joueur and not du_mode & du_joueur, (du_mode, du_joueur)

    def test_un_chemin_que_le_correctif_refuserait_n_est_pas_propose(self, tmp_path):
        assert une_vie.pour_le_jeu(tmp_path / "Save_UneVie") is not None
        long = tmp_path / ("x" * 160) / "Save_UneVie"
        assert une_vie.pour_le_jeu(long, plafond=True) is None, "HP4 à HP6 : plus de 150 caractères"
        assert une_vie.pour_le_jeu(long) is not None, "HP1 à HP3 : pas de plafond relevé"
        assert une_vie.pour_le_jeu(tmp_path / "a;b" / "Save_UneVie") is None, "coupé au commentaire"
        assert une_vie.pour_le_jeu(tmp_path / "" / "Save_UneVie") is None, "hors de la page de codes"


class TestCles:
    def test_entrer_pose_les_trois_cles_et_cree_le_dossier(self, tmp_path):
        ini = _installer(tmp_path, "hp6")
        assert une_vie.ini(_CATALOGUE["hp6"], tmp_path) == ini
        assert une_vie.entrer(_CATALOGUE["hp6"], ini)
        ou = une_vie.dossier(_CATALOGUE["hp6"])
        assert _valeurs(ini) == {"OneLife": "1", "DeathCounter": "1", "OneLifeSaves": str(ou)}
        assert ou.is_dir() and une_vie.actif(ini)

    def test_hp5_se_ferme_a_la_fin_de_vie(self, tmp_path):
        """Le retour au menu n'est vu que sur un KO forgé : la voie sûre, le jeu se ferme."""
        ini = _installer(tmp_path, "hp5")
        assert une_vie.entrer(_CATALOGUE["hp5"], ini)
        assert _valeurs(ini)["OneLife"] == "2"

    def test_sortir_remet_l_ini_livre_et_n_efface_rien(self, tmp_path):
        ini = _installer(tmp_path, "hp1")
        game = _CATALOGUE["hp1"]
        une_vie.entrer(game, ini)
        partie = une_vie.dossier(game) / "Save0.usa"
        partie.write_bytes(b"vie")
        assert une_vie.sortir(ini)
        assert _valeurs(ini) == {"OneLife": "0", "DeathCounter": "0", "OneLifeSaves": ""}
        assert partie.read_bytes() == b"vie", "le launcher n'efface jamais rien"
        assert not une_vie.actif(ini)

    def test_sortir_reprend_les_valeurs_de_l_origine(self, tmp_path):
        ini = _installer(tmp_path, "hp6")
        rc.chemin_origine(ini).write_bytes(INI.replace("DeathCounter=0", "DeathCounter=1").encode("ascii"))
        une_vie.entrer(_CATALOGUE["hp6"], ini)
        une_vie.sortir(ini)
        assert _valeurs(ini)["DeathCounter"] == "1"

    def test_un_correctif_sans_les_cles_n_a_pas_le_mode(self, tmp_path):
        _installer(tmp_path, "hp6", INI.replace("OneLife=0\r\n", ""))
        assert une_vie.ini(_CATALOGUE["hp6"], tmp_path) is None
        assert not dp.une_vie_proposee(_CATALOGUE["hp6"], SimpleNamespace(install_path=tmp_path))

    def test_une_section_absente_laisse_le_mode_coupe(self, tmp_path):
        """`OneLife` se pose en DERNIER : un échec en route ne lance pas le mode à moitié."""
        ini = tmp_path / "d3d9.ini"
        ini.write_bytes(b"; Accio\r\n[Accio.Window]\r\n")
        assert not une_vie.entrer(_CATALOGUE["hp6"], ini)
        assert rc.valeur_posee(ini, une_vie.SECTION, une_vie.CLE_MODE) is None


class TestEtat:
    def test_marque_presente_vie_finie_sinon_en_cours_avec_des_parties(self, tmp_path):
        game = _CATALOGUE["hp1"]
        ou = une_vie.dossier(game)
        ou.mkdir(parents=True)
        assert une_vie.etat(game) == une_vie.Etat()
        (ou / "Save0.usa").write_bytes(b"x")
        assert une_vie.etat(game) == une_vie.Etat(en_cours=True)
        (ou / une_vie.MARQUE).write_bytes(b"")
        assert une_vie.etat(game) == une_vie.Etat(finie=True), "la DLL retire au lancement suivant ce qui reste"


class TestLancement:
    def test_hp2_toujours_sur_son_emplacement(self, tmp_path):
        game = _CATALOGUE["hp2"]
        ini = _installer(tmp_path, "hp2")
        assert une_vie.pour_la_partie(game, tmp_path) is game, "mode coupé : le jeu tel quel"
        une_vie.entrer(game, ini)
        joue = une_vie.pour_la_partie(game, tmp_path)
        assert une_vie.arguments(joue) == ("PrivetDr.unr", "-SAVESLOT=7"), "pas de partie : Privet Drive"
        (une_vie.dossier(game) / "Save0.usa").write_bytes(b"x")
        assert une_vie.arguments(joue) == ("-LOADGAME=0", "-SAVESLOT=7")
        assert une_vie.arguments(game) is None

    def test_hp1_reprend_la_partie_du_mode(self, tmp_path):
        from src.core import reprise
        game = _CATALOGUE["hp1"]
        une_vie.entrer(game, _installer(tmp_path, "hp1"))
        joue = une_vie.pour_la_partie(game, tmp_path)
        assert une_vie.arguments(joue) is None
        assert reprise.arguments_pour("hp1", une_vie.dossier(game) / "Save3.usa") == ("?load=3",)
        assert joue.sauvegardes.fichiers.startswith("Save_UneVie/")

    def test_le_vrai_lancement_de_hp2_passe_par_son_emplacement(self, tmp_path, monkeypatch):
        """`GameManager.launch_game` : en une seule vie, HP2 part sur l'emplacement 7 même sans la reprise."""
        from unittest.mock import patch

        from src.core.config import Config
        from src.core.game_data import Catalog
        from src.core.game_manager import GameManager
        game = _CATALOGUE["hp2"]
        catalogue = Catalog(catalog_version="1.0", catalog_url="", games=(game,))
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        with patch("src.core.game_manager.load_catalog", return_value=catalogue):
            manager = GameManager(Config(install_path=tmp_path, cache_path=tmp_path / ".cache"))
        exe = tmp_path / game.executable
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        une_vie.entrer(game, _installer(tmp_path, "hp2"))
        monkeypatch.setattr("src.core.game_manager.prerequis_manquants", lambda _r: [])
        monkeypatch.setattr(GameManager, "apply_game_language", lambda self, g, confirmer=None: True)
        lignes: list = []
        monkeypatch.setattr("src.core.game_manager.subprocess.Popen", lambda args, **k: lignes.append(args))
        manager.launch_game("hp2")
        assert lignes and lignes[0][1:] == ["PrivetDr.unr", "-SAVESLOT=7"]

    def test_au_lancement_le_preset_tenu(self, tmp_path):
        game = _CATALOGUE["hp1"]
        config = SimpleNamespace(install_path=tmp_path, reprise={})
        ini = _installer(tmp_path, "hp1")
        assert dp.au_lancement(game, config) == "normal"
        une_vie.entrer(game, ini)
        assert dp.au_lancement(game, config) == "realiste"
        rc.poser_valeur(ini, "Accio.Game", "QuidditchDifficulty", "2")
        assert dp.au_lancement(game, config) == "impardonnable"


class TestTextes:
    def test_chaque_texte_du_mode_est_traduit(self):
        textes = {t for m in une_vie.MODES.values() for t in (m.apres, m.note) if t}
        for code in ("en", "es"):
            cles = json.loads(Path(f"src/data/i18n/{code}.json").read_text(encoding="utf-8"))["strings"]
            assert not sorted(t for t in textes if t not in cles), code


class TestCompteur:
    def test_une_chute_d_equipier_n_est_pas_une_mort(self):
        """C5 : Ron ou Hermione que personne ne joue (HP3), un équipier de HP4."""
        r = compteur_morts.analyser(
            "2026-11-18T10:00:00\tchute_equipier\t\tron\n"
            "2026-11-18T10:00:05\tchute_equipier\t\thermione\n"
            "2026-11-18T10:02:40\tmort\t\tjoueur1\n"
            "2026-11-18T10:02:41\tune_vie_fin\t\t160\n")
        assert (r.morts, r.chutes_equipier, r.fins_une_vie) == (1, 2, 1)
        assert r.plus_longue_vie == 160 and r.derniere_fin == datetime(2026, 11, 18, 10, 2, 41)

    def test_la_plus_longue_vie_et_un_detail_illisible(self):
        r = compteur_morts.analyser("2026-11-18T10:00:00\tune_vie_fin\t\t90\n"
                                    "2026-11-18T11:00:00\tune_vie_fin\t\t3600\n"
                                    "2026-11-18T12:00:00\tune_vie_fin\t\t²\n")
        assert r.fins_une_vie == 3 and r.plus_longue_vie == 3600

    def test_un_horodatage_avec_decalage_se_compare(self):
        r = compteur_morts.analyser("2026-11-18T10:00:00\tune_vie_fin\t\t9\n"
                                    "2026-11-18T09:00:00+00:00\tune_vie_fin\t\t9\n")
        assert r.derniere_fin is not None and r.derniere_fin.tzinfo is None


class TestPresetTenu:
    """`sauvegardes.attribuer` : le preset tenu depuis la naissance de la sauvegarde."""

    def _jouer(self, avant, apres, prereglage, fichier, debut=datetime(2026, 11, 18, 20)):
        return sauvegardes.attribuer("hp1", avant, apres, debut, 600, chemin=fichier, prereglage=prereglage)

    def test_nee_sous_un_preset_le_garde_tant_qu_il_tient(self, tmp_path):
        fichier = tmp_path / "sauvegardes.json"
        etat = sauvegardes.Etat(modifie=1.0, cree=1.0)
        self._jouer({}, {"Save0.usa": etat}, "hardcore", fichier)
        assert sauvegardes.charger(fichier)[("hp1", "Save0.usa")]["prereglage"] == "hardcore"
        plus_tard = sauvegardes.Etat(modifie=2.0, cree=1.0)
        self._jouer({"Save0.usa": etat}, {"Save0.usa": plus_tard}, "hardcore", fichier)
        assert sauvegardes.charger(fichier)[("hp1", "Save0.usa")]["prereglage"] == "hardcore"
        encore = sauvegardes.Etat(modifie=3.0, cree=1.0)
        self._jouer({"Save0.usa": plus_tard}, {"Save0.usa": encore}, "normal", fichier)
        assert sauvegardes.charger(fichier)[("hp1", "Save0.usa")]["prereglage"] == "", "perdu pour de bon"

    def test_une_sauvegarde_d_avant_le_suivi_n_en_a_aucun(self, tmp_path):
        fichier = tmp_path / "sauvegardes.json"
        vieille = sauvegardes.Etat(modifie=1.0, cree=1.0)
        self._jouer({"Save0.usa": vieille}, {"Save0.usa": sauvegardes.Etat(modifie=2.0, cree=1.0)},
                    "hardcore", fichier)
        assert sauvegardes.charger(fichier)[("hp1", "Save0.usa")]["prereglage"] is None


class TestMedailles:
    @pytest.fixture
    def partie(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.core.progression.cible", lambda spec, rel: (tmp_path / "x", 1))
        lue = SimpleNamespace(niveau="SNAPES_OFFICE", cartes=frozenset(), points={})
        monkeypatch.setattr(succes, "_partie", lambda jeu, chemin, n: lue)
        stock: dict = {}
        monkeypatch.setattr(sauvegardes, "charger", lambda chemin=None: stock)
        return stock

    def test_fin_du_jeu_au_preset_tenu_depuis_le_debut(self, partie):
        partie[("hp1", "Save_UneVie/Save0.usa")] = {"prereglage": "realiste"}
        porte = succes.evaluer("hp1", None, "Save_UneVie/Save0.usa")
        assert {i for i in porte if i.startswith("fin_")} == {"fin_realiste"}

    @pytest.mark.parametrize("tenu", [None, ""])
    def test_sans_preset_tenu_aucune(self, partie, tenu):
        partie[("hp1", "Save0.usa")] = {"prereglage": tenu}
        assert not {i for i in succes.evaluer("hp1", None, "Save0.usa") if i.startswith("fin_")}

    def test_les_presets_des_medailles_sont_ceux_que_le_jeu_propose(self):
        """Récit et Détendu exceptés : plus doux que le jeu, ils ne sont pas un défi."""
        for jeu, presets in succes.FINS_PAR_PRESET.items():
            idents = dp.idents_du_jeu(_CATALOGUE[jeu])
            attendus = tuple(p.ident for p in dp.PRESETS if dp.disponible(p, jeu, idents)
                             and p.ident not in ("recit", "detendu"))
            assert presets == attendus, jeu


pytest.importorskip("pytestqt")


class TestSession:
    """Au retour : la partie va à la sauvegarde du MODE, et une vie finie s'annonce."""

    @staticmethod
    def _session(tmp_path):
        from unittest.mock import patch

        from src.core.config import Config
        from src.core.game_data import Catalog
        from src.core.game_manager import GameManager
        from src.ui.game_session import GameSession
        catalogue = Catalog(catalog_version="1.0", catalog_url="", games=(_CATALOGUE["hp1"],))
        with patch("src.core.game_manager.load_catalog", return_value=catalogue):
            s = GameSession(GameManager(Config(install_path=tmp_path, cache_path=tmp_path / ".cache")))
        s._monitor.start = lambda proc, nom, *, relance: None
        return s

    def test_une_vie_finie_pendant_la_partie_s_annonce(self, tmp_path, qtbot):
        game = _CATALOGUE["hp1"]
        ini = _installer(tmp_path, "hp1")
        une_vie.entrer(game, ini)
        s = self._session(tmp_path)
        s.demarrer(SimpleNamespace(pid=1, poll=lambda: None), "HP1", "hp1")
        partie = une_vie.dossier(game) / "Save0.usa"
        partie.write_bytes(b"x")
        quand = (datetime.now() + timedelta(seconds=1)).isoformat(timespec="seconds")
        (ini.parent / compteur_morts.FICHIER).write_text(
            f"{quand}\tmort\tLev_Tut1\tHarry\n{quand}\tune_vie_fin\t\t600\n", encoding="utf-8")
        with qtbot.waitSignal(s.vie_terminee, timeout=2000) as bloc:
            s._monitor.game_exited.emit("HP1", 0, 600.0)
        assert bloc.args == ["hp1"]
        stock = sauvegardes.charger()
        assert stock[("hp1", "Save_UneVie/Save0.usa")]["prereglage"] == "realiste"
        assert ("hp1", "Save0.usa") not in stock, "rien chez les parties du joueur"

    def test_une_fin_d_une_seance_d_avant_ne_s_annonce_pas(self, tmp_path, qtbot):
        game = _CATALOGUE["hp1"]
        ini = _installer(tmp_path, "hp1")
        une_vie.entrer(game, ini)
        (ini.parent / compteur_morts.FICHIER).write_text("2026-01-01T10:00:00\tune_vie_fin\t\t60\n",
                                                         encoding="utf-8")
        s = self._session(tmp_path)
        s.demarrer(SimpleNamespace(pid=1, poll=lambda: None), "HP1", "hp1")
        annonces: list = []
        s.vie_terminee.connect(annonces.append)
        s._monitor.game_exited.emit("HP1", 0, 600.0)
        assert annonces == []


class TestFenetre:
    """La vraie fenêtre : l'épée de HP3, l'onglet, le choix, le toast du retour."""

    @staticmethod
    def _installe(monkeypatch, jeux):
        from src.core.game_manager import GameManager, GameState
        monkeypatch.setattr(GameManager, "is_installed", lambda self, j: j in jeux)
        monkeypatch.setattr(GameManager, "get_state", lambda self, j: GameState.INSTALLED
                            if j in jeux else GameState.NOT_INSTALLED)

    def test_hp3_choisit_realiste_dans_la_vraie_fenetre(self, make_window, monkeypatch, tmp_path, qtbot):
        from PyQt6.QtCore import Qt

        from src.ui.game_settings_dialog import GameSettingsDialog
        from src.ui.icon_button import IconButton
        self._installe(monkeypatch, {"hp3"})
        win = make_window()
        ini = _installer(win.manager.config.install_path, "hp3",
                         INI.replace("[Accio.Hardcore]", "[Accio.Overlay]"))
        game = next(e.game for e in win.manager.get_games() if e.game.id == "hp3")
        win._detail.set_game(game)
        bouton = next(b for b in win._detail._action_panel.findChildren(IconButton, "boutonDifficulte")
                      if game.name in b.accessibleName())
        bouton.click()
        page = win._pages.page
        assert isinstance(page, GameSettingsDialog) and page._onglets["difficulte"].isChecked()
        panneau = page._panneau
        assert [c.ident for c in panneau.cartes_presets] == ["normal"]
        assert [c.ident for c in panneau.cartes_une_vie] == ["realiste"], "Impardonnable : Hardcore ne change rien"
        explication = page.findChild(type(panneau.etat_une_vie), "explicationUneVie")   # posé par la fenêtre
        assert "héros que vous jouez" in explication.text()
        assert panneau.etat_une_vie.isHidden(), "mode coupé : rien à dire"
        realiste = panneau.cartes_une_vie[0]
        page.show()
        qtbot.mouseClick(realiste, Qt.MouseButton.LeftButton)
        assert _valeurs(ini)["OneLife"] == "1"
        assert realiste.property("actif") == "true"
        assert (panneau.cadran.nom, panneau.cadran.sous) == ("Réaliste", "Une seule vie")
        assert panneau.etat_une_vie.text() == "La prochaine partie commence votre vie."
        qtbot.mouseClick(panneau.cartes_presets[0], Qt.MouseButton.LeftButton)
        assert _valeurs(ini)["OneLife"] == "0" and une_vie.dossier(game).is_dir()
        page.accept()

    def test_le_toast_dit_la_fin_de_vie(self, make_window, monkeypatch):
        win = make_window()
        win.show()
        win._session.vie_terminee.emit("hp6")
        assert win._toast.isVisible()
        assert "votre vie s'est terminée" in win._toast.text()

    def test_les_defis_montrent_le_compteur(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QLabel

        from src.ui.defis_page import DefisPage
        (tmp_path / compteur_morts.FICHIER).write_text(
            "2026-11-18T10:00:00\tmort\tSave0\tHarry\n2026-11-18T10:00:01\tune_vie_fin\t\t5400\n"
            "2026-11-18T11:00:00\tchute_balai\tquid\tHarry\n", encoding="utf-8")
        page = DefisPage(dataclasses.replace(_CATALOGUE["hp1"], sauvegardes=None), dossier_exe=tmp_path)
        qtbot.addWidget(page)
        textes = [[lbl.text() for lbl in t.findChildren(QLabel)] for t in page.tuiles_morts]
        assert [t[:2] for t in textes] == [["1", "Morts"], ["1", "Vies terminées"],
                                           ["1 h 30 min", "La plus longue vie"]]

    def test_sans_compteur_rien_ne_s_ecrit(self, qtbot, tmp_path):
        from src.ui.defis_page import DefisPage
        page = DefisPage(dataclasses.replace(_CATALOGUE["hp1"], sauvegardes=None), dossier_exe=tmp_path)
        qtbot.addWidget(page)
        assert page.tuiles_morts == []


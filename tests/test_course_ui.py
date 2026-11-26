"""La course (1.5) dans l'interface : le chrono de la fiche (sur tout jeu qui a une course), la page Course
(catégories du catalogue, règles, correctif trop ancien, empreinte dans un fil, record et classement), le départ
orchestré, la session qui conclut la course à la fermeture du jeu, le résultat (deux temps, meilleurs passages,
record, place) et le Carnet (partager, comparer, records successifs). Chaque page s'ouvre sous 0,5 s (Ludo,
2026-11-16)."""

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")

from src.core import course, mode_course  # noqa: E402
from src.core.game_data import load_catalog  # noqa: E402
from tests.test_course import HP2, journal  # noqa: E402
from tests.test_mode_course import INI_HP2, dll_versionnee  # noqa: E402

_CATALOGUE = {g.id: g for g in load_catalog().games}
_DEMI_SECONDE = 0.5


@pytest.fixture(autouse=True)
def _course_sous_windows(monkeypatch):
    """Ces tests jugent une course « Windows » : sous Linux (CI), une course n'entre pas au classement
    (`course.SOUS_WINE`), ce que `test_sous_linux_la_course_est_refusee` vérifie à part."""
    monkeypatch.setattr(mode_course, "plateforme", lambda: "win32")


def _poser_ini(install_path: Path, texte: str = INI_HP2, version: tuple[int, int, int, int] = (2, 5, 0, 0)) -> Path:
    game = _CATALOGUE["hp2"]
    ini = install_path / Path(game.executable).parent / "winmm.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(texte.encode("ascii"))
    dll_versionnee(ini.with_suffix(".dll"), version)
    return ini


def _conclusion(tmp_path: Path, categorie: str = "Any%") -> mode_course.Conclusion:
    game = _CATALOGUE["hp2"]
    ini = _poser_ini(tmp_path)
    etat = mode_course.entrer(game, ini, categorie, course.Empreinte("ab" * 32, "abababab", ()), "normal")
    evts = list(HP2)
    evts[0] = (0, "seance", "", f"HP2;fix=2.5.0;RaceId={etat.ligne_id}")
    (ini.parent / course.FICHIER).write_text(journal(*evts), encoding="utf-8", newline="\n")
    return mode_course.conclure(etat, "1.5.0")


def _installe(monkeypatch):
    from src.core.game_manager import GameManager, GameState
    monkeypatch.setattr(GameManager, "is_installed", lambda self, j: j in ("hp2", "hp7a"))
    monkeypatch.setattr(GameManager, "get_state", lambda self, j: GameState.INSTALLED
                        if j in ("hp2", "hp7a") else GameState.NOT_INSTALLED)


def _textes(widget) -> str:
    from PyQt6.QtWidgets import QLabel
    return " ".join(lb.text() for lb in widget.findChildren(QLabel))


class TestFiche:
    @staticmethod
    def _chrono(win):
        from src.ui.icon_button import IconButton
        return win._detail._action_panel.findChildren(IconButton, "boutonCourse")

    def test_chrono_sur_tout_jeu_qui_a_une_course(self, make_window, monkeypatch):
        """Même avec un correctif trop ancien : la page dira pourquoi. HP7 n'a pas de course."""
        _installe(monkeypatch)
        win = make_window()
        game = _CATALOGUE["hp2"]
        _poser_ini(win.manager.config.install_path, version=(2, 4, 0, 0))
        win._detail.set_game(game)
        (chrono,) = self._chrono(win)
        assert game.name in chrono.accessibleName()
        win._detail.set_game(_CATALOGUE["hp7a"])
        assert not any(_CATALOGUE["hp7a"].name in c.accessibleName() for c in self._chrono(win))

    def test_le_chrono_ouvre_la_page(self, make_window, monkeypatch):
        from src.ui import course_ui
        from src.ui.page_course import CoursePage
        _installe(monkeypatch)
        win = make_window()
        _poser_ini(win.manager.config.install_path)
        win._detail.set_game(_CATALOGUE["hp2"])
        debut = time.perf_counter()
        course_ui.partir(win._detail)
        page = win._pages.page
        assert isinstance(page, CoursePage) and time.perf_counter() - debut < _DEMI_SECONDE
        lancees = []
        from src.ui import game_detail_handlers as handlers
        monkeypatch.setattr(handlers, "on_play", lambda view: lancees.append(1))
        page.reject()                                          # le retour : rien ne part
        assert lancees == [] and win._pages.page is None and mode_course.en_cours() == []

    def test_lancer_pose_la_course_puis_lance(self, make_window, monkeypatch):
        from src.ui import course_ui
        from src.ui import game_detail_handlers as handlers
        from src.ui.page_course import Choix
        _installe(monkeypatch)
        win = make_window()
        game = _CATALOGUE["hp2"]
        ini = _poser_ini(win.manager.config.install_path, INI_HP2.replace("DamageTaken=3", "DamageTaken=1"))
        win._detail.set_game(game)
        lancee = []
        monkeypatch.setattr(handlers, "on_play", lambda view: lancee.append(view.game.id))
        win._detail.partie_en_cours = lambda: "HP2" if lancee else ""
        course_ui.lancer(win._detail, Choix("hp2", ini, "Warpless", course.Empreinte("cd" * 32, "cdcdcdcd", ()),
                                            True))
        assert lancee == ["hp2"]
        (etat,) = mode_course.en_cours("hp2")
        assert mode_course.actif(ini) and etat.ligne_id.endswith("cdcdcdcd HP2 Warpless")

    def test_lancer_pose_le_fantome_et_retient_la_preference(self, make_window, monkeypatch, tmp_path):
        from src.ui import course_ui
        from src.ui import game_detail_handlers as handlers
        from src.ui.page_course import Choix
        _installe(monkeypatch)
        win = make_window()
        game = _CATALOGUE["hp2"]
        _conclusion(tmp_path / "ailleurs")                            # le record Any% de HP2
        ini = _poser_ini(win.manager.config.install_path)
        win._detail.set_game(game)
        lancees = []
        monkeypatch.setattr(handlers, "on_play", lambda view: lancees.append(1))
        win._detail.partie_en_cours = lambda: "HP2" if lancees else ""
        emp = course.Empreinte("cd" * 32, "cdcdcdcd", ())
        course_ui.lancer(win._detail, Choix("hp2", ini, "Any%", emp, True))
        lignes = (ini.parent / course.FANTOME).read_text(encoding="utf-8").splitlines()
        assert [ligne.split("\t")[0] for ligne in lignes] == ["PrivetDr", "Adv1Willow"]
        (etat,) = mode_course.en_cours("hp2")
        mode_course.sortir(etat)
        sauvees = []
        from src.core.config import Config                          # une dataclass, pas un objet Qt (règle 12)
        monkeypatch.setattr(Config, "save", lambda cfg: sauvees.append(cfg.course_fantome))
        lancees.clear()
        course_ui.lancer(win._detail, Choix("hp2", ini, "Any%", emp, False, True, 2))
        assert not (ini.parent / course.FANTOME).exists() and win.manager.config.course_fantome is False
        assert sauvees == [False], "la préférence changée s'enregistre, une fois"
        config = win.manager.config
        assert config.course_complet and config.course_coin == 2, "Complet et le coin, retenus avec le fantôme"
        record = course.meilleure(course.passees("hp2"), "Any%", _CATALOGUE["hp2"].course.temps)
        texte = ini.read_text(encoding="utf-8")
        assert record is not None and f"RaceRecord={record.net_us}" in texte, "HP2 se classe sans chargements"
        assert "RaceDetail=1" in texte and "RaceCorner=2" in texte

    def test_jeu_qui_ne_part_pas_rend_les_reglages(self, make_window, monkeypatch):
        from src.ui import course_ui
        from src.ui import game_detail_handlers as handlers
        from src.ui.page_course import Choix
        _installe(monkeypatch)
        win = make_window()
        ini = _poser_ini(win.manager.config.install_path)
        avant = ini.read_bytes()
        win._detail.set_game(_CATALOGUE["hp2"])
        monkeypatch.setattr(handlers, "on_play", lambda view: None)
        win._detail.partie_en_cours = lambda: ""
        course_ui.lancer(win._detail, Choix("hp2", ini, "Any%", course.Empreinte("cd" * 32, "cdcdcdcd", ()), True))
        assert ini.read_bytes() == avant and mode_course.en_cours() == []


class TestPage:
    @staticmethod
    def _page(make_window, monkeypatch, qtbot, bloquants=(), **kw):
        """La page de HP2 ; la difficulté (`course_ui.bloquants`) ne bloque que si le test le demande : l'ini
        de test porte une difficulté du mode difficile."""
        from src.ui import course_ui
        from src.ui.page_course import CoursePage
        monkeypatch.setattr(course_ui, "bloquants", lambda game, config: list(bloquants))
        _installe(monkeypatch)
        win = make_window()
        _poser_ini(win.manager.config.install_path, **kw)
        debut = time.perf_counter()
        page = CoursePage(_CATALOGUE["hp2"], win.manager)
        qtbot.addWidget(page)
        page.show()
        qtbot.waitExposed(page)
        assert time.perf_counter() - debut < _DEMI_SECONDE
        return win, page

    def test_categories_et_regles_du_catalogue(self, make_window, monkeypatch, qtbot):
        _, page = self._page(make_window, monkeypatch, qtbot)
        regles = _CATALOGUE["hp2"].course
        assert list(page.pastilles) == list(regles.idents) and page.categorie == "Any%"
        assert page.pastilles["Warpless"].text() == "Sans warp"
        textes = _textes(page)
        assert regles.depart in textes and regles.arrivee in textes and "Temps sans les chargements" in textes
        assert page._partir.isEnabled() and page._partir.text() == "Partir en Any%" and not page._bloque.isVisible()
        page.pastilles["Warpless"].click()
        assert page.categorie == "Warpless" and page._regle.text() == regles.categorie("Warpless").regle
        assert page._partir.text() == "Partir en Sans warp"

    def test_simple_complet_et_coin_de_l_ecran(self, make_window, monkeypatch, qtbot):
        win, page = self._page(make_window, monkeypatch, qtbot)
        assert page.details[False].isChecked() and not page.complet and page.coin == 4
        assert page.ecran.coins[4].isChecked() and page._nom_coin.text() == "En bas à droite"
        bande = page.ecran.coins[1].size()
        page.details[True].click()
        assert page.complet and page.ecran.coins[1].height() > bande.height(), "Complet : un pavé, plus une bande"
        page.ecran.coins[2].click()
        assert page.coin == 2 and page._nom_coin.text() == "En haut à droite"
        assert [page.ecran.coins[n].isChecked() for n in (1, 2, 3, 4)] == [False, True, False, False]
        # Le choix part avec la course ; la page se fige pendant l'empreinte.
        page._figer(True)
        assert not page.ecran.isEnabled() and not page.details[False].isEnabled()
        page._figer(False)
        page._prete(course.Empreinte("cd" * 32, "cdcdcdcd", ()))
        assert page.choix is not None and page.choix.complet and page.choix.coin == 2
        x = page.ecran.coins[2].geometry()
        assert x.right() > page.ecran.width() // 2 and x.top() < page.ecran.height() // 2, "en haut à droite"

    def test_regles_detaillees_repliees(self, make_window, monkeypatch, qtbot):
        _, page = self._page(make_window, monkeypatch, qtbot)
        assert not page.regles_detaillees.isVisible()
        page.bouton_regles.click()
        assert page.regles_detaillees.isVisible() and "65 images" in _textes(page.regles_detaillees)

    def test_note_d_une_categorie_qui_finit_ailleurs_sur_speedrun(self, make_window, monkeypatch, qtbot):
        from src.ui.page_course import CoursePage
        _installe(monkeypatch)
        win = make_window()
        page = CoursePage(_CATALOGUE["hp1"], win.manager)
        qtbot.addWidget(page)
        page.show()
        assert page._note.isHidden()
        page.pastilles["100%"].click()
        assert not page._note.isHidden() and "speedrun.com" in page._note.text()

    def test_correctif_trop_ancien(self, make_window, monkeypatch, qtbot):
        _, page = self._page(make_window, monkeypatch, qtbot, version=(2, 4, 0, 0))
        assert page.ini is None and not page._partir.isEnabled() and page._bloque.isVisible()
        assert "2.5.0" in _textes(page._bloque)
        page._calculer()
        assert page._fil is None, "rien ne part sans un correctif qui chronomètre"

    def test_difficulte_bloque(self, make_window, monkeypatch, qtbot):
        _, page = self._page(make_window, monkeypatch, qtbot, bloquants=["Choisissez la difficulté Normal."])
        assert not page._partir.isEnabled() and "Choisissez la difficulté Normal." in _textes(page._bloque)

    def test_partir_calcule_l_empreinte_dans_un_fil(self, make_window, monkeypatch, qtbot):
        win, page = self._page(make_window, monkeypatch, qtbot)
        (win.manager.config.install_path / Path(_CATALOGUE["hp2"].executable)).write_bytes(b"exe")
        page.pastilles["Glitchless"].click()
        with qtbot.waitSignal(page.accepted, timeout=5000):
            page._partir.click()
            assert not page.pastilles["100%"].isEnabled(), "la catégorie ne change plus pendant l'empreinte"
        assert page.choix is not None and page.choix.categorie == "Glitchless" and page.choix.ini == page.ini
        assert [f.chemin for f in page.choix.empreinte.fichiers] == ["system/game.exe", "system/winmm.dll"]
        assert (course.racine() / "empreintes.json").is_file()

    def test_fermer_pendant_le_calcul(self, make_window, monkeypatch, qtbot):
        win, page = self._page(make_window, monkeypatch, qtbot)
        (win.manager.config.install_path / Path(_CATALOGUE["hp2"].executable)).write_bytes(b"exe")
        page._partir.click()
        page.reject()
        assert page._fil is None and page.choix is None

    def test_fantome_dit_le_record_de_la_categorie(self, make_window, monkeypatch, qtbot, tmp_path):
        record = _conclusion(tmp_path / "jeux")
        _, page = self._page(make_window, monkeypatch, qtbot)
        assert page.fantome and page.bascule_fantome.isChecked()
        assert course.format_temps(record.resultat.net_us) in page.note_fantome
        page.pastilles["100%"].click()
        assert "100%" in page.note_fantome and course.format_temps(record.resultat.net_us) not in page.note_fantome
        from PyQt6.QtCore import Qt
        qtbot.mouseClick(page.bascule_fantome, Qt.MouseButton.LeftButton)
        assert not page.fantome and "100%" not in page.note_fantome

    def test_record_essais_et_classement_a_droite(self, make_window, monkeypatch, qtbot, tmp_path):
        from src.core import classement
        fin = _conclusion(tmp_path / "jeux")
        assert classement.garder(json.dumps({"format": 1, "jeux": {"hp2": {"Any%": [
            {"joueur": "Rapide", "temps": "0:00.001", "date": "2026-12-01"}]}}}).encode())
        _, page = self._page(make_window, monkeypatch, qtbot)
        assert page.categorie == "Any%", "la catégorie de la dernière course"
        assert page.temps_record.text() == course.format_temps(fin.resultat.net_us)
        textes = _textes(page)
        assert "Rapide" in textes and "1 essai" in textes and "0:39.000 en temps réel" in textes
        assert page.place_record == 2 and "Vous (non envoyé)" in textes, "le joueur à la place de son record"
        page.pastilles["100%"].click()
        assert page.temps_record.text() == "—" and page.place_record is None
        assert "Personne n'est encore classé en 100%." in _textes(page)


class TestResultat:
    def test_deux_temps_decoupage_et_resume(self, qtbot, tmp_path):
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtWidgets import QLabel

        from src.ui.course_ui import CourseResultat
        fin = _conclusion(tmp_path)
        debut = time.perf_counter()
        dlg = CourseResultat(fin, "Harry Potter et la Chambre des Secrets", game=_CATALOGUE["hp2"])
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        assert time.perf_counter() - debut < _DEMI_SECONDE
        assert dlg.findChild(QLabel, "tempsCourse").text() == "0:34.000", "HP2 se classe sans les chargements"
        textes = _textes(dlg)
        assert "PrivetDr" in textes and "Adv1Willow" in textes and "Temps valable" in textes
        assert "0:39.000 en temps réel" in textes and "essai 1" in textes
        assert "Premier temps valable" in dlg.phrase_record.text() and "place 1" in textes
        assert "la vidéo reste la preuve" in textes.lower()
        dlg._copier()
        copie = QGuiApplication.clipboard().text()
        assert copie.startswith("Harry Potter et la Chambre des Secrets — Any%")
        assert "0:34.000" in copie and "0:39.000" in copie and fin.code in copie

    def test_hp4_se_classe_au_temps_reel(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QLabel

        from src.ui.course_ui import CourseResultat
        fin = _conclusion(tmp_path)
        dlg = CourseResultat(fin, "HP4", game=_CATALOGUE["hp4"], courses=[])
        qtbot.addWidget(dlg)
        assert dlg.findChild(QLabel, "tempsCourse").text() == "0:39.000"
        assert "0:34.000 sans chargements" in _textes(dlg)

    def test_meilleurs_passages_en_or_et_record_garde(self, qtbot, tmp_path):
        from src.ui.course_ui import CourseResultat
        _conclusion(tmp_path / "a")
        seconde = _conclusion(tmp_path / "b")
        dlg = CourseResultat(seconde, "HP2", game=_CATALOGUE["hp2"])
        qtbot.addWidget(dlg)
        assert dlg.meilleurs == [0, 1], "à égalité, un meilleur passage"
        assert "essai 2" in _textes(dlg) and "Votre record reste" in dlg.phrase_record.text()

    def test_voir_dans_le_carnet(self, qtbot, tmp_path):
        """Le bouton n'existe que si la fenêtre sait ouvrir le Carnet ; il ferme le résultat puis l'ouvre."""
        from PyQt6.QtWidgets import QPushButton

        from src.ui.course_ui import CourseResultat
        fin = _conclusion(tmp_path)
        seul = CourseResultat(fin, "HP2", game=_CATALOGUE["hp2"])
        qtbot.addWidget(seul)
        assert "Voir dans le Carnet" not in [b.text() for b in seul.findChildren(QPushButton)]
        ouvert = []
        dlg = CourseResultat(fin, "HP2", game=_CATALOGUE["hp2"], carnet=lambda: ouvert.append(dlg.isVisible()))
        qtbot.addWidget(dlg)
        dlg.show()
        next(b for b in dlg.findChildren(QPushButton) if b.text() == "Voir dans le Carnet").click()
        assert ouvert == [False], "le résultat se ferme avant que le Carnet s'ouvre"

    def test_pieces_communes(self, qtbot):
        from PyQt6.QtGui import QFont

        from src.ui import course_visuel as visuel
        f = visuel.chiffres(QFont())
        assert f.featureValue(QFont.Tag("tnum")) == 1 and f.featureValue(QFont.Tag("lnum")) == 1
        a, b = visuel.rond("Hermione"), visuel.rond("Hermione")
        assert a.text() == "H" and a.styleSheet() == b.styleSheet(), "le même rond pour le même joueur"
        assert visuel.rond("<b>", vous=True).text() == "B" and "#d6a72c" in visuel.rond("x", vous=True).styleSheet()

    def test_refus_dits(self, qtbot, tmp_path):
        from src.ui.course_ui import CourseResultat, raison
        fin = _conclusion(tmp_path)
        refuse = mode_course.Conclusion(fin.code, fin.jeu, fin.resultat, (course.DEPART_CHARGE,), fin.journal, False)
        dlg = CourseResultat(refuse, "HP2", game=_CATALOGUE["hp2"])
        qtbot.addWidget(dlg)
        textes = _textes(dlg)
        assert raison(course.DEPART_CHARGE) in textes and "réessaiera" in textes
        assert dlg.phrase_record is None, "un temps refusé ne se compare à aucun record"

    def test_chaque_refus_a_sa_phrase(self):
        from src.ui.course_ui import raison
        codes = [v for k, v in vars(course).items() if k.isupper() and isinstance(v, str) and v.islower()
                 and k in {"SANS_SEANCE", "RELANCE", "AUTRE_ID", "SANS_DEPART", "DEPART_CHARGE", "DEPART_CLIC",
                           "DEPART_INCONNU", "SANS_FIN", "RETOUCHE", "TROP_D_IMAGES", "MODE_NON_TENU",
                           "INTERDITS", "SOUS_WINE"}]
        assert len(codes) == 13
        for code in codes + ["sauvegardes", "ini", "journal_tenu"]:
            assert raison(code) != code
        assert "65" in raison(course.TROP_D_IMAGES)


class TestSession:
    def test_la_fin_du_jeu_conclut_la_course(self, tmp_path, qtbot):
        from unittest.mock import patch

        from src.core.config import Config
        from src.core.game_data import Catalog
        from src.core.game_manager import GameManager
        from src.ui.game_session import GameSession
        game = _CATALOGUE["hp2"]
        catalogue = Catalog(catalog_version="1.0", catalog_url="", games=(game,))
        with patch("src.core.game_manager.load_catalog", return_value=catalogue):
            s = GameSession(GameManager(Config(install_path=tmp_path, cache_path=tmp_path / ".cache")))
        s._monitor.start = lambda proc, nom, *, relance: None
        ini = _poser_ini(tmp_path)
        avant = ini.read_bytes()
        etat = mode_course.entrer(game, ini, "Any%", course.Empreinte("ab" * 32, "abababab", ()), "normal")
        s.demarrer(SimpleNamespace(pid=1, poll=lambda: None), game.name, "hp2")
        evts = list(HP2)
        evts[0] = (0, "seance", "", f"HP2;fix=2.5.0;RaceId={etat.ligne_id}")
        (ini.parent / course.FICHIER).write_text(journal(*evts), encoding="utf-8", newline="\n")
        with qtbot.waitSignal(s.course_terminee, timeout=2000) as bloc:
            s._monitor.game_exited.emit(game.name, 0, 600.0)
        (fin,) = bloc.args
        assert fin.code == etat.code and fin.refus == () and fin.rendu
        assert ini.read_bytes() == avant

    def test_course_interrompue_conclue_au_demarrage(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from src.core.config import Config
        from src.core.game_data import Catalog
        from src.core.game_manager import GameManager
        from src.ui.game_session import GameSession
        from src.ui.process_monitor import ProcessMonitor
        game = _CATALOGUE["hp2"]
        with patch("src.core.game_manager.load_catalog",
                   return_value=Catalog(catalog_version="1.0", catalog_url="", games=(game,))):
            s = GameSession(GameManager(Config(install_path=tmp_path, cache_path=tmp_path / ".cache")))
        ini = _poser_ini(tmp_path)
        mode_course.entrer(game, ini, "Any%", course.Empreinte("ab" * 32, "abababab", ()), "normal")
        monkeypatch.setattr(ProcessMonitor, "_is_exe_running", staticmethod(lambda exe: None))
        assert s.courses_interrompues() == [], "jeu peut-être encore ouvert : on attend"
        monkeypatch.setattr(ProcessMonitor, "_is_exe_running", staticmethod(lambda exe: False))
        (fin,) = s.courses_interrompues()
        assert fin.refus == (course.SANS_SEANCE,) and fin.rendu and mode_course.en_cours() == []


class TestCarnet:
    """La rubrique Courses du Carnet : là seulement quand une course est gardée ou classée, record au temps qui
    classe le jeu, records successifs, partage et comparaison, suppression après confirmation."""

    @staticmethod
    def _carnet(make_window, monkeypatch, qtbot):
        from src.ui.carnet_page import CarnetPage
        _installe(monkeypatch)
        win = make_window()
        carnet = CarnetPage(win.manager, win, jeu="hp2")
        qtbot.addWidget(carnet)
        return win, carnet

    @staticmethod
    def _classer(*entrees: dict) -> None:
        from src.core import classement
        assert classement.garder(json.dumps({"format": 1, "jeux": {"hp2": {"Any%": list(entrees)}}}).encode())

    @staticmethod
    def _page(carnet):
        from src.ui.carnet_page import COURSES
        carnet.rubrique(COURSES)
        assert carnet._courses is not None
        return carnet._courses

    def test_classement_sans_course_gardee(self, make_window, monkeypatch, qtbot):
        from PyQt6.QtWidgets import QFrame, QLabel, QPushButton

        from src.ui import courses_page
        from src.ui.carnet_page import COURSES
        self._classer({"joueur": "Ronald <b>W</b>", "temps": "40:00.000", "date": "2026-12-02",
                       "video": "https://exemple.com/piege"},
                      {"joueur": "Ludo", "temps": "31:04.512", "date": "2026-12-01", "code": "7KQ2-M4XP",
                       "video": "https://youtu.be/abc"})
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        assert COURSES in carnet._rubriques, "le classement suffit à montrer la rubrique"
        debut = time.perf_counter()
        page = self._page(carnet)
        assert time.perf_counter() - debut < _DEMI_SECONDE
        assert [e.joueur for e in page.places] == ["Ludo", "Ronald <b>W</b>"]
        textes = [lbl.text() for lbl in page.findChildren(QLabel)]
        assert "Ronald <b>W</b>" in textes and "31:04.512" in textes
        assert any(f.toolTip() == "2026-12-01 · 7KQ2-M4XP" for f in page.findChildren(QFrame, "ligneClassee"))
        nom = next(lbl for lbl in page.findChildren(QLabel) if lbl.text() == "Ronald <b>W</b>")
        assert nom.textFormat() == courses_page.Qt.TextFormat.PlainText, "un nom venu du réseau, en texte brut"
        videos = [b for b in page.findChildren(QPushButton) if b.text() == "Vidéo"]
        assert [b.toolTip() for b in videos] == ["https://youtu.be/abc"], "la vidéo d'un hôte inconnu n'a pas de lien"
        ouvertes = []
        monkeypatch.setattr(courses_page, "open_url", ouvertes.append)
        videos[0].click()
        assert ouvertes == ["https://youtu.be/abc"] and page.note_place is None
        source = next(b for b in page.findChildren(QPushButton) if "speedrun.com" in b.text())
        source.click()
        assert ouvertes[-1] == "https://www.speedrun.com/hp2pc", "les records du jeu d'origine"

    def test_place_que_prendrait_le_record(self, make_window, monkeypatch, qtbot, tmp_path):
        fin = _conclusion(tmp_path / "jeux")
        self._classer({"joueur": "Rapide", "temps": "0:00.001", "date": "2026-12-01"},
                      {"joueur": "Lent", "temps": "9:59:59.000", "date": "2026-12-01"})
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        page = self._page(carnet)
        assert page.note_place is not None
        assert course.format_temps(fin.resultat.net_us) in page.note_place.text() and " 2." in page.note_place.text()

    def test_pas_de_rubrique_sans_course(self, make_window, monkeypatch, qtbot):
        from src.ui.carnet_page import COURSES
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        assert COURSES not in carnet._rubriques

    def test_meilleur_temps_et_suppression(self, make_window, monkeypatch, qtbot, tmp_path):
        from src.ui import courses_page
        from src.ui.carnet_page import COURSES
        fin = _conclusion(tmp_path / "jeux")
        lectures = []
        vrai = course.passees
        monkeypatch.setattr(course, "passees", lambda *a: lectures.append(a) or vrai(*a))
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        carnet.show()
        debut = time.perf_counter()
        carnet._rubriques[COURSES].click()
        page = carnet._courses
        qtbot.waitExposed(page)
        assert time.perf_counter() - debut < _DEMI_SECONDE
        assert isinstance(page, courses_page.CoursesPage) and [li.code for li in page.lignes] == [fin.code]
        assert len(lectures) == 1, "les journaux sont lus UNE fois par visite du Carnet (règle 140)"
        textes = _textes(page)
        assert "0:34.000" in textes and "Meilleur temps valable" in textes and "0:39.000 en temps réel" in textes
        assert "1 essai · 1 finie" in textes and "Temps valable · record" in textes
        monkeypatch.setattr(courses_page, "message", lambda *a, **k: 1)       # « Annuler »
        page.lignes[0].bouton_supprimer.click()
        assert course.dossier(fin.code).is_dir()
        monkeypatch.setattr(courses_page, "message", lambda *a, **k: 0)       # « Supprimer »
        page.lignes[0].bouton_supprimer.click()
        assert not course.dossier(fin.code).exists() and page.lignes == []
        assert "Aucune course" in _textes(page)

    def test_par_categorie_dans_l_ordre_du_catalogue(self, make_window, monkeypatch, qtbot, tmp_path):
        seule = _conclusion(tmp_path / "jeux")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        page = self._page(carnet)
        assert list(page.pastilles) == ["Any%", "100%", "Warpless", "Glitchless", "All Wizard Cards"], (
            "toutes les catégories du jeu, dans l'ordre du catalogue")
        assert [s.carte for s in page.passages] == ["PrivetDr", "Adv1Willow"]
        assert all(s.code == seule.code for s in page.passages)
        carnet._retirer_courses()
        autre = _conclusion(tmp_path / "jeux2", "Warpless")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        page = self._page(carnet)
        assert page.pastilles["Warpless"].text() == "Sans warp"
        assert page.categorie == "Warpless" and [li.code for li in page.lignes] == [autre.code], (
            "la catégorie de la course la plus récente d'abord")
        page.pastilles["Any%"].click()
        assert page.categorie == "Any%" and [li.code for li in page.lignes] == [seule.code]
        assert "MEILLEUR PASSAGE PAR CARTE" in _textes(page)

    def test_exporter_pour_livesplit(self, make_window, monkeypatch, qtbot, tmp_path):
        import xml.etree.ElementTree as ET

        from src.ui import courses_page
        _conclusion(tmp_path / "jeux")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        page = self._page(carnet)
        assert page.bouton_livesplit is not None
        cible = tmp_path / "sortie" / "course"
        cible.parent.mkdir()
        monkeypatch.setattr(courses_page.QFileDialog, "getSaveFileName", lambda *a, **k: (str(cible), ""))
        page.bouton_livesplit.click()
        run = ET.fromstring((tmp_path / "sortie" / "course.lss").read_bytes())
        assert [s.findtext("Name") for s in run.findall("Segments/Segment")] == ["PrivetDr", "Adv1Willow"]
        monkeypatch.setattr(courses_page.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
        page.bouton_livesplit.click()                                 # annulé : rien d'écrit, rien ne casse

    def test_partager_puis_comparer(self, make_window, monkeypatch, qtbot, tmp_path):
        """Le record partagé est le `course.json` tel quel (signature intacte) ; relu comme la course d'un ami,
        il se met carte par carte en face du record. Un autre jeu ou une autre catégorie est refusé."""
        from src.ui import courses_page
        _conclusion(tmp_path / "jeux")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        page = self._page(carnet)
        partage = tmp_path / "partage" / "mon record"
        partage.parent.mkdir()
        monkeypatch.setattr(courses_page.QFileDialog, "getSaveFileName", lambda *a, **k: (str(partage), ""))
        page.bouton_partager.click()
        copie = partage.with_name("mon record.json")
        assert course.verifier_journal(copie).signature
        monkeypatch.setattr(courses_page.QFileDialog, "getOpenFileName", lambda *a, **k: (str(copie), ""))
        page.bouton_comparer.click()
        page = carnet._courses
        assert [c.carte for c in page.comparaison] == ["PrivetDr", "Adv1Willow"]
        assert all(c.ecart_us == 0 for c in page.comparaison)
        assert page.note_comparaison is not None and "Fichier signé" in page.note_comparaison.text()
        donnees = json.loads(copie.read_text(encoding="utf-8"))
        donnees["categorie"] = "100%"
        copie.write_text(json.dumps(donnees), encoding="utf-8")
        refus = []
        monkeypatch.setattr(courses_page, "message", lambda *a, **k: refus.append(a[3]))
        page.bouton_comparer.click()
        assert refus and "100%" not in refus[0] and "Any%" in refus[0]

    def test_records_successifs(self, make_window, monkeypatch, qtbot, tmp_path):
        premiere = _conclusion(tmp_path / "a")
        seconde = _conclusion(tmp_path / "b")
        chemin = course.dossier(seconde.code) / course.JOURNAL
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        donnees["date"] = "2099-01-01"
        donnees["resultat"]["net_us"] = premiere.resultat.net_us - 1_000_000     # plus rapide (non signé : Carnet)
        chemin.write_text(json.dumps(donnees), encoding="utf-8")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        page = self._page(carnet)
        assert [c.code for c in page.records] == [premiere.code, seconde.code]
        assert "Records successifs" in _textes(page)

    def test_changer_de_jeu_rebatit(self, make_window, monkeypatch, qtbot, tmp_path):
        _conclusion(tmp_path / "jeux")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        avant = self._page(carnet)
        carnet._retirer_courses()
        assert carnet._courses is None and avant is not None

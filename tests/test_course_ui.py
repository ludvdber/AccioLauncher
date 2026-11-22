"""La course (1.5) dans l'interface : le chrono de la fiche (seulement là où le correctif connaît la course), le
dialogue de départ (empreinte dans un fil, Partir grisé tant qu'un bloquant reste), le départ orchestré, la
session qui conclut la course à la fermeture du jeu, et la fenêtre du résultat. Chaque page s'ouvre sous 0,5 s
(Ludo, 2026-11-16)."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")

from src.core import course, mode_course  # noqa: E402
from src.core.game_data import load_catalog  # noqa: E402
from tests.test_course import HP2, journal  # noqa: E402
from tests.test_mode_course import INI_HP2  # noqa: E402

_CATALOGUE = {g.id: g for g in load_catalog().games}
_DEMI_SECONDE = 0.5


def _poser_ini(install_path: Path, texte: str = INI_HP2) -> Path:
    game = _CATALOGUE["hp2"]
    ini = install_path / Path(game.executable).parent / "winmm.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(texte.encode("ascii"))
    return ini


def _conclusion(tmp_path: Path, categorie: str = "Any%") -> mode_course.Conclusion:
    game = _CATALOGUE["hp2"]
    ini = _poser_ini(tmp_path)
    etat = mode_course.entrer(game, ini, categorie, course.Empreinte("ab" * 32, "abababab", ()), "normal")
    evts = list(HP2)
    evts[0] = (0, "seance", "", f"HP2;fix=2.5.0;RaceId={etat.ligne_id}")
    (ini.parent / course.FICHIER).write_text(journal(*evts), encoding="utf-8", newline="\n")
    return mode_course.conclure(etat, "1.5.0")


class TestFiche:
    @staticmethod
    def _installe(monkeypatch):
        from src.core.game_manager import GameManager, GameState
        monkeypatch.setattr(GameManager, "is_installed", lambda self, j: j == "hp2")
        monkeypatch.setattr(GameManager, "get_state", lambda self, j: GameState.INSTALLED
                            if j == "hp2" else GameState.NOT_INSTALLED)

    @staticmethod
    def _chrono(win):
        from src.ui.icon_button import IconButton
        return win._detail._action_panel.findChildren(IconButton, "boutonCourse")

    def test_chrono_seulement_si_le_correctif_connait_la_course(self, make_window, monkeypatch):
        self._installe(monkeypatch)
        win = make_window()
        game = _CATALOGUE["hp2"]
        _poser_ini(win.manager.config.install_path, INI_HP2.replace("RaceLog=0\r\n", ""))
        win._detail.set_game(game)
        assert self._chrono(win) == [], "ini de la 1.4 : pas de course"
        _poser_ini(win.manager.config.install_path)
        win._detail.set_game(game)
        (chrono,) = self._chrono(win)
        assert game.name in chrono.accessibleName()

    def test_partir_pose_la_course_puis_lance(self, make_window, monkeypatch):
        from src.ui import course_ui
        from src.ui import game_detail_handlers as handlers
        self._installe(monkeypatch)
        win = make_window()
        game = _CATALOGUE["hp2"]
        ini = _poser_ini(win.manager.config.install_path, INI_HP2.replace("DamageTaken=3", "DamageTaken=1")
                         .replace("QuidditchDifficulty=2", "QuidditchDifficulty=0"))
        win._detail.set_game(game)

        class Accepte(course_ui.CourseDialog):
            def exec(self):
                self.empreinte = course.Empreinte("cd" * 32, "cdcdcdcd", ())
                return course_ui.QDialog.DialogCode.Accepted

        monkeypatch.setattr(course_ui, "CourseDialog", Accepte)
        lancee = []
        monkeypatch.setattr(handlers, "on_play", lambda view: lancee.append(view.game.id))
        win._detail.partie_en_cours = lambda: "HP2" if lancee else ""
        course_ui.partir(win._detail)
        assert lancee == ["hp2"]
        (etat,) = mode_course.en_cours("hp2")
        assert mode_course.actif(ini) and "cdcdcdcd HP2 Any%" in etat.ligne_id

    def test_jeu_qui_ne_part_pas_rend_les_reglages(self, make_window, monkeypatch):
        from src.ui import course_ui
        from src.ui import game_detail_handlers as handlers
        self._installe(monkeypatch)
        win = make_window()
        ini = _poser_ini(win.manager.config.install_path)
        avant = ini.read_bytes()
        win._detail.set_game(_CATALOGUE["hp2"])

        class Accepte(course_ui.CourseDialog):
            def exec(self):
                self.empreinte = course.Empreinte("cd" * 32, "cdcdcdcd", ())
                return course_ui.QDialog.DialogCode.Accepted

        monkeypatch.setattr(course_ui, "CourseDialog", Accepte)
        monkeypatch.setattr(course_ui, "bloquants", lambda game, config: [])
        monkeypatch.setattr(handlers, "on_play", lambda view: None)
        win._detail.partie_en_cours = lambda: ""
        course_ui.partir(win._detail)
        assert ini.read_bytes() == avant and mode_course.en_cours() == []


class TestDialogue:
    def test_bloquant_grise_partir(self, qtbot, tmp_path):
        from src.ui.course_ui import CourseDialog
        ini = _poser_ini(tmp_path)
        debut = time.perf_counter()
        dlg = CourseDialog(_CATALOGUE["hp2"], tmp_path, ["Choisissez la difficulté Normal."],
                           mode_course.ecarts("hp2", ini))
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        assert time.perf_counter() - debut < _DEMI_SECONDE
        assert not dlg._partir.isEnabled() and dlg._bloque.isVisible()

    def test_partir_calcule_l_empreinte_dans_un_fil(self, qtbot, tmp_path):
        from src.ui.course_ui import CourseDialog
        _poser_ini(tmp_path)
        exe = tmp_path / Path(_CATALOGUE["hp2"].executable)
        exe.write_bytes(b"exe")
        dlg = CourseDialog(_CATALOGUE["hp2"], tmp_path, [], [])
        qtbot.addWidget(dlg)
        with qtbot.waitSignal(dlg.accepted, timeout=5000):
            dlg._partir.click()
        assert dlg.empreinte is not None and [f.chemin for f in dlg.empreinte.fichiers] == ["system/game.exe"]
        assert (course.racine() / "empreintes.json").is_file()

    def test_choix_de_la_categorie(self, qtbot, tmp_path):
        from src.ui.course_ui import CourseDialog, regle_categorie
        _poser_ini(tmp_path)
        (tmp_path / Path(_CATALOGUE["hp2"].executable)).write_bytes(b"exe")
        dlg = CourseDialog(_CATALOGUE["hp2"], tmp_path, [], [])
        qtbot.addWidget(dlg)
        assert list(dlg.pastilles) == list(course.CATEGORIES) and dlg.categorie == "Any%"
        assert dlg.pastilles["Any%"].isChecked() and dlg._regle.text() == regle_categorie("Any%")
        dlg.pastilles["Glitchless"].click()
        assert dlg.categorie == "Glitchless" and not dlg.pastilles["Any%"].isChecked()
        assert dlg._regle.text() == regle_categorie("Glitchless") != regle_categorie("100%") != ""
        with qtbot.waitSignal(dlg.accepted, timeout=5000):
            dlg._partir.click()
            assert not dlg.pastilles["100%"].isEnabled(), "la catégorie ne change plus pendant l'empreinte"
        assert dlg.categorie == "Glitchless"

    def test_fermer_pendant_le_calcul(self, qtbot, tmp_path):
        from src.ui.course_ui import CourseDialog
        _poser_ini(tmp_path)
        (tmp_path / Path(_CATALOGUE["hp2"].executable)).write_bytes(b"exe")
        dlg = CourseDialog(_CATALOGUE["hp2"], tmp_path, [], [])
        qtbot.addWidget(dlg)
        dlg._partir.click()
        dlg.reject()
        assert dlg._fil is None and dlg.empreinte is None


class TestResultat:
    def test_temps_decoupage_et_resume(self, qtbot, tmp_path):
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtWidgets import QLabel

        from src.ui.course_ui import CourseResultat
        fin = _conclusion(tmp_path)
        debut = time.perf_counter()
        dlg = CourseResultat(fin, "Harry Potter et la Chambre des Secrets")
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        assert time.perf_counter() - debut < _DEMI_SECONDE
        assert dlg.findChild(QLabel, "tempsCourse").text() == "0:34.000"
        textes = " ".join(lb.text() for lb in dlg.findChildren(QLabel))
        assert "PrivetDr" in textes and "Adv1Willow" in textes and "Temps valable" in textes
        assert "la vidéo reste la preuve" in textes.lower()
        dlg._copier()
        copie = QGuiApplication.clipboard().text()
        assert "0:34.000" in copie and fin.code in copie

    def test_categorie_dite_et_copiee(self, qtbot, tmp_path):
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtWidgets import QLabel

        from src.ui.course_ui import CourseResultat
        fin = _conclusion(tmp_path, "100%")
        assert fin.categorie == "100%" and fin.ligne_id.endswith(" HP2 100%") and not fin.refus
        dlg = CourseResultat(fin, "Harry Potter et la Chambre des Secrets")
        qtbot.addWidget(dlg)
        assert "100%" in [lb.text() for lb in dlg.findChildren(QLabel)]
        dlg._copier()
        assert QGuiApplication.clipboard().text().startswith("Harry Potter et la Chambre des Secrets — 100%")

    def test_refus_dits(self, qtbot, tmp_path):
        from PyQt6.QtWidgets import QLabel

        from src.ui.course_ui import CourseResultat, raison
        fin = _conclusion(tmp_path)
        refuse = mode_course.Conclusion(fin.code, fin.jeu, fin.resultat, (course.DEPART_CHARGE,), fin.journal, False)
        dlg = CourseResultat(refuse, "HP2")
        qtbot.addWidget(dlg)
        textes = " ".join(lb.text() for lb in dlg.findChildren(QLabel))
        assert raison(course.DEPART_CHARGE) in textes and "réessaiera" in textes

    def test_chaque_refus_a_sa_phrase(self):
        from src.ui.course_ui import raison
        codes = [v for k, v in vars(course).items() if k.isupper() and isinstance(v, str) and v.islower()
                 and k in {"SANS_SEANCE", "RELANCE", "AUTRE_ID", "SANS_DEPART", "DEPART_CHARGE", "DEPART_CLIC",
                           "DEPART_INCONNU", "SANS_FIN", "RETOUCHE", "TROP_D_IMAGES", "MODE_NON_TENU",
                           "INTERDITS", "SOUS_WINE"}]
        assert len(codes) == 13
        for code in codes + ["sauvegardes", "ini", "journal_tenu"]:
            assert raison(code) != code


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
    """La rubrique Courses du Carnet : là seulement quand une course est gardée, meilleur temps valable,
    suppression après confirmation."""

    @staticmethod
    def _carnet(make_window, monkeypatch, qtbot):
        from src.ui.carnet_page import CarnetPage
        TestFiche._installe(monkeypatch)
        win = make_window()
        carnet = CarnetPage(win.manager, win, jeu="hp2")
        qtbot.addWidget(carnet)
        return win, carnet

    def test_pas_de_rubrique_sans_course(self, make_window, monkeypatch, qtbot):
        from src.ui.carnet_page import COURSES
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        assert COURSES not in carnet._rubriques

    def test_meilleur_temps_et_suppression(self, make_window, monkeypatch, qtbot, tmp_path):
        from PyQt6.QtWidgets import QLabel

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
        textes = " ".join(lb.text() for lb in page.findChildren(QLabel))
        assert "0:34.000" in textes and "Meilleur temps valable" in textes
        monkeypatch.setattr(courses_page, "message", lambda *a, **k: 1)       # « Annuler »
        page.lignes[0].bouton_supprimer.click()
        assert course.dossier(fin.code).is_dir()
        monkeypatch.setattr(courses_page, "message", lambda *a, **k: 0)       # « Supprimer »
        page.lignes[0].bouton_supprimer.click()
        assert not course.dossier(fin.code).exists() and page.lignes == []
        assert "Aucune course" in " ".join(lb.text() for lb in page.findChildren(QLabel))

    def test_par_categorie_et_par_carte(self, make_window, monkeypatch, qtbot, tmp_path):
        from PyQt6.QtWidgets import QLabel

        from src.ui.carnet_page import COURSES
        seule = _conclusion(tmp_path / "jeux")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        carnet.rubrique(COURSES)
        page = carnet._courses
        assert page is not None and page.pastilles == {}, "une seule catégorie : pas de pastilles"
        assert [s.carte for s in page.passages] == ["PrivetDr", "Adv1Willow"]
        assert all(s.code == seule.code for s in page.passages)
        carnet._retirer_courses()
        autre = _conclusion(tmp_path / "jeux2", "Glitchless")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        carnet.rubrique(COURSES)
        page = carnet._courses
        assert page is not None and list(page.pastilles) == ["Any%", "Glitchless"]
        assert page.categorie == "Glitchless" and [li.code for li in page.lignes] == [autre.code], (
            "la catégorie de la course la plus récente d'abord")
        page.pastilles["Any%"].click()
        assert page.categorie == "Any%" and [li.code for li in page.lignes] == [seule.code]
        assert page.pastilles["Any%"].isChecked()
        textes = " ".join(lb.text() for lb in page.findChildren(QLabel))
        assert "Meilleur passage par carte" in textes and "Any%" in textes

    def test_exporter_pour_livesplit(self, make_window, monkeypatch, qtbot, tmp_path):
        import xml.etree.ElementTree as ET

        from src.ui import courses_page
        from src.ui.carnet_page import COURSES
        _conclusion(tmp_path / "jeux")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        carnet.rubrique(COURSES)
        page = carnet._courses
        assert page is not None and page.bouton_livesplit is not None
        cible = tmp_path / "sortie" / "course"
        cible.parent.mkdir()
        monkeypatch.setattr(courses_page.QFileDialog, "getSaveFileName", lambda *a, **k: (str(cible), ""))
        page.bouton_livesplit.click()
        run = ET.fromstring((tmp_path / "sortie" / "course.lss").read_bytes())
        assert [s.findtext("Name") for s in run.findall("Segments/Segment")] == ["PrivetDr", "Adv1Willow"]
        monkeypatch.setattr(courses_page.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
        page.bouton_livesplit.click()                                 # annulé : rien d'écrit, rien ne casse

    def test_changer_de_jeu_rebatit(self, make_window, monkeypatch, qtbot, tmp_path):
        from src.ui.carnet_page import COURSES
        _conclusion(tmp_path / "jeux")
        _, carnet = self._carnet(make_window, monkeypatch, qtbot)
        carnet.rubrique(COURSES)
        avant = carnet._courses
        carnet._retirer_courses()
        assert carnet._courses is None and avant is not None

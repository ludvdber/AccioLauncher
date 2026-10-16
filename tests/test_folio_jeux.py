"""Les pages du folio de HP3, HP5 et HP6 : sauvegardes et jeu FABRIQUÉS, hors écran."""

from datetime import datetime

import pytest

from src.core.i18n import set_language

pytest.importorskip("pytestqt")


def _jeu(game_id: str, executable: str, saves: dict):
    from src.core.game_data import GameData
    return GameData.from_dict({
        "id": game_id, "name": f"Jeu {game_id}", "year": 2004, "description": "d",
        "developer": "d", "executable": executable, "cover_image": "c.jpg", "saves": saves})


@pytest.fixture
def racines(tmp_path, monkeypatch):
    from src.core import sauvegardes
    set_language("fr")
    monkeypatch.setattr(sauvegardes, "racines", lambda: {
        "documents": tmp_path / "Docs", "localappdata": tmp_path / "Local"})
    return tmp_path


class TestHP3:
    def _installe(self, racines):
        from tests.test_folio_hp3 import TestNomsDesCartes, _partie
        jeu = _jeu("hp3", "HP3/system/hppoa.exe", {
            "root": "documents", "folders": ["HP3/Save"], "files": "Save*.usa", "first": 0})
        (racines / "Jeux" / "HP3").mkdir(parents=True)
        TestNomsDesCartes()._jeu(racines / "Jeux" / "HP3", (
            "[All]\r\nWizardName_142=Dzou Yen\r\nWizardName_150=Thadée Thurkell\r\n"
            "wizarddesc_142=Dzou Yen (an 300 environ) - Sorcier chinois.\r\n"
            "wizardmenu_104=Cartes des sorciers célèbres\r\nwizardmenu_112=Cartes des monstres\r\n"
            "achievemntsmenu_2=Défi du Carpe Retractum\r\n"))
        saves = racines / "Docs" / "HP3" / "Save"
        saves.mkdir(parents=True)
        (saves / "Save0.usa").write_bytes(_partie())
        return jeu, racines / "Jeux"

    def test_par_serie_et_la_fiche_de_la_carte(self, qtbot, racines):
        from src.ui.folio_jeux import FolioPageHP3, page_folio
        jeu, install = self._installe(racines)
        page = page_folio(jeu, install)
        qtbot.addWidget(page)
        assert isinstance(page, FolioPageHP3)
        assert [c.numero for c in page._cases] == [1, 2], "une case par carte du catalogue"
        page._cases[1].click()
        assert page._fiche_nom.text() == "Dzou Yen"
        assert (page._fiche_dates.text(), page._fiche_texte.text()) == (
            "an 300 environ", "Sorcier chinois.")

    def test_sans_le_jeu_les_chiffres_restent(self, qtbot, racines):
        from src.ui.folio_jeux import page_folio
        jeu, _ = self._installe(racines)
        page = page_folio(jeu, racines / "ailleurs")
        qtbot.addWidget(page)
        assert page.releve.dragees == 813 and page._cases == []


class TestHP5:
    def test_trois_parties_la_plus_recente_d_abord(self, qtbot, racines):
        from src.ui.folio_jeux import FolioPageHP5, page_folio
        from tests.test_folio_hp5_hp6 import TestHP5 as Fichier
        dossier = racines / "Local" / "EA" / "HPOOTP"
        dossier.mkdir(parents=True)
        (dossier / "HPOOTP").write_bytes(Fichier._fichier(330, 75, 0))
        jeu = _jeu("hp5", "HP5/hp5.exe", {"root": "localappdata", "folders": ["EA/HPOOTP"],
                                           "files": "HPOOTP", "first": 1, "slots": "hp5"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)
        assert isinstance(page, FolioPageHP5)
        assert len(page._lignes) == 3
        assert page.releve.decouverte == 330
        from PyQt6.QtWidgets import QLabel
        textes = {lab.text() for lab in page.findChildren(QLabel)}
        assert {"Personnages rencontrés", "0 / 58", "0 %"} <= textes


class TestHP4:
    def test_l_emplacement(self, qtbot, racines):
        from PyQt6.QtWidgets import QLabel

        from src.ui.folio_jeux import FolioPageHP4, page_folio
        from tests.test_folio_hp4 import _hpgof
        dossier = racines / "Local" / "EA" / "HPGOF"
        dossier.mkdir(parents=True)
        (dossier / "HPGOF").write_bytes(_hpgof())
        jeu = _jeu("hp4", "HP4/gof_f.exe", {"root": "localappdata", "folders": ["EA/HPGOF"],
                                             "files": "HPGOF", "first": 1, "slots": "hp4"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)
        assert isinstance(page, FolioPageHP4)
        assert page.releve.emplacement == 1
        # Sans le jeu installé, les noms français passent par `tr()`.
        textes = {lab.text() for lab in page.findChildren(QLabel)}
        assert {"Compétent(e)", "3 / 38", "Wingardium Leviosa", "Gargouilles", "0 / 6",
                "SORTS", "QUÊTES"} <= textes


class TestHP6:
    def test_la_partie(self, qtbot, racines):
        from src.ui.folio_jeux import FolioPageHP6, page_folio
        from tests.test_folio_hp5_hp6 import _hphbp0
        dossier = racines / "Local" / "EA" / "HPHBP0"
        dossier.mkdir(parents=True)
        (dossier / "HPHBP0").write_bytes(_hphbp0())
        jeu = _jeu("hp6", "HP6/hp6.exe", {"root": "localappdata", "folders": ["EA/HPHBP0"],
                                           "files": "HPHBP0"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)
        assert isinstance(page, FolioPageHP6)
        assert page.releve.ecrite == datetime(2026, 10, 1, 18, 42, 44)
        assert page.releve.sorts == ("Stupefy", "Lumos")
        # Les écussons lieu par lieu, par ordre alphabétique : « Bibliothèque »
        # en tête de la première colonne, et les trois du chemin de la forêt.
        from PyQt6.QtWidgets import QLabel
        textes = [lab.text() for lab in page.findChildren(QLabel)]
        assert "ÉCUSSONS PAR LIEU" in textes     # `surtitre` met en capitales
        assert {"Chemin de la forêt", "3 / 3", "Bibliothèque", "0 / 3"} <= set(textes)
        lieux = [t for t in textes if t in {"Bibliothèque", "Volière", "Cachots"}]
        assert lieux == ["Bibliothèque", "Cachots", "Volière"]

    def test_sans_sauvegarde(self, qtbot, racines):
        from src.ui.folio_jeux import page_folio
        jeu = _jeu("hp6", "HP6/hp6.exe", {"root": "localappdata", "folders": ["EA/HPHBP0"],
                                           "files": "HPHBP0"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)
        assert page.releve is None and page._lignes == {}


def test_le_bloc_de_la_fiche_pour_hp3(qtbot, tmp_path):
    """Sur 80 cartes, et sans maison en tête : HP3 n'écrit pas leurs points."""
    from src.core import folio, folio_hp3
    from src.ui.resume_partie import BlocFolio
    set_language("fr")
    releve = folio_hp3.Releve(1, tmp_path / "Save0.usa", datetime(2026, 9, 20), True,
                              cartes=frozenset({"wc_a", "wc_b"}), total_cartes=80)
    bloc = BlocFolio()
    qtbot.addWidget(bloc)
    bloc.montrer(folio.Resume(releve, "", 2, 80), [], 0)
    assert bloc.texte_compte() == "2 cartes sur 80"
    assert bloc.texte_detail() == ""

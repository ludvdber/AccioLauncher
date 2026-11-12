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
    def test_arreter_coupe_d_abord_le_son_de_la_carte(self, qtbot, racines):
        """Le Carnet qui change de jeu appelle `arreter()` sans `done()` : sans
        `_arreter_son`, le son d'une carte continuait (fusion du 2026-10-29)."""
        from PyQt6.QtCore import QObject

        from src.ui.folio_jeux import page_folio
        from tests.test_folio_hp4 import _hpgof
        dossier = racines / "Local" / "EA" / "HPGOF"
        dossier.mkdir(parents=True)
        (dossier / "HPGOF").write_bytes(_hpgof())
        jeu = _jeu("hp4", "HP4/gof_f.exe", {"root": "localappdata", "folders": ["EA/HPGOF"],
                                             "files": "HPGOF", "first": 1, "slots": "hp4"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)

        class _Lecteur(QObject):
            arrete = False

            def setSource(self, source):
                self.arrete = source.isEmpty()

            def stop(self):
                raise AssertionError("stop() garde le GIL (règle 135)")
        lecteur, sortie = _Lecteur(), QObject()
        page._lecteur_son = (lecteur, sortie)
        page.arreter()
        assert lecteur.arrete and page._lecteur_son is None
        assert page._fil._shutdown, "le décodage s'arrête aussi"

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

    def test_les_jeux_de_cartes_et_la_carte_choisie(self, qtbot, racines):
        """Une case par carte des 26 jeux ; à l'ouverture, la première carte
        possédée qui a une illustration est montrée en grand."""
        from src.ui.folio_jeux import page_folio
        from tests.test_folio_hp4 import _hpgof
        dossier = racines / "Local" / "EA" / "HPGOF"
        dossier.mkdir(parents=True)
        (dossier / "HPGOF").write_bytes(_hpgof(cartes=[1, 7, 151]))
        jeu = _jeu("hp4", "HP4/gof_f.exe", {"root": "localappdata", "folders": ["EA/HPGOF"],
                                             "files": "HPGOF", "first": 1, "slots": "hp4"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)
        assert len(page._vignettes) == 18 * 7 + 3 * 6 + 5 * 6
        assert sum(v.possedee for v in page._vignettes) == 3
        montree = page._carte_montree_hp4
        assert (montree.jeu.image, montree.rang) == ("wc_hry_set1", 0)
        assert page._carte_etat.text() == "Obtenue"
        # La carte de la créature elle-même n'a pas d'illustration dans le jeu.
        fangieux = next(v for v in page._vignettes if v.jeu.image == "wc_dugbog" and v.rang == 4)
        fangieux.click()
        assert page._carte_etat.text() == "Obtenue, sans illustration dans le jeu"
        page.done(0)

    def test_le_son_de_la_carte_suit_le_son_coupe(self, qtbot, racines, monkeypatch):
        """Une carte possédée demande le son de sa scène ; le son coupé du launcher l'interdit."""
        from types import SimpleNamespace

        from src.core import sons_cartes_hp4
        from src.ui.folio_jeux import page_folio
        from tests.test_folio_hp4 import _hpgof
        dossier = racines / "Local" / "EA" / "HPGOF"
        dossier.mkdir(parents=True)
        (dossier / "HPGOF").write_bytes(_hpgof(cartes=[1, 151]))
        jeu = _jeu("hp4", "HP4/gof_f.exe", {"root": "localappdata", "folders": ["EA/HPGOF"],
                                             "files": "HPGOF", "first": 1, "slots": "hp4"})
        demandes = []
        monkeypatch.setattr(sons_cartes_hp4, "son_carte", lambda system, flux: demandes.append(flux))
        config = SimpleNamespace(son_coupe=True, volume_musique=50, install_path=racines / "Jeux")
        page = page_folio(jeu, racines / "Jeux", config=config)
        qtbot.addWidget(page)
        fangieux = next(v for v in page._vignettes if v.jeu.image == "wc_dugbog" and v.rang == 4)
        fangieux.click()
        qtbot.wait(50)
        assert demandes == []
        config.son_coupe = False
        harry = next(v for v in page._vignettes if v.jeu.image == "wc_hry_set1" and v.rang == 0)
        harry.click()
        fangieux.click()
        qtbot.waitUntil(lambda: demandes[-1:] == [fangieux.jeu.flux], timeout=2000)
        page.done(0)


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
        # Les onze sorts, ceux à venir en pointillés, et le compte.
        from PyQt6.QtWidgets import QFrame
        assert len(page.findChildren(QFrame, "sortAppris")) == 2
        assert len(page.findChildren(QFrame, "sortAVenir")) == 9
        # Les écussons lieu par lieu, par ordre alphabétique : « Bibliothèque »
        # en tête de la première colonne, et les trois du chemin de la forêt.
        from PyQt6.QtWidgets import QLabel
        textes = [lab.text() for lab in page.findChildren(QLabel)]
        assert "ÉCUSSONS PAR LIEU" in textes     # `surtitre` met en capitales
        assert {"Chemin de la forêt", "3 / 3", "Bibliothèque", "0 / 3", "2 / 11"} <= set(textes)
        lieux = [t for t in textes if t in {"Bibliothèque", "Volière", "Cachots"}]
        assert lieux == ["Bibliothèque", "Cachots", "Volière"]
        # Le chemin de la forêt, fini (3 / 3), passe après tous les lieux à fouiller.
        noms = [lab.text() for lab in page.findChildren(QLabel)
                if lab.objectName() in {"lieuFini", "lieuAFouiller"}]
        assert noms.index("Chemin de la forêt") > noms.index("Volière")
        assert [lab.text() for lab in page.findChildren(QLabel, "lieuFini")] == [
            "Chemin de la forêt", "Dortoir des garçons", "Pont couvert"]

    def test_les_trois_emplacements(self, qtbot, racines):
        """Firox, Discord, 2026-11-02 : le Carnet montrait la partie de sa
        copine (`HPHBP0`), pas la sienne. HP6 a trois emplacements, un dossier
        chacun ; catalogue 0.52 : la racine est le dossier du jeu."""
        from src.ui.folio_jeux import page_folio
        from tests.test_folio_hp5_hp6 import _hphbp0
        for n, (ecussons, quand) in enumerate([(7, datetime(2026, 10, 1)), (3, datetime(2026, 10, 20))]):
            dossier = racines / "Local" / "EA" / "HP6" / f"HPHBP{n}"
            dossier.mkdir(parents=True)
            (dossier / f"HPHBP{n}").write_bytes(_hphbp0(ecussons=ecussons, quand=quand))
        jeu = _jeu("hp6", "HP6/hp6.exe", {"root": "localappdata", "folders": ["EA/HP6"],
                                           "files": "HPHBP?/HPHBP?"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)
        assert sorted(page._lignes) == [1, 2], "une ligne par emplacement, aucune écrasée"
        assert page.releve.emplacement == 2, "la dernière partie jouée d'abord"
        assert page._entree(page.releves[0])[0] == "Partie 1"
        page.choisir(1)
        assert page.releve.emplacement == 1

    def test_sans_sauvegarde(self, qtbot, racines):
        from src.ui.folio_jeux import page_folio
        jeu = _jeu("hp6", "HP6/hp6.exe", {"root": "localappdata", "folders": ["EA/HPHBP0"],
                                           "files": "HPHBP0"})
        page = page_folio(jeu, racines / "Jeux")
        qtbot.addWidget(page)
        assert page.releve is None and page._lignes == {}


class TestLieuxHP6:
    """Constat car5 (2026-11-12) : à 1920 × 1080, les badges laissaient 1 000 px
    vides à leur droite et les 43 lieux tombaient sous la ligne de flottaison,
    triés par nom, les lieux finis mêlés aux autres, 700 px entre nom et compte."""

    @staticmethod
    def _lieux(trouves: frozenset[int] = frozenset()):
        from src.core import folio_hp6
        return folio_hp6.par_lieu(trouves)

    def test_les_lieux_finis_a_la_fin(self):
        from src.core import folio_hp6
        from src.ui.folio_jeux import _lieux_ordonnes
        set_language("fr")
        lieux = [folio_hp6.Lieu("Volière", 1, 3), folio_hp6.Lieu("Écuries", 2, 2),
                 folio_hp6.Lieu("Bibliothèque", 0, 3), folio_hp6.Lieu("Cachots", 4, 4),
                 folio_hp6.Lieu("Entrée", 0, 1)]
        assert [nom for nom, _ in _lieux_ordonnes(lieux)] == [
            "Bibliothèque", "Entrée", "Volière", "Cachots", "Écuries"]

    def test_les_lieux_finis_grises(self, qtbot):
        from PyQt6.QtWidgets import QLabel
        from src.core import folio_hp6
        from src.ui.composants import ENCRE, ENCRE_DISCRETE
        from src.ui.folio_jeux import FolioPageHP6
        set_language("fr")
        cadre = FolioPageHP6._lieux([folio_hp6.Lieu("Volière", 1, 3),
                                     folio_hp6.Lieu("Cachots", 4, 4)])
        qtbot.addWidget(cadre)
        fini = cadre.findChild(QLabel, "lieuFini")
        reste = cadre.findChild(QLabel, "lieuAFouiller")
        assert fini.text() == "Cachots" and ENCRE_DISCRETE in fini.styleSheet()
        assert reste.text() == "Volière" and ENCRE in reste.styleSheet()

    def test_pas_de_desert_entre_nom_et_compte(self, qtbot):
        """Le cadre prend la largeur de ses colonnes, pas celle de la page."""
        from src.ui.folio_jeux import FolioPageHP6, _BadgesEtLieux
        set_language("fr")
        cadre = FolioPageHP6._lieux(self._lieux())
        bloc = _BadgesEtLieux(None, cadre)
        qtbot.addWidget(bloc)
        bloc.resize(1800, 900)
        bloc.show()
        qtbot.waitExposed(bloc)
        assert cadre.width() <= cadre.sizeHint().width() < 1100

    def _bloc(self, qtbot, largeur: int):
        from PyQt6.QtWidgets import QWidget
        from src.ui.folio_jeux import FolioPageHP6, _BadgesEtLieux
        set_language("fr")
        badges = QWidget()
        badges.setMinimumSize(300, 200)
        cadre = FolioPageHP6._lieux(self._lieux())
        bloc = _BadgesEtLieux(badges, cadre)
        qtbot.addWidget(bloc)
        bloc.resize(largeur, 1200)
        bloc.show()
        qtbot.waitExposed(bloc)
        return bloc, badges, cadre

    def test_large_cote_a_cote(self, qtbot):
        # 1920 px de fenêtre : la page fait ~1 570 px, rail et marges ôtés.
        bloc, badges, cadre = self._bloc(qtbot, 1570)
        qtbot.waitUntil(bloc.cote_a_cote)
        qtbot.waitUntil(lambda: cadre.x() > badges.x() + badges.width())
        assert cadre.y() == badges.y()

    def test_etroit_empile(self, qtbot):
        bloc, badges, cadre = self._bloc(qtbot, 900)
        assert not bloc.cote_a_cote()
        qtbot.waitUntil(lambda: cadre.y() >= badges.y() + badges.height())

    def test_la_barre_de_defilement_ne_fait_pas_basculer(self, qtbot):
        from src.ui.folio_jeux import _BadgesEtLieux
        bloc, _, _ = self._bloc(qtbot, _BadgesEtLieux.COTE_A_COTE)
        qtbot.waitUntil(bloc.cote_a_cote)
        bloc.resize(_BadgesEtLieux.COTE_A_COTE - 12, 1200)
        qtbot.wait(20)
        assert bloc.cote_a_cote()
        bloc.resize(_BadgesEtLieux.COTE_A_COTE - 200, 1200)
        qtbot.waitUntil(lambda: not bloc.cote_a_cote())

    def test_un_nom_sur_une_ligne_quand_la_place_le_permet(self, qtbot):
        """Relecture car5 : la largeur que Qt devine d'un libellé à la ligne
        (~150 px) coupait les noms en deux à 1920 px, toutes les rangées doublées."""
        from PyQt6.QtWidgets import QLabel
        bloc, _, cadre = self._bloc(qtbot, 1570)
        qtbot.waitUntil(bloc.cote_a_cote)
        nom = next(lab for lab in cadre.findChildren(QLabel)
                   if lab.text() == "Couloir de la Salle sur Demande")
        qtbot.waitUntil(lambda: nom.height() < 2 * nom.fontMetrics().lineSpacing())

    def test_la_page_peut_encore_retrecir(self, qtbot):
        """Les minima des noms suivent la largeur reçue sans devenir celui du
        bloc : sinon la fenêtre réduite gardait une barre de défilement horizontale."""
        bloc, _, _ = self._bloc(qtbot, 1570)
        qtbot.waitUntil(bloc.cote_a_cote)
        bloc.resize(900, 1200)
        qtbot.waitUntil(lambda: not bloc.cote_a_cote())
        assert bloc.minimumSizeHint().width() < 600


def test_le_bloc_de_la_fiche_pour_hp3(qtbot, tmp_path):
    """Sur 80 cartes, et sans maison en tête : HP3 n'écrit pas leurs points."""
    from src.core import folio, folio_hp3
    from src.ui.resume_partie import BlocFolio
    set_language("fr")
    releve = folio_hp3.Releve(1, tmp_path / "Save0.usa", datetime(2026, 9, 20), True,
                              cartes=frozenset({"wc_a", "wc_b"}), total_cartes=80)
    bloc = BlocFolio()
    qtbot.addWidget(bloc)
    bloc.montrer(folio.Resume(releve, "", 2, 80), [])
    assert bloc.texte_compte() == "2 cartes sur 80"
    assert bloc.texte_detail() == ""


class TestRangee:
    """Les tuiles passent à la ligne au lieu de se couper : à 980 px, « 6 / 80 »
    de HP3 sortait de sa tuile (capture de Ludo, 2026-10-17)."""

    def _rangee(self, qtbot, largeur: int):
        from src.ui.folio_page import Rangee, _tuile
        tuiles = [_tuile(f"{n} / 80", "Cartes trouvées") for n in range(4)]
        rangee = Rangee(*tuiles)
        qtbot.addWidget(rangee)
        rangee.resize(largeur, 300)
        rangee.show()
        qtbot.waitExposed(rangee)
        return rangee, tuiles

    def test_large_une_ligne(self, qtbot):
        _, tuiles = self._rangee(qtbot, 1600)
        assert len({t.y() for t in tuiles}) == 1

    def test_etroite_deux_lignes_de_deux(self, qtbot):
        rangee, tuiles = self._rangee(qtbot, 2 * tuiles_min(qtbot) + 40)
        qtbot.waitUntil(lambda: len({t.y() for t in tuiles}) == 2)
        assert all(t.width() >= t.minimumSizeHint().width() for t in tuiles)
        assert rangee.minimumSizeHint().width() < 2 * tuiles[0].minimumSizeHint().width()


def tuiles_min(qtbot) -> int:
    from src.ui.folio_page import _tuile
    t = _tuile("6 / 80", "Cartes trouvées")
    qtbot.addWidget(t)
    return t.minimumSizeHint().width()

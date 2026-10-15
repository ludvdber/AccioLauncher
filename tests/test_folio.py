"""Le folio de HP1 : lecture de la sauvegarde, textes du jeu, page.

Les sauvegardes sont FABRIQUÉES sur le modèle relevé chez Ludo le 2026-10-14
(bloc texte d'Harry au milieu d'un binaire, `GameSaveInfoN` à côté).
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

from src.core import folio
from src.core.i18n import set_language

BLOC = (b"\x00\x01\x07Player\x00u\nClass=HarryPotter.Harry Name=Harry0\r\n{\r\n"
        b"numHousePointsHarry=155\r\nnumHousePointsGryffindor=155\r\n"
        b"numHousePointsSlytherin=173\r\nnumHousePointsHufflepuff=93\r\n"
        b"numHousePointsRavenclaw=111\r\nnumBeans=112\r\n"
        b"WizardCards[0]=(bHasCard=True)\r\nWizardCards[3]=(bHasCard=True)\r\n"
        b"WizardCards[24]=(bHasCard=True)\r\nWizardCards[25]=(bHasCard=True)\r\n"
        b"Weapon=baseWand4\r\nbaseWand'LEV_TUT3B.baseWand4'\r\n}\r\n"
        b"Class=HPBase.baseWand Name=baseWand4\r\n{\r\n}\r\n\x00x\x1c")

MENU = ("[Wizards]\r\n"
        "wizard_card_new_01=Merlin. Moyen Age, dates inconnues. Le plus célèbre sorcier.\r\n"
        "wizard_card_new_04=Albus Dumbledore.  ??? - vit encore. Directeur.\r\n"
        "wizard_card_new_28=Hengist de Woodcroft. Moyen Age. Ecosse. fondant.\r\n"
        "wizard_card_new_28b=Hengist de Woodcroft. Moyen Age. Ecosse, fondant.\r\n"
        "title_lev2_hogfront=Parc de Poudlard\r\n"
        "[Autre]\r\nwizard_card_new_01=\r\ntitle_lev2_hogfront=\r\n")


def _info(niveau: bytes) -> bytes:
    return b"~\x00\x00\x00\x00\x00\x00\x00\x9b\x00\x00\x00\xff\xff\xff\xff" + \
        bytes([len(niveau) + 1]) + niveau + b"\x00"


def _save(dossier: Path, n: int, contenu: bytes, niveau: bytes, quand: datetime) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"Save{n}.usa"
    chemin.write_bytes(b"\x00" * 300 + contenu + b"\x00" * 300)
    (dossier / f"GameSaveInfo{n}").write_bytes(_info(niveau))
    os.utime(chemin, (quand.timestamp(), quand.timestamp()))
    return chemin


class TestLecture:
    def test_le_bloc_d_harry(self):
        bloc = folio.lire_bloc_hp1(BLOC)
        assert bloc["points"] == {"gryffondor": 155, "serpentard": 173,
                                  "serdaigle": 111, "poufsouffle": 93}
        assert bloc["dragees"] == 112 and bloc["points_harry"] == 155
        assert bloc["cartes"] == frozenset({1, 4, 25}), "emplacements 1 à 25, le 26e est ignoré"

    def test_sans_bloc_rien_n_est_invente(self):
        assert folio.lire_bloc_hp1(b"\x00" * 1000) is None

    def test_une_propriete_absente_vaut_zero(self):
        """Unreal n'écrit que ce qui diffère de la valeur par défaut."""
        bloc = folio.lire_bloc_hp1(b"Class=HarryPotter.Harry Name=Harry0\r\n{\r\nnumBeans=3\r\n}")
        assert bloc["points"][folio.SERDAIGLE] == 0 and bloc["cartes"] == frozenset()

    def test_le_niveau_de_game_save_info(self, tmp_path):
        info = tmp_path / "GameSaveInfo0"
        info.write_bytes(_info(b"LEV2_HOGFRONT"))
        assert folio.niveau_hp1(info) == "LEV2_HOGFRONT"
        info.write_bytes(b"\x00" * 12 + b"\xff\xff\xff\xff\x09Lev_Tut1\x00")
        assert folio.niveau_hp1(info) == "Lev_Tut1"

    @pytest.mark.parametrize("brut", [b"", b"\xff\xff\xff\xff", b"\xff\xff\xff\xff\x05a/b\x00x"])
    def test_un_info_fautif_rend_vide(self, tmp_path, brut):
        info = tmp_path / "GameSaveInfo0"
        info.write_bytes(brut)
        assert folio.niveau_hp1(info) == ""

    def test_emplacements_dans_l_ordre_du_menu(self, tmp_path):
        d = tmp_path / "Save"
        _save(d, 1, b"rien", b"Lev_Tut1", datetime(2026, 4, 3))
        _save(d, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        releves = folio.emplacements_hp1({p.name: p for p in d.glob("Save*.usa")})
        assert [(r.emplacement, r.lu, r.niveau) for r in releves] == [
            (1, True, "LEV2_HOGFRONT"), (2, False, "Lev_Tut1")]
        assert folio.le_plus_avance(releves).emplacement == 1

    def test_un_seul_emplacement_n_a_rien_a_departager(self, tmp_path):
        d = tmp_path / "Save"
        _save(d, 0, BLOC, b"X", datetime(2026, 3, 8))
        assert folio.le_plus_avance(folio.emplacements_hp1({"Save0.usa": d / "Save0.usa"})) is None

    def test_qui_mene(self, tmp_path):
        d = tmp_path / "Save"
        _save(d, 0, BLOC, b"X", datetime(2026, 3, 8))
        (releve,) = folio.emplacements_hp1({"Save0.usa": d / "Save0.usa"})
        assert releve.en_tete() == (folio.SERPENTARD, 18)


class TestTextesDuJeu:
    def test_cartes_et_lieux_en_windows_1252(self, tmp_path):
        system = tmp_path / "System"
        system.mkdir()
        (system / "HPmenu.fre").write_bytes(MENU.encode("cp1252"))
        (system / "HPMenu.int").write_bytes(b"wizard_card_new_01=Merlin. Medieval. Famous.\r\n")
        cartes, titres = folio.textes_hp1(folio.fichier_textes(system, "fr"))
        # L'ordre du FOLIO du jeu, pas celui du fichier de textes : l'emplacement 1
        # est Dumbledore (texte 04), le 2 Merlin (texte 01), le 20 Hengist (texte 28).
        assert cartes[2] == folio.Carte(2, "Merlin", "Moyen Age, dates inconnues",
                                        "Le plus célèbre sorcier.")
        assert cartes[1].dates == "??? - vit encore"
        assert cartes[20].texte == "Ecosse, fondant.", "la variante corrigée « b » l'emporte"
        assert folio.lieu(titres, "LEV2_HOGFRONT") == "Parc de Poudlard"

    def test_sans_la_langue_l_anglais(self, tmp_path):
        system = tmp_path / "System"
        system.mkdir()
        (system / "HPMenu.int").write_bytes(b"wizard_card_new_01=Merlin. Medieval. Famous.\r\n")
        assert folio.fichier_textes(system, "es").name == "HPMenu.int"

    def test_jeu_absent(self, tmp_path):
        assert folio.textes_hp1(folio.fichier_textes(tmp_path / "rien", "fr")) == ({}, {})


class TestResumeDeLaFiche:
    """Ce qui remplace la description : la dernière partie LISIBLE, et son lieu."""

    @staticmethod
    def _system(tmp_path: Path) -> Path:
        system = tmp_path / "System"
        system.mkdir()
        (system / "HPmenu.fre").write_bytes(MENU.encode("cp1252"))
        return system

    def test_la_derniere_lisible_et_son_lieu(self, tmp_path):
        saves = tmp_path / "Save"
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        _save(saves, 1, b"rien", b"Lev_Tut1", datetime(2026, 10, 1))
        fichiers = {p.name: p for p in saves.glob("Save*.usa")}
        resume = folio.resume_hp1(fichiers, self._system(tmp_path), "fr")
        assert resume is not None
        assert resume.releve.emplacement == 1, "un début de jeu plus récent ne compte pas"
        assert resume.lieu == "Parc de Poudlard"

    def test_rien_de_lisible_la_description_reste(self, tmp_path):
        saves = tmp_path / "Save"
        _save(saves, 0, b"rien", b"Lev_Tut1", datetime(2026, 10, 1))
        fichiers = {p.name: p for p in saves.glob("Save*.usa")}
        assert folio.resume_hp1(fichiers, self._system(tmp_path), "fr") is None

    def test_sans_sauvegarde(self, tmp_path):
        assert folio.resume_hp1({}, self._system(tmp_path), "fr") is None

    def test_sans_les_textes_du_jeu_pas_de_lieu(self, tmp_path):
        saves = tmp_path / "Save"
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        fichiers = {p.name: p for p in saves.glob("Save*.usa")}
        resume = folio.resume_hp1(fichiers, tmp_path / "absent", "fr")
        assert resume is not None and resume.lieu == ""


pytest.importorskip("pytestqt")


@pytest.fixture
def hp1(tmp_path, monkeypatch):
    """Un HP1 installé et ses sauvegardes, dans tmp_path."""
    from src.core import sauvegardes
    from src.core.game_data import GameData
    set_language("fr")
    monkeypatch.setattr(sauvegardes, "racines", lambda: {"documents": tmp_path / "Docs"})
    jeu = GameData.from_dict({
        "id": "hp1", "name": "Harry Potter à l'École des Sorciers", "year": 2001,
        "description": "d", "developer": "d", "executable": "HP1/System/HP.exe",
        "cover_image": "c.jpg",
        "saves": {"root": "documents", "folders": ["Harry Potter/Save"],
                  "files": "Save*.usa", "first": 0}})
    system = tmp_path / "Jeux" / "HP1" / "System"
    system.mkdir(parents=True)
    (system / "HPmenu.fre").write_bytes(MENU.encode("cp1252"))
    return jeu, tmp_path / "Jeux", tmp_path / "Docs" / "Harry Potter" / "Save"


class TestPage:
    def test_ouvre_sur_la_derniere_jouee(self, qtbot, hp1):
        from src.ui.folio_page import FolioPage
        jeu, install, saves = hp1
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        _save(saves, 1, BLOC.replace(b"numBeans=3", b"numBeans=1"), b"Lev_Tut1", datetime(2026, 10, 1))
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        assert page.releve.emplacement == 2, "la plus récente, pas la plus avancée"

    def test_une_derniere_illisible_cede_a_une_lisible(self, qtbot, hp1):
        from src.ui.folio_page import FolioPage
        jeu, install, saves = hp1
        _save(saves, 0, b"rien", b"Lev_Tut1", datetime(2026, 10, 1))
        _save(saves, 1, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        assert page.releve.emplacement == 2
        assert page.phrase_coupe.text() == "Serpentard mène de 18 points"
        assert page.carte_montree == 1 and page._fiche_nom.text() == "Albus Dumbledore"

    def test_une_carte_pas_trouvee_ne_se_devoile_pas(self, qtbot, hp1):
        from src.ui.folio_page import FolioPage
        jeu, install, saves = hp1
        _save(saves, 0, BLOC, b"X", datetime(2026, 3, 8))
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        page._cases[1].click()   # emplacement 2 (Merlin), pas trouvé
        assert page._fiche_nom.text() == "Pas encore trouvée"
        assert "célèbre" not in page._fiche_texte.text()
        assert page._fiche_image.isHidden(), "l'image la dévoilerait"

    def test_la_carte_trouvee_montre_son_image_du_jeu(self, qtbot, hp1):
        from src.ui.folio_page import FolioPage
        from tests.test_textures_ue1 import paquet
        jeu, install, saves = hp1
        (install / "HP1" / "System" / "HPMenu.u").write_bytes(paquet("WizCardDumbledoreBigTexture"))
        _save(saves, 0, BLOC, b"X", datetime(2026, 3, 8))
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        assert page.carte_montree == 1 and not page._fiche_image.isHidden()
        assert not page._fiche_image.pixmap().isNull()

    def test_sans_le_jeu_pas_d_image_mais_la_fiche(self, qtbot, hp1):
        from src.ui.folio_page import FolioPage
        jeu, install, saves = hp1
        _save(saves, 0, BLOC, b"X", datetime(2026, 3, 8))
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        assert page._fiche_image.isHidden() and page._fiche_nom.text() == "Albus Dumbledore"

    def test_debut_de_jeu_il_le_dit(self, qtbot, hp1):
        from PyQt6.QtWidgets import QLabel
        from src.ui.folio_page import FolioPage
        jeu, install, saves = hp1
        _save(saves, 0, b"rien", b"Lev_Tut1", datetime(2026, 10, 1))
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        textes = " ".join(lbl.text() for lbl in page.findChildren(QLabel))
        assert "tout début du jeu" in textes and "Hall" not in textes

    def test_sans_sauvegarde(self, qtbot, hp1):
        from PyQt6.QtWidgets import QLabel
        from src.ui.folio_page import FolioPage
        jeu, install, _saves = hp1
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        assert any("Aucune sauvegarde" in lbl.text() for lbl in page.findChildren(QLabel))

    def test_le_retour_rouvre_mes_annees(self, qtbot, hp1):
        from PyQt6.QtWidgets import QPushButton
        from src.ui.folio_page import FolioPage
        jeu, install, _saves = hp1
        revenu = []
        page = FolioPage(jeu, install, revenir=lambda: revenu.append(1))
        qtbot.addWidget(page)
        retour = page.findChild(QPushButton, "retour")
        assert retour.text() == "Mes années"
        retour.click()
        assert revenu == [1]

    def test_rien_n_est_ecrit_dans_les_sauvegardes(self, qtbot, hp1):
        from src.ui.folio_page import FolioPage
        jeu, install, saves = hp1
        chemin = _save(saves, 0, BLOC, b"X", datetime(2026, 3, 8))
        avant = (chemin.read_bytes(), chemin.stat().st_mtime)
        page = FolioPage(jeu, install)
        qtbot.addWidget(page)
        assert (chemin.read_bytes(), chemin.stat().st_mtime) == avant


class TestDepuisMesAnnees:
    def test_le_bouton_du_folio_ouvre_la_page(self, qtbot, tmp_path, monkeypatch):
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.folio_page import FolioPage
        from src.ui.stats_dialog import StatsDialog
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        manager = GameManager(Config(install_path=tmp_path / "g", cache_path=tmp_path / "c"))
        jeux = [e.game.id for e in manager.get_games() if e.game.id in folio.JEUX]
        if not jeux:
            pytest.skip("aucun jeu du folio dans ce catalogue")
        ouvertes = []
        dlg = StatsDialog(manager, ouvrir_page=lambda page, *_cle: ouvertes.append(page))
        qtbot.addWidget(dlg)
        dlg.ouvrir_folio(jeux[0])
        assert len(ouvertes) == 1 and isinstance(ouvertes[0], FolioPage)
        qtbot.addWidget(ouvertes[0])

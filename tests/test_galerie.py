"""La galerie des captures : la liste, les mois, la page, le partage."""

import os
from datetime import datetime
from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QImage

from src.core import captures, galerie
from src.core.game_data import GameData
from src.core.i18n import set_language


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


def _jeu(id_jeu: str, nom: str) -> GameData:
    return GameData.from_dict({
        "id": id_jeu, "name": nom, "year": 2005, "description": "d", "developer": "d",
        "executable": f"{id_jeu}/jeu.exe", "cover_image": "c.jpg"})


def _capture(jeu: GameData, nom: str, quand: datetime, taille=(64, 36)) -> Path:
    dossier = captures.dossier(jeu)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    image = QImage(*taille, QImage.Format.Format_RGB32)
    image.fill(QColor("steelblue"))
    assert image.save(str(chemin), "PNG")
    os.utime(chemin, (quand.timestamp(), quand.timestamp()))
    return chemin


HP4 = _jeu("hp4", "Harry Potter et la Coupe de Feu")
HP5 = _jeu("hp5", "Harry Potter et l'Ordre du Phénix")


class TestListe:
    def test_les_plus_recentes_d_abord_tous_jeux_confondus(self):
        _capture(HP4, "a.png", datetime(2026, 9, 3, 20, 0))
        _capture(HP5, "b.png", datetime(2026, 10, 14, 21, 3))
        _capture(HP4, "c.png", datetime(2026, 10, 1, 18, 0))
        liste = galerie.lister([HP4, HP5])
        assert [c.chemin.name for c in liste] == ["b.png", "c.png", "a.png"]

    def test_groupees_par_mois(self):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        _capture(HP4, "c.png", datetime(2026, 10, 1))
        groupes = galerie.par_mois(galerie.lister([HP4, HP5]))
        assert [(cle, len(liste)) for cle, liste in groupes] == [((2026, 10), 2), ((2026, 9), 1)]

    def test_compte_par_jeu(self):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP4, "b.png", datetime(2026, 9, 4))
        assert galerie.compte_par_jeu(galerie.lister([HP4, HP5])) == {"hp4": 2}

    def test_sans_dossier_rien(self):
        assert galerie.lister([HP4, HP5]) == []

    def test_un_dossier_partage_n_est_lu_qu_une_fois(self):
        jumeau = _jeu("hp4b", "Harry Potter et la Coupe de Feu")
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        assert len(galerie.lister([HP4, jumeau])) == 1


pytest.importorskip("pytestqt")


class TestTextes:
    @pytest.mark.parametrize("nom,court", [
        ("Harry Potter et la Coupe de Feu", "La Coupe de Feu"),
        ("Harry Potter and the Goblet of Fire", "The Goblet of Fire"),
        ("Harry Potter y el cáliz de fuego", "El cáliz de fuego"),
        ("Autre jeu", "Autre jeu"),
    ])
    def test_nom_court(self, nom, court):
        from src.ui.galerie_page import nom_court
        assert nom_court(nom) == court

    def test_le_mois_en_capitales(self):
        from src.ui.galerie_page import mois
        assert mois(2026, 10) == "OCTOBRE 2026"


class TestPage:
    def _page(self, qtbot, jeu=""):
        from src.ui.galerie_page import GaleriePage
        page = GaleriePage([HP4, HP5], jeu=jeu)
        qtbot.addWidget(page)
        return page

    def test_vide_elle_le_dit_et_ne_propose_rien(self, qtbot):
        from PyQt6.QtWidgets import QLabel
        page = self._page(qtbot)
        assert page.choisie is None
        assert not page._partager.isEnabled()
        textes = " ".join(lbl.text() for lbl in page.findChildren(QLabel))
        assert "Pas encore de capture" in textes
        assert "inutile de le signaler" in textes, "la note F12 de HP1-HP3 doit rester"

    def test_ouvre_sur_la_plus_recente(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        page = self._page(qtbot)
        assert page.choisie.chemin.name == "b.png"
        assert "2560" not in page._details.text() and "64 × 36" in page._details.text()

    def test_le_filtre_ne_garde_que_le_jeu(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        page = self._page(qtbot)
        page.filtrer("hp4")
        visibles = [v.capture.chemin.name for v in page._vignettes if not v.isHidden()]
        assert visibles == ["a.png"]
        assert page.choisie.chemin.name == "a.png", "la choisie cachée laisse place à une visible"
        page.filtrer("")
        assert len([v for v in page._vignettes if not v.isHidden()]) == 2

    def test_ouverte_sur_un_jeu(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        assert self._page(qtbot, "hp4").choisie.chemin.name == "a.png"

    def test_les_vignettes_se_chargent_apres_l_ouverture(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        assert page._vignettes[0]._pix is None
        qtbot.waitUntil(lambda: page._vignettes[0]._pix is not None, timeout=2000)

    def test_partager_copie_puis_ouvre_le_discord(self, qtbot, monkeypatch):
        from PyQt6.QtGui import QGuiApplication
        from src.core.liens import DISCORD_MEDIAS_URL
        ouverts = []
        monkeypatch.setattr("src.ui.galerie_page.open_url", ouverts.append)
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        page._partager.click()
        assert ouverts == [DISCORD_MEDIAS_URL], "le salon des captures, pas l'invitation"
        assert QGuiApplication.clipboard().image().width() == 64
        assert "Ctrl+V" in page._confirmation.text() and not page._confirmation.isHidden()

    def test_ouvrir_l_image_la_donne_a_la_visionneuse(self, qtbot, monkeypatch):
        ouverts = []
        monkeypatch.setattr("src.ui.galerie_page.open_local_path", ouverts.append)
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        page._ouvrir.click()
        assert ouverts == [str(chemin)], "l'image elle-même, pas son dossier"

    def test_vide_ouvrir_l_image_est_eteint(self, qtbot):
        assert not self._page(qtbot)._ouvrir.isEnabled()

    def test_une_image_illisible_ne_promet_rien(self, qtbot, monkeypatch):
        ouverts = []
        monkeypatch.setattr("src.ui.galerie_page.open_url", ouverts.append)
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        chemin.write_bytes(b"pas une image")
        page._partager.click()
        assert ouverts == [], "Discord ne s'ouvre pas pour une image qui n'est pas copiée"
        assert "ne se lit pas" in page._confirmation.text()


class TestDepuisMesAnnees:
    def test_le_bouton_ouvre_la_galerie(self, qtbot, tmp_path, monkeypatch):
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.galerie_page import GaleriePage
        from src.ui.stats_dialog import StatsDialog
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        manager = GameManager(Config(install_path=tmp_path / "g", cache_path=tmp_path / "c"))
        ouvertes = []
        dlg = StatsDialog(manager, ouvrir_page=lambda page, cle="": ouvertes.append((page, cle)))
        qtbot.addWidget(dlg)
        dlg.ouvrir_galerie()
        assert len(ouvertes) == 1 and isinstance(ouvertes[0][0], GaleriePage)
        assert ouvertes[0][1] == "galerie", "l'onglet Galerie se souligne, même venue de Mes années"
        qtbot.addWidget(ouvertes[0][0])

    def test_sans_hote_pas_de_bouton(self, qtbot, tmp_path, monkeypatch):
        from PyQt6.QtWidgets import QPushButton
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.stats_dialog import StatsDialog
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        manager = GameManager(Config(install_path=tmp_path / "g", cache_path=tmp_path / "c"))
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert not [b for b in dlg.findChildren(QPushButton) if b.text().startswith("Galerie")]


class TestVignettesEnCache:
    """Une capture de 10 Mo coûtait 155 ms à chaque ouverture (2026-10-14)."""

    def test_rangee_puis_relue_sans_redecoder(self, qtbot, monkeypatch):
        from src.ui import galerie_page
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3), taille=(1920, 1080))
        premiere = galerie_page._vignette(chemin)
        cache = galerie.chemin_vignette(chemin)
        assert cache is not None and cache.is_file()
        assert premiere.width() == galerie_page._VIGNETTE.width() * 2

        def interdit(*_a):
            raise AssertionError("la capture a été redécodée")
        monkeypatch.setattr(galerie_page, "_lire", interdit)
        assert not galerie_page._vignette(chemin).isNull()

    def test_une_capture_remplacee_a_une_autre_vignette(self):
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3))
        avant = galerie.chemin_vignette(chemin)
        _capture(HP4, "a.png", datetime(2026, 9, 4), taille=(80, 45))
        assert galerie.chemin_vignette(chemin) != avant

    def test_capture_disparue(self, tmp_path):
        assert galerie.chemin_vignette(tmp_path / "absente.png") is None

    def test_fermer_la_page_arrete_le_chargement(self, qtbot):
        from src.ui.galerie_page import GaleriePage
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = GaleriePage([HP4])
        qtbot.addWidget(page)
        page.accept()
        assert not page._chargeur.isActive()

    def test_l_apercu_arrive_en_grand_apres_coup(self, qtbot):
        from src.ui.galerie_page import GaleriePage
        _capture(HP4, "a.png", datetime(2026, 9, 3), taille=(1920, 1080))
        page = GaleriePage([HP4])
        qtbot.addWidget(page)
        page.show()
        qtbot.waitUntil(lambda: page._apercu_attendu is None, timeout=3000)
        assert not page._apercu.pixmap().isNull()

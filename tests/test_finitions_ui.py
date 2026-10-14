"""Finitions de l'audit UI du 2026-10-14 (retours de Ludo sur captures).

Chaque classe garde une décision : les boutons de la barre de titre dessinés
et non écrits, la barre d'état dans la police du launcher, le générique par
personne, la version écrite une seule fois et cliquable, la mise en garde du
catalogue tue sur un jeu installé et entier, À propos bâti à sa visite.
"""

import dataclasses
from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget  # noqa: E402

from src.core.game_data import Contributor  # noqa: E402
from src.core.i18n import set_language, tr  # noqa: E402


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")


class TestBarreDeTitre:
    def _barre(self, qtbot):
        from src.ui.title_bar import TitleBar
        fenetre = QWidget()
        qtbot.addWidget(fenetre)
        return fenetre, TitleBar(fenetre)

    def test_aucun_caractere_en_guise_de_pictogramme(self, qtbot):
        """Règle 59 : ─ □ ✕ prenaient la police de repli de Windows."""
        _, barre = self._barre(qtbot)
        for bouton in barre.findChildren(QPushButton):
            assert bouton.text() not in ("─", "□", "✕"), bouton.text()

    def test_agrandie_la_fenetre_se_restaure(self, qtbot):
        """Le pictogramme et l'infobulle suivent l'état RÉEL de la fenêtre."""
        fenetre, barre = self._barre(qtbot)
        assert barre._agrandir.icone() == "agrandir"
        fenetre.setWindowState(Qt.WindowState.WindowMaximized)
        qtbot.waitUntil(lambda: barre._agrandir.icone() == "restaurer")
        assert barre._agrandir.toolTip() == tr("Restaurer")
        fenetre.setWindowState(Qt.WindowState.WindowNoState)
        qtbot.waitUntil(lambda: barre._agrandir.icone() == "agrandir")


class TestBarreDEtat:
    def _barre(self, qtbot):
        from src.ui.barre_de_statut import BarreDeStatut
        barre = BarreDeStatut(SimpleNamespace(faits_du_jour=False),
                              SimpleNamespace(is_busy=False))
        qtbot.addWidget(barre)
        return barre

    def test_le_message_est_un_libelle_et_non_le_texte_natif(self, qtbot):
        """Le texte natif se peint à 6 px du bord, en police système."""
        barre = self._barre(qtbot)
        barre.showMessage("Retour de HP1")
        assert barre._libelle.text() == "Retour de HP1"
        assert QStatusBarNatif.message(barre) == ""

    def test_un_message_long_s_elide_sans_elargir_la_fenetre(self, qtbot):
        barre = self._barre(qtbot)
        barre.resize(300, 30)
        barre.show()
        long = "Nick Quasi-Sans-Tête " * 20
        barre.showMessage(long)
        qtbot.waitUntil(lambda: barre._libelle.text() != long)
        assert barre.currentMessage() == long, "le message complet reste lisible au code"
        assert barre._libelle.toolTip() == long, "et en infobulle"
        assert barre.minimumSizeHint().width() < 300


class QStatusBarNatif:
    """Le message tel que QStatusBar le peindrait lui-même."""

    @staticmethod
    def message(barre) -> str:
        from PyQt6.QtWidgets import QStatusBar
        return QStatusBar.currentMessage(barre)


class TestGenerique:
    def test_une_personne_un_nom_et_tous_ses_roles(self, qtbot, monkeypatch):
        """« ASTeam » trois fois, pour la création et deux traductions."""
        from src.ui import about_page
        monkeypatch.setattr("src.ui.about_page.translator_credits",
                            lambda: [("English", ("ASTeam",)), ("Español", ("ASTeam",))])
        page = about_page.construire(
            [Contributor(name="ASTeam", role="Création", url="https://exemple.org")])
        qtbot.addWidget(page)
        noms = [lbl for lbl in page.findChildren(QLabel) if "ASTeam" in lbl.text()
                and "©" not in lbl.text()]
        assert len(noms) == 1, [lbl.text() for lbl in noms]
        assert 'href="https://exemple.org"' in noms[0].text()
        textes = [lbl.text() for lbl in page.findChildren(QLabel)]
        assert "Création" in textes
        assert sum("English" in t for t in textes) == 1
        assert sum("Español" in t for t in textes) == 1

    def test_un_traducteur_seul_reste_en_texte_brut(self, qtbot, monkeypatch):
        from src.ui import about_page
        monkeypatch.setattr("src.ui.about_page.translator_credits",
                            lambda: [("Español", ("<b>Ana</b>",))])
        page = about_page.construire([])
        qtbot.addWidget(page)
        porteur = next(lbl for lbl in page.findChildren(QLabel) if "Ana" in lbl.text())
        assert porteur.textFormat() == Qt.TextFormat.PlainText


class TestUneSeuleVersion:
    def test_a_propos_porte_la_version_cliquable(self, qtbot, monkeypatch):
        from src.core.config import APP_VERSION
        from src.core.liens import NOTES_VERSIONS_URL
        from src.ui import about_page
        ouverts = []
        monkeypatch.setattr(about_page, "open_url", ouverts.append)
        page = about_page.construire([])
        qtbot.addWidget(page)
        version = page.findChild(QLabel, "versions")
        assert APP_VERSION in version.text()
        version.linkActivated.emit(NOTES_VERSIONS_URL)
        assert ouverts == [NOTES_VERSIONS_URL]

    def test_la_colonne_des_parametres_ne_la_redit_pas(self, qtbot, tmp_path, monkeypatch):
        from src.core.config import APP_VERSION, Config
        from src.core.game_manager import GameManager
        from src.ui.settings_panel import SettingsDialog
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        dlg = SettingsDialog(cfg, GameManager(cfg))
        qtbot.addWidget(dlg)
        colonne = dlg.findChild(QWidget, "rubriques")
        assert not [lbl for lbl in colonne.findChildren(QLabel) if APP_VERSION in lbl.text()]


class TestAProposALaVisite:
    def test_construit_au_premier_passage_seulement(self, qtbot, tmp_path, monkeypatch):
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui import about_page
        from src.ui.settings_panel import SettingsDialog
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        appels = []
        vrai = about_page.construire
        monkeypatch.setattr(about_page, "construire",
                            lambda *a, **k: appels.append(1) or vrai(*a, **k))
        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        dlg = SettingsDialog(cfg, GameManager(cfg))
        qtbot.addWidget(dlg)
        assert appels == [], "À propos ne coûte rien tant qu'on n'y va pas"
        dernier = dlg._nav.count() - 1
        dlg._nav.setCurrentRow(dernier)
        assert appels == [1]
        assert dlg._pages.currentIndex() == dernier
        assert dlg._pages.currentWidget().findChild(QLabel, "versions") is not None
        dlg._nav.setCurrentRow(0)
        dlg._nav.setCurrentRow(dernier)
        assert appels == [1], "construit une fois"
        assert dlg._pages.count() == dlg._nav.count()


class TestMiseEnGardeDuCatalogue:
    """« Votre antivirus peut supprimer Paul.dll pendant l'installation »,
    sous JOUER, à chaque visite d'un jeu installé et entier."""

    @pytest.fixture
    def panneau(self, qtbot, tmp_path, monkeypatch):
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.action_panel import ActionPanel
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "c.json")
        cfg = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache")
        manager = GameManager(cfg)
        widget = ActionPanel(manager)
        qtbot.addWidget(widget)
        return widget, manager, tmp_path / "jeux"

    def _jeu(self, manager):
        jeu = next(e.game for e in manager.get_games() if e.game.current_download)
        return dataclasses.replace(jeu, warning="Votre antivirus peut supprimer X.dll.",
                                   requires=(), executable="Jeu/jeu.exe",
                                   fichiers_essentiels=("Jeu/x.dll",))

    def test_jeu_installe_et_entier_rien_a_dire(self, panneau, monkeypatch):
        from src.core.game_manager import GameState
        monkeypatch.setattr("src.ui.alert_banner.prerequis_manquants", lambda _r: [])
        widget, manager, racine = panneau
        jeu = self._jeu(manager)
        (racine / "Jeu").mkdir(parents=True)
        (racine / "Jeu" / "jeu.exe").write_bytes(b"")
        (racine / "Jeu" / "x.dll").write_bytes(b"")
        manager.set_game_state(jeu.id, GameState.INSTALLED)
        widget.set_game(jeu)
        widget.refresh()
        assert widget._alert.isHidden()

    def test_un_fichier_retire_la_fait_revenir(self, panneau, monkeypatch):
        """Le moment où elle sert : l'antivirus a pris la DLL, le jeu ne démarre plus."""
        from src.core.game_manager import GameState
        monkeypatch.setattr("src.ui.alert_banner.prerequis_manquants", lambda _r: [])
        widget, manager, racine = panneau
        jeu = self._jeu(manager)
        (racine / "Jeu").mkdir(parents=True)
        (racine / "Jeu" / "jeu.exe").write_bytes(b"")
        manager.set_game_state(jeu.id, GameState.INSTALLED)
        widget.set_game(jeu)
        widget.refresh()
        assert "antivirus" in widget._alert.text()

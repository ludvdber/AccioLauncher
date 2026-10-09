"""Paramètres refaits (2026-10-09) : rubriques à gauche, cartes, chemin coupé
au milieu, barre du disque, retour vers la bibliothèque."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402

from src.core.config import Config  # noqa: E402
from src.core.game_manager import GameManager  # noqa: E402
from src.ui import composants  # noqa: E402
from src.ui.settings_panel import SettingsDialog, _Chemin  # noqa: E402


@pytest.fixture
def dialogue(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    cfg = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache", langue="fr")
    dlg = SettingsDialog(cfg, GameManager(cfg))
    qtbot.addWidget(dlg)
    yield dlg
    dlg._shutdown_scan()


class TestChemin:
    def test_coupe_au_milieu_et_garde_le_chemin_entier(self, qtbot):
        chemin = r"D:\Un dossier très long\encore plus long\et encore\AccioLauncher"
        lbl = _Chemin(chemin)
        qtbot.addWidget(lbl)
        lbl.show()   # règle 48 : un widget caché ne reçoit son resizeEvent qu'à l'affichage
        lbl.resize(160, 30)
        visible = super(_Chemin, lbl).text()
        assert "…" in visible
        assert visible.startswith("D:") and visible.endswith("Launcher")
        assert lbl.text() == chemin and lbl.toolTip() == chemin


class TestDialogue:
    def test_cinq_rubriques_et_cinq_pages(self, dialogue):
        assert dialogue._nav.count() == dialogue._pages.count() == 5

    def test_bibliotheque_ferme_le_dialogue(self, dialogue, qtbot):
        from PyQt6.QtWidgets import QPushButton
        dialogue.show()
        retour = dialogue.findChild(QPushButton, "retour")
        with qtbot.waitSignal(dialogue.accepted, timeout=1000):
            retour.click()

    def test_le_scan_remplit_la_ligne_et_la_legende(self, dialogue):
        dialogue._on_scan_done(3, 9_800_000_000)
        assert dialogue._installed_label.text().startswith("3 jeux installés, ")
        assert dialogue._legende_jeux.text().startswith("Vos jeux · ")
        assert dialogue._barre_disque._jeux > 0

    def test_le_pied_n_apparait_pas_sur_a_propos(self, dialogue, qtbot):
        dialogue.show()
        pied = next(lbl for lbl in dialogue.findChildren(composants.QLabel)
                    if lbl.text().startswith("Chaque changement est enregistré"))
        assert pied.isVisible()
        dialogue._nav.setCurrentRow(4)
        assert not pied.isVisible()

    def test_la_ligne_de_redemarrage_attend_un_changement(self, dialogue, qtbot):
        dialogue.show()
        dialogue._nav.setCurrentRow(0)
        assert not dialogue._lang_hint.isVisible()
        autre = next(i for i in range(dialogue._lang_combo.count())
                     if dialogue._lang_combo.itemData(i) != "fr")
        dialogue._lang_combo.setCurrentIndex(autre)
        assert dialogue._lang_hint.isVisible() and dialogue._lang_restart.isVisible()

    def test_chaque_interrupteur_a_un_nom(self, dialogue):
        from src.ui.toggle_switch import ToggleSwitch
        for bascule in dialogue.findChildren(ToggleSwitch):
            assert bascule.accessibleName()


class TestComposants:
    def test_carte_pose_un_filet_entre_les_lignes(self, qtbot):
        carte = composants.Carte()
        qtbot.addWidget(carte)
        carte.ajouter(composants.LigneReglage("Un"))
        carte.ajouter(composants.LigneReglage("Deux"))
        filets = carte.findChildren(composants.QFrame, "separateur")
        assert len(filets) == 1

    def test_le_texte_n_est_jamais_interprete(self, qtbot):
        lbl = composants.texte("<b>x</b>")
        qtbot.addWidget(lbl)
        assert lbl.textFormat() == Qt.TextFormat.PlainText

    def test_description_vide_cachee(self, qtbot):
        ligne = composants.LigneReglage("Titre")
        qtbot.addWidget(ligne)
        ligne.show()
        assert not ligne.description.isVisible()
        ligne.decrire("Une phrase")
        assert ligne.description.isVisible()

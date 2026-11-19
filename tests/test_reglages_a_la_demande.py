"""Les rubriques des réglages d'un jeu bâties à leur première ouverture (règle des 0,5 s par page, 2026-11-19).

Banc hors écran : les rubriques qu'on ne voit pas à l'ouverture (Difficulté, Jeu, Fichiers…) faisaient plus de
la moitié du temps d'ouverture de la fenêtre. Seule la rubrique ouverte se bâtit ; les autres attendent leur
pastille. Qu'une rubrique existe se décide sans la bâtir (`_a_une_page`) : ce test vérifie que l'annonce et la
page disent la même chose pour chaque jeu du catalogue, installé ou non.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout

from src.core.config import Config
from src.core.game_data import load_catalog
from src.ui.difficulte_panneau import PanneauDifficulte
from src.ui.reglages_rubriques import ActionFichier, _ONGLETS
from tests.test_reglages_finitions import INI, _fenetre


def _dialogue(qtbot, jeu, install, langue=None, actions=()):
    from src.ui.game_settings_dialog import GameSettingsDialog
    manager = SimpleNamespace(game_language=lambda _g: langue, langues_disponibles=lambda _g: (),
                              config=Config(install_path=install))
    dlg = GameSettingsDialog(jeu, manager, lambda _c: True, actions=actions)
    qtbot.addWidget(dlg)
    return dlg


class TestALaDemande:
    def test_une_rubrique_non_ouverte_n_est_pas_batie(self, qtbot, tmp_path):
        dlg, _ini = _fenetre(qtbot, tmp_path)
        assert dlg._onglets["image"].isChecked()
        assert {"jeu", "difficulte"} <= dlg._a_batir
        assert dlg._panneau is None and not dlg.findChildren(PanneauDifficulte)
        assert "arriere_plan" not in dlg._controles, "la rubrique Jeu n'est pas bâtie"
        # Sa pastille, elle, est là dès l'ouverture, avec son « Bêta ».
        assert dlg._beta["difficulte"].parentWidget() is dlg._onglets["difficulte"]
        rang = list(dlg._onglets).index("difficulte")
        dlg._onglets["difficulte"].click()
        assert "difficulte" not in dlg._a_batir
        assert dlg._panneau is not None and dlg._defile.currentIndex() == rang
        assert dlg._defile.currentWidget().isAncestorOf(dlg._panneau)
        # Rouverte, elle n'est pas rebâtie.
        panneau = dlg._panneau
        dlg._onglets["image"].click()
        dlg._onglets["difficulte"].click()
        assert dlg._panneau is panneau and len(dlg.findChildren(PanneauDifficulte)) == 1

    def test_la_rubrique_demandee_est_celle_qui_se_batit(self, qtbot, tmp_path):
        """La page Difficulté ouvre « jeu » : c'est elle qui se bâtit, l'Image attend."""
        from src.ui.game_settings_dialog import GameSettingsDialog
        _fenetre(qtbot, tmp_path)   # pose l'ini du jeu
        from tests.test_reglages_finitions import IDENTS, _jeu
        manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                                  config=SimpleNamespace(install_path=tmp_path, reprise={}))
        dlg = GameSettingsDialog(_jeu(*IDENTS), manager, lambda c: True, onglet="jeu")
        qtbot.addWidget(dlg)
        assert dlg._onglets["jeu"].isChecked() and "arriere_plan" in dlg._controles
        assert "image" in dlg._a_batir and dlg._page_img is None

    def test_le_clavier_ouvre_une_rubrique_a_batir(self, qtbot, tmp_path):
        """Espace sur une pastille au focus bâtit et montre sa rubrique, comme un clic."""
        dlg, _ini = _fenetre(qtbot, tmp_path)
        dlg.show()
        qtbot.waitExposed(dlg)
        pastille = dlg._onglets["jeu"]
        pastille.setFocus(Qt.FocusReason.TabFocusReason)
        qtbot.keyClick(pastille, Qt.Key.Key_Space)
        assert pastille.isChecked() and "jeu" not in dlg._a_batir
        assert dlg._defile.currentWidget().isAncestorOf(dlg._controles["arriere_plan"])

    def test_revenir_a_l_installation_sans_avoir_ouvert_l_image(self, qtbot, tmp_path):
        """Le bouton du pied vaut pour la page Image même quand elle n'est pas encore bâtie."""
        from src.ui.game_settings_dialog import GameSettingsDialog
        from tests.test_reglages_finitions import IDENTS, _jeu
        _fenetre(qtbot, tmp_path)
        manager = SimpleNamespace(game_language=lambda g: None, langues_disponibles=lambda g: (),
                                  config=SimpleNamespace(install_path=tmp_path, reprise={}))
        dlg = GameSettingsDialog(_jeu(*IDENTS), manager, lambda c: True, onglet="jeu")
        qtbot.addWidget(dlg)
        assert dlg._page_img is None and dlg._bouton_reset is not None


_JEUX = load_catalog().games


@pytest.mark.parametrize("installe", [False, True], ids=["absent", "installe"])
@pytest.mark.parametrize("jeu", _JEUX, ids=[g.id for g in _JEUX])
def test_l_annonce_d_une_rubrique_est_sa_page(qtbot, tmp_path, jeu, installe):
    """Pour chaque jeu du catalogue : une rubrique annoncée a de quoi se montrer, une rubrique tue n'en a pas."""
    install = tmp_path / "jeux"
    if installe:
        dossier = install / Path(jeu.executable).parent
        dossier.mkdir(parents=True)
        for nom in ("d3d9.ini", "winmm.ini", "dinput8.ini"):
            (dossier / nom).write_bytes(INI.encode("ascii"))
    actions = (ActionFichier("Ouvrir le dossier", lambda: None, "e", "o"),) if installe else ()
    dlg = _dialogue(qtbot, jeu, install, langue="fr" if installe and jeu.langues else None, actions=actions)
    for ident, _libelle, _icone in _ONGLETS:
        annoncee = dlg._a_une_page(ident)
        assert annoncee == (ident in dlg._onglets), (jeu.id, ident)
        # Bâtie à part, sur un corps jetable : la page dit-elle la même chose que l'annonce ?
        assert dlg._remplir(ident, QVBoxLayout()) == annoncee, (jeu.id, ident)

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


class TestCeQueLOuvertureNeFaitPlus:
    """Sentinelles du banc du 2026-11-19 (ouverture des réglages de HP6 : 290 → 113 ms sous profileur), chacune
    contre-éprouvée sur l'ancien code."""

    def test_chaque_ligne_ne_repasse_pas_sous_la_feuille_a_chaque_etage(self, qtbot, tmp_path):
        """Bâties du haut vers le bas (règle 143) : 13 changements de style pour 6 lignes, 58 quand chaque
        ligne, sa carte, sa page et sa zone se rattachaient l'une après l'autre."""
        from PyQt6.QtCore import QEvent, QObject
        from PyQt6.QtWidgets import QApplication
        from src.ui.page_image import _LigneImage
        from tests.test_reglages_correctif import INI_V2, _dialogue as dialogue_hp4, _jeu, _manager

        class Compte(QObject):
            n = 0

            def eventFilter(self, obj, e):  # noqa: N802 (Qt)
                if e.type() == QEvent.Type.StyleChange and isinstance(obj, _LigneImage):
                    Compte.n += 1
                return False

        (tmp_path / "HP4").mkdir()
        (tmp_path / "HP4" / "d3d9.ini").write_bytes(INI_V2.encode("ascii"))
        compte = Compte()
        QApplication.instance().installEventFilter(compte)
        try:
            dlg = dialogue_hp4(qtbot, _jeu(tmp_path, ["surechantillonnage", "lissage", "anticrenelage", "filtrage",
                                                      "arriere_plan", "compteur_fps", "panneau_perfs"]),
                               _manager(tmp_path))
            dlg.show()
            qtbot.waitExposed(dlg)
            dlg._onglets["jeu"].click()
        finally:
            QApplication.instance().removeEventFilter(compte)
        lignes = len(dlg.findChildren(_LigneImage))
        assert lignes >= 3
        assert Compte.n <= 3 * lignes, (Compte.n, lignes)

    def test_le_fond_precharge_par_la_fiche_n_est_pas_redecode(self, qtbot):
        """La fiche du jeu décode le fond du bandeau dès qu'elle montre le jeu : ses réglages le trouvent
        prêt (la première peinture l'attendait 60 à 75 ms)."""
        from src.ui import bandeau_jeu
        bandeau_jeu.precharger("hp6")
        decodage = bandeau_jeu._DERNIER[str(bandeau_jeu.fond_du_jeu("hp6"))]
        assert not decodage.result().isNull()
        bandeau = bandeau_jeu.Bandeau(bandeau_jeu.fond_du_jeu("hp6"))
        qtbot.addWidget(bandeau)
        assert bandeau._attente is decodage

    def test_un_fond_annule_se_decode_sur_place(self, qtbot, monkeypatch):
        """Un autre fond demandé avant que celui d'un bandeau commence : le bandeau le lit lui-même."""
        from concurrent.futures import Future
        from src.ui import bandeau_jeu
        annule: Future = Future()
        annule.cancel()
        monkeypatch.setattr(bandeau_jeu, "_decodage", lambda _c: annule)
        bandeau = bandeau_jeu.Bandeau(bandeau_jeu.fond_du_jeu("hp6"))
        qtbot.addWidget(bandeau)
        assert not bandeau._image().isNull()

    def test_une_rubrique_se_batit_sans_les_filtres_globaux(self, qtbot, tmp_path):
        """Comme la fenêtre à son ouverture : les filtres posés sur toute l'application ne voient pas la
        construction de la Difficulté (17 ms de son premier clic)."""
        from PyQt6.QtCore import QEvent, QObject
        from src.ui import filtres_globaux

        class Compte(QObject):
            ajouts = 0

            def eventFilter(self, obj, e):  # noqa: N802 (Qt)
                if e.type() == QEvent.Type.ChildAdded and isinstance(obj, PanneauDifficulte):
                    Compte.ajouts += 1
                return False

        dlg, _ini = _fenetre(qtbot, tmp_path)
        compte = Compte()
        filtres_globaux.poser(compte)
        try:
            dlg._onglets["difficulte"].click()
        finally:
            filtres_globaux.retirer(compte)
        assert dlg._panneau is not None and Compte.ajouts == 0

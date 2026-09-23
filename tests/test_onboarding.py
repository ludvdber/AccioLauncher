"""Tests pour src/ui/onboarding.py — détection des installations existantes (pur)."""

from src.core.game_data import GameData
from src.ui.onboarding import detect_installed_games


def _game(game_id: str, executable: str) -> GameData:
    return GameData.from_dict({
        "id": game_id, "name": game_id.upper(), "year": 2001, "description": "d",
        "developer": "Dev", "executable": executable, "cover_image": f"{game_id}.jpg",
    })


class TestDetectInstalledGames:
    def test_detects_game_with_exe(self, tmp_path):
        (tmp_path / "HP1" / "System").mkdir(parents=True)
        (tmp_path / "HP1" / "System" / "HP.exe").write_bytes(b"x")
        games = [_game("hp1", "HP1/System/HP.exe"), _game("hp2", "HP2/System/Game.exe")]

        found = detect_installed_games(tmp_path, games)

        assert len(found) == 1
        game, src = found[0]
        assert game.id == "hp1"
        assert src == tmp_path / "HP1"

    def test_folder_without_exe_ignored(self, tmp_path):
        (tmp_path / "HP1" / "System").mkdir(parents=True)  # pas d'exe dedans
        found = detect_installed_games(tmp_path, [_game("hp1", "HP1/System/HP.exe")])
        assert found == []

    def test_empty_parent(self, tmp_path):
        assert detect_installed_games(tmp_path, [_game("hp1", "HP1/System/HP.exe")]) == []


class TestChoixpeauDansLAssistant:
    """Le Choixpeau PROPOSE un thème, il ne l'impose pas.

    Ludo, 2026-09-19 : « soit proposer le thème de la maison après le choix,
    soit garder Poudlard en disant que c'est modifiable dans les Paramètres ».
    On fait les deux : la maison pré-sélectionne le thème, qui reste un combo
    modifiable juste à côté du verdict.
    """

    @staticmethod
    def _assistant(qtbot):
        from src.ui.onboarding import OnboardingDialog
        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg._build_rest()          # les écrans 2-5 naissent après la langue
        return dlg

    def test_l_assistant_compte_bien_cinq_ecrans(self, qtbot):
        from src.ui.onboarding import TOTAL_PAGES
        dlg = self._assistant(qtbot)
        assert dlg._pages.count() == TOTAL_PAGES == 5

    def test_une_question_par_groupe_de_boutons(self, qtbot):
        from src.core.choixpeau import QUESTIONS
        dlg = self._assistant(qtbot)
        assert len(dlg._groupes_maison) == len(QUESTIONS)
        for groupe in dlg._groupes_maison:
            assert len(groupe.buttons()) == 4
            assert groupe.checkedId() == -1      # rien de coché d'avance

    def test_la_maison_preselectionne_son_theme(self, qtbot):
        from src.core.choixpeau import QUESTIONS, SERPENTARD
        dlg = self._assistant(qtbot)
        for index, groupe in enumerate(dlg._groupes_maison):
            rang = next(i for i, (_, m) in enumerate(QUESTIONS[index][1])
                        if m == SERPENTARD)
            groupe.button(rang).setChecked(True)
        dlg._repartir()
        assert dlg._maison == SERPENTARD
        assert dlg._theme_combo.currentData() == SERPENTARD
        assert dlg._maison_label.isVisible() or dlg._maison_label.text()
        assert "SERPENTARD" in dlg._maison_label.text()

    def test_sans_reponse_le_theme_reste_poudlard(self, qtbot):
        """Répartir quelqu'un qui n'a rien répondu serait inventer un choix."""
        dlg = self._assistant(qtbot)
        dlg._repartir()
        assert dlg._maison == ""
        assert dlg._theme_combo.currentData() == "poudlard"
        assert not dlg._maison_label.isVisible()

    def test_le_theme_reste_modifiable_apres_la_repartition(self, qtbot):
        from src.core.choixpeau import QUESTIONS, GRYFFONDOR
        dlg = self._assistant(qtbot)
        for index, groupe in enumerate(dlg._groupes_maison):
            rang = next(i for i, (_, m) in enumerate(QUESTIONS[index][1])
                        if m == GRYFFONDOR)
            groupe.button(rang).setChecked(True)
        dlg._repartir()
        assert dlg._theme_combo.currentData() == GRYFFONDOR
        dlg._theme_combo.setCurrentIndex(dlg._theme_combo.findData("serdaigle"))
        dlg._pages.setCurrentIndex(dlg._pages.count() - 1)
        dlg._go_next()                       # « Terminer »
        assert dlg.theme == "serdaigle"      # le dernier mot revient au joueur


class TestChaquePageAUnTitre:
    """Les cinq écrans partageaient sept lignes de préambule, recopiées.

    Ce n'était pas un coût de frappe : l'`objectName` « wizTitle » est ce qui
    donne au titre sa couleur et son espacement dans la feuille de style de
    l'assistant. Une page qui l'oublierait s'afficherait en texte ordinaire —
    et personne ne le verrait, la suite tournant `offscreen`. Le préambule vit
    désormais dans `_page_titree`, et ce test garde ce que le helper promet.
    """

    @staticmethod
    def _assistant(qtbot):
        from src.ui.onboarding import OnboardingDialog
        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg._build_rest()
        return dlg

    def test_chaque_ecran_porte_exactement_un_titre_wiztitle(self, qtbot):
        from PyQt6.QtWidgets import QLabel
        from src.ui.onboarding import TOTAL_PAGES

        dlg = self._assistant(qtbot)
        for index in range(TOTAL_PAGES):
            page = dlg._pages.widget(index)
            titres = [w for w in page.findChildren(QLabel)
                      if w.objectName() == "wizTitle"]
            assert len(titres) == 1, (
                f"écran {index + 1} : {len(titres)} titre(s) « wizTitle »")
            assert titres[0].text().strip(), f"écran {index + 1} : titre vide"

    def test_le_helper_rend_une_page_et_sa_colonne(self, qtbot):
        from PyQt6.QtWidgets import QVBoxLayout, QWidget
        from src.ui.onboarding import _page_titree

        page, lay = _page_titree("Essai")
        qtbot.addWidget(page)
        assert isinstance(page, QWidget) and isinstance(lay, QVBoxLayout)
        assert lay.parentWidget() is page, (
            "la colonne doit être POSÉE sur la page, sinon les widgets ajoutés "
            "ensuite n'apparaissent nulle part")

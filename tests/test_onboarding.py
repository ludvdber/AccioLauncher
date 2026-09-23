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


class TestFermerLAssistantNEcritRien:
    """La croix doit REPORTER l'installation, pas la sauter.

    `run_onboarding` écrivait des défauts quand l'assistant n'aboutissait
    pas. Deux conséquences, toutes deux silencieuses : le launcher démarrait
    comme si l'assistant avait été terminé, et `Config.exists()` devenait
    vrai, si bien que l'assistant ne revenait JAMAIS. Fermer la fenêtre
    n'était donc pas « pas maintenant » mais « plus jamais » — signalé par
    Ludo le 2026-09-23 en testant l'exe 1.0.5.

    On bouchonne la classe au niveau du MODULE (jamais un attribut de classe
    Qt, cf. CLAUDE.md) : le faux assistant n'est même pas un widget.
    """

    @staticmethod
    def _poser_faux_assistant(monkeypatch, code):
        from pathlib import Path

        from src.ui import onboarding as module

        class _FauxAssistant:
            def __init__(self):
                self.install_path = Path.home() / "Games" / "AccioLauncher"
                self.langue = "fr"
                self.theme = "poudlard"
                self.autoplay = True
                self.mute_videos = True
                self.trailers_optin = False

            def exec(self):
                return code

            def perform_imports(self, _config):
                raise AssertionError("ne doit pas être atteint après un abandon")

        monkeypatch.setattr(module, "OnboardingDialog", _FauxAssistant)

    def test_la_croix_leve_et_n_ecrit_aucune_config(self, monkeypatch):
        import pytest
        from PyQt6.QtWidgets import QDialog

        from src.core.config import Config
        from src.ui.onboarding import OnboardingAnnule, run_onboarding

        self._poser_faux_assistant(monkeypatch, QDialog.DialogCode.Rejected)
        assert not Config.exists(), "le test part d'un poste sans config"

        with pytest.raises(OnboardingAnnule):
            run_onboarding()

        assert not Config.exists(), (
            "une config a été écrite malgré l'abandon : l'assistant ne "
            "reviendra jamais")

    def test_un_dossier_inaccessible_abandonne_aussi(self, monkeypatch):
        import pytest
        from PyQt6.QtWidgets import QDialog

        from src.core.config import Config
        from src.ui import onboarding as module
        from src.ui.onboarding import OnboardingAnnule, run_onboarding

        self._poser_faux_assistant(monkeypatch, QDialog.DialogCode.Accepted)
        monkeypatch.setattr(module, "is_writable_dir", lambda _p: False)

        with pytest.raises(OnboardingAnnule):
            run_onboarding()
        assert not Config.exists()


class TestChangerDeLangueRebatitLesEcrans:
    """Revenir en arrière et changer de langue doit tout retraduire.

    Les `tr()` sont évalués à la CONSTRUCTION des widgets, et `_rest_built`
    ne les faisait construire qu'une fois : le titre de la fenêtre et les
    boutons, refaits à chaque passage, obéissaient — pas les pages. D'où la
    capture de Ludo (2026-09-23) : un launcher en anglais où seuls « Back »
    et « Next » étaient traduits. Ces tests échouent sur le code d'avant.
    """

    @staticmethod
    def _titre_de_la_page(dlg, index):
        from PyQt6.QtWidgets import QLabel
        page = dlg._pages.widget(index)
        return next(w.text() for w in page.findChildren(QLabel)
                    if w.objectName() == "wizTitle")

    @staticmethod
    def _choisir(dlg, code):
        rang = dlg._lang_combo.findData(code)
        assert rang >= 0, f"langue {code} absente du sélecteur"
        dlg._lang_combo.setCurrentIndex(rang)
        dlg._go_next()

    def test_repasser_en_francais_retraduit_les_pages(self, qtbot):
        from src.core.i18n import get_language, set_language
        from src.ui.onboarding import OnboardingDialog

        origine = get_language()
        try:
            dlg = OnboardingDialog()
            qtbot.addWidget(dlg)

            self._choisir(dlg, "en")
            en_anglais = self._titre_de_la_page(dlg, 1)

            dlg._go_back()
            self._choisir(dlg, "fr")
            en_francais = self._titre_de_la_page(dlg, 1)

            assert en_anglais != en_francais, (
                "les écrans sont restés dans la langue du premier passage : "
                f"« {en_anglais} » des deux côtés")
            assert en_francais == "Bienvenue dans Accio Launcher"
        finally:
            set_language(origine)

    def test_le_choixpeau_ne_double_pas_ses_questions(self, qtbot):
        from src.core.choixpeau import QUESTIONS
        from src.core.i18n import get_language, set_language
        from src.ui.onboarding import OnboardingDialog

        origine = get_language()
        try:
            dlg = OnboardingDialog()
            qtbot.addWidget(dlg)
            self._choisir(dlg, "en")
            dlg._go_back()
            self._choisir(dlg, "fr")

            assert len(dlg._groupes_maison) == len(QUESTIONS), (
                "les groupes de boutons du Choixpeau se sont accumulés")
        finally:
            set_language(origine)

    def test_les_widgets_persistants_survivent_au_rebati(self, qtbot):
        from src.core.i18n import get_language, set_language
        from src.ui.onboarding import OnboardingDialog

        origine = get_language()
        try:
            dlg = OnboardingDialog()
            qtbot.addWidget(dlg)
            self._choisir(dlg, "en")
            dlg._go_back()
            self._choisir(dlg, "fr")

            # Détruits avec leur page, ils laisseraient un objet C++ mort
            # derrière un attribut Python vivant : le premier accès planterait.
            for widget in (dlg._path_label, dlg._free_label, dlg._scan_label,
                           dlg._import_list, dlg._theme_combo,
                           dlg._maison_label):
                widget.isVisible()
        finally:
            set_language(origine)


class TestLeRebatiRendLesWidgetsVisibles:
    """Survivre ne suffit pas : il faut aussi RÉAPPARAÎTRE.

    Le premier correctif cachait explicitement les widgets persistants avant
    de jeter leurs pages, et un widget caché explicitement le reste quand on
    le repose dans un layout. Vu dans l'exe le 2026-09-24 : après un passage
    par l'anglais, l'écran 2 en français n'avait plus ni le chemin du dossier
    ni l'espace libre. Les tests d'alors vérifiaient la survie, pas la vue.
    """

    PERSISTANTS = ("_path_label", "_free_label", "_scan_label",
                   "_import_list", "_theme_combo", "_maison_label")

    @staticmethod
    def _choisir(dlg, code):
        dlg._lang_combo.setCurrentIndex(dlg._lang_combo.findData(code))
        dlg._go_next()

    def _etats(self, dlg):
        return {nom: getattr(dlg, nom).isHidden() for nom in self.PERSISTANTS}

    def test_meme_visibilite_qu_a_la_premiere_construction(self, qtbot):
        from src.core.i18n import get_language, set_language
        from src.ui.onboarding import OnboardingDialog

        origine = get_language()
        try:
            premiere = OnboardingDialog()
            qtbot.addWidget(premiere)
            self._choisir(premiere, "fr")
            attendu = self._etats(premiere)

            dlg = OnboardingDialog()
            qtbot.addWidget(dlg)
            self._choisir(dlg, "en")
            dlg._go_back()
            self._choisir(dlg, "fr")
            assert self._etats(dlg) == attendu
        finally:
            set_language(origine)

    def test_l_ecran_du_dossier_montre_chemin_et_espace(self, qtbot):
        from src.core.i18n import get_language, set_language
        from src.ui.onboarding import OnboardingDialog

        origine = get_language()
        try:
            dlg = OnboardingDialog()
            qtbot.addWidget(dlg)
            dlg.show()
            self._choisir(dlg, "en")
            dlg._go_back()
            self._choisir(dlg, "fr")
            assert dlg._path_label.isVisible(), "chemin du dossier invisible"
            assert dlg._free_label.isVisible(), "espace libre invisible"
        finally:
            set_language(origine)


class TestLesEcransDefilentSiNecessaire:
    """Le Choixpeau débordait de la fenêtre, et un pixel de plus le réparait.

    Quatre questions, seize réponses : la page réclame bien plus que les
    430 px du minimum du dialogue. Sans zone défilante, le texte se
    chevauchait, et agrandir d'un pixel remettait tout d'aplomb d'un coup —
    c'est le redimensionnement qui déclenchait enfin la passe de mise en
    page (Ludo, 2026-09-23, capture à l'appui).
    """

    @staticmethod
    def _assistant(qtbot):
        from src.ui.onboarding import OnboardingDialog
        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg._build_rest()
        return dlg

    def test_chaque_ecran_est_dans_une_zone_defilante(self, qtbot):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QScrollArea

        from src.ui.onboarding import TOTAL_PAGES

        dlg = self._assistant(qtbot)
        for index in range(TOTAL_PAGES):
            zone = dlg._pages.widget(index)
            assert isinstance(zone, QScrollArea), f"écran {index + 1}"
            assert zone.widgetResizable(), f"écran {index + 1}"
            # « Si ça ne fit pas » : la barre n'apparaît que lorsqu'elle sert.
            assert (zone.verticalScrollBarPolicy()
                    == Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            assert (zone.horizontalScrollBarPolicy()
                    == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            # Sans règle, c'est la barre native de Windows, grise et hachurée.
            assert "QScrollBar::handle:vertical" in zone.styleSheet(), (
                f"écran {index + 1} : barre de défilement non stylée")

    def test_le_choixpeau_reclame_plus_que_la_hauteur_minimale(self, qtbot):
        dlg = self._assistant(qtbot)
        # L'écran du Choixpeau est l'avant-dernier.
        interieur = dlg._pages.widget(dlg._pages.count() - 2).widget()
        assert interieur.sizeHint().height() > dlg.minimumHeight(), (
            "le Choixpeau tiendrait désormais sans défilement : ce test ne "
            "garde plus rien, vérifier que la page n'a pas été vidée")

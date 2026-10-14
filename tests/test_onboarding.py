"""Tests de l'assistant de premier lancement (refait le 2026-10-09) et de son rattrapage."""

from pathlib import Path

import pytest

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


def _poser_un_jeu(racine: Path, game: GameData) -> None:
    exe = racine / Path(game.executable)
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"exe")


@pytest.fixture
def assistant(qtbot, tmp_path, monkeypatch):
    """L'assistant en français, sur un dossier de jeux temporaire."""
    monkeypatch.setattr("src.ui.onboarding.DEFAULT_INSTALL_PATH", tmp_path / "jeux")
    (tmp_path / "jeux").mkdir()

    def _fabriquer(avant=None):
        from src.ui.onboarding import OnboardingDialog
        if avant is not None:
            avant(tmp_path / "jeux")
        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg.choisir_langue("fr")
        dlg._quitter_la_langue()
        return dlg
    return _fabriquer


def _repondre_partout(dlg, maison):
    from src.core.choixpeau import QUESTIONS
    for index in range(len(QUESTIONS)):
        rang = next(i for i, (_, m) in enumerate(QUESTIONS[index][1]) if m == maison)
        dlg._cartes_reponse[rang].click()
        dlg._suivant()


class TestLeParcours:
    def test_la_langue_ouvre_sur_le_dossier(self, assistant):
        from src.ui.onboarding import DOSSIER
        dlg = assistant()
        assert dlg._ecran == DOSSIER
        assert dlg._btn_retour.isVisibleTo(dlg)

    def test_le_rail_dit_ce_qui_vient(self, assistant):
        dlg = assistant()
        noms = [e.libelle.text() for e in dlg._rail.etapes]
        assert noms == ["Dossier", "Vos jeux", "Le Choixpeau", "Dernières touches"]

    def test_chaque_ecran_est_dans_une_zone_defilante(self, assistant):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QScrollArea
        dlg = assistant()
        for ecran, zone in dlg._zones.items():
            assert isinstance(zone, QScrollArea), ecran
            assert zone.widgetResizable(), ecran
            assert zone.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


class TestLesJeuxDejaLa:
    """Config effacée, jeux restés : l'assistant les retrouve tout seul (Ludo, 2026-10-09)."""

    def test_les_jeux_du_dossier_sont_repris_d_office(self, assistant, tmp_path):
        from src.core.config import Config
        from src.core.game_data import load_catalog
        jeu = load_catalog().games[0]
        dlg = assistant(lambda dossier: _poser_un_jeu(dossier, jeu))

        assert [g.id for g, _ in dlg._en_place] == [jeu.id]
        assert "déjà un jeu" in dlg._texte_place.text()
        assert [g.id for g, _ in dlg.checked_imports()] == [jeu.id]

        config = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "jeux" / "c")
        dlg.perform_imports(config)
        assert config.installed_versions[jeu.id] == jeu.recommended_version
        assert (tmp_path / "jeux" / Path(jeu.executable)).exists(), "rien ne doit bouger"

    def test_sans_jeu_l_ecran_propose_de_chercher(self, assistant):
        dlg = assistant()
        assert dlg._en_place == []
        assert dlg.checked_imports() == []

    def test_un_jeu_trouve_ailleurs_se_coche_et_se_decoche(self, assistant, tmp_path):
        from src.core.game_data import load_catalog
        from src.ui.onboarding import JEUX
        jeu = load_catalog().games[0]
        _poser_un_jeu(tmp_path / "ailleurs", jeu)
        dlg = assistant()
        dlg._suivant()
        assert dlg._ecran == JEUX
        dlg._dossier_cherche = tmp_path / "ailleurs"
        dlg._regler_jeux()
        assert dlg._btn_suivant.text() == "Importer 1 jeu"
        dlg._lignes[jeu.id].click()
        assert dlg.checked_imports() == []
        assert dlg._btn_suivant.text() == "Suivant"


class TestLeChoixpeau:
    """Une question à la fois, et la maison PROPOSE ses couleurs sans les imposer."""

    def _au_choixpeau(self, assistant):
        from src.ui.onboarding import CHOIXPEAU_Q
        dlg = assistant()
        dlg._suivant()      # dossier
        dlg._suivant()      # vos jeux
        assert dlg._ecran == CHOIXPEAU_Q
        return dlg

    def test_suivant_attend_une_reponse(self, assistant):
        dlg = self._au_choixpeau(assistant)
        assert not dlg._btn_suivant.isEnabled()
        dlg._cartes_reponse[0].click()
        assert dlg._btn_suivant.isEnabled()

    def test_rien_n_est_coche_d_avance(self, assistant):
        dlg = self._au_choixpeau(assistant)
        assert not any(c.isChecked() for c in dlg._cartes_reponse)

    def test_le_verdict_prend_les_couleurs_de_la_maison(self, assistant):
        from src.core.choixpeau import SERPENTARD
        from src.ui.onboarding import DERNIERES, VERDICT
        from src.ui.theme import current
        dlg = self._au_choixpeau(assistant)
        _repondre_partout(dlg, SERPENTARD)
        assert dlg._ecran == VERDICT
        assert dlg._maison == SERPENTARD
        assert current().id == SERPENTARD
        dlg._suivant()
        assert dlg._ecran == DERNIERES
        assert dlg._cartes_couleur[SERPENTARD].isChecked()
        assert dlg._cartes_couleur[SERPENTARD].note.text() == "Choisie par le Choixpeau"

    def test_les_couleurs_restent_au_choix_du_joueur(self, assistant):
        from src.core.choixpeau import GRYFFONDOR
        dlg = self._au_choixpeau(assistant)
        _repondre_partout(dlg, GRYFFONDOR)
        dlg._suivant()
        dlg._cartes_couleur["serdaigle"].click()
        dlg._suivant()                       # « Ouvrir la bibliothèque »
        assert dlg.theme == "serdaigle"      # le dernier mot revient au joueur

    def test_garder_poudlard_saute_le_test(self, assistant):
        from src.ui.onboarding import DERNIERES
        dlg = self._au_choixpeau(assistant)
        dlg._cartes_reponse[2].click()
        dlg._sur_lien()
        assert dlg._ecran == DERNIERES
        assert dlg._maison == ""
        assert dlg.theme == "poudlard"

    def test_refaire_le_test_repart_de_zero(self, assistant):
        from src.core.choixpeau import SERDAIGLE
        from src.ui.onboarding import CHOIXPEAU_Q
        from src.ui.theme import current
        dlg = self._au_choixpeau(assistant)
        _repondre_partout(dlg, SERDAIGLE)
        dlg._retour()                        # « Refaire le test »
        assert dlg._ecran == CHOIXPEAU_Q
        assert dlg._question == 0 and dlg._reponses == [-1] * 4
        assert current().id == "poudlard"


class TestFermerLAssistantNEcritRien:
    """La croix doit REPORTER l'installation, pas la sauter (Ludo, 2026-09-23).

    On bouchonne la classe au niveau du MODULE (jamais un attribut de classe
    Qt) : le faux assistant n'est même pas un widget.
    """

    @staticmethod
    def _poser_faux_assistant(monkeypatch, code):
        from src.ui import onboarding as module

        class _FauxAssistant:
            def __init__(self, *_a):
                self.install_path = Path.home() / "Games" / "AccioLauncher"
                self.langue = "fr"
                self.theme = "serdaigle"
                self.autoplay = True
                self.mute_videos = True
                self.trailers_optin = False

            def exec(self):
                return code

            def perform_imports(self, _config):
                raise AssertionError("ne doit pas être atteint après un abandon")

        monkeypatch.setattr(module, "OnboardingDialog", _FauxAssistant)

    def test_la_croix_leve_et_n_ecrit_aucune_config(self, monkeypatch):
        from PyQt6.QtWidgets import QDialog

        from src.core.config import Config
        from src.ui.onboarding import OnboardingAnnule, run_onboarding

        self._poser_faux_assistant(monkeypatch, QDialog.DialogCode.Rejected)
        assert not Config.exists(), "le test part d'un poste sans config"
        with pytest.raises(OnboardingAnnule):
            run_onboarding()
        assert not Config.exists(), "une config a été écrite malgré l'abandon"

    def test_un_dossier_inaccessible_abandonne_aussi(self, monkeypatch):
        from PyQt6.QtWidgets import QDialog

        from src.core.config import Config
        from src.ui import onboarding as module
        from src.ui.onboarding import OnboardingAnnule, run_onboarding

        self._poser_faux_assistant(monkeypatch, QDialog.DialogCode.Accepted)
        monkeypatch.setattr(module, "is_writable_dir", lambda _p: False)
        with pytest.raises(OnboardingAnnule):
            run_onboarding()
        assert not Config.exists()

    def test_le_rattrapage_ferme_note_les_etapes_sans_rien_changer(self, monkeypatch):
        from PyQt6.QtWidgets import QDialog

        from src.core.config import Config
        from src.ui.onboarding import run_rattrapage

        self._poser_faux_assistant(monkeypatch, QDialog.DialogCode.Rejected)
        config = Config(etapes_assistant=[], trailers_optin=False)
        run_rattrapage(config, ("choixpeau", "touches"))
        relue = Config.load()
        assert relue.theme == "poudlard", "rien de ce qui n'a pas été répondu ne change"
        assert set(relue.etapes_assistant) == {"choixpeau", "touches"}, (
            "fermée, la fenêtre ne doit pas revenir au lancement suivant")

    def test_le_rattrapage_termine_applique_les_reponses(self, monkeypatch):
        from PyQt6.QtWidgets import QDialog

        from src.core.config import Config
        from src.ui.onboarding import run_rattrapage

        self._poser_faux_assistant(monkeypatch, QDialog.DialogCode.Accepted)
        config = Config(etapes_assistant=[])
        run_rattrapage(config, ("choixpeau", "touches"))
        assert Config.load().theme == "serdaigle"


class TestLeRattrapage:
    """Ceux qui avaient le launcher avant le Choixpeau : ces étapes-là, rien d'autre."""

    def test_il_ouvre_sur_le_choixpeau_sans_retour(self, qtbot):
        from src.core.config import Config
        from src.ui.onboarding import CHOIXPEAU_Q, OnboardingDialog
        dlg = OnboardingDialog(Config(langue="fr"), ("choixpeau", "touches"))
        qtbot.addWidget(dlg)
        assert dlg._ecran == CHOIXPEAU_Q
        assert not dlg._btn_retour.isVisibleTo(dlg)
        assert [e.libelle.text() for e in dlg._rail.etapes] == ["Le Choixpeau", "Dernières touches"]

    def test_seulement_les_dernieres_touches(self, qtbot):
        from src.core.config import Config
        from src.ui.onboarding import DERNIERES, OnboardingDialog
        dlg = OnboardingDialog(Config(langue="fr", theme="serdaigle"), ("touches",))
        qtbot.addWidget(dlg)
        assert dlg._ecran == DERNIERES
        assert dlg._cartes_couleur["serdaigle"].isChecked()
        assert dlg._btn_suivant.text() == "Terminer"


class TestChangerDeLangueRebatitLesEcrans:
    """Revenir à la langue et en changer doit tout retraduire (capture de Ludo, 2026-09-23)."""

    def test_repasser_en_francais_retraduit_les_etapes(self, assistant):
        dlg = assistant()
        dlg._retour()
        dlg.choisir_langue("en")
        dlg._quitter_la_langue()
        en_anglais = [e.libelle.text() for e in dlg._rail.etapes]
        dlg._retour()
        dlg.choisir_langue("fr")
        dlg._quitter_la_langue()
        en_francais = [e.libelle.text() for e in dlg._rail.etapes]
        assert en_anglais != en_francais
        assert en_francais[0] == "Dossier"

    def test_l_ecran_de_langue_se_retraduit_au_clic(self, qtbot):
        from src.ui.onboarding import OnboardingDialog
        dlg = OnboardingDialog()
        qtbot.addWidget(dlg)
        dlg.choisir_langue("fr")
        assert dlg._continuer.text() == "Suivant"
        dlg.choisir_langue("en")
        assert dlg._continuer.text() == "Next"


@pytest.mark.parametrize("langue", ["fr", "en", "es"])
def test_a_la_taille_minimale_rien_ne_deborde_a_droite(qtbot, qapp, tmp_path, monkeypatch, langue):
    """Chaque étape tient dans la largeur à 860 × 600, vraies polices.

    Cinq cartes de couleurs débordaient : un bouton tient sa largeur voulue
    pour un minimum, et la rangée demandait 590 px pour 532 de place.
    """
    from src.ui.fonts import load_fonts
    from src.ui.onboarding import OnboardingDialog
    load_fonts()
    monkeypatch.setattr("src.ui.onboarding.DEFAULT_INSTALL_PATH", tmp_path)
    dlg = OnboardingDialog()
    qtbot.addWidget(dlg)
    dlg.choisir_langue(langue)
    dlg._quitter_la_langue()
    dlg.show()
    dlg.resize(dlg.minimumSize())
    qtbot.waitExposed(dlg)
    for ecran, zone in dlg._zones.items():
        dlg._pile.setCurrentWidget(zone)
        qtbot.waitUntil(lambda z=zone: z.viewport().width() > 0)
        assert zone.widget().minimumSizeHint().width() <= zone.viewport().width(), ecran

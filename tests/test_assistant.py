"""Quelles étapes de l'assistant montrer à quelqu'un qui a déjà le launcher (pur)."""

import json

from src.core.assistant import CHOIXPEAU, TOUCHES, etapes_a_rattraper


class TestEtapesARattraper:
    def test_une_config_d_avant_sans_maison_revoit_tout(self):
        assert etapes_a_rattraper([], "poudlard", False) == (CHOIXPEAU, TOUCHES)

    def test_une_maison_deja_choisie_saute_le_choixpeau(self):
        assert etapes_a_rattraper([], "serpentard", False) == (TOUCHES,)

    def test_maison_et_bandes_annonces_acceptees_rien_a_montrer(self):
        assert etapes_a_rattraper([], "gryffondor", True) == ()

    def test_le_choixpeau_ramene_les_couleurs(self):
        """Sa maison se choisit aux dernières touches : elles viennent avec lui."""
        assert etapes_a_rattraper([], "poudlard", True) == (CHOIXPEAU, TOUCHES)

    def test_une_etape_vue_ne_revient_jamais(self):
        assert etapes_a_rattraper([CHOIXPEAU, TOUCHES], "poudlard", False) == ()


class TestLaConfigLesRetient:
    def test_une_config_neuve_a_tout_vu(self):
        from src.core.config import Config
        cfg = Config()
        assert etapes_a_rattraper(cfg.etapes_assistant, cfg.theme, cfg.trailers_optin) == ()

    def test_une_config_d_avant_se_charge_sans_etape(self):
        from src.core import config as module
        donnees = {"install_path": "C:/Jeux", "theme": "poudlard"}
        module.CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        module.CONFIG_FILE_PATH.write_text(json.dumps(donnees), encoding="utf-8")
        assert module.Config.load().etapes_assistant == []

    def test_aller_retour(self):
        from src.core.config import Config
        Config(etapes_assistant=[CHOIXPEAU]).save()
        assert Config.load().etapes_assistant == [CHOIXPEAU]

    def test_une_valeur_aberrante_est_ecartee(self):
        from src.core import config as module
        module.CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        module.CONFIG_FILE_PATH.write_text(json.dumps({"etapes_assistant": [1, "touches", None]}),
                                           encoding="utf-8")
        assert module.Config.load().etapes_assistant == ["touches"]

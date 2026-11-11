"""L'incrustation du correctif sous Wine : le remède au gel du GPU Intel, puis le dessin autorisé.

Relevé sur Bazzite le 2026-11-11 : le texte du compteur (F10) passait par le
vertex shader « ubershader » de DXVK, auquel le pilote Intel donnait 132
registres pour 128. Le lanceur écarte ce shader, et seulement alors laisse le
correctif dessiner.
"""

from pathlib import Path

import pytest

from src.core import compat, incrustation_wine, reglages_correctif
from src.core.compat import Lanceur

_INI = (
    "[Accio.Window]\r\nFPSLimit=120\r\n\r\n"
    "[Accio.Overlay]\r\nShowFPS=0\r\n; Under Wine the first panel drawn hung an Intel chip.\r\n"
    "DrawUnderWine=0\r\nPipeline=0\r\n\r\n[Accio.Game]\r\nLanguage=auto\r\n"
)


def _ini(dossier: Path, contenu: str = _INI) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    ini = dossier / "d3d9.ini"
    ini.write_bytes(contenu.encode("cp1252"))
    return ini


class TestOptionDxvk:
    def test_l_option_est_posee_pour_les_deux_familles(self, tmp_path):
        for lanceur in (Lanceur("umu", "/usr/bin/umu-run", proton="/p/GE"), Lanceur("wine", "/usr/bin/wine")):
            env = compat.environnement(lanceur, tmp_path, base={})
            assert env["DXVK_CONFIG"] == "d3d9.ffUbershaderVS = False"
            assert compat.dxvk_sans_gel(env)

    def test_les_options_de_l_utilisateur_sont_gardees(self):
        assert (compat.composer_dxvk("dxvk.hud = fps;")
                == "dxvk.hud = fps;d3d9.ffUbershaderVS = False")

    @pytest.mark.parametrize("le_sien", [
        "d3d9.ffUbershaderVS = True",
        "D3D9.FFUBERSHADERVS=False",
        "dxvk.enableDescriptorBuffer = True",
        "dxvk.hud = fps; dxvk.enableDescriptorBuffer = Auto",
    ])
    def test_son_reglage_sur_le_meme_sujet_reste_le_sien(self, le_sien):
        assert compat.composer_dxvk(le_sien) == le_sien

    @pytest.mark.parametrize("config, protege", [
        ("d3d9.ffUbershaderVS = False", True),
        ("d3d9.ffUbershaderVS=False", True),
        ("dxvk.hud = fps;dxvk.enableDescriptorBuffer = True", True),
        ("d3d9.ffUbershaderVS = True", False),
        ("dxvk.enableDescriptorBuffer = Auto", False),
        ("", False),
    ])
    def test_ce_qui_ecarte_le_gel(self, config, protege):
        assert compat.dxvk_sans_gel({"DXVK_CONFIG": config}) is protege
        assert compat.dxvk_sans_gel({}) is False


class TestSuivre:
    def test_avec_le_remede_le_dessin_est_autorise(self, tmp_path):
        ini = _ini(tmp_path)
        assert incrustation_wine.suivre(tmp_path, {"DXVK_CONFIG": compat.OPTION_DXVK_SANS_GEL})
        assert reglages_correctif.valeur_posee(ini, "Accio.Overlay", "DrawUnderWine") == "1"
        # Le reste de l'ini, ses commentaires et ses fins de ligne ne bougent pas.
        assert ini.read_bytes() == _INI.replace("DrawUnderWine=0", "DrawUnderWine=1").encode("cp1252")
        # Déjà posé : rien n'est réécrit.
        assert not incrustation_wine.suivre(tmp_path, {"DXVK_CONFIG": compat.OPTION_DXVK_SANS_GEL})

    def test_sans_le_remede_le_dessin_est_coupe(self, tmp_path):
        """Quelqu'un qui remet l'ubershader ne doit pas retrouver un jeu qui se fige sur F10."""
        ini = _ini(tmp_path, _INI.replace("DrawUnderWine=0", "DrawUnderWine=1"))
        assert incrustation_wine.suivre(tmp_path, {"DXVK_CONFIG": "d3d9.ffUbershaderVS = True"})
        assert reglages_correctif.valeur_posee(ini, "Accio.Overlay", "DrawUnderWine") == "0"

    def test_un_ini_sans_la_cle_n_est_pas_touche(self, tmp_path):
        """Correctif d'avant la 2.2.0 : la clé ne lui dirait rien."""
        ancien = _INI.replace("DrawUnderWine=0\r\n", "")
        ini = _ini(tmp_path, ancien)
        assert not incrustation_wine.suivre(tmp_path, {"DXVK_CONFIG": compat.OPTION_DXVK_SANS_GEL})
        assert ini.read_bytes() == ancien.encode("cp1252")

    def test_sans_ini_rien_ne_leve(self, tmp_path):
        assert not incrustation_wine.suivre(tmp_path / "absent", {})

    def test_un_ini_illisible_ne_bloque_pas_le_lancement(self, tmp_path, monkeypatch):
        _ini(tmp_path)

        def refuse(*_a, **_k):
            raise OSError("verrouillé")
        monkeypatch.setattr(reglages_correctif, "poser_valeur", refuse)
        assert not incrustation_wine.suivre(tmp_path, {"DXVK_CONFIG": compat.OPTION_DXVK_SANS_GEL})

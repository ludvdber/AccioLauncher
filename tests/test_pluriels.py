"""Les pluriels justes à 1 (décision de Ludo, audit du 2026-10-29).

« 1 points », « et 1 autres », « 1 copie(s) » : les textes étaient écrits
pour le cas courant. `i18n.trn` choisit le gabarit d'après le nombre, avec la
règle de chaque langue (en français, 0 et 1 au singulier).
"""

from datetime import datetime
from pathlib import Path

import pytest

from src.core import i18n
from src.core.i18n import set_language, trn


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


class TestLaRegle:
    @pytest.mark.parametrize("n, attendu", [(0, "{} point"), (1, "{} point"), (2, "{} points")])
    def test_en_francais_zero_et_un_au_singulier(self, n, attendu):
        assert trn(n, "{} point", "{} points") == attendu

    @pytest.mark.parametrize("n, attendu", [(0, "{} discovery points"), (1, "{} discovery point"),
                                            (2, "{} discovery points")])
    def test_en_anglais_un_seul(self, n, attendu):
        set_language("en")
        assert trn(n, "{} point de découverte", "{} points de découverte") == attendu


class TestLesTextesAUn:
    def test_la_coupe_mene_d_un_point(self):
        from src.core import folio
        from src.ui.folio_page import phrase_coupe
        releve = folio.Releve(emplacement=1, chemin=Path("x"), modifie=datetime(2026, 10, 1), lu=True,
                              points={folio.SERPENTARD: 11, folio.GRYFFONDOR: 10,
                                      folio.SERDAIGLE: 0, folio.POUFSOUFFLE: 0})
        assert phrase_coupe(releve).endswith("mène de 1 point")

    def test_et_un_autre_succes(self):
        from src.core import succes
        from src.ui.succes_widgets import annonce_succes
        quatre = [succes.Succes(f"s{i}", f"Titre {i}", "d", lambda _r: True) for i in range(4)]
        assert annonce_succes("HP1", quatre).endswith("et 1 autre")

    def test_une_minute_restante(self):
        from src.core.formatting import format_eta
        assert format_eta(60) == "~1 min restante"
        assert format_eta(1) == "~1s restante"

    def test_aucun_gabarit_bricole(self):
        """« copie(s) » et ses cousins : un pluriel entre parenthèses ne
        s'écrit plus ; `trn` existe pour ça."""
        import json
        for fichier in Path(i18n.I18N_DIR).glob("*.json"):
            for cle in json.loads(fichier.read_text(encoding="utf-8"))["strings"]:
                assert "(s)" not in cle, cle

"""La carte d'avancement des Collections (`carte_avancement.py`, audit UI col14, 2026-11-13)."""

import pytest

pytest.importorskip("pytestqt")

from src.core import discographie, encyclopedie  # noqa: E402
from src.core.i18n import set_language  # noqa: E402


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")


def test_le_seuil_s_ecrit_d_une_seule_facon():
    from src.ui.carte_avancement import texte_seuil
    assert texte_seuil(discographie.TOUT_A) == f"S'ouvre à {discographie.TOUT_A} %"
    assert texte_seuil(40) == "S'ouvre vers 40 %"


def test_sans_seuil_ni_barre_ni_sauvegarde(qtbot):
    from src.ui.carte_avancement import CarteAvancement
    carte = CarteAvancement()
    qtbot.addWidget(carte)
    carte.poser("HP4", "12 morceaux sur 12", None, a_des_seuils=False)
    assert not carte.barre.isVisibleTo(carte) and not carte.bas.isVisibleTo(carte)
    carte.poser("HP2", "3 morceaux sur 40", 12, a_des_seuils=True)
    assert carte.barre.isVisibleTo(carte) and carte.barre.pct == 12
    assert carte.avance.text() == "Votre sauvegarde la plus avancée : 12 %"


class _Media:
    def __init__(self, avance):
        self._avance = avance

    def dossier_exe(self, jeu):
        return None

    def nom(self, jeu):
        return jeu.upper()

    def avance(self, jeu):
        return self._avance

    def ouvert(self, jeu, seuil):
        return discographie.ouvert_au_seuil(seuil, self._avance)


def test_les_fiches_comptent_les_ouvertes_sur_le_total(qtbot):
    """« 26 personnages » comptait aussi les fiches fermées."""
    from src.ui.carte_avancement import CarteAvancement
    from src.ui.encyclopedie_page import VueEncyclopedie
    vue = VueEncyclopedie(_Media(0), encyclopedie.PERSONNAGES)
    qtbot.addWidget(vue)
    vue.montrer("hp5")
    fiches = encyclopedie.fiches(encyclopedie.PERSONNAGES, "hp5")
    ouvertes = sum(discographie.ouvert_au_seuil(f.seuil, 0) for f in fiches)
    assert ouvertes < len(fiches), "le jeu d'essai a des fiches fermées"
    carte = vue.findChild(CarteAvancement)
    assert carte.compte.text() == f"{ouvertes} personnage{'s' if ouvertes > 1 else ''} sur {len(fiches)}"
    vue.fermer()

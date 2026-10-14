"""La fiche pendant un téléchargement et une installation (`carte_progression`)."""

import pytest

pytest.importorskip("pytestqt")


@pytest.fixture
def carte(qtbot):
    from src.core.i18n import get_language, set_language
    avant = get_language()
    set_language("fr")
    from src.ui.carte_progression import CarteProgression

    def _fabriquer(phase="download"):
        c = CarteProgression(phase)
        qtbot.addWidget(c)
        return c
    yield _fabriquer
    set_language(avant)


def test_l_etape_dit_combien_il_en_reste(carte):
    c = carte()
    assert c._etape.text() == "ÉTAPE 1 SUR 4 · TÉLÉCHARGEMENT"
    c.regler_phase("install")
    assert c._etape.text() == "ÉTAPE 3 SUR 4 · INSTALLATION"


def test_les_chiffres_sont_ceux_de_la_barre_du_bas(carte):
    """Mêmes morceaux que `format_progress_line` : les deux ne se contredisent jamais."""
    from src.core.formatting import format_progress_line
    c = carte()
    c.regler_telechargement(1_240_000_000, 2_900_000_000, 18_500_000, 90)
    ligne = format_progress_line(1_240_000_000, 2_900_000_000, 18_500_000, 90)
    assert c.pourcentage.text() == "42 %" and ligne.startswith("42%")
    for morceau in ligne.split(" — ")[1:]:
        for mot in morceau.split(" / "):
            assert mot in c.detail.text(), mot


def test_annuler_ne_vaut_que_pendant_le_telechargement(carte):
    c = carte()
    assert not c.bouton_annuler.isHidden()
    c.regler_phase("install")
    assert c.bouton_annuler.isHidden(), "une installation arrêtée laisserait un jeu à moitié posé"


def test_une_phase_sans_chiffre_n_en_invente_pas(carte):
    c = carte()
    c.regler_phase("verify")
    assert c.pourcentage.text() == ""
    assert c._barre.sans_chiffre


def test_l_installation_reprend_la_main_sans_signal_de_phase(carte):
    c = carte()
    c.regler_installation(42)
    assert c.phase == "install" and c.pourcentage.text() == "42 %"


def test_les_parties_s_ajoutent_au_detail(carte):
    c = carte()
    c.regler_parties(2, 3)
    c.regler_telechargement(10, 100, 1024 * 1024, 30)
    assert "partie 2 sur 3" in c.detail.text()


def test_annuler_remonte_au_panneau(carte, qtbot):
    c = carte()
    with qtbot.waitSignal(c.annuler, timeout=1000):
        c.bouton_annuler.click()

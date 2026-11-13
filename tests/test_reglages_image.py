"""L'onglet Image en six catégories et ses curseurs (maquette « Curseurs gradués », 2026-11-13) :
le rangement (`reglages_image`) et les valeurs que les curseurs écrivent (`reglages_correctif`)."""

import pytest

from src.core import reglages_correctif as rc
from src.core import reglages_image as ri
from src.core.reglages_table import CURSEURS, REGLAGES, VALEURS_DU_JEU

INI = "[Accio.Window]\r\nWindowStyle=1\r\n[Accio.Graphics]\r\nSharpness=0.40\r\nVibrance=0.35\r\nFXAA=1\r\n"


@pytest.fixture
def ini(tmp_path):
    chemin = tmp_path / "d3d9.ini"
    chemin.write_bytes(INI.encode("ascii"))
    return chemin


class TestRangement:
    def test_six_categories_dans_l_ordre_de_la_maquette(self):
        assert [i for i, _n in ri.CATEGORIES] == ["ecran", "qualite", "lumiere", "distance", "couleurs", "ciel"]

    def test_chaque_reglage_d_image_a_sa_place(self):
        for r in REGLAGES.values():
            if r.onglet in ("image", "affichage"):
                assert ri.place(r) != ri._AILLEURS, r.ident

    def test_une_categorie_vide_n_existe_pas(self):
        cats = ri.ranger([REGLAGES["halo"], REGLAGES["surechantillonnage"]])
        assert [c.ident for c in cats] == ["qualite", "lumiere"]

    def test_le_surechantillonnage_ouvre_les_contours(self):
        """Celui qui se voit le plus, en tête (maquette)."""
        (qualite,) = ri.ranger([REGLAGES["lissage"], REGLAGES["surechantillonnage"]])
        assert [r.ident for r in qualite.reglages] == ["surechantillonnage", "lissage"]

    @pytest.mark.parametrize("ident, sorte", [
        ("lissage", "inter"), ("surechantillonnage", "boutons"), ("nettete", "curseur"),
        ("ciel_couleur", "teinte"), ("mode_fenetre", "liste")])
    def test_le_controle_suit_le_reglage(self, ident, sorte):
        assert ri.controle(REGLAGES[ident]) == sorte

    def test_la_recherche_ignore_casse_et_accents(self):
        r = REGLAGES["occlusion"]
        assert ri.correspond(r, *rc.textes(r), "OMBRES DE CONTACT")
        assert ri.correspond(r, *rc.textes(r), "decor")       # « décor » dans la description
        assert not ri.correspond(r, *rc.textes(r), "   ")


class TestCurseurs:
    def test_les_paliers_sont_dans_les_bornes(self):
        """Les crans nommés du réglage restent des paliers du curseur."""
        for ident, (bas, haut, _pas) in CURSEURS.items():
            for v in REGLAGES[ident].choix:
                assert bas <= v <= haut, (ident, v)

    def test_une_valeur_du_pas_s_ecrit_et_se_relit_sans_etre_a_la_main(self, ini):
        r = REGLAGES["nettete"]
        rc.ecrire(ini, r, 0.35)
        assert b"Sharpness=0.35" in ini.read_bytes()
        assert rc.lire(ini, r) == rc.Etat(0.35)

    def test_hors_des_bornes_ou_du_pas_refuse(self, ini):
        r = REGLAGES["nettete"]
        for douteux in (0.9, 0.333, True):
            with pytest.raises(ValueError):
                rc.ecrire(ini, r, douteux)

    def test_l_arrondi_ramene_au_pas(self):
        assert rc.arrondir(REGLAGES["nettete"], 0.1 + 0.2) == 0.3
        assert rc.arrondir(REGLAGES["force_halo"], 62.4) == 60
        assert isinstance(rc.arrondir(REGLAGES["force_halo"], 62.4), int)
        assert rc.arrondir(REGLAGES["textures_lointaines"], -9) == -1.5

    def test_meme_valeur_aux_arrondis_pres(self):
        assert rc.meme_valeur(0.3, 0.1 + 0.2) and rc.meme_valeur(1, 1.0)
        assert not rc.meme_valeur(0.3, 0.35)


class TestReperes:
    def test_la_valeur_accio_vient_de_la_copie_d_origine(self, ini):
        r = REGLAGES["vivacite"]
        rc.ecrire(ini, r, 0.5)   # première retouche : l'ini installé est gardé
        assert rc.valeur_accio(ini, r) == 0.35
        assert rc.lire(ini, r).valeur == 0.5

    def test_sans_retouche_accio_est_l_ini(self, ini):
        assert rc.valeur_accio(ini, REGLAGES["nettete"]) == 0.4

    def test_les_valeurs_du_jeu_sont_proposees(self):
        """Le bouton « Valeur du jeu » écrit cette valeur : elle doit être un choix du réglage."""
        for ident, valeur in VALEURS_DU_JEU.items():
            r = REGLAGES[ident]
            if r.choix:
                assert valeur in r.choix or rc.sur_le_curseur(r, valeur), ident
            else:
                assert isinstance(valeur, bool), ident

    def test_un_reglage_sans_equivalent_n_a_pas_de_valeur_du_jeu(self):
        assert rc.valeur_du_jeu(REGLAGES["ciel_couleur"]) is None

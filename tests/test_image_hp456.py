"""Le menu Image de HP4, HP5 et HP6 complété le 2026-11-20 (choix de Ludo) : les dosages des effets, la
rubrique « Réglages fins » repliée, la précision des ombres et la finesse de la lueur (HP5, HP6), la vue
resserrée en courant (HP6), les petits objets et l'horizon (HP4)."""
import pytest

from src.core import reglages_correctif as rc
from src.core import reglages_image as ri
from src.core.game_data import load_catalog
from src.core.reglages_table import REGLAGES
from tests.test_reglages_correctif import INI_JEU, _dialogue, _jeu, _manager

# Le neutre du correctif quand la clé manque (source/settings.cpp, relevé le 2026-11-20) : le premier choix
# de chaque dosage, pour qu'un ini sans la clé se lise sur le bon cran.
NEUTRES = {
    "force_occlusion": 0.5, "portee_occlusion": 6, "intensite_halo": 0.35, "seuil_halo": 0.75,
    "force_rayons": 0.45, "longueur_rayons": 0.96, "tons_moyens": 1, "temperature": 0, "noirs_releves": 0,
    "exposition": 1, "teinte": 0, "virage": 0, "retenue_jaune": 0, "retenue_vert": 0,
    "ombres_fines": 0, "halo_fin": 0, "petits_objets_lointains": 0, "horizon": 0,
}
FINS = {"portee_occlusion", "seuil_halo", "longueur_rayons", "noirs_releves", "exposition", "teinte", "virage",
        "retenue_jaune"}


class TestTable:
    @pytest.mark.parametrize("ident", sorted(NEUTRES))
    def test_le_premier_choix_est_le_neutre_du_correctif(self, ident):
        assert REGLAGES[ident].choix[0] == NEUTRES[ident]

    def test_la_vue_resserree_est_allumee_sans_la_cle(self):
        """AdaptiveFov manque : le correctif l'allume (Bool(game, "AdaptiveFov", true))."""
        r = REGLAGES["fov_course"]
        assert (r.section, r.cle, r.defaut, r.depend_de) == ("Accio.Game", "AdaptiveFov", True, "champ_vision")

    def test_le_vert_des_montagnes_attend_la_retenue_du_vert(self):
        """À GreenRestraint=0 (HP5 livré), GreenRestraintTerrain n'a rien à rendre au relief."""
        r = REGLAGES["vert_relief"]
        assert r.depend_de == "retenue_vert"
        valeurs = {"lissage": True, "couleurs": True, "retenue_vert": 0, "vert_relief": 0.4}
        assert rc.bloque_par(r, valeurs) is REGLAGES["retenue_vert"]
        assert rc.bloque_par(r, {**valeurs, "retenue_vert": 1}) is None
        assert rc.bloque_par(r, {**valeurs, "retenue_vert": 1, "couleurs": False}) is REGLAGES["couleurs"]


class TestRangement:
    def test_les_dosages_fins_ferment_leur_categorie(self):
        cats = ri.ranger(REGLAGES.values())
        for cat in cats:
            noms = [g.nom for g in cat.groupes]
            if ri.GROUPE_FIN in noms:
                assert noms[-1] == ri.GROUPE_FIN, cat.ident
        fins = {r.ident for c in cats for g in c.groupes if g.nom == ri.GROUPE_FIN for r in g.reglages}
        assert fins == FINS

    def test_chaque_dosage_suit_son_effet(self):
        assert ri.place(REGLAGES["force_occlusion"]) == ri.place(REGLAGES["occlusion"])
        assert ri.place(REGLAGES["intensite_halo"]) == ri.place(REGLAGES["halo"])
        assert ri.place(REGLAGES["fov_course"]) == ri.place(REGLAGES["champ_vision"])
        assert ri.place(REGLAGES["ombres_fines"]) == ri.place(REGLAGES["ombres_douces"])


class TestCatalogue:
    """Les deux catalogues ont le même contenu (test_catalogue) ; l'embarqué suffit ici."""

    def _declares(self, jeu):
        return set(next(g for g in load_catalog().games if g.id == jeu).fix_settings)

    def test_les_dosages_dans_les_trois_jeux(self):
        dosages = set(NEUTRES) - {"ombres_fines", "halo_fin", "petits_objets_lointains", "horizon",
                                  "retenue_vert"}
        for jeu in ("hp4", "hp5", "hp6"):
            assert dosages <= self._declares(jeu), jeu

    def test_chaque_jeu_n_a_que_ce_qui_agit_chez_lui(self):
        hp4, hp5, hp6 = (self._declares(j) for j in ("hp4", "hp5", "hp6"))
        # Le voile menthe n'existe que dans HP5 et HP6 ; ShadowTextureSize et NativeBloomSize aussi.
        assert not {"retenue_vert", "vert_relief", "ombres_fines", "halo_fin"} & hp4
        assert {"retenue_vert", "vert_relief", "ombres_fines", "halo_fin"} <= hp5
        assert {"retenue_vert", "vert_relief", "ombres_fines", "halo_fin", "fov_course"} <= hp6
        # CullDistance et MaxFarClip (pour ce dernier, rien de visible au cloître de HP5) : HP4 seul.
        assert {"petits_objets_lointains", "horizon"} <= hp4
        assert not {"petits_objets_lointains", "horizon", "fov_course"} & (hp5 | (hp6 - {"fov_course"}))

    def test_les_essais_de_hp6_en_beta_pour_lui_seul(self):
        """Ludo, 2026-11-20 : ombres douces et braises pas vues dans HP6 (vues dans HP5 et HP4)."""
        def betas(jeu):
            g = next(g for g in load_catalog().games if g.id == jeu)
            return {r.ident for r in rc.reglages_du_jeu(g.fix_settings, g.id) if r.beta}
        assert {"ombres_douces", "particules_lointaines"} <= betas("hp6")
        assert "ombres_douces" not in betas("hp5")
        assert "particules_lointaines" not in betas("hp4")
        assert not REGLAGES["ombres_douces"].beta, "la table reste neutre : la bêta est par jeu"

    def test_un_dosage_declare_a_son_effet_declare(self):
        """Un dosage dont l'interrupteur manque au catalogue serait une ligne sans parent qui ne grise jamais."""
        for g in load_catalog().games:
            declares = set(g.fix_settings)
            for ident in declares & set(NEUTRES):
                parent = REGLAGES[ident].depend_de
                assert not parent or parent in declares, (g.id, ident, parent)


# Les clés de HP4 posées dans la section [Accio.Graphics] de l'ini d'essai, à la place de son FXAA=0.
INI_HP4 = INI_JEU.replace("FXAA=0\r\n", "\r\n".join([
    "FXAA=1", "ColorGrading=1", "SSAO=1", "Bloom=1", "GodRays=1", "Gamma=0.90",
    "Temperature=0.05", "Lift=0.00", "Gain=1.00", "Tint=0.00", "SplitTone=0.00", "YellowRestraint=0.00",
    "SSAOStrength=0.50", "SSAORadius=6.0", "BloomStrength=0.25", "BloomThreshold=0.85",
    "GodRaysStrength=0.45", "GodRaysDecay=0.96", "",
]))
IDENTS_HP4 = ["lissage", "couleurs", "vivacite", "occlusion", "halo", "rayons", "force_occlusion", "tons_moyens",
              "temperature", "intensite_halo", "force_rayons", "noirs_releves", "exposition", "teinte", "virage",
              "retenue_jaune", "portee_occlusion", "seuil_halo", "longueur_rayons"]


class TestPage:
    def _page(self, qtbot, tmp_path):
        dossier = tmp_path / "HP4"
        dossier.mkdir()
        ini = dossier / "d3d9.ini"
        ini.write_bytes(INI_HP4.encode("ascii"))
        dlg = _dialogue(qtbot, _jeu(tmp_path, IDENTS_HP4), _manager(tmp_path))
        return dlg, dlg._page_img, ini

    def _ouvrir(self, page, cat):
        page.montrer([c.ident for c in page.categories].index(cat))

    def test_les_reglages_fins_sont_replies(self, qtbot, tmp_path):
        dlg, page, _ini = self._page(qtbot, tmp_path)
        dlg.resize(1400, 900)
        dlg.show()
        self._ouvrir(page, "couleurs")
        (bouton, carte, reglages), = page._fins
        assert {r.ident for r in reglages} == {"noirs_releves", "exposition", "teinte", "virage", "retenue_jaune"}
        assert bouton.isVisible() and not carte.isVisible()
        assert page.ligne("tons_moyens").isVisible(), "les curseurs choisis restent en vue"
        bouton.click()
        assert carte.isVisible() and page.ligne("teinte").isVisible()
        bouton.click()
        assert not carte.isVisible()

    def test_sans_couleurs_retravaillees_le_groupe_replie_disparait(self, qtbot, tmp_path):
        dlg, page, ini = self._page(qtbot, tmp_path)
        dlg.resize(1400, 900)
        dlg.show()
        self._ouvrir(page, "couleurs")
        (bouton, carte, _r), = page._fins
        bouton.click()
        page.regler("couleurs", False)
        assert not bouton.isVisible() and not carte.isVisible()
        page.regler("couleurs", True)
        assert bouton.isVisible() and carte.isVisible(), "rouvert comme on l'avait laissé"

    def test_un_dosage_s_ecrit_dans_l_ini(self, qtbot, tmp_path):
        _dlg, page, ini = self._page(qtbot, tmp_path)
        assert page.valeur("intensite_halo") == 0.25, "le cran livré de HP4, entre deux paliers"
        page.regler("intensite_halo", 0.5)
        page.regler("tons_moyens", 0.8)
        texte = ini.read_bytes().decode("ascii")
        assert "BloomStrength=0.5\r\n" in texte and "Gamma=0.8\r\n" in texte

    def test_la_recherche_trouve_un_reglage_replie(self, qtbot, tmp_path):
        _dlg, page, _ini = self._page(qtbot, tmp_path)
        page.recherche.setText("teinte vert")
        nom, _aide, ligne = page._trouvables["teinte"]
        assert nom == "Teinte vert-rose" and not ligne.isHidden()

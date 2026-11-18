"""La difficulté de HP6 par ses scripts Lua : le launcher pose le script réglé dans `lua_launcher`
et laisse la clé jumelle du correctif à l'origine (les deux se multiplieraient)."""
import pytest

from src.core import difficulte_lua as dl
from src.core import difficulte_presets as dp
from src.core import reglages_correctif as rc
from src.core.game_data import GameData
from src.core.reglages_table import REGLAGES

INI = "\r\n".join([
    "; Accio Launcher - PC fix", "[Accio.Window]", "WindowStyle=0", "",
    "[Accio.Game]", "LuaFolder=lua", "",
    "[Accio.Hardcore]", "DamageTaken=1", "DamageDealt=1", "EnemyReaction=1", "RemovedSpells=",
    "PlayerHealth=1", "PlayerRegen=1", "Invincible=0", "",
]) + "\r\n"
IDENTS = ("degats_recus", "degats_infliges", "reaction_ennemis", "vie_joueur", "regeneration", "invincible")


def _modele(*reglages: str) -> str:
    """Un préréglage comme accio-moteur les livre : ses réglages en tête, son code dessous."""
    lignes = [f"{r:<21}-- ce que règle cette ligne" for r in (*reglages, "actif = true", "afficher = false")]
    return "\n".join(["-- Un préréglage.", "-- RÉGLAGES", *lignes, "-- FIN DES RÉGLAGES", "local vie = 12", ""])


MODELES = {
    "degats_recus": _modele("facteur = 1.0", "multiplier = false"),
    "ennemis_plus_resistants": _modele("vie = 1.5"),
    "ennemis_plus_vifs": _modele("reaction = 1.5"),
    "harry_plus_resistant": _modele("vie = 1.5"),
    "regeneration": _modele("points = 2", "delai = 6", "part_du_jeu = 0"),
}


@pytest.fixture
def jeu(tmp_path):
    """Un HP6 installé qui porte Lua : l'hôte, les modèles, le dossier de scripts du joueur."""
    (tmp_path / "d3d9.ini").write_bytes(INI.encode("ascii"))
    (tmp_path / dl.HOTE).write_bytes(b"MZ")
    (tmp_path / "lua").mkdir()
    (tmp_path / dl.DOSSIER_MODELES).mkdir()
    for nom, source in MODELES.items():
        (tmp_path / dl.DOSSIER_MODELES / f"{nom}.lua").write_text(source, encoding="utf-8")
    return tmp_path


def _script(jeu, nom: str) -> str:
    return (jeu / dl.DOSSIER_FOURNI / f"{nom}.lua").read_text(encoding="utf-8")


def _game() -> GameData:
    return GameData.from_dict({"id": "hp6", "name": "HP6", "year": 2009, "description": "d", "developer": "d",
                               "executable": "HP6/hp6.exe", "cover_image": "c.jpg", "fix_settings": list(IDENTS)})


class TestVoie:
    def test_tout_est_la(self, jeu):
        assert all(dl.pret(jeu, ident, "lua") for ident in dl.TRADUCTIONS)

    @pytest.mark.parametrize("dossier", [None, "", "0", "absent"])
    def test_sans_dossier_de_scripts_l_hote_n_est_pas_charge(self, jeu, dossier):
        assert not dl.pret(jeu, "degats_recus", dossier)

    def test_sans_hote_ou_sans_modele(self, jeu):
        (jeu / dl.DOSSIER_MODELES / "regeneration.lua").unlink()
        assert not dl.pret(jeu, "regeneration", "lua")
        (jeu / dl.HOTE).unlink()
        assert not dl.pret(jeu, "degats_recus", "lua")
        # L'hôte peut aussi vivre dans le dossier de scripts : le correctif l'y cherche d'abord.
        (jeu / "lua" / dl.HOTE).write_bytes(b"MZ")
        assert dl.pret(jeu, "degats_recus", "lua")

    def test_un_reglage_sans_script_reste_au_correctif(self, jeu):
        assert not dl.pret(jeu, "invincible", "lua")


class TestScripts:
    def test_la_valeur_d_origine_est_un_script_absent(self, jeu):
        dl.ecrire(jeu, "degats_recus", 3, 1)
        dl.ecrire(jeu, "degats_recus", 1, 1)
        assert not (jeu / dl.DOSSIER_FOURNI / "degats_recus.lua").exists()
        assert dl.lire(jeu, "degats_recus", 1) == 1

    def test_detendu_multiplie_et_hardcore_remplace(self, jeu):
        dl.ecrire(jeu, "degats_recus", 0.5, 1)
        assert "facteur = 0.5 " in _script(jeu, "degats_recus") and "multiplier = true" in _script(jeu, "degats_recus")
        dl.ecrire(jeu, "degats_recus", 3, 1)
        assert "facteur = 3 " in _script(jeu, "degats_recus") and "multiplier = false" in _script(jeu, "degats_recus")
        assert dl.lire(jeu, "degats_recus", 1) == 3

    @pytest.mark.parametrize("facteur", REGLAGES["degats_infliges"].choix[1:])
    def test_des_sorts_plus_faibles_sont_des_adversaires_plus_resistants(self, jeu, facteur):
        dl.ecrire(jeu, "degats_infliges", facteur, 1)
        vie = float(_script(jeu, "ennemis_plus_resistants").split("vie = ")[1].split()[0])
        assert vie == pytest.approx(1 / facteur, abs=1e-3)
        assert dl.lire(jeu, "degats_infliges", 1) == facteur

    def test_la_regeneration_garde_une_part_de_celle_du_jeu_sans_rien_ajouter(self, jeu):
        dl.ecrire(jeu, "regeneration", 0.5, 1)
        source = _script(jeu, "regeneration")
        assert "points = 0 " in source and "part_du_jeu = 0.5 " in source and "delai = 6 " in source
        dl.ecrire(jeu, "regeneration", 0, 1)
        assert dl.lire(jeu, "regeneration", 1) == 0

    def test_le_code_du_script_n_est_pas_touche(self, jeu):
        """`local vie = 12` sous l'en-tête n'est pas un réglage."""
        dl.ecrire(jeu, "vie_joueur", 0.5, 1)
        source = _script(jeu, "harry_plus_resistant")
        assert "vie = 0.5 " in source and source.endswith("-- FIN DES RÉGLAGES\nlocal vie = 12\n")

    def test_un_script_coupe_ou_abime_ne_fait_rien(self, jeu):
        dl.ecrire(jeu, "vie_joueur", 0.5, 1)
        pose = jeu / dl.DOSSIER_FOURNI / "harry_plus_resistant.lua"
        pose.write_text(_script(jeu, "harry_plus_resistant").replace("actif = true", "actif = false"), encoding="utf-8")
        assert dl.lire(jeu, "vie_joueur", 1) == 1
        pose.write_text("vie = beaucoup\n", encoding="utf-8")
        assert dl.lire(jeu, "vie_joueur", 1) == 1

    def test_un_modele_d_un_hote_plus_ancien_est_refuse(self, jeu):
        (jeu / dl.DOSSIER_MODELES / "degats_recus.lua").write_text(_modele("facteur = 1.0"), encoding="utf-8")
        with pytest.raises(ValueError, match="multiplier"):
            dl.ecrire(jeu, "degats_recus", 0.5, 1)
        assert not (jeu / dl.DOSSIER_FOURNI / "degats_recus.lua").exists()


class TestParLesReglages:
    """Presets et « Sur mesure » passent tous par `reglages_correctif` : une seule voie."""

    def test_chaque_choix_propose_fait_l_aller_retour(self, jeu):
        ini = jeu / "d3d9.ini"
        for ident in dl.TRADUCTIONS:
            for valeur in REGLAGES[ident].choix:
                rc.ecrire(ini, REGLAGES[ident], valeur)
                etat = rc.lire(ini, REGLAGES[ident])
                assert (etat.valeur, etat.personnalise) == (valeur, False), (ident, valeur)

    def test_la_cle_jumelle_du_correctif_revient_a_l_origine(self, jeu):
        ini = jeu / "d3d9.ini"
        ini.write_bytes(INI.replace("DamageTaken=1", "DamageTaken=3").encode("ascii"))
        rc.ecrire(ini, REGLAGES["degats_recus"], 3)
        assert rc.valeur_posee(ini, "Accio.Hardcore", "DamageTaken") == "1"
        assert rc.lire(ini, REGLAGES["degats_recus"]).valeur == 3

    def test_sans_lua_tout_reste_dans_l_ini(self, jeu):
        ini = jeu / "d3d9.ini"
        (jeu / dl.HOTE).unlink()
        rc.ecrire(ini, REGLAGES["degats_recus"], 3)
        assert rc.valeur_posee(ini, "Accio.Hardcore", "DamageTaken") == "3"
        assert not (jeu / dl.DOSSIER_FOURNI).exists()

    def test_un_reglage_que_seul_lua_porte_est_propose(self, jeu):
        """Un correctif sans section [Accio.Hardcore] : les scripts suffisent."""
        ini = jeu / "d3d9.ini"
        ini.write_bytes(INI.split("[Accio.Hardcore]")[0].encode("ascii"))
        portes = rc.portes_par(ini, rc.reglages_du_jeu(IDENTS))
        assert {r.ident for r in portes} == set(dl.TRADUCTIONS)
        rc.ecrire(ini, REGLAGES["vie_joueur"], 1.5)
        assert rc.lire(ini, REGLAGES["vie_joueur"]).valeur == 1.5

    def test_un_preset_pose_ses_scripts_et_normal_les_retire(self, jeu):
        ini, game = jeu / "d3d9.ini", _game()
        idents = dp.idents_du_jeu(game, ini)
        assert dp.appliquer(dp.PAR_IDENT["hardcore"], game, None, ini, idents) == []
        assert dp.courant(dp.lire(game, None, ini, idents), idents) == "hardcore"
        assert sorted(p.name for p in (jeu / dl.DOSSIER_FOURNI).iterdir()) == [
            "degats_recus.lua", "ennemis_plus_resistants.lua", "ennemis_plus_vifs.lua", "regeneration.lua"]
        assert dp.appliquer(dp.PAR_IDENT["detendu"], game, None, ini, idents) == []
        assert "multiplier = true" in _script(jeu, "degats_recus")
        assert dp.appliquer(dp.PAR_IDENT["normal"], game, None, ini, idents) == []
        assert list((jeu / dl.DOSSIER_FOURNI).iterdir()) == []
        assert dp.courant(dp.lire(game, None, ini, idents), idents) == "normal"

    def test_remettre_l_origine_retire_les_scripts(self, jeu):
        ini = jeu / "d3d9.ini"
        rc.ecrire(ini, REGLAGES["reaction_ennemis"], 5)
        rc.remettre_origine(ini, [REGLAGES["reaction_ennemis"]])
        assert list((jeu / dl.DOSSIER_FOURNI).iterdir()) == []
        assert rc.lire(ini, REGLAGES["reaction_ennemis"]).valeur == 1

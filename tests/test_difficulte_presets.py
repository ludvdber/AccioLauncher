"""Les presets de difficulté de la 1.4 (Normal, Détendu, Hardcore ; Réaliste et Impardonnable à une
seule vie), tranchés par Ludo le 2026-10-30."""
import itertools
from types import SimpleNamespace

import pytest

from src.core import difficulte_presets as dp
from src.core import reglages_correctif as rc
from src.core.game_data import GameData, load_catalog
from src.core.i18n import set_language
from src.core.reglages_table import REGLAGES

INI = "\r\n".join([
    "; Accio Launcher - PC fix", "[Accio.Window]", "WindowStyle=0", "",
    "[Accio.Hardcore]", "DamageTaken=1", "DamageDealt=1", "EnemyReaction=1", "RemovedSpells=",
    "PlayerHealth=1", "PlayerRegen=1", "Invincible=0", "",
]) + "\r\n"
HP6 = ("degats_recus", "degats_infliges", "reaction_ennemis", "sorts_retires", "vie_joueur", "regeneration",
       "invincible")
# Ce que les presets règlent : tout sauf les sorts retirés (ils peuvent bloquer la partie).
HP6_PRESETS = frozenset(HP6) - {"sorts_retires"}


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


@pytest.fixture
def ini(tmp_path):
    p = tmp_path / "d3d9.ini"
    p.write_bytes(INI.encode("ascii"))
    return p


def _jeu(**champs):
    return GameData.from_dict({"id": "hp6", "name": "HP6", "year": 2009, "description": "d",
                               "developer": "d", "executable": "HP6/hp6.exe", "cover_image": "c.jpg",
                               **champs})


class TestValeurs:
    def test_chaque_valeur_est_un_choix_que_l_interface_propose(self):
        """`reglages_correctif.ecrire` refuse une valeur hors de ses choix : un preset l'aurait vue échouer."""
        for preset in dp.PRESETS:
            for ident, valeur in preset.valeurs.items():
                if ident == dp.NATIVE:
                    assert valeur in (0, 1, 2)
                elif not REGLAGES[ident].choix:
                    assert isinstance(valeur, bool), (preset.ident, ident)
                else:
                    assert valeur in REGLAGES[ident].choix, (preset.ident, ident, valeur)

    def test_normal_est_le_jeu_tel_que_livre(self):
        """Le premier choix de chaque réglage est son « d'origine »."""
        for ident, valeur in dp.PAR_IDENT["normal"].valeurs.items():
            if ident == dp.NATIVE:
                continue
            reglage = REGLAGES[ident]
            assert valeur == (reglage.choix[0] if reglage.choix else reglage.defaut), ident

    def test_sept_presets_du_plus_doux_au_plus_dur(self):
        assert [p.ident for p in dp.PRESETS] == ["recit", "detendu", "normal", "difficile", "hardcore", "realiste", "impardonnable"]

    def test_chaque_cran_est_plus_dur_que_le_precedent(self):
        """Ludo, 2026-10-30 : Difficile entre la difficulté d'origine et Hardcore, Hardcore bien au-delà."""
        crans = [dp.PAR_IDENT[i].valeurs for i in ("detendu", "normal", "difficile", "hardcore")]
        for doux, dur in itertools.pairwise(crans):
            assert doux["degats_recus"] < dur["degats_recus"]
            assert doux["degats_infliges"] > dur["degats_infliges"]
        assert dp.PAR_IDENT["hardcore"].valeurs["reaction_ennemis"] < max(REGLAGES["reaction_ennemis"].choix),             "le sur mesure va plus loin que Hardcore"

    def test_recit_seulement_la_ou_harry_peut_etre_invincible(self):
        """Sans invincibilité (correctif 2.2.0, HP1-HP3), Récit ne serait qu'un Détendu mal nommé."""
        recit = dp.PAR_IDENT["recit"]
        assert not dp.disponible(recit, "hp6", {"degats_recus", "degats_infliges"})
        assert dp.disponible(recit, "hp6", {"degats_infliges", "invincible"})
        idents = {"degats_recus", "degats_infliges"}
        assert dp.courant({"degats_recus": 1, "degats_infliges": 1.5}, idents) == dp.SUR_MESURE

    def test_aucun_preset_ne_retire_de_sort(self):
        """Ludo, 2026-10-30 : un sort retiré peut bloquer la partie, c'est un réglage à part."""
        assert all("sorts_retires" not in p.valeurs for p in dp.PRESETS)

    def test_une_seule_vie_reprend_normal_et_hardcore(self):
        assert dp.PAR_IDENT["realiste"].valeurs == dp.PAR_IDENT["normal"].valeurs
        assert dp.PAR_IDENT["impardonnable"].valeurs == dp.PAR_IDENT["hardcore"].valeurs
        assert [p.ident for p in dp.PRESETS if p.une_vie] == ["realiste", "impardonnable"]


class TestParJeu:
    def test_rien_pour_un_jeu_sans_reglage_de_difficulte(self):
        idents = dp.idents_du_jeu(_jeu(fix_settings=["limite_fps"]))
        assert idents == frozenset()
        assert [p.ident for p in dp.PRESETS if dp.disponible(p, "hp4", idents)] == ["normal"]

    def test_hp6_tout_sauf_une_seule_vie(self, ini):
        idents = dp.idents_du_jeu(_jeu(fix_settings=list(HP6)), ini)
        assert idents == HP6_PRESETS
        assert [p.ident for p in dp.PRESETS if dp.disponible(p, "hp6", idents)] == \
            ["recit", "detendu", "normal", "difficile", "hardcore"]

    def test_une_seule_vie_s_ouvre_jeu_par_jeu(self, monkeypatch):
        """Le jour où le mécanisme existe dans un jeu : Réaliste s'y offre même sans
        autre réglage, Impardonnable seulement là où Hardcore change quelque chose."""
        monkeypatch.setattr(dp, "UNE_VIE_POSSIBLE", frozenset({"hp4", "hp6"}))
        assert dp.disponible(dp.PAR_IDENT["realiste"], "hp4", frozenset())
        assert not dp.disponible(dp.PAR_IDENT["impardonnable"], "hp4", frozenset())
        assert dp.disponible(dp.PAR_IDENT["impardonnable"], "hp6", HP6_PRESETS)
        assert not dp.disponible(dp.PAR_IDENT["realiste"], "hp5", HP6_PRESETS)

    def test_une_section_absente_de_l_ini_installe_retire_ses_reglages(self, tmp_path):
        """L'ancien correctif (sans [Accio.Hardcore]) : rien à écrire, rien à proposer."""
        p = tmp_path / "d3d9.ini"
        p.write_bytes(b"; Accio Launcher - PC fix\r\n[Accio.Window]\r\nWindowStyle=0\r\n")
        assert dp.idents_du_jeu(_jeu(fix_settings=list(HP6)), p) == frozenset()

    def test_la_difficulte_propre_du_jeu_compte(self):
        hp2 = next(g for g in load_catalog().games if g.id == "hp2")
        idents = dp.idents_du_jeu(hp2)
        assert dp.NATIVE in idents
        assert dp.disponible(dp.PAR_IDENT["hardcore"], "hp2", idents)
        assert ("Difficulté du jeu", "Difficile") in dp.changements(dp.PAR_IDENT["hardcore"], idents)

    def test_normal_reconnu_avant_un_preset_qui_ne_change_rien(self):
        """HP2 : Détendu (premier de la liste) y vaut Normal ; la page disait « Détendu » choisi."""
        assert dp.courant({dp.NATIVE: 0, "quidditch": 0}, {dp.NATIVE, "quidditch"}) == "normal"

    def test_detendu_ne_s_offre_pas_la_ou_il_ne_change_rien(self):
        """HP2 sans réglage du correctif : Détendu vaudrait Normal (la difficulté livrée est déjà Facile)."""
        assert not dp.disponible(dp.PAR_IDENT["detendu"], "hp2", {dp.NATIVE, "quidditch"})

    def test_le_catalogue_embarque_propose_ce_qu_il_declare(self):
        jeux = {g.id: g for g in load_catalog().games}
        for ident in ("hp3", "hp4", "hp7a", "hp7b"):
            idents = dp.idents_du_jeu(jeux[ident])
            assert not dp.disponible(dp.PAR_IDENT["hardcore"], ident, idents), ident
        for ident in ("hp1", "hp2", "hp5", "hp6"):
            assert dp.disponible(dp.PAR_IDENT["hardcore"], ident, dp.idents_du_jeu(jeux[ident])), ident


class TestLireEtAppliquer:
    def test_aller_retour_et_preset_reconnu(self, ini):
        jeu = _jeu(fix_settings=list(HP6))
        idents = dp.idents_du_jeu(jeu, ini)
        config = SimpleNamespace(install_path=ini.parent)
        assert dp.courant(dp.lire(jeu, config, ini, idents), idents) == "normal"
        assert dp.appliquer(dp.PAR_IDENT["hardcore"], jeu, config, ini, idents) == []
        lignes = set(ini.read_bytes().decode().split("\r\n"))
        assert {"DamageTaken=3", "DamageDealt=0.5", "EnemyReaction=5", "RemovedSpells=",
                "PlayerRegen=0"} <= lignes
        assert dp.courant(dp.lire(jeu, config, ini, idents), idents) == "hardcore"
        assert dp.appliquer(dp.PAR_IDENT["normal"], jeu, config, ini, idents) == []
        assert dp.courant(dp.lire(jeu, config, ini, idents), idents) == "normal"

    def test_un_reglage_change_a_la_main_donne_sur_mesure(self, ini):
        jeu = _jeu(fix_settings=list(HP6))
        idents = dp.idents_du_jeu(jeu, ini)
        config = SimpleNamespace(install_path=ini.parent)
        dp.appliquer(dp.PAR_IDENT["hardcore"], jeu, config, ini, idents)
        rc.ecrire(ini, REGLAGES["degats_recus"], 5)
        assert dp.courant(dp.lire(jeu, config, ini, idents), idents) == dp.SUR_MESURE

    def test_sans_ini_rien_n_est_ecrit_et_tout_est_signale(self):
        jeu = _jeu(fix_settings=list(HP6))
        config = SimpleNamespace(install_path=None)
        rates = dp.appliquer(dp.PAR_IDENT["hardcore"], jeu, config, None, {"degats_recus"})
        assert rates == ["degats_recus"]

    def test_changements_en_mots(self, ini):
        idents = dp.idents_du_jeu(_jeu(fix_settings=list(HP6)), ini)
        lignes = dict(dp.changements(dp.PAR_IDENT["hardcore"], idents))
        assert lignes["Régénération"] == "Jamais"
        assert "Sorts retirés" not in lignes
        assert "Vie de Harry" not in lignes, "Hardcore ne la change pas"
        assert ("Harry invincible", "") in dp.changements(dp.PAR_IDENT["recit"], idents)
        assert dp.changements(dp.PAR_IDENT["normal"], idents) == ()


pytest.importorskip("pytestqt")


@pytest.fixture
def dossier_hp6(tmp_path):
    (tmp_path / "HP6").mkdir()
    (tmp_path / "HP6" / "d3d9.ini").write_bytes(INI.encode("ascii"))
    return SimpleNamespace(config=SimpleNamespace(install_path=tmp_path))


class TestPage:
    def _page(self, qtbot, manager, **champs):
        from src.ui.difficulte_page import DifficultePage
        ouverts = []
        page = DifficultePage(_jeu(**champs), manager, ouvrir_detail=lambda: ouverts.append(1))
        qtbot.addWidget(page)
        return page, ouverts

    def test_une_carte_par_preset_utile_et_une_seule_vie_bientot(self, qtbot, dossier_hp6):
        page, _ = self._page(qtbot, dossier_hp6, fix_settings=list(HP6))
        assert [c.ident for c in page.cartes] == ["recit", "detendu", "normal", "difficile", "hardcore", "realiste", "impardonnable"]
        for carte in page.cartes[-2:]:
            assert carte.bouton is None and carte.property("bientot") == "true"
        assert next(c for c in page.cartes if c.ident == "normal").property("actif") == "true", "un ini neuf : Normal"

    def test_choisir_ecrit_et_marque_la_carte(self, qtbot, dossier_hp6):
        page, _ = self._page(qtbot, dossier_hp6, fix_settings=list(HP6))
        next(c for c in page.cartes if c.ident == "hardcore").bouton.click()
        ini = dossier_hp6.config.install_path / "HP6" / "d3d9.ini"
        assert "DamageTaken=3" in ini.read_bytes().decode().split("\r\n")
        actifs = [c.ident for c in page.cartes if c.property("actif") == "true"]
        assert actifs == ["hardcore"]
        assert not next(c for c in page.cartes if c.ident == "hardcore").bouton.isEnabled()

    def test_sur_mesure_ouvre_le_detail(self, qtbot, dossier_hp6):
        from PyQt6.QtWidgets import QPushButton
        page, ouverts = self._page(qtbot, dossier_hp6, fix_settings=list(HP6))
        next(b for b in page.findChildren(QPushButton) if b.text() == "Régler chaque paramètre").click()
        assert ouverts == [1]

    def test_un_jeu_sans_reglage_ne_propose_que_normal(self, qtbot, dossier_hp6):
        page, _ = self._page(qtbot, dossier_hp6, fix_settings=["limite_fps"])
        assert [c.ident for c in page.cartes] == ["normal", "realiste"]


class TestBoutonDeLaFiche:
    def _bouton(self, win, jeu):
        from src.ui.icon_button import IconButton
        game = next(e.game for e in win.manager.get_games() if e.game.id == jeu)
        win._detail.set_game(game)
        return win._detail._action_panel.findChild(IconButton, "boutonDifficulte")

    def test_hp2_ouvre_la_page_et_hp3_attend(self, make_window, monkeypatch):
        from src.core.game_manager import GameManager, GameState
        from src.ui.difficulte_page import DifficultePage
        monkeypatch.setattr(GameManager, "is_installed", lambda self, j: j in {"hp2", "hp3"})
        monkeypatch.setattr(GameManager, "get_state", lambda self, j: GameState.INSTALLED
                            if j in {"hp2", "hp3"} else GameState.NOT_INSTALLED)
        win = make_window()
        assert not self._bouton(win, "hp3").isEnabled(), "rien à régler dans HP3 : bientôt"
        bouton = self._bouton(win, "hp2")
        assert bouton.isEnabled()
        bouton.click()
        assert isinstance(win._pages.page, DifficultePage)
        win._pages.page.accept()

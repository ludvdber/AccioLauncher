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
        assert dp.changements(dp.PAR_IDENT["recit"], idents)[0] == ("Harry invincible", ""), \
            "le réglage qui définit le preset passe en tête"
        assert dp.changements(dp.PAR_IDENT["normal"], idents) == ()


# Du plus doux au plus dur, écrit ici à la main (et non tiré de la formule) :
# c'est ce que la monotonie doit respecter.
_DURCIT = {
    "degats_recus": sorted(REGLAGES["degats_recus"].choix),
    "degats_infliges": sorted(REGLAGES["degats_infliges"].choix, reverse=True),
    "reaction_ennemis": sorted(REGLAGES["reaction_ennemis"].choix),
    "vie_joueur": sorted(REGLAGES["vie_joueur"].choix, reverse=True),
    "regeneration": sorted(REGLAGES["regeneration"].choix, reverse=True),
    "quidditch": sorted(REGLAGES["quidditch"].choix),
    dp.NATIVE: [0, 1, 2],
}
HP2 = frozenset({dp.NATIVE, "quidditch"})


class TestNiveau:
    """Le niveau de défi du cadran (maquette validée par Ludo le 2026-10-31)."""

    def _niveau(self, ident, idents=HP6_PRESETS, jeu="hp6"):
        return dp.niveau(dp.valeurs_pour(dp.PAR_IDENT[ident], idents), jeu, idents)

    def test_chaque_preset_a_son_cran_dans_chaque_jeu(self):
        """Les noms gravés autour du cadran sont à la même place partout."""
        for idents, jeu in ((HP6_PRESETS, "hp6"), (HP2, "hp2"), (frozenset({"quidditch"}), "hp1")):
            for preset, cran in dp.reperes(jeu, idents):
                assert self._niveau(preset.ident, idents, jeu) == pytest.approx(cran), (jeu, preset.ident)
        assert [p.ident for p, _ in dp.reperes("hp2", HP2)] == ["normal", "difficile", "hardcore"]
        assert [round(c) for _, c in dp.reperes("hp6", HP6_PRESETS)] == [3, 25, 40, 60, 82]

    def test_une_seule_vie_a_le_cran_de_ses_valeurs(self):
        assert self._niveau("realiste") == self._niveau("normal")
        assert self._niveau("impardonnable") == self._niveau("hardcore")

    def test_le_plus_dur_que_le_jeu_permet_vaut_100(self):
        dur = {k: v[-1] for k, v in _DURCIT.items() if k in HP6_PRESETS}
        assert dp.niveau(dur, "hp6", HP6_PRESETS) == 100
        assert dp.niveau({**dur, "invincible": True}, "hp6", HP6_PRESETS) == dp.NIVEAUX["recit"]

    def test_un_jeu_sans_reglage_est_normal(self):
        assert dp.niveau({}, "hp4", frozenset()) == dp.NIVEAUX["normal"]

    def test_durcir_un_reglage_ne_fait_jamais_baisser_le_niveau(self):
        """Réglage par réglage, de chaque combinaison possible vers le cran plus dur suivant."""
        for idents, jeu in ((HP6_PRESETS - {"invincible"}, "hp6"), (HP2, "hp2")):
            axes = {k: v for k, v in _DURCIT.items() if k in idents}
            for combinaison in itertools.product(*axes.values()):
                valeurs = dict(zip(axes, combinaison, strict=True))
                avant = dp.niveau(valeurs, jeu, idents)
                assert 0 <= avant <= 100
                for ident, crans in axes.items():
                    rang = crans.index(valeurs[ident])
                    if rang + 1 < len(crans):
                        assert dp.niveau({**valeurs, ident: crans[rang + 1]}, jeu, idents) >= avant, \
                            (ident, valeurs)

    def test_chaque_reglage_compte_depuis_normal(self):
        normal = dp.valeurs_pour(dp.PAR_IDENT["normal"], HP6_PRESETS)
        for ident in HP6_PRESETS - {"invincible"}:
            niveaux = [dp.niveau({**normal, ident: v}, "hp6", HP6_PRESETS) for v in _DURCIT[ident]]
            assert niveaux == sorted(niveaux) and len(set(niveaux)) == len(niveaux), (ident, niveaux)

    def test_le_sur_mesure_se_situe_sans_chiffre(self):
        crans = dp.reperes("hp6", HP6_PRESETS)
        assert dp.situer(50, crans) == "Entre Normal et Difficile"
        assert dp.situer(91, crans) == "Au-delà de Hardcore"
        assert dp.situer(40, crans) == "Au niveau de Normal"
        assert dp.situer(1, crans) == "En deçà de Récit"
        assert dp.situer(50, ()) == ""


pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402


@pytest.fixture
def dossier_hp6(tmp_path):
    (tmp_path / "HP6").mkdir()
    (tmp_path / "HP6" / "d3d9.ini").write_bytes(INI.encode("ascii"))
    return SimpleNamespace(config=SimpleNamespace(install_path=tmp_path, reprise={}),
                           game_language=lambda g: None, langues_disponibles=lambda g: ())


class TestOnglet:
    """L'onglet Difficulté des réglages du jeu (Ludo, 2026-10-31 : « un seul onglet
    Difficulté avec tout dedans et pas une autre page »)."""

    def _onglet(self, qtbot, manager, **champs):
        from src.ui.game_settings_dialog import GameSettingsDialog
        dlg = GameSettingsDialog(_jeu(**champs), manager, lambda c: True)
        qtbot.addWidget(dlg)
        dlg.ouvrir_onglet("difficulte")
        return dlg, dlg._panneau

    @staticmethod
    def _carte(panneau, ident):
        return next(c for c in [*panneau.cartes_presets, *panneau.tuiles] if c.ident == ident)

    def test_cartes_reglages_et_une_seule_vie_dans_le_meme_onglet(self, qtbot, dossier_hp6):
        dlg, panneau = self._onglet(qtbot, dossier_hp6, fix_settings=list(HP6))
        assert [c.ident for c in panneau.cartes_presets] == ["recit", "detendu", "normal", "difficile", "hardcore"]
        assert [t.ident for t in panneau.tuiles] == ["realiste", "impardonnable"]
        for tuile in panneau.tuiles:
            assert tuile.property("bientot") == "true" and tuile.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert self._carte(panneau, "normal").property("actif") == "true", "un ini neuf : Normal"
        assert panneau.cadran.nom == "Normal" and panneau.cadran.valeur() == 40
        assert set(HP6) <= set(dlg._controles), "chaque réglage, sorts retirés compris, est dans l'onglet"

    def test_le_jeu_ne_porte_plus_la_difficulte(self, qtbot, dossier_hp6):
        """Plus de difficulté dans l'onglet Jeu : elle y passait avant « Démarrage »
        et le Quidditch après, sans ordre (Ludo, 2026-10-31)."""
        assert all(REGLAGES[i].onglet == "difficulte" for i in (*HP6, "quidditch"))

    def test_un_clic_sur_une_carte_remet_chaque_reglage(self, qtbot, dossier_hp6):
        dlg, panneau = self._onglet(qtbot, dossier_hp6, fix_settings=list(HP6))
        dlg.show()
        qtbot.mouseClick(self._carte(panneau, "hardcore"), Qt.MouseButton.LeftButton)
        ini = dossier_hp6.config.install_path / "HP6" / "d3d9.ini"
        assert "DamageTaken=3" in ini.read_bytes().decode().split("\r\n")
        assert dlg._controles["degats_recus"].currentData() == 3, "la liste suit le preset"
        assert [c.ident for c in panneau.cartes_presets if c.property("actif") == "true"] == ["hardcore"]
        assert self._carte(panneau, "hardcore").sceau.isVisibleTo(panneau)
        assert panneau.cadran.nom == "Hardcore" and panneau.cadran.actif == "hardcore"
        qtbot.waitUntil(lambda: panneau.cadran.valeur() == 82, timeout=3000)

    def test_un_reglage_change_allume_sur_mesure(self, qtbot, dossier_hp6):
        dlg, panneau = self._onglet(qtbot, dossier_hp6, fix_settings=list(HP6))
        liste = dlg._controles["degats_recus"]
        liste.setCurrentIndex(liste.findData(2))
        assert panneau.sceau_sur_mesure.isVisibleTo(panneau)
        assert not any(c.property("actif") == "true" for c in panneau.cartes_presets)
        assert (panneau.cadran.nom, panneau.cadran.sous) == ("Sur mesure", "Entre Normal et Difficile")

    def test_au_clavier_fleche_et_espace(self, qtbot, dossier_hp6):
        """Règle 119 : un bloc qui a l'air d'un bouton se choisit aussi au clavier."""
        _dlg, panneau = self._onglet(qtbot, dossier_hp6, fix_settings=list(HP6))
        qtbot.keyClick(self._carte(panneau, "normal"), Qt.Key.Key_Right)
        assert panneau.courant() == "difficile"
        qtbot.keyClick(self._carte(panneau, "difficile"), Qt.Key.Key_Home)
        assert panneau.courant() == "recit"
        qtbot.keyClick(self._carte(panneau, "hardcore"), Qt.Key.Key_Space)
        assert panneau.courant() == "hardcore"

    def test_un_nom_grave_sur_le_cadran_se_clique(self, qtbot, dossier_hp6):
        dlg, panneau = self._onglet(qtbot, dossier_hp6, fix_settings=list(HP6))
        dlg.resize(1400, 900)
        dlg.show()
        panneau.cadran.grab()          # les zones des noms se posent à la peinture
        zone = panneau.cadran._zones["detendu"]
        k, dx, dy = panneau.cadran._echelle()
        qtbot.mouseClick(panneau.cadran, Qt.MouseButton.LeftButton,
                         pos=QPoint(round(zone.center().x() * k + dx), round(zone.center().y() * k + dy)))
        assert panneau.courant() == "detendu"

    def test_un_jeu_sans_reglage_n_a_pas_l_onglet(self, qtbot, dossier_hp6):
        dlg, panneau = self._onglet(qtbot, dossier_hp6, fix_settings=["limite_fps"])
        assert panneau is None and "difficulte" not in dlg._onglets


class TestBoutonDeLaFiche:
    def _bouton(self, win, jeu):
        from src.ui.icon_button import IconButton
        game = next(e.game for e in win.manager.get_games() if e.game.id == jeu)
        win._detail.set_game(game)
        return win._detail._action_panel.findChild(IconButton, "boutonDifficulte")

    def test_hp2_ouvre_l_onglet_et_hp3_attend(self, make_window, monkeypatch):
        from src.core.game_manager import GameManager, GameState
        from src.ui.game_settings_dialog import GameSettingsDialog
        monkeypatch.setattr(GameManager, "is_installed", lambda self, j: j in {"hp2", "hp3"})
        monkeypatch.setattr(GameManager, "get_state", lambda self, j: GameState.INSTALLED
                            if j in {"hp2", "hp3"} else GameState.NOT_INSTALLED)
        win = make_window()
        assert not self._bouton(win, "hp3").isEnabled(), "rien à régler dans HP3 : bientôt"
        bouton = self._bouton(win, "hp2")
        assert bouton.isEnabled()
        bouton.click()
        page = win._pages.page
        assert isinstance(page, GameSettingsDialog)
        assert page._onglets["difficulte"].isChecked(), "ouverte sur l'onglet Difficulté"
        page.accept()


def test_le_pied_dit_quand_hp6_le_prend(qtbot, dossier_hp6):
    """Sur l'onglet Difficulté de HP6, la partie en cours le prend : le pied ne dit
    plus « au prochain lancement » (2026-10-31)."""
    from src.ui.game_settings_dialog import GameSettingsDialog
    dlg = GameSettingsDialog(_jeu(fix_settings=list(HP6)), dossier_hp6, lambda c: True)
    qtbot.addWidget(dlg)
    dlg.ouvrir_onglet("difficulte")
    assert dlg._pied_notes.text().startswith("Change à tout moment")
    dlg.ouvrir_onglet("jeu")
    assert not dlg._pied_notes.text().startswith("Change à tout moment")

"""L'éditeur de touches de HP4 : `[Accio.Keys]` du correctif, action par action."""

import sys

import pytest

from src.core import reglages_correctif as rc
from src.core import touches_correctif as tc
from src.core.i18n import tr

from tests.test_reglages_correctif import INI_V2, _dialogue, _jeu, _manager


@pytest.fixture
def qwerty(monkeypatch):
    """Positions US, comme sous Linux : le résultat ne dépend pas du clavier du poste."""
    monkeypatch.setattr(sys, "platform", "linux")


@pytest.fixture
def ini(tmp_path):
    p = tmp_path / "d3d9.ini"
    p.write_bytes(INI_V2.encode("ascii"))
    return p


def _lignes(ini):
    return ini.read_bytes().decode().split("\r\n")


class TestNoms:
    def test_les_noms_que_le_correctif_lit(self):
        for nom in ("Space", "LShift", "RCtrl", "Up", "F12", "Num5", "NumEnter", "MouseLeft", "Mouse5", "Z", "&", "1"):
            assert tc.nom_valide(nom), nom

    def test_les_separateurs_et_le_reste_refuses(self):
        # « , » et « ; » séparent les touches d'une ligne ; un caractère accentué
        # ne passe pas la page de codes que lit le correctif.
        for nom in (",", ";", " ", "é", "ù", "", "Souris", "F13", "ZZ"):
            assert not tc.nom_valide(nom), nom

    def test_casse_et_alias_ramenes_au_nom_du_correctif(self):
        assert tc._canonique("space") == "Space"
        assert tc._canonique("return") == "Enter"
        assert tc._canonique("z") == "Z"

    def test_ce_qu_on_montre(self):
        assert tc.texte_touche("MouseLeft") == tr("Clic gauche")
        assert tc.texte_touche("Up") == tr("Flèche haut")
        assert tc.texte_touche("Num7") == tr("Pavé {}").format("7")
        assert tc.texte_touche("F5") == "F5"
        assert tc.texte_touche("q") == "Q"

    def test_la_touche_d_origine_en_qwerty(self, qwerty):
        assert tc.touche_d_origine(tc.PAR_CLE["Accio"]) == "Z"
        assert tc.touche_d_origine(tc.PAR_CLE["Extremos"]) == "S"
        assert tc.touche_d_origine(tc.PAR_CLE["MoveUp"]) == tr("Flèche haut")
        assert tc.touche_d_origine(tc.PAR_CLE["Pause"]) == tr("Échap")

    def test_les_onze_actions_du_correctif(self):
        """Les noms de kActionsHp4 (keys.cpp) : un nom faux serait « unknown action »."""
        assert [a.cle for a in tc.ACTIONS] == [
            "MoveUp", "MoveDown", "MoveLeft", "MoveRight", "Charm", "Jinx", "Accio", "Extremos",
            "Pause", "Confirm", "Back"]


class TestEcriture:
    def test_aucune_touche_choisie_au_depart(self, ini):
        assert all(not v for v in tc.touches(ini).values())

    def test_attribuer_decommente_la_ligne_en_place(self, ini):
        avant = len(_lignes(ini))
        assert tc.attribuer(ini, "MoveUp", "I") == ()
        lignes = _lignes(ini)
        assert "MoveUp=I" in lignes and ";MoveUp=Z" not in lignes
        assert len(lignes) == avant
        assert tc.touches(ini)["MoveUp"] == ("I",)

    def test_une_action_sans_ligne_prend_sa_place_dans_la_section(self, ini):
        tc.attribuer(ini, "Pause", "P")
        lignes = _lignes(ini)
        assert lignes.index("[Accio.Keys]") < lignes.index("Pause=P") < lignes.index("[Accio.Graphics]")

    def test_une_touche_n_a_qu_une_action(self, ini):
        tc.attribuer(ini, "Accio", "E")
        assert tc.attribuer(ini, "Charm", "e") == ("Accio",)
        choisies = tc.touches(ini)
        assert choisies["Charm"] == ("E",) and choisies["Accio"] == ()

    def test_retirer_une_touche_d_une_liste_garde_les_autres(self, ini):
        ini.write_bytes(ini.read_bytes().replace(b";Charm=MouseLeft", b"Charm=MouseLeft,J"))
        tc.attribuer(ini, "Jinx", "J")
        assert tc.touches(ini)["Charm"] == ("MouseLeft",)

    def test_rendre_la_touche_du_jeu(self, ini):
        tc.attribuer(ini, "MoveUp", "I")
        tc.attribuer(ini, "Pause", "P")
        tc.rendre(ini, ("MoveUp",))
        assert tc.touches(ini)["MoveUp"] == () and tc.touches(ini)["Pause"] == ("P",)
        tc.rendre(ini)
        assert all(not v for v in tc.touches(ini).values())

    def test_nom_refuse_rien_n_est_ecrit(self, ini):
        avant = ini.read_bytes()
        with pytest.raises(ValueError):
            tc.attribuer(ini, "MoveUp", ",")
        with pytest.raises(ValueError):
            tc.attribuer(ini, "Inconnue", "Z")
        assert ini.read_bytes() == avant

    def test_la_premiere_retouche_garde_l_origine(self, ini):
        tc.attribuer(ini, "Back", "B")
        assert rc.a_une_origine(ini)
        assert b"Back=B" not in rc.chemin_origine(ini).read_bytes()

    def test_retablir_l_origine_couvre_toutes_les_actions(self, ini):
        """« Rétablir les réglages d'origine » passe par le préréglage ZQSD : il doit
        emporter aussi Pause, Valider et Retour, que seul l'éditeur règle."""
        tc.attribuer(ini, "Confirm", "Space")
        tc.attribuer(ini, "MoveUp", "I")
        rc.remettre_origine(ini, [rc.REGLAGES["touches_zqsd"]])
        assert all(not v for v in tc.touches(ini).values())


class TestSansTouche:
    def test_s_sur_reculer_retire_extremos(self, qwerty):
        """Le cas du préréglage : sans R pour Extremos, S lui est retirée (g_consumed)."""
        perdues = tc.sans_touche({**{a.cle: () for a in tc.ACTIONS}, "MoveDown": ("S",)})
        assert perdues == {"Extremos": "MoveDown"}

    def test_une_autre_touche_pour_extremos_le_sauve(self, qwerty):
        choisies = {**{a.cle: () for a in tc.ACTIONS}, "MoveDown": ("S",), "Extremos": ("R",)}
        assert tc.sans_touche(choisies) == {}

    def test_sa_propre_touche_ne_retire_rien(self, qwerty):
        assert tc.sans_touche({**{a.cle: () for a in tc.ACTIONS}, "Extremos": ("S",)}) == {}

    def test_la_souris_ne_prend_aucune_touche(self, qwerty):
        assert tc.sans_touche({**{a.cle: () for a in tc.ACTIONS}, "Charm": ("MouseLeft",)}) == {}

    def test_une_fleche_retire_le_deplacement(self, qwerty):
        choisies = {**{a.cle: () for a in tc.ACTIONS}, "Accio": ("Up",)}
        assert tc.sans_touche(choisies) == {"MoveUp": "Accio"}


def test_le_module_ne_depend_pas_de_qt():
    from pathlib import Path
    assert "PyQt6" not in Path(tc.__file__).read_text(encoding="utf-8")


# ── L'appui, tel que Qt le donne ──

class TestAppui:
    def test_lettres_et_touches_nommees(self):
        from PyQt6.QtCore import Qt
        from src.ui.editeur_touches import nom_de_touche
        assert nom_de_touche(Qt.Key.Key_Z, "z", 0x2C, False) == "Z"
        assert nom_de_touche(Qt.Key.Key_Space, " ", 0x39, False) == "Space"
        assert nom_de_touche(Qt.Key.Key_F3, "", 0x3D, False) == "F3"
        assert nom_de_touche(Qt.Key.Key_Return, "\r", 0x1C, False) == "Enter"

    def test_gauche_et_droite_par_le_code_de_balayage(self):
        from PyQt6.QtCore import Qt
        from src.ui.editeur_touches import nom_de_touche
        assert nom_de_touche(Qt.Key.Key_Shift, "", 0x2A, False) == "LShift"
        assert nom_de_touche(Qt.Key.Key_Shift, "", 0x36, False) == "RShift"
        assert nom_de_touche(Qt.Key.Key_Control, "", 0x11D, False) == "RCtrl"
        assert nom_de_touche(Qt.Key.Key_Control, "", 37, False) == "LCtrl"    # X11
        assert nom_de_touche(Qt.Key.Key_Control, "", 105, False) == "RCtrl"   # X11

    def test_pave_numerique(self):
        from PyQt6.QtCore import Qt
        from src.ui.editeur_touches import nom_de_touche
        assert nom_de_touche(Qt.Key.Key_7, "7", 0x47, True) == "Num7"
        assert nom_de_touche(Qt.Key.Key_Up, "", 0x48, True) == "Num8"   # verrouillage éteint
        assert nom_de_touche(Qt.Key.Key_Up, "", 0xC8, False) == "Up"
        assert nom_de_touche(Qt.Key.Key_Enter, "\r", 0x11C, True) == "NumEnter"

    def test_ce_que_le_correctif_ne_lirait_pas(self):
        from PyQt6.QtCore import Qt
        from src.ui.editeur_touches import nom_de_touche
        assert nom_de_touche(Qt.Key.Key_Eacute, "é", 0x03, False) is None
        assert nom_de_touche(Qt.Key.Key_Comma, ",", 0x33, False) is None
        assert nom_de_touche(Qt.Key.Key_A, "\x01", 0x1E, False) is None   # Ctrl+A


# ── Dans la fenêtre de réglages ──

def _fenetre(qtbot, tmp_path, idents=("touches_zqsd",)):
    (tmp_path / "HP4").mkdir()
    ini = tmp_path / "HP4" / "d3d9.ini"
    ini.write_bytes(INI_V2.encode("ascii"))
    dlg = _dialogue(qtbot, _jeu(tmp_path, list(idents)), _manager(tmp_path))
    return dlg, ini


class TestFenetre:
    def test_l_editeur_est_dans_l_onglet_commandes(self, qtbot, tmp_path):
        from src.ui.editeur_touches import EditeurTouches
        dlg, _ = _fenetre(qtbot, tmp_path, ("touches_zqsd", "surechantillonnage"))
        image, commandes = dlg._contenus[:2]
        assert commandes.findChildren(EditeurTouches) and not image.findChildren(EditeurTouches)

    def test_pas_d_editeur_sans_le_preregle(self, qtbot, tmp_path):
        """Les actions sont celles de HP4 : un jeu qui ne déclare pas ses touches n'en a pas."""
        dlg, _ = _fenetre(qtbot, tmp_path, ("arriere_plan",))
        assert dlg._editeur is None

    def test_une_touche_au_clavier_s_ecrit_aussitot(self, qtbot, tmp_path):
        from PyQt6.QtCore import Qt
        dlg, ini = _fenetre(qtbot, tmp_path)
        bouton = dlg._editeur._boutons["Accio"]
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        assert bouton.ecoute() and bouton.text() == tr("Appuyez sur une touche…")
        qtbot.keyClick(bouton, Qt.Key.Key_F)
        assert not bouton.ecoute()
        assert "Accio=F" in _lignes(ini)
        assert bouton.text() == "F"

    def test_un_bouton_de_souris(self, qtbot, tmp_path):
        from PyQt6.QtCore import Qt
        dlg, ini = _fenetre(qtbot, tmp_path)
        bouton = dlg._editeur._boutons["Jinx"]
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(bouton, Qt.MouseButton.RightButton)
        assert "Jinx=MouseRight" in _lignes(ini)
        assert bouton.text() == tr("Clic droit")

    def test_un_clic_ailleurs_annule(self, qtbot, tmp_path):
        """Pendant la capture, la souris est saisie : un clic HORS de la case arrive
        quand même au bouton, et ne doit rien donner à l'action."""
        from PyQt6.QtCore import QPoint, Qt
        dlg, ini = _fenetre(qtbot, tmp_path)
        avant = ini.read_bytes()
        bouton = dlg._editeur._boutons["Accio"]
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton, pos=QPoint(-20, -20))
        assert not bouton.ecoute() and ini.read_bytes() == avant

    def test_echap_annule_sans_rien_ecrire(self, qtbot, tmp_path):
        from PyQt6.QtCore import Qt
        dlg, ini = _fenetre(qtbot, tmp_path)
        avant = ini.read_bytes()
        bouton = dlg._editeur._boutons["Pause"]
        fermee = []
        dlg.rejected.connect(lambda: fermee.append(True))
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        qtbot.keyClick(bouton, Qt.Key.Key_Escape)
        assert not bouton.ecoute() and ini.read_bytes() == avant
        assert not fermee   # Échap a annulé la capture, pas fermé la fenêtre
        assert bouton.text() == tc.touche_d_origine(tc.PAR_CLE["Pause"])

    def test_la_perte_d_extremos_est_dite(self, qtbot, tmp_path, qwerty):
        from PyQt6.QtCore import Qt
        dlg, _ = _fenetre(qtbot, tmp_path)
        bouton = dlg._editeur._boutons["MoveDown"]
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        qtbot.keyClick(bouton, Qt.Key.Key_S)
        avis = dlg._editeur._avis
        assert not avis.isHidden()
        assert tr("{} n'a plus de touche : {} sert maintenant à {}.").format(
            "Extremos", "S", tr("Reculer")) in avis.text()
        assert dlg._editeur._boutons["Extremos"].text() == tr("Aucune")

    def test_le_preregle_se_verrouille_puis_se_libere(self, qtbot, tmp_path):
        from PyQt6.QtCore import Qt
        dlg, _ = _fenetre(qtbot, tmp_path)
        bascule = dlg._controles["touches_zqsd"]
        assert bascule.isEnabled() and dlg._note_preregle.isHidden()
        # Retour n'est pas au préréglage : il n'en empêche rien.
        bouton = dlg._editeur._boutons["Back"]
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        qtbot.keyClick(bouton, Qt.Key.Key_B)
        assert bascule.isEnabled()
        # Avancer, si : le préréglage l'écraserait.
        bouton = dlg._editeur._boutons["MoveUp"]
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        qtbot.keyClick(bouton, Qt.Key.Key_I)
        assert not bascule.isEnabled() and not dlg._note_preregle.isHidden()
        dlg._editeur._tout.click()
        assert bascule.isEnabled() and dlg._note_preregle.isHidden()

    def test_le_preregle_se_voit_dans_l_editeur(self, qtbot, tmp_path, monkeypatch):
        monkeypatch.setattr(rc, "touches_preregle", lambda: (
            ("MoveUp", "W"), ("MoveLeft", "A"), ("MoveDown", "S"), ("MoveRight", "D"),
            ("Accio", "E"), ("Extremos", "R"), ("Charm", "MouseLeft"), ("Jinx", "MouseRight")))
        dlg, _ = _fenetre(qtbot, tmp_path)
        dlg._controles["touches_zqsd"]._basculer()
        assert dlg._editeur._boutons["MoveUp"].text() == "W"
        assert dlg._editeur._boutons["Charm"].text() == tr("Clic gauche")
        # Le préréglage donne R à Extremos : personne n'est laissé sans touche.
        assert dlg._editeur._avis.isHidden()

    def test_echec_d_ecriture_dit_et_ne_change_rien(self, qtbot, tmp_path, monkeypatch):
        from PyQt6.QtCore import Qt
        dlg, _ = _fenetre(qtbot, tmp_path)

        def refus(*_a):
            raise PermissionError("lecture seule")
        monkeypatch.setattr(rc, "_ecrire", refus)
        bouton = dlg._editeur._boutons["Accio"]
        qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
        qtbot.keyClick(bouton, Qt.Key.Key_F)
        assert not dlg._erreur.isHidden()
        assert bouton.text() == tc.touche_d_origine(tc.PAR_CLE["Accio"])

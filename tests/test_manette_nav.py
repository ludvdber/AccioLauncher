"""Naviguer dans le launcher à la manette.

Aucun test ne lit une vraie manette (conftest._jamais_la_vraie_manette rend un
lecteur muet) : la logique se teste sur des relevés fabriqués, dont ceux de la
DS4 de Ludo (054C:09CC, 2026-10-03), et l'interface sur de vrais widgets avec
un faux lecteur.
"""
import struct

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.core import manette_lecture as lec
from src.core.manette_lecture import Etat, Repetition
from tests.test_integration_smoke import make_window  # noqa: F401  (fixture)


class TestPov:
    @pytest.mark.parametrize("pov, attendu", [
        (0, lec.HAUT), (9000, lec.DROITE), (18000, lec.BAS), (27000, lec.GAUCHE),
        (4500, lec.DROITE), (13500, lec.BAS), (31500, lec.HAUT), (3000, lec.HAUT),
    ])
    def test_une_seule_direction(self, pov, attendu):
        assert lec.directions_du_pov(pov) == {attendu}

    def test_centre(self):
        assert lec.directions_du_pov(0xFFFF) == frozenset()


def _caps():
    caps = lec._JOYCAPSW()
    caps.wXmax = caps.wYmax = caps.wRmax = 65535
    return caps


def _info(boutons=0, pov=0xFFFF, x=32767, y=32767, r=32767):
    info = lec._JOYINFOEX()
    info.dwButtons, info.dwPOV, info.dwXpos, info.dwYpos, info.dwRpos = boutons, pov, x, y, r
    return info


class TestWinmm:
    def test_ds4_croix_valide_rond_revient(self):
        """Numéros VUS sur la DS4 de Ludo : croix = bouton 2 (bit 1), rond = 3 (bit 2)."""
        assert lec.etat_winmm(_info(1 << 1), _caps(), lec.PLAYSTATION).appuis == {lec.VALIDER}
        assert lec.etat_winmm(_info(1 << 2), _caps(), lec.PLAYSTATION).appuis == {lec.RETOUR}
        # Carré (bouton 1) ne fait rien sur une PlayStation…
        assert lec.etat_winmm(_info(1 << 0), _caps(), lec.PLAYSTATION).appuis == frozenset()

    def test_xbox_a_valide_b_revient(self):
        assert lec.etat_winmm(_info(1 << 0), _caps(), lec.XBOX).appuis == {lec.VALIDER}
        assert lec.etat_winmm(_info(1 << 1), _caps(), lec.XBOX).appuis == {lec.RETOUR}

    def test_l1_r1_et_croix_directionnelle(self):
        e = lec.etat_winmm(_info((1 << 4) | (1 << 5), pov=27000), _caps(), lec.PLAYSTATION)
        assert e.appuis == {lec.PRECEDENT, lec.SUIVANT, lec.GAUCHE}

    def test_axes_normalises(self):
        """Repos de la DS4 de Ludo : R 31 743 → à peine -3 %, sous la zone morte."""
        e = lec.etat_winmm(_info(x=0, y=65535, r=31743), _caps(), lec.PLAYSTATION)
        assert e.stick_x == -1.0 and e.stick_y == 1.0
        assert lec.defilement_utile(e.defilement) == 0.0

    def test_axe_sans_course_ne_divise_pas_par_zero(self):
        assert lec.etat_winmm(_info(), lec._JOYCAPSW(), lec.XBOX).stick_x == 0.0


class TestStick:
    def test_seuil_et_hysteresis(self):
        assert lec.directions_du_stick(0.5, 0, frozenset()) == frozenset()
        assert lec.directions_du_stick(0.7, 0, frozenset()) == {lec.DROITE}
        # Allumée, elle tient jusqu'à 40 % : un stick près du seuil ne clignote pas.
        assert lec.directions_du_stick(0.5, 0, frozenset({lec.DROITE})) == {lec.DROITE}
        assert lec.directions_du_stick(0.3, 0, frozenset({lec.DROITE})) == frozenset()

    def test_diagonale_l_axe_le_plus_pousse(self):
        assert lec.directions_du_stick(-0.7, 0.9, frozenset()) == {lec.BAS}
        assert lec.directions_du_stick(-0.9, -0.7, frozenset()) == {lec.GAUCHE}

    def test_defilement(self):
        assert lec.defilement_utile(0.2) == 0.0
        assert lec.defilement_utile(1.0) == 1.0
        assert lec.defilement_utile(-1.0) == -1.0


class TestRepetition:
    def test_un_appui_une_action(self):
        r = Repetition()
        assert r.actions(Etat(frozenset({lec.VALIDER})), 0.0) == [lec.VALIDER]
        assert r.actions(Etat(frozenset({lec.VALIDER})), 5.0) == []     # tenu : pas de répétition
        assert r.actions(Etat(), 5.1) == []                              # rien au relâchement
        assert r.actions(Etat(frozenset({lec.VALIDER})), 5.2) == [lec.VALIDER]

    def test_une_direction_tenue_repete_comme_une_touche(self):
        r = Repetition()
        tenu = Etat(frozenset({lec.DROITE}))
        assert r.actions(tenu, 0.0) == [lec.DROITE]
        assert r.actions(tenu, 0.39) == []
        assert r.actions(tenu, 0.40) == [lec.DROITE]
        assert r.actions(tenu, 0.50) == []
        assert r.actions(tenu, 0.51) == [lec.DROITE]

    def test_le_stick_repete_aussi(self):
        r = Repetition()
        assert r.actions(Etat(stick_y=1.0), 0.0) == [lec.BAS]
        assert r.actions(Etat(stick_y=1.0), 0.4) == [lec.BAS]

    def test_reprendre_rend_muet_ce_qui_est_deja_tenu(self):
        """Retour d'un jeu, croix encore enfoncée : elle n'agit pas dans le launcher."""
        r = Repetition()
        r.reprendre(Etat(frozenset({lec.VALIDER, lec.DROITE})))
        assert r.actions(Etat(frozenset({lec.VALIDER, lec.DROITE})), 0.0) == []
        assert r.actions(Etat(frozenset({lec.VALIDER, lec.DROITE})), 9.0) == []
        assert r.actions(Etat(frozenset({lec.VALIDER, lec.RETOUR})), 9.1) == [lec.RETOUR]
        assert r.actions(Etat(), 9.2) == []
        assert r.actions(Etat(frozenset({lec.VALIDER})), 9.3) == [lec.VALIDER]


def test_deux_manettes_naviguent_ensemble():
    e = lec.fusionner([Etat(frozenset({lec.VALIDER}), stick_x=0.2),
                       Etat(frozenset({lec.RETOUR}), stick_x=-0.9)])
    assert e.appuis == {lec.VALIDER, lec.RETOUR} and e.stick_x == -0.9
    assert lec.fusionner([]) == Etat()


def _evenement(type_, numero, valeur):
    return struct.pack("<IhBB", 0, valeur, type_, numero)


class TestLinux:
    AXES = {0: lec.ABS_X, 1: lec.ABS_Y, 4: lec.ABS_RY, 6: lec.ABS_HAT0X, 7: lec.ABS_HAT0Y}

    def test_evenements(self):
        m = lec.ManetteJs(axes=self.AXES)
        m.appliquer(_evenement(lec.JS_EVENT_BUTTON | lec.JS_EVENT_INIT, 0, 0)
                    + _evenement(lec.JS_EVENT_BUTTON, 0, 1)
                    + _evenement(lec.JS_EVENT_AXIS, 6, -32767)
                    + _evenement(lec.JS_EVENT_AXIS, 4, 32767)
                    + b"\x01\x02")                         # morceau d'événement : ignoré
        e = m.etat()
        assert e.appuis == {lec.VALIDER, lec.GAUCHE} and e.defilement == 1.0

    def test_axe_inconnu_ignore_et_diagonale_horizontale(self):
        m = lec.ManetteJs(axes=self.AXES)
        m.appliquer(_evenement(lec.JS_EVENT_AXIS, 9, 32767)
                    + _evenement(lec.JS_EVENT_AXIS, 6, 32767)
                    + _evenement(lec.JS_EVENT_AXIS, 7, 32767))
        assert m.etat().appuis == {lec.DROITE}

    def test_lecteur_sur_un_faux_dossier(self, tmp_path):
        """Un fichier ordinaire : `read` rend tout puis rien, et l'ioctl échoue → axes par défaut."""
        (tmp_path / "js0").write_bytes(_evenement(lec.JS_EVENT_BUTTON, 1, 1))
        (tmp_path / "event3").write_bytes(b"")             # pas un js : jamais ouvert
        lecteur = lec.LecteurLinux(tmp_path)
        try:
            assert lecteur.lire(0.0).appuis == {lec.RETOUR}
            assert lecteur.nombre() == 1
            lecteur._dossier = tmp_path / "debranchee"     # Windows verrouille un fichier ouvert
            assert lecteur.lire(5.0) == Etat() and lecteur.nombre() == 0
        finally:
            for fd, _ in lecteur._ouvertes.values():
                import os
                os.close(fd)

    def test_dossier_absent(self, tmp_path):
        assert lec.LecteurLinux(tmp_path / "rien").lire(0.0) == Etat()


def test_lecteur_muet():
    m = lec.LecteurMuet()
    m.prechauffer()
    assert m.lire(0.0) == Etat() and m.nombre() == 0


# ──────────────────── Interface ────────────────────

class _FauxLecteur:
    def __init__(self):
        self.etat = Etat()

    def prechauffer(self):
        pass

    def lire(self, _maintenant):
        return self.etat

    def nombre(self):
        return 1


@pytest.fixture
def nav(qtbot):
    from src.ui.manette_nav import NavigationManette
    temps = [0.0]
    n = NavigationManette(QApplication.instance(), _FauxLecteur(), horloge=lambda: temps[0])
    n.temps = temps
    yield n
    n.set_actif(False)
    n.deleteLater()


@pytest.fixture
def fenetre(qtbot):
    w = QWidget()
    lay = QVBoxLayout(w)
    boutons = [QPushButton(f"b{i}") for i in range(3)]
    for b in boutons:
        lay.addWidget(b)
    qtbot.addWidget(w)
    w.show()
    w.activateWindow()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is w)
    boutons[0].setFocus(Qt.FocusReason.OtherFocusReason)
    qtbot.waitUntil(boutons[0].hasFocus)
    return w, boutons


class TestNavigation:
    def test_bas_et_haut_deplacent_le_focus_avec_l_anneau(self, nav, fenetre):
        _w, b = fenetre
        nav.agir(lec.BAS)
        assert b[1].hasFocus()
        nav.agir(lec.HAUT)
        assert b[0].hasFocus()

    def test_valider_appuie_sur_le_bouton(self, nav, fenetre, qtbot):
        _w, b = fenetre
        with qtbot.waitSignal(b[0].clicked, timeout=1000):
            nav.agir(lec.VALIDER)

    def test_retour_ferme_le_dialogue(self, nav, qtbot):
        d = QDialog()
        qtbot.addWidget(d)
        d.show()
        d.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is d)
        with qtbot.waitSignal(d.rejected, timeout=1000):
            nav.agir(lec.RETOUR)

    def test_un_champ_texte_valide_par_entree_sans_ecrire_d_espace(self, nav, qtbot):
        w = QWidget()
        champ = QLineEdit(w)
        qtbot.addWidget(w)
        w.show()
        w.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is w)
        champ.setFocus()
        qtbot.waitUntil(champ.hasFocus)
        with qtbot.waitSignal(champ.returnPressed, timeout=1000):
            nav.agir(lec.VALIDER)
        assert champ.text() == ""

    def test_lecture_complete_et_retour_de_jeu(self, nav, fenetre, qtbot):
        """Premier relevé : on note ce qui est tenu, sans agir ; ensuite, l'appui agit."""
        _w, b = fenetre
        nav._lecteur.etat = Etat(frozenset({lec.BAS}))
        nav._lire()
        assert b[0].hasFocus()                 # tenu au retour : muet
        nav._lecteur.etat = Etat()
        nav.temps[0] = 1.0
        nav._lire()
        nav._lecteur.etat = Etat(frozenset({lec.BAS}))
        nav.temps[0] = 1.1
        nav._lire()
        assert b[1].hasFocus()

    def test_stick_droit_fait_defiler(self, nav, qtbot):
        zone = QScrollArea()
        contenu = QWidget()
        contenu.setMinimumHeight(3000)
        bouton = QPushButton("dans la zone", contenu)
        zone.setWidget(contenu)
        zone.resize(200, 200)
        qtbot.addWidget(zone)
        zone.show()
        bouton.setFocus()
        nav._reprendre = False
        nav._lecteur.etat = Etat(defilement=1.0)
        nav._lire()
        assert zone.verticalScrollBar().value() > 0

    def test_arret_quand_desactive(self, nav):
        nav.set_actif(True)
        nav.set_actif(False)
        assert not nav._timer.isActive() and not nav.actif

    def test_sans_cible_rien_ne_casse(self, nav, monkeypatch):
        from src.ui import manette_nav
        monkeypatch.setattr(manette_nav.NavigationManette, "_cible", staticmethod(lambda: None))
        nav.agir(lec.VALIDER)


def test_la_suite_ne_lit_jamais_la_vraie_manette():
    assert isinstance(lec.lecteur(), lec.LecteurMuet)


class TestDansLaVraieFenetre:
    """Ce que Ludo a vécu le 2026-10-07 avec sa DS4, rejoué sur la vraie fenêtre.

    La croix au démarrage RÉDUISAIT le launcher (le focus était sur « Réduire »
    de la barre de titre) ; une fois sur la barre de volume, plus rien n'en
    faisait sortir et chaque direction changeait le volume.
    """

    @pytest.fixture
    def fenetre_reelle(self, make_window, qtbot, nav):  # noqa: F811  (fixture importée)
        win = make_window()
        win.show()
        win.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is win, timeout=3000)
        return win

    def test_la_barre_de_titre_n_est_pas_dans_l_anneau(self, fenetre_reelle):
        from src.ui.title_bar import TitleBar
        boutons = fenetre_reelle.findChild(TitleBar).findChildren(QPushButton)
        assert boutons and all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in boutons)

    def test_la_croix_au_demarrage_lance_l_action_principale(self, fenetre_reelle, nav,
                                                            monkeypatch):
        appels = []
        monkeypatch.setattr(fenetre_reelle._detail, "trigger_primary_action",
                            lambda: appels.append(1))
        nav.agir(lec.VALIDER)
        assert appels == [1]
        assert fenetre_reelle.isVisible() and not fenetre_reelle.isMinimized()

    def test_aucun_appui_vers_le_bas_ne_tombe_sur_la_fenetre(self, fenetre_reelle, nav):
        from src.ui.title_bar import TitleBar
        barre = fenetre_reelle.findChild(TitleBar)
        for _ in range(30):
            nav.agir(lec.BAS)
            assert not barre.isAncestorOf(QApplication.focusWidget())

    def test_on_sort_d_un_curseur_horizontal_sans_changer_sa_valeur(self, nav, qtbot):
        from PyQt6.QtWidgets import QSlider
        w = QWidget()
        lay = QVBoxLayout(w)
        curseur = QSlider(Qt.Orientation.Horizontal)
        curseur.setValue(50)
        apres = QPushButton("après")
        lay.addWidget(curseur)
        lay.addWidget(apres)
        qtbot.addWidget(w)
        w.show()
        w.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is w)
        curseur.setFocus()
        qtbot.waitUntil(curseur.hasFocus)
        nav.agir(lec.BAS)
        assert apres.hasFocus() and curseur.value() == 50
        nav.agir(lec.HAUT)
        nav.agir(lec.DROITE)                     # ← → règlent toujours la valeur
        assert curseur.value() > 50

    def test_une_liste_fermee_ne_change_pas_en_passant(self, nav, qtbot):
        from PyQt6.QtWidgets import QComboBox
        w = QWidget()
        lay = QVBoxLayout(w)
        liste = QComboBox()
        liste.addItems(["8x", "4x", "aucun"])
        apres = QPushButton("après")
        lay.addWidget(liste)
        lay.addWidget(apres)
        qtbot.addWidget(w)
        w.show()
        w.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is w)
        liste.setFocus()
        qtbot.waitUntil(liste.hasFocus)
        nav.agir(lec.BAS)
        assert apres.hasFocus() and liste.currentIndex() == 0


class TestMiseEnEvidence:
    """Ludo, 2026-10-07, à la manette : « tout n'est pas mis en évidence clairement,
    surtout côté paramètres graphiques et dropdown ». Quatre causes, mesurées sur capture."""

    def test_le_focus_d_ouverture_s_allume_au_premier_appui(self, nav, fenetre):
        from src.ui.focus_visible import PROPRIETE
        _w, b = fenetre                       # focus posé SANS le clavier : pas d'anneau
        assert not b[0].property(PROPRIETE)
        nav.agir(lec.RETOUR)                  # un appui qui ne déplace pas le focus
        assert b[0].hasFocus() and b[0].property(PROPRIETE)

    def test_la_ligne_choisie_d_une_liste_obeit_au_style(self, qtbot):
        from PyQt6.QtWidgets import QStyledItemDelegate
        from src.ui.settings_panel import _COMBO_STYLE
        from src.ui.utils import liste_deroulante
        liste = liste_deroulante()
        qtbot.addWidget(liste)
        liste.setStyleSheet(_COMBO_STYLE)
        # Le délégué standard, qui lit la feuille de style. Celui d'une QComboBox
        # nue (QComboMenuDelegate) ignore ::item:selected : la ligne choisie
        # restait du même bleu que les autres.
        assert isinstance(liste.view().itemDelegate(), QStyledItemDelegate)
        assert "::item:selected" in _COMBO_STYLE
        assert '[focusClavier="true"]:focus' in _COMBO_STYLE

    def test_l_anneau_de_l_interrupteur_est_hors_de_la_piste(self, qtbot):
        from src.ui.toggle_switch import ToggleSwitch
        t = ToggleSwitch(True)
        qtbot.addWidget(t)
        # Or sur or quand il était dans la piste : il faut de la place autour.
        assert t.width() >= t._TRACK_W + 6 and t.height() >= t._TRACK_H + 6

    def test_une_zone_defilante_n_est_pas_un_arret(self, qtbot):
        from src.ui.utils import zone_defilable
        zone = zone_defilable(QWidget())
        qtbot.addWidget(zone)
        assert zone.focusPolicy() == Qt.FocusPolicy.NoFocus

"""Interrupteur ON/OFF : il doit s'atteindre AUSSI au clavier.

`ToggleSwitch` était un `QWidget` nu, `NoFocus`, ne répondant qu'à
`mousePressEvent` : **sept réglages ne s'atteignaient qu'à la souris** (audit du
2026-08-28) — lecture automatique des vidéos, son, présence Discord et
suppression des archives dans les Paramètres, plus trois dans l'assistant de
premier lancement, dont l'acceptation des bandes-annonces.

C'est une impasse, et elle contredisait un investissement explicite du projet :
`focus_visible.py` existe pour que l'anneau doré soit réservé au clavier, et
CLAUDE.md interdit de retirer la règle `outline` parce que « c'est le seul
repère d'un utilisateur au clavier ». Encore faut-il pouvoir y arriver.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402

from src.ui.toggle_switch import ToggleSwitch  # noqa: E402


class TestToggleSwitch:
    def test_initial_state_off(self, qtbot):
        t = ToggleSwitch(checked=False)
        qtbot.addWidget(t)
        assert t.isChecked() is False

    def test_initial_state_on(self, qtbot):
        t = ToggleSwitch(checked=True)
        qtbot.addWidget(t)
        assert t.isChecked() is True

    def test_set_checked_changes_state(self, qtbot):
        t = ToggleSwitch(checked=False)
        qtbot.addWidget(t)
        t.setChecked(True)
        assert t.isChecked() is True

    def test_set_checked_no_op(self, qtbot):
        t = ToggleSwitch(checked=True)
        qtbot.addWidget(t)
        t.setChecked(True)  # déjà True
        assert t.isChecked() is True


def _touche(widget, cle) -> None:
    widget.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, cle, Qt.KeyboardModifier.NoModifier))


class TestAtteignableAuClavier:
    def test_l_interrupteur_prend_le_focus(self, qtbot):
        sw = ToggleSwitch(False)
        qtbot.addWidget(sw)
        assert sw.focusPolicy() != Qt.FocusPolicy.NoFocus, (
            "réglage inatteignable au clavier")

    def test_espace_bascule(self, qtbot):
        sw = ToggleSwitch(False)
        qtbot.addWidget(sw)
        with qtbot.waitSignal(sw.toggled, timeout=1000) as bloc:
            _touche(sw, Qt.Key.Key_Space)
        assert sw.isChecked() is True
        assert bloc.args == [True]

    def test_entree_bascule_aussi(self, qtbot):
        """Convention d'une case (Espace) ET d'un bouton (Entrée) : l'objet
        ressemble assez aux deux pour qu'on essaie l'une ou l'autre."""
        sw = ToggleSwitch(True)
        qtbot.addWidget(sw)
        _touche(sw, Qt.Key.Key_Return)
        assert sw.isChecked() is False

    def test_une_autre_touche_ne_bascule_pas(self, qtbot):
        sw = ToggleSwitch(False)
        qtbot.addWidget(sw)
        _touche(sw, Qt.Key.Key_A)
        assert sw.isChecked() is False

    def test_deux_bascules_reviennent_au_depart(self, qtbot):
        sw = ToggleSwitch(False)
        qtbot.addWidget(sw)
        _touche(sw, Qt.Key.Key_Space)
        _touche(sw, Qt.Key.Key_Space)
        assert sw.isChecked() is False


class TestReperesVisuelsEtAccessibles:
    def test_l_anneau_de_focus_entoure_la_piste_au_clavier(self, qtbot):
        """Un widget PEINT doit se voir au clavier : l'anneau unique de `focus_visible` entoure
        la piste (pas la marge transparente autour), à 3 px de son bord."""
        from PyQt6.QtCore import QPoint, QRect, QSize
        from PyQt6.QtWidgets import QVBoxLayout, QWidget
        from src.ui.focus_visible import _Anneau, _marque

        fenetre = QWidget()
        sw = ToggleSwitch(False)
        QVBoxLayout(fenetre).addWidget(sw)
        qtbot.addWidget(fenetre)
        fenetre.show()
        qtbot.waitExposed(fenetre)
        _marque(sw, True)
        anneau = fenetre.findChild(_Anneau)
        piste = QRect(sw.mapTo(fenetre, QPoint(sw._MARGE, sw._MARGE)), QSize(sw._TRACK_W, sw._TRACK_H))
        assert anneau.isVisible() and anneau.geometry() == piste.adjusted(-5, -5, 5, 5)
        assert anneau._rayon == sw._TRACK_H / 2 + 3


class TestTousLesReglagesDuDialogue:
    """Aucun interrupteur ne doit repartir en `NoFocus` par recopie."""

    def test_les_toggles_des_parametres_sont_focusables(self, qtbot, tmp_path,
                                                        monkeypatch):
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH",
                            tmp_path / "config.json")
        from src.core.config import Config
        from src.core.game_manager import GameManager
        from src.ui.settings_panel import SettingsDialog

        cfg = Config(install_path=tmp_path / "g", cache_path=tmp_path / "c")
        dlg = SettingsDialog(cfg, GameManager(cfg))
        qtbot.addWidget(dlg)
        toggles = dlg.findChildren(ToggleSwitch)
        assert toggles, "aucun interrupteur trouvé — test à revoir"
        for sw in toggles:
            assert sw.focusPolicy() != Qt.FocusPolicy.NoFocus, (
                f"réglage {sw.accessibleName()!r} inatteignable au clavier")


@pytest.mark.parametrize("maison", ["poudlard", "gryffondor", "serpentard", "serdaigle", "poufsouffle"])
def test_eteint_et_allume_se_distinguent_dans_chaque_maison(qtbot, maison):
    """Audit UI v5 (2026-11-13) : sous une maison, la piste éteinte prenait la teinte de la maison
    en plus sombre, à côté de la même teinte vive allumée. Éteinte, elle est neutre partout."""
    from src.ui.theme import set_theme
    set_theme(maison)
    try:
        eteint, allume = ToggleSwitch(False), ToggleSwitch(True)
        for t in (eteint, allume):
            qtbot.addWidget(t)
            t.resize(t.sizeHint())
        x, y = eteint._MARGE + eteint._TRACK_W - 8, eteint._MARGE + eteint._TRACK_H // 2
        pe = eteint.grab().toImage().pixelColor(x, y)
        pa = allume.grab().toImage().pixelColor(allume._MARGE + 8, y)
        assert abs(pe.saturation() - pa.saturation()) > 60 or abs(pe.lightness() - pa.lightness()) > 60
        assert pe.saturation() < 40, "la piste éteinte n'a pas de teinte"
    finally:
        set_theme("poudlard")

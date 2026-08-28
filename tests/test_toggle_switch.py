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

from src.ui.focus_visible import PROPRIETE as FOCUS_CLAVIER  # noqa: E402
from src.ui.toggle_switch import ToggleSwitch, toggle_row  # noqa: E402


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

    def test_toggle_row_returns_pair(self, qtbot):
        row, toggle = toggle_row("Mon réglage", checked=True)
        qtbot.addWidget(row)
        assert toggle.isChecked() is True


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
    def test_l_anneau_de_focus_est_peint_au_clavier(self, qtbot):
        """Un widget PEINT n'est pas atteint par la règle `:focus` du
        stylesheet : sans tracé maison, on peut atteindre l'interrupteur sans
        jamais voir lequel est sélectionné."""
        from PyQt6.QtGui import QColor, QImage, QPainter

        sw = ToggleSwitch(False)
        qtbot.addWidget(sw)
        sw.show()
        qtbot.waitExposed(sw)

        def rendu(clavier: bool) -> QImage:
            sw.setProperty(FOCUS_CLAVIER, clavier)
            img = QImage(sw.size(), QImage.Format.Format_ARGB32)
            img.fill(QColor(0, 0, 0, 0))
            p = QPainter(img)
            sw.render(p)
            p.end()
            return img

        # Compter les pixels OPAQUES ne prouve rien : l'anneau est peint
        # PAR-DESSUS une piste déjà pleine, donc le nombre ne bouge pas (880
        # dans les deux cas, mesuré). C'est la COULEUR qui change — on compare
        # donc les deux rendus pixel à pixel.
        avec, sans = rendu(True), rendu(False)
        differents = sum(
            1 for y in range(avec.height()) for x in range(avec.width())
            if avec.pixelColor(x, y) != sans.pixelColor(x, y)
        )
        assert differents > 20, (
            f"seulement {differents} pixel(s) de différence : "
            "aucun anneau dessiné au focus clavier")

    def test_la_ligne_donne_un_nom_accessible(self, qtbot):
        """Le libellé est à CÔTÉ du widget, pas dedans : sans nom accessible,
        une aide technique n'annonce qu'« interrupteur »."""
        row, sw = toggle_row("Lire les bandes-annonces", True)
        qtbot.addWidget(row)
        assert sw.accessibleName() == "Lire les bandes-annonces"


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

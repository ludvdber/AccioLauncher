"""L'anneau de focus doré ne doit apparaître qu'au CLAVIER.

Qt n'a pas d'équivalent de `:focus-visible` : la règle `:focus` s'appliquait
aussi bien à Tab qu'au focus que Qt pose lui-même sur le premier bouton de la
chaîne à l'ouverture de la fenêtre. Le launcher s'ouvrait donc avec le bouton
« Réduire » cerclé d'or alors que l'utilisateur n'avait rien fait.

Retirer l'anneau n'était pas une option : c'est le seul repère d'un utilisateur
au clavier. Ces tests vérifient les deux moitiés du contrat.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QFocusEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from src.ui.focus_visible import PROPRIETE, install  # noqa: E402


@pytest.fixture
def filtre_pose():
    install(QApplication.instance())


def _focus(widget, raison):
    QApplication.sendEvent(widget, QFocusEvent(QEvent.Type.FocusIn, raison))


class TestRaisonDuFocus:
    @pytest.mark.parametrize("raison", [
        Qt.FocusReason.ActiveWindowFocusReason,   # ouverture de la fenêtre
        Qt.FocusReason.MouseFocusReason,          # simple clic
        Qt.FocusReason.PopupFocusReason,
        Qt.FocusReason.OtherFocusReason,
    ])
    def test_pas_d_anneau_sans_le_clavier(self, qtbot, filtre_pose, raison):
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, raison)
        assert btn.property(PROPRIETE) is False, (
            "l'anneau serait visible pour un focus non clavier (%s)" % raison)

    @pytest.mark.parametrize("raison", [
        Qt.FocusReason.TabFocusReason,
        Qt.FocusReason.BacktabFocusReason,
        Qt.FocusReason.ShortcutFocusReason,
    ])
    def test_anneau_au_clavier(self, qtbot, filtre_pose, raison):
        """A11Y : la navigation au clavier DOIT rester visible."""
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, raison)
        assert btn.property(PROPRIETE) is True, (
            "un utilisateur au clavier ne verrait plus où il est (%s)" % raison)

    def test_l_anneau_part_avec_le_focus(self, qtbot, filtre_pose):
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, Qt.FocusReason.TabFocusReason)
        QApplication.sendEvent(
            btn, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason))
        assert btn.property(PROPRIETE) is False


class TestStylesheet:
    def test_la_regle_focus_est_conditionnee(self):
        """Sans la condition, la règle redeviendrait celle d'avant."""
        from src.ui.styles import MAIN_STYLE
        assert 'QPushButton[focusClavier="true"]:focus' in MAIN_STYLE
        assert "QPushButton:focus" not in MAIN_STYLE, (
            "un sélecteur :focus non conditionné remettrait l'anneau à "
            "l'ouverture de la fenêtre")

    def test_l_anneau_existe_toujours(self):
        """L'A11Y n'est pas négociable : la règle doit rester présente."""
        from src.ui.styles import COLOR_ACCENT_GOLD, MAIN_STYLE
        assert "outline: 2px solid" in MAIN_STYLE
        assert COLOR_ACCENT_GOLD in MAIN_STYLE

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
from PyQt6.QtGui import QFocusEvent, QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton, QScrollArea, QVBoxLayout, QWidget  # noqa: E402

from src.ui.focus_visible import PROPRIETE, install  # noqa: E402


@pytest.fixture
def filtre_pose():
    install(QApplication.instance())


def _focus(widget, raison, touche=True):
    """Un focus reçu pendant l'appui d'une touche (Tab), ou hors de tout appui."""
    if touche:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Shift,
                                                 Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(widget, QFocusEvent(QEvent.Type.FocusIn, raison))


class TestRaisonDuFocus:
    @pytest.mark.parametrize("raison", [
        Qt.FocusReason.MouseFocusReason,          # simple clic
        Qt.FocusReason.OtherFocusReason,
    ])
    def test_pas_d_anneau_sans_le_clavier(self, qtbot, filtre_pose, raison):
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, raison)
        assert btn.property(PROPRIETE) is False, (
            f"l'anneau serait visible pour un focus non clavier ({raison})")

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
            f"un utilisateur au clavier ne verrait plus où il est ({raison})")

    def test_l_anneau_part_avec_le_focus(self, qtbot, filtre_pose):
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, Qt.FocusReason.TabFocusReason)
        QApplication.sendEvent(
            btn, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason))
        assert btn.property(PROPRIETE) is False

    @pytest.mark.parametrize("raison", [Qt.FocusReason.ActiveWindowFocusReason,
                                        Qt.FocusReason.PopupFocusReason])
    def test_ouverture_de_fenetre_sans_anneau(self, qtbot, filtre_pose, raison):
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, raison)
        assert not btn.property(PROPRIETE)

    @pytest.mark.parametrize("raison", [Qt.FocusReason.ActiveWindowFocusReason,
                                        Qt.FocusReason.PopupFocusReason])
    def test_alt_tab_garde_l_anneau(self, qtbot, filtre_pose, raison):
        """Audit UI 2026-11-13 : après Alt+Tab, le focus revenait sans anneau, et Espace
        agissait sur un bouton qu'on ne voyait plus désigné."""
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, Qt.FocusReason.TabFocusReason)
        QApplication.sendEvent(btn, QFocusEvent(QEvent.Type.FocusOut, raison))
        assert btn.property(PROPRIETE) is True
        _focus(btn, raison, touche=False)
        assert btn.property(PROPRIETE) is True

    def test_une_raison_tab_sans_touche_n_allume_rien(self, qtbot, filtre_pose):
        """Un widget qui se cache en tenant le focus le passe au suivant avec la raison
        Tab : un clic sur « ← Bibliothèque » allumait l'onglet BIBLIOTHÈQUE."""
        btn = QPushButton("x")
        qtbot.addWidget(btn)
        _focus(btn, Qt.FocusReason.TabFocusReason, touche=False)
        assert btn.property(PROPRIETE) is False


def test_un_focus_au_clavier_fait_defiler_jusqu_a_lui(qtbot, filtre_pose):
    """Maj+Tab depuis la barre du haut posait le focus 39 px sous le bas de la fenêtre
    (Réglages HP6 > Image) : Qt ne défile que pour un Tab parti de la zone elle-même."""
    page = QWidget()
    lay = QVBoxLayout(page)
    boutons = [QPushButton(str(n)) for n in range(40)]
    for b in boutons:
        b.setFixedHeight(40)
        lay.addWidget(b)
    zone = QScrollArea()
    zone.setWidget(page)
    zone.setWidgetResizable(True)
    zone.resize(200, 300)
    qtbot.addWidget(zone)
    zone.show()
    qtbot.waitExposed(zone)
    assert zone.verticalScrollBar().value() == 0
    _focus(boutons[-1], Qt.FocusReason.BacktabFocusReason)
    bas = boutons[-1].mapTo(zone.viewport(), boutons[-1].rect().bottomLeft()).y()
    assert 0 < bas <= zone.viewport().height()


def test_tab_entre_dans_un_groupe_par_le_choix_coche(qtbot):
    """Le Carnet ouvert sur les Défis : Tab cerclait « Folio », et Espace l'ouvrait (audit UI,
    2026-11-13). Entrer dans le groupe mène au choix coché ; y circuler reste libre."""
    from PyQt6.QtWidgets import QButtonGroup
    from src.ui.focus_visible import _choix_du_groupe
    hote = QWidget()
    qtbot.addWidget(hote)
    lay = QVBoxLayout(hote)
    dehors = QPushButton("dehors")
    lay.addWidget(dehors)
    groupe = QButtonGroup(hote)
    boutons = [QPushButton(str(n)) for n in range(3)]
    for b in boutons:
        b.setCheckable(True)
        groupe.addButton(b)
        lay.addWidget(b)
    boutons[2].setChecked(True)
    hote.show()
    assert _choix_du_groupe(boutons[0], dehors) is boutons[2]
    assert _choix_du_groupe(boutons[0], None) is boutons[2]
    assert _choix_du_groupe(boutons[1], boutons[2]) is None, "dans le groupe, Tab avance"
    assert _choix_du_groupe(boutons[2], dehors) is None
    assert _choix_du_groupe(dehors, boutons[0]) is None


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


def test_aucun_selecteur_focus_non_conditionne():
    """Règle 16 : un `:focus` nu cercle aussi le bouton que Qt met au focus à
    l'ouverture, ou après un clic. Seize sélecteurs étaient retombés dedans
    (Collections, Carnet, barre du haut, aide antivirus ; audit du 2026-10-29).
    Les mentions entre accents graves (documentation) ne comptent pas."""
    import re
    from pathlib import Path
    fautifs = []
    for fichier in sorted(Path("src/ui").glob("*.py")):
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if "`" in ligne:
                continue
            if re.search(r"[\w)]:focus\b", ligne):
                fautifs.append(f"{fichier.name}:{numero}")
    assert fautifs == []

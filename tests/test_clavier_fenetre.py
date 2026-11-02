"""Clavier, manette et fenêtre (lot 2 du grand audit du 2026-11-02).

Chaque test échoue sur le code d'avant : Entrée sur un bouton icône lançait le
jeu, Tab sortait de la visite guidée, la fenêtre agrandie revenait en taille
normale, la barre lumineuse restait allumée.
"""
import threading
import time
from types import SimpleNamespace

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from src.core import manette
from src.ui.clickable_label import ClickableLabel
from src.ui.focus_visible import PROPRIETE
from src.ui.glow_button import GlowButton
from src.ui.icon_button import IconButton


def _dans(widget, parent) -> bool:
    while widget is not None:
        if widget is parent:
            return True
        widget = widget.parentWidget()
    return False


class TestEntree:
    def test_entree_sur_un_bouton_icone_ne_lance_pas_le_jeu(self, make_window, qtbot):
        win = make_window(visite_vue=True)
        win.show()
        qtbot.waitExposed(win)
        actions = []
        win._detail.trigger_primary_action = lambda: actions.append(1)   # sur l'INSTANCE (règle 12)
        bouton = next(b for b in win._detail.findChildren(IconButton) if b.isVisible())
        clics = []
        bouton.clicked.connect(lambda: clics.append(1))
        qtbot.keyClick(bouton, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: clics == [1])
        assert actions == [], "Entrée sur un bouton icône a lancé l'action de la fiche"

    def test_entree_clique_un_glowbutton(self, qtbot):
        bouton = GlowButton("JOUER")
        qtbot.addWidget(bouton)
        clics = []
        bouton.clicked.connect(lambda: clics.append(1))
        qtbot.keyClick(bouton, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: clics == [1])

    def test_une_touche_tenue_ne_clique_qu_une_fois(self, qtbot):
        lien = ClickableLabel("Lire la suite")
        qtbot.addWidget(lien)
        clics = []
        lien.clicked.connect(lambda: clics.append(1))
        for repetition in (False, True, True):
            QApplication.sendEvent(lien, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                                   Qt.KeyboardModifier.NoModifier, "", repetition))
        assert clics == [1]


class TestAnneau:
    def test_glowbutton_dessine_son_anneau_au_clavier(self, qtbot):
        bouton = GlowButton("JOUER")
        qtbot.addWidget(bouton)
        bouton.resize(160, 46)
        sans = bouton.grab().toImage()
        bouton.setProperty(PROPRIETE, True)
        avec = bouton.grab().toImage()
        assert sans != avec, "JOUER atteint au clavier ne se distingue en rien"


class TestVisite:
    def test_tab_tourne_dans_la_carte(self, make_window, qtbot):
        win = make_window(visite_vue=False)
        win.show()
        qtbot.waitExposed(win)
        actions = []
        win._detail.trigger_primary_action = lambda: actions.append(1)
        win._visite.proposer()
        calque = win._visite.calque
        calque._btn_suivant.setFocus(Qt.FocusReason.TabFocusReason)
        for touche in [Qt.Key.Key_Tab] * 6 + [Qt.Key.Key_Backtab] * 6:
            qtbot.keyClick(win.focusWidget(), touche)
            assert _dans(win.focusWidget(), calque), f"le focus est sorti vers {win.focusWidget()!r}"
            qtbot.keyClick(win.focusWidget(), Qt.Key.Key_Space)
            if win._visite.calque is None:
                break
        assert actions == []

    def test_la_ligne_meta_n_arrete_plus_tab(self, make_window):
        win = make_window(visite_vue=True)
        assert not win._detail._info._meta.focusPolicy() & Qt.FocusPolicy.TabFocus


class TestFenetreAgrandie:
    def test_retour_du_jeu_la_garde_agrandie(self, make_window, qtbot):
        win = make_window(visite_vue=True)
        win.showMaximized()
        qtbot.waitExposed(win)
        win._minimize_to_tray()
        win._restore_from_tray()
        assert win.windowState() & Qt.WindowState.WindowMaximized

    def test_un_clic_sur_la_barre_ne_la_restaure_pas(self, make_window, qtbot):
        win = make_window(visite_vue=True)
        win.showMaximized()
        qtbot.waitExposed(win)
        barre = win._title_bar
        point = QPoint(barre.width() // 2, barre.height() // 2)
        qtbot.mousePress(barre, Qt.MouseButton.LeftButton, pos=point)
        qtbot.mouseRelease(barre, Qt.MouseButton.LeftButton, pos=point)
        assert win.windowState() & Qt.WindowState.WindowMaximized
        qtbot.mouseDClick(barre, Qt.MouseButton.LeftButton, pos=point)
        assert not win.windowState() & Qt.WindowState.WindowMaximized, \
            "le double-clic doit rétablir la fenêtre agrandie"


class TestBarreLumineuse:
    def test_seule_la_derniere_demande_ecrit(self, monkeypatch):
        """Une couleur encore en attente ne passe plus après le noir d'`eteindre`."""
        ecrits = []
        monkeypatch.setattr(manette, "_poser", lambda rgb: ecrits.append(rgb) or 1)
        depart = manette._derniere
        with manette._VERROU:
            fils = [threading.Thread(target=manette.colorer, args=("gryffondor",)),
                    threading.Thread(target=manette._demander, args=((0, 0, 0),))]
            fils[0].start()
            while manette._derniere < depart + 1:
                time.sleep(0.001)
            fils[1].start()
            while manette._derniere < depart + 2:
                time.sleep(0.001)
        for fil in fils:
            fil.join(2)
        assert ecrits == [(0, 0, 0)]
        assert not manette.allumee_par_nous()

    def test_decocher_eteint_la_barre(self, monkeypatch):
        from src.core.config import Config
        from src.ui.settings_panel import SettingsDialog
        appels = []
        monkeypatch.setattr(manette, "eteindre_en_fond", lambda: appels.append("eteindre"))
        monkeypatch.setattr(manette, "colorer_en_fond", lambda theme: appels.append(theme))
        SettingsDialog._on_couleur_manette(SimpleNamespace(config=Config()), False)
        assert appels == ["eteindre"]

"""Entrée active le bouton qui a le focus (`src/ui/entree_focus.py`).

Audit du 2026-11-13 : dans les boîtes de message, Tab jusqu'à « Annuler »
posait l'anneau dessus, mais Entrée cliquait le bouton PAR DÉFAUT (« Écrire et
lancer » dans la boîte « Réglage du jeu »). Dans la boîte de plantage, Entrée
ne faisait rien. Contre-épreuve : sans le filtre, ces tests échouent.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from src.ui.entree_focus import entree_suit_le_focus
from src.ui.fenetre_message import FenetreMessage, message


def _quand_ouverte(action):
    def essayer():
        boite = QApplication.activeModalWidget()
        if isinstance(boite, FenetreMessage):
            action(boite)
        else:
            QTimer.singleShot(10, essayer)
    QTimer.singleShot(0, essayer)


def _entree_sur(qtbot, bouton):
    bouton.setFocus()
    qtbot.keyClick(bouton, Qt.Key.Key_Return)


class TestBoiteDeMessage:
    def test_entree_sur_le_retrait_choisit_le_retrait(self, qtbot):
        _quand_ouverte(lambda b: _entree_sur(qtbot, b.buttons()[1]))
        assert message(None, QMessageBox.Icon.Question, "Réglage du jeu", "x",
                       ("Écrire et lancer", "Annuler"), defaut=0) == 1

    def test_entree_sur_le_bouton_par_defaut_le_choisit(self, qtbot):
        _quand_ouverte(lambda b: _entree_sur(qtbot, b.buttons()[0]))
        assert message(None, QMessageBox.Icon.Question, "T", "x", ("Oui", "Non"), defaut=0) == 0

    def test_entree_du_pave_numerique(self, qtbot):
        def agir(b):
            b.buttons()[2].setFocus()
            qtbot.keyClick(b.buttons()[2], Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)
        _quand_ouverte(agir)
        assert message(None, QMessageBox.Icon.Warning, "T", "x", ("Supprimer", "Garder", "Annuler")) == 2


class TestAutresFenetres:
    def test_boite_de_plantage_entree_ferme(self, qtbot):
        from src.ui.crash_dialog import construire_dialogue
        dlg = construire_dialogue("rapport")
        qtbot.addWidget(dlg)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        dlg.show()
        fermer = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Fermer")
        _entree_sur(qtbot, fermer)
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_dans_un_champ_le_bouton_par_defaut_repond_encore(self, qtbot):
        dlg = QDialog()
        qtbot.addWidget(dlg)
        lay = QVBoxLayout(dlg)
        champ, ok, non = QLineEdit(), QPushButton("OK"), QPushButton("Non")
        for w in (champ, ok, non):
            lay.addWidget(w)
        for b in (ok, non):
            b.setAutoDefault(False)
        ok.setDefault(True)
        clics = []
        ok.clicked.connect(lambda: clics.append("ok"))
        non.clicked.connect(lambda: clics.append("non"))
        entree_suit_le_focus(dlg)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        dlg.show()
        champ.setFocus()
        qtbot.keyClick(champ, Qt.Key.Key_Return)
        assert clics == ["ok"]

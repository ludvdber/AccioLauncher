"""La fenêtre de message du launcher (`src/ui/fenetre_message.py`), qui remplace
QMessageBox : l'index du bouton choisi, Échap = le retrait, le texte toujours brut,
la ligne verte de ce qui est conservé."""

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from src.ui.fenetre_message import FenetreMessage, message


def _quand_ouverte(action):
    """Agit sur la fenêtre modale dès qu'elle s'affiche (exec() bloque)."""
    def essayer():
        boite = QApplication.activeModalWidget()
        if isinstance(boite, FenetreMessage):
            action(boite)
        else:
            QTimer.singleShot(10, essayer)
    QTimer.singleShot(0, essayer)


class TestMessage:
    def test_rend_l_index_du_bouton_clique(self, qtbot):
        _quand_ouverte(lambda b: b.buttons()[1].click())
        assert message(None, QMessageBox.Icon.Question, "Titre", "Texte",
                       ("Installer", "Plus tard")) == 1

    def test_echap_choisit_le_retrait(self, qtbot):
        _quand_ouverte(lambda b: qtbot.keyClick(b, Qt.Key.Key_Escape))
        assert message(None, QMessageBox.Icon.Warning, "T", "x", ("Supprimer", "Garder", "Annuler")) == 2

    def test_sans_choix_un_seul_bouton_fermer(self, qtbot):
        vus = []
        _quand_ouverte(lambda b: (vus.append([x.text() for x in b.buttons()]), b.buttons()[0].click()))
        assert message(None, QMessageBox.Icon.Information, "T", "x") == -1
        assert vus == [["Fermer"]]

    def test_le_texte_reste_brut(self, qtbot):
        """Les messages citent des noms venus du catalogue : jamais interprétés."""
        lus = []

        def lire(b):
            lus.extend(lbl for lbl in b.findChildren(QLabel) if "<b>" in lbl.text())
            lus.append(lus[-1].textFormat() if lus else None)
            b.buttons()[0].click()
        _quand_ouverte(lire)
        message(None, QMessageBox.Icon.Information, "T", "<b>HP1</b>")
        assert lus and lus[-1] == Qt.TextFormat.PlainText

    def test_la_ligne_de_ce_qui_est_conserve(self, qtbot):
        textes = []

        def lire(b):
            textes.extend(lbl.text() for lbl in b.findChildren(QLabel))
            b.buttons()[0].click()
        _quand_ouverte(lire)
        message(None, QMessageBox.Icon.Critical, "Échec", "x", conserve="Les 2,1 Go déjà reçus")
        assert "CE QUI EST CONSERVÉ" in textes and "Les 2,1 Go déjà reçus" in textes


class TestBoutons:
    def test_le_plus_engageant_a_droite_et_le_destructif_en_rouge(self, qtbot):
        boite = FenetreMessage()
        qtbot.addWidget(boite)
        oui = boite.addButton("Installer", QMessageBox.ButtonRole.AcceptRole)
        effacer = boite.addButton("Effacer", QMessageBox.ButtonRole.DestructiveRole)
        non = boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.show()
        assert oui.objectName() == "principal"
        assert effacer.objectName() == "danger"
        assert non.objectName() == "secondaire"
        assert oui.isDefault(), "sans défaut désigné : le premier"
        assert oui.x() > non.x(), "celui qui agit finit à droite"

    def test_echap_sans_retrait_ne_ferme_rien(self, qtbot):
        boite = FenetreMessage()
        qtbot.addWidget(boite)
        boite.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        boite.show()
        qtbot.keyClick(boite, Qt.Key.Key_Escape)
        assert boite.clickedButton() is None

    @pytest.mark.parametrize("defaut", [-5, 99])
    def test_un_defaut_hors_bornes_est_ramene(self, qtbot, defaut):
        vus = []
        _quand_ouverte(lambda b: (vus.append(next(x.text() for x in b.buttons() if x.isDefault())),
                                  b.buttons()[0].click()))
        message(None, QMessageBox.Icon.Question, "T", "x", ("A", "B"), defaut=defaut)
        assert vus == ["A" if defaut < 0 else "B"]

"""La fenêtre de message du launcher (`src/ui/fenetre_message.py`), qui remplace
QMessageBox : l'index du bouton choisi, Échap = le retrait, le texte toujours brut,
la ligne verte de ce qui est conservé."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox

from src.ui.fenetre_message import FenetreMessage, message
from tests.modales import quand_ouverte


class TestMessage:
    def test_rend_l_index_du_bouton_clique(self, qtbot):
        quand_ouverte(lambda b: b.buttons()[1].click())
        assert message(None, QMessageBox.Icon.Question, "Titre", "Texte",
                       ("Installer", "Plus tard")) == 1

    def test_echap_choisit_le_retrait(self, qtbot):
        quand_ouverte(lambda b: qtbot.keyClick(b, Qt.Key.Key_Escape))
        assert message(None, QMessageBox.Icon.Warning, "T", "x", ("Supprimer", "Garder", "Annuler")) == 2

    def test_la_boite_ne_survit_pas_a_sa_reponse(self, qtbot):
        """2026-11-15 : chaque message restait caché sous sa fenêtre jusqu'à la fermeture du launcher."""
        from PyQt6.QtCore import QCoreApplication, QEvent
        from PyQt6.QtWidgets import QWidget
        parent = QWidget()
        qtbot.addWidget(parent)
        quand_ouverte(lambda b: b.buttons()[0].click())
        assert message(parent, QMessageBox.Icon.Question, "T", "x", ("Oui", "Non")) == 0
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert parent.findChildren(FenetreMessage) == []

    def test_sans_choix_un_seul_bouton_fermer(self, qtbot):
        vus = []
        quand_ouverte(lambda b: (vus.append([x.text() for x in b.buttons()]), b.buttons()[0].click()))
        assert message(None, QMessageBox.Icon.Information, "T", "x") == -1
        assert vus == [["Fermer"]]

    def test_le_texte_reste_brut(self, qtbot):
        """Les messages citent des noms venus du catalogue : jamais interprétés."""
        lus = []

        def lire(b):
            lus.extend(lbl for lbl in b.findChildren(QLabel) if "<b>" in lbl.text())
            lus.append(lus[-1].textFormat() if lus else None)
            b.buttons()[0].click()
        quand_ouverte(lire)
        message(None, QMessageBox.Icon.Information, "T", "<b>HP1</b>")
        assert lus and lus[-1] == Qt.TextFormat.PlainText

    def test_la_ligne_de_ce_qui_est_conserve(self, qtbot):
        textes = []

        def lire(b):
            textes.extend(lbl.text() for lbl in b.findChildren(QLabel))
            b.buttons()[0].click()
        quand_ouverte(lire)
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
        quand_ouverte(lambda b: (vus.append(next(x.text() for x in b.buttons() if x.isDefault())),
                                  b.buttons()[0].click()))
        message(None, QMessageBox.Icon.Question, "T", "x", ("A", "B"), defaut=defaut)
        assert vus == ["A" if defaut < 0 else "B"]

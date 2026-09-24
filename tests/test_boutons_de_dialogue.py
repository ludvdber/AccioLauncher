"""Les boutons d'un dialogue : lisibles, et dans la langue choisie.

Deux défauts signalés le même jour (Ludo, 2026-09-23), sur la même capture :

① **« Mettre à jour maintenant » sortait de son cadre**, coupé des deux côtés.
   Cause mesurée : la feuille de style posait `min-width: 70px` sur les boutons
   de `QMessageBox`. Qt traduit un `min-width` de feuille de style en un
   `setMinimumWidth()` POSÉ sur le widget, et `qSmartMinSize` REMPLACE alors le
   minimum calculé par cette valeur au lieu d'en prendre le maximum. Le minimum
   du bouton tombait donc à 108 px (70 + 36 de padding + 2 de bordure) quel que
   soit son libellé — et `QMessageBox` se dimensionne sur le MINIMUM de son
   layout. Relevé en vraies polices : 146 px accordés pour 182 demandés.

② **« Yes » et « No » en anglais dans un launcher réglé en français.** Ces
   libellés ne viennent pas de `tr()` mais des fichiers `qtbase_<langue>.qm`
   de Qt — que `_keep()` dans `accio_launcher.spec` écarte volontairement du
   build. Deux systèmes de traduction pour une même fenêtre, dont un que
   `tests/test_i18n.py` ne voit pas et qu'un traducteur bénévole ne peut pas
   atteindre. Les dialogues du launcher nomment donc leurs boutons.
"""

import ast
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QMessageBox, QWidget  # noqa: E402

from src.ui.styles import MAIN_STYLE  # noqa: E402
from src.ui.theme import themed  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"

# Boutons dont le libellé est fourni par Qt, donc traduit hors de `src/data/i18n`.
_BOUTONS_DE_QT = {"Yes", "No", "Ok", "Cancel", "Abort", "Retry", "Ignore",
                  "Close", "Save", "Discard", "Apply", "Open"}
# Raccourcis `QMessageBox` qui posent eux-mêmes un bouton standard, et laissent
# en prime le texte en `AutoText` alors qu'il interpole souvent du catalogue.
_RACCOURCIS = {"question", "warning", "information", "critical", "about"}


def _chemin_attribut(noeud: ast.AST) -> str:
    """« QMessageBox.StandardButton.Yes » à partir du nœud AST, ou ''."""
    morceaux = []
    while isinstance(noeud, ast.Attribute):
        morceaux.append(noeud.attr)
        noeud = noeud.value
    if not isinstance(noeud, ast.Name):
        return ""
    morceaux.append(noeud.id)
    return ".".join(reversed(morceaux))


def _fichiers_python():
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


class TestAucunBoutonTraduitParQt:
    """L'AST et non le texte : les commentaires de ce dépôt CITENT ces noms
    pour expliquer pourquoi on ne les emploie plus, et un balayage littéral se
    ferait piéger par sa propre documentation."""

    def test_aucun_standardbutton_dans_src(self):
        fautes = []
        for chemin in _fichiers_python():
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, ast.Attribute):
                    continue
                plein = _chemin_attribut(noeud)
                if (plein.startswith("QMessageBox.StandardButton.")
                        and plein.rsplit(".", 1)[1] in _BOUTONS_DE_QT):
                    fautes.append(f"{chemin.relative_to(SRC)}:{noeud.lineno} {plein}")
        assert not fautes, (
            "ces boutons sont traduits par les .qm de Qt, que le build écarte — "
            "ils sortiront en anglais : " + ", ".join(fautes))

    def test_aucun_raccourci_qmessagebox(self):
        """`QMessageBox.question(...)` pose un Yes/No de Qt et laisse le texte
        en AutoText. Passer par `_boite` (handlers) ou `utils.avertir`."""
        fautes = []
        for chemin in _fichiers_python():
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, ast.Call):
                    continue
                plein = _chemin_attribut(noeud.func)
                if (plein.startswith("QMessageBox.")
                        and plein.split(".")[1] in _RACCOURCIS):
                    fautes.append(f"{chemin.relative_to(SRC)}:{noeud.lineno} {plein}")
        assert not fautes, (
            "raccourci QMessageBox à remplacer par _boite / avertir : "
            + ", ".join(fautes))


class TestLaFeuilleDeStyleNeBridePasLesBoutons:

    def test_pas_de_min_width_sur_les_boutons_de_dialogue(self):
        """Le `min-width` d'une feuille de style devient un minimum DUR qui
        écrase celui que Qt calcule d'après le texte."""
        regle = MAIN_STYLE.split("QMessageBox QPushButton")[1].split("}}")[0]
        assert "min-width" not in regle, (
            "un min-width ici rogne tout bouton dont le libellé dépasse cette "
            "largeur — le confort visuel se règle par le padding")


class TestAucunePoliceDansUnPseudoEtat:
    """Le cas que `TestUnBoutonNEstJamaisRogne` ne pouvait pas voir.

    `QMessageBox QPushButton:default` passait le bouton par défaut en GRAS.
    Qt dimensionne le bouton avec la police de la règle de base et n'applique
    le gras qu'au dessin : 144 px de place pour 154 px de texte, « Mettre à
    jour maintenant » coupé des deux côtés (Ludo, boîte de mise à jour vers la
    1.0.6). Les tests de largeur mesuraient le texte avec `fontMetrics()` du
    widget — la police NON grasse — donc passaient au vert sur le défaut.
    """

    def test_aucune_propriete_de_police_sous_un_pseudo_etat(self):
        import re

        # Les commentaires d'abord : ils CITENT des pseudo-états pour expliquer.
        style = re.sub(r"/\*.*?\*/", "", MAIN_STYLE, flags=re.S)
        fautes = []
        for selecteur, corps in re.findall(r"([^{}]+)\{\{?([^{}]*)\}", style):
            if ":" not in selecteur.split("::")[0]:
                continue
            if "QPushButton" in selecteur and re.search(r"\bfont(-[a-z]+)?\s*:", corps):
                fautes.append(" ".join(selecteur.split()))
        assert not fautes, (
            "police changée dans un pseudo-état : le bouton est dimensionné "
            "sans elle et son libellé sera rogné — " + ", ".join(fautes))


class TestUnBoutonNEstJamaisRogne:

    @staticmethod
    def _boite_avec(qtbot, libelle_long: str):
        hote = QWidget()
        hote.setStyleSheet(themed(MAIN_STYLE))
        qtbot.addWidget(hote)
        hote.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        hote.show()

        boite = QMessageBox(hote)
        qtbot.addWidget(boite)
        boite.setIcon(QMessageBox.Icon.NoIcon)
        boite.setTextFormat(Qt.TextFormat.PlainText)
        boite.setText("Accio Launcher v9.9.9 est disponible !")
        # Un texte COURT : c'est le cas piège. Une boîte large cache le défaut,
        # puisque les boutons y tiennent par accident.
        boite.setInformativeText("Courte explication.")
        long = boite.addButton(libelle_long, QMessageBox.ButtonRole.AcceptRole)
        court = boite.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
        boite.setDefaultButton(long)
        boite.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        boite.show()
        qtbot.waitUntil(lambda: boite.isVisible(), timeout=3000)
        return boite, long, court

    def test_le_bouton_recoit_la_largeur_qu_il_demande(self, qtbot):
        boite, long, _ = self._boite_avec(qtbot, "Mettre à jour maintenant")
        assert long.width() >= long.sizeHint().width(), (
            f"bouton rogné de {long.sizeHint().width() - long.width()} px : "
            "son libellé sortira du cadre")

    def test_le_texte_tient_dans_le_bouton(self, qtbot):
        """La mesure qui compte pour l'utilisateur : le libellé est-il lisible
        en entier ? On compare à l'AVANCE du texte, pas au sizeHint."""
        libelle = "Mettre à jour maintenant"
        boite, long, _ = self._boite_avec(qtbot, libelle)
        assert long.width() >= long.fontMetrics().horizontalAdvance(libelle), (
            "le libellé déborde du bouton (il était coupé des deux côtés, "
            "le texte d'un QPushButton étant centré)")

    def test_la_boite_grandit_pour_ses_boutons(self, qtbot):
        """Le dialogue doit GRANDIR pour ses boutons, jamais les comprimer.

        Le libellé reste RÉALISTE — « Déplacer et importer », le plus long des
        nôtres — et pas absurde : au-delà, c'est le plafond de largeur de
        `QMessageBox` (une fraction de l'écran) qui tranche, et non nous. Un
        test sur une chaîne de 50 caractères mesurerait ce plafond de Qt et
        échouerait sans qu'aucun défaut du launcher soit en cause.
        """
        boite, long, court = self._boite_avec(qtbot, "Déplacer et importer")
        assert long.width() >= long.sizeHint().width()
        assert boite.width() >= long.width() + court.width()

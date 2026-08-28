"""Page « À propos » — remerciements, liens, échappement du catalogue.

Cette page n'avait AUCUN test tant qu'elle vivait au milieu de
`settings_panel.py` : l'exercer supposait d'ouvrir le dialogue de réglages
entier, avec son scan disque et ses combos. C'est le motif habituel — ce qui est
noyé n'est pas testé — et il est ici plus gênant qu'ailleurs, parce que la page
affiche du texte VENU DU CATALOGUE, c'est-à-dire de l'extérieur.
"""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QLabel  # noqa: E402

from src.core.game_data import Contributor  # noqa: E402
from src.ui import about_page  # noqa: E402


def _labels(page) -> list[QLabel]:
    return page.findChildren(QLabel)


def _textes(page) -> str:
    return "\n".join(lbl.text() for lbl in _labels(page))


class TestContenu:
    def test_la_version_affichee_est_celle_du_launcher(self, qtbot):
        from src.core.config import APP_VERSION
        page = about_page.construire([])
        qtbot.addWidget(page)
        assert f"v{APP_VERSION}" in _textes(page)

    def test_les_trois_liens_portent_un_pictogramme(self, qtbot):
        """Sans icône, trois cadres gris ne se distinguent qu'en LISANT —
        et le libellé change avec la langue, la destination non."""
        from PyQt6.QtWidgets import QPushButton
        page = about_page.construire([])
        qtbot.addWidget(page)
        boutons = page.findChildren(QPushButton)
        assert len(boutons) == 3
        for b in boutons:
            assert not b.icon().isNull(), f"{b.text()} n'a pas de pictogramme"

    def test_discord_et_kofi_ne_sont_pas_traduits(self, qtbot):
        """Ce sont des noms propres. Les passer par tr() obligerait à écrire
        trois traductions identiques, ce que la suite i18n refuse."""
        from PyQt6.QtWidgets import QPushButton
        page = about_page.construire([])
        qtbot.addWidget(page)
        libelles = {b.text() for b in page.findChildren(QPushButton)}
        assert "Discord" in libelles
        assert "Ko-fi" in libelles


class TestRemerciements:
    def test_sans_contributeur_ni_traducteur_aucune_rubrique(self, qtbot, monkeypatch):
        """Un titre « Remerciements » au-dessus de rien annoncerait une liste
        qui n'existe pas — la règle « rien de normal ne s'affiche »."""
        monkeypatch.setattr("src.ui.about_page.translator_credits", lambda: [])
        page = about_page.construire([])
        qtbot.addWidget(page)
        assert "Remerciements" not in _textes(page)

    def test_un_contributeur_est_affiche_avec_son_role(self, qtbot, monkeypatch):
        monkeypatch.setattr("src.ui.about_page.translator_credits", lambda: [])
        page = about_page.construire(
            [Contributor(name="Ludovic", role="Création", url="")])
        qtbot.addWidget(page)
        texte = _textes(page)
        assert "Remerciements" in texte
        assert "Ludovic" in texte and "Création" in texte

    def test_une_url_devient_un_lien(self, qtbot, monkeypatch):
        monkeypatch.setattr("src.ui.about_page.translator_credits", lambda: [])
        page = about_page.construire(
            [Contributor(name="Ludovic", role="", url="https://github.com/ludvdber")])
        qtbot.addWidget(page)
        assert '<a href="https://github.com/ludvdber"' in _textes(page)

    def test_sans_url_aucun_lien_mort(self, qtbot, monkeypatch):
        monkeypatch.setattr("src.ui.about_page.translator_credits", lambda: [])
        page = about_page.construire([Contributor(name="Anonyme", role="", url="")])
        qtbot.addWidget(page)
        assert "<a href" not in _textes(page)


class TestBalisageDuCatalogueJamaisInterprete:
    """Le catalogue est DISTANT : son texte ne doit jamais être du balisage.

    Ce qu'on empêche est l'INTERPRÉTATION — mise en page détournée par une
    chaîne extérieure, et lecture d'un fichier LOCAL par `<img src="file:///…">`.
    (Le motif longtemps écrit dans le projet — « une image distante déclenche
    une requête réseau » — est faux : mesuré le 2026-08-27, un QLabel n'a pas de
    gestionnaire réseau et n'émet rien. La règle tient, sa justification a
    changé.)
    """

    def test_le_nom_est_echappe(self, qtbot, monkeypatch):
        monkeypatch.setattr("src.ui.about_page.translator_credits", lambda: [])
        page = about_page.construire(
            [Contributor(name='<img src="file:///C:/secret.png">', role="", url="")])
        qtbot.addWidget(page)
        texte = _textes(page)
        assert "&lt;img" in texte
        assert "<img" not in texte

    def test_le_role_est_echappe(self, qtbot, monkeypatch):
        monkeypatch.setattr("src.ui.about_page.translator_credits", lambda: [])
        page = about_page.construire(
            [Contributor(name="X", role="<b>patron</b>", url="")])
        qtbot.addWidget(page)
        assert "&lt;b&gt;" in _textes(page)

    def test_l_apostrophe_reste_lisible(self, qtbot, monkeypatch):
        """`quote=False` : dans un contenu d'élément, échapper l'apostrophe ne
        protège de rien et remplit l'écran de `&#x27;`."""
        monkeypatch.setattr("src.ui.about_page.translator_credits", lambda: [])
        page = about_page.construire(
            [Contributor(name="L'équipe", role="", url="")])
        qtbot.addWidget(page)
        assert "L'équipe" in _textes(page)

    def test_les_traducteurs_ne_sont_pas_du_richtext(self, qtbot, monkeypatch):
        """Un fichier de langue est déposé par un contributeur : extérieur lui
        aussi. Il est affiché en PlainText, donc jamais interprété."""
        monkeypatch.setattr("src.ui.about_page.translator_credits",
                            lambda: [("Español", ["<b>quelqu'un</b>"])])
        page = about_page.construire([])
        qtbot.addWidget(page)
        porteurs = [lbl for lbl in _labels(page) if "quelqu" in lbl.text()]
        assert porteurs, "la ligne des traducteurs a disparu"
        for lbl in porteurs:
            assert lbl.textFormat() == Qt.TextFormat.PlainText

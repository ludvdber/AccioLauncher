"""L'échelle des rayons et les boutons communs (constat tra12, 2026-11-12).

Treize rayons différents sur les boutons pour trois formes, et le retour, les
rubriques d'un rail et les filtres recopiés page par page : `theme` porte trois
jetons, `composants` les boutons et leur style, une seule fois.
"""

import re
from pathlib import Path

from PyQt6.QtWidgets import QWidget

from src.ui import composants
from src.ui.theme import RAYON_CARTE, RAYON_CONTROLE, rayon_pastille

_UI = Path(__file__).resolve().parent.parent / "src" / "ui"


def _rayons(qss: str) -> set[int]:
    return {int(r) for r in re.findall(r"border-radius:\s*(\d+)px", qss)}


class TestJetons:
    def test_les_trois_formes(self):
        assert (RAYON_CONTROLE, RAYON_CARTE) == (6, 10)
        assert rayon_pastille(28) == 14 and rayon_pastille(38) == 19

    def test_la_feuille_commune_ne_parle_que_l_echelle(self):
        pastilles = {rayon_pastille(h) for h in (
            composants.HAUTEUR_FILTRE, composants.HAUTEUR_FILTRE_GRAND,
            composants.HAUTEUR_FILTRE_JAQUETTE, 38)}
        assert _rayons(composants.feuille_de_style()) <= {RAYON_CONTROLE, RAYON_CARTE} | pastilles

    def test_les_listes_ont_le_rayon_d_une_commande(self):
        for liste in (composants.LISTE, composants.LISTE_HAUTE):
            assert _rayons(liste) == {RAYON_CONTROLE}
            assert "::item:selected" in liste


class TestUneSeuleDefinition:
    """Le style du retour et des filtres ne vit QUE dans `composants`."""

    def test_aucune_page_ne_recopie_le_style(self):
        for regle in ("QPushButton#retour {", "QPushButton#filtre {",
                      "QPushButton#danger {", "QComboBox { background: #15152a"):
            porteurs = sorted(f.name for f in _UI.glob("*.py")
                              if regle in f.read_text(encoding="utf-8").replace("{{", "{"))
            assert porteurs == ["composants.py"], (regle, porteurs)

    def test_aucune_page_ne_rebatit_le_retour(self):
        """Le retour était bâti à la main dans sept pages, à l'identique."""
        porteurs = sorted(f.name for f in _UI.glob("*.py")
                          if 'setObjectName("retour")' in f.read_text(encoding="utf-8"))
        assert porteurs == ["composants.py"]

    def test_parametres_et_reglages_sans_rayon_hors_echelle(self):
        from src.ui import reglages_widgets, settings_panel
        permis = {RAYON_CONTROLE, RAYON_CARTE}
        assert _rayons(reglages_widgets._STYLE) <= permis
        assert _rayons(settings_panel.SettingsDialog._style(None)) <= permis
        assert _rayons(settings_panel._COMBO_STYLE) == {RAYON_CONTROLE}

    def test_les_cartes_des_defis_et_de_l_atelier(self):
        """tra12b : cartes des Défis à 12, encadré de format de l'Atelier à 13, au lieu de 10."""
        from src.ui import atelier_page, defis_page
        assert _rayons(defis_page._STYLE) == {RAYON_CARTE}
        assert RAYON_CARTE in _rayons(atelier_page._STYLE) and 13 not in _rayons(atelier_page._STYLE)


class TestBoutonsCommuns:
    def test_retour(self, qtbot):
        appels = []
        b = composants.bouton_retour("Bibliothèque", lambda: appels.append(1))
        qtbot.addWidget(b)
        assert b.objectName() == "retour" and not b.autoDefault() and not b.icon().isNull()
        b.click()
        assert appels == [1]

    def test_les_pages_a_rail_ont_la_meme_colonne(self):
        """f75 : 236, 270, 280 et 300 px ; le Journal des changements, au même en-tête que
        les réglages du jeu, faisait sauter la page. Une constante, aucune autre largeur."""
        import re
        # Les réglages d'un jeu et les Paramètres n'ont plus de rail (maquettes B et A, 2026-11-15) : leur
        # bandeau ; le Journal garde la colonne de ses versions.
        for nom in ("folio_page", "versions_dialog", "atelier_page"):
            source = Path(f"src/ui/{nom}.py").read_text(encoding="utf-8")
            assert "setFixedWidth(LARGEUR_RAIL)" in source, nom
            assert not re.search(r"^_LARGEUR_(RAIL|RUBRIQUES) = ", source, re.M), nom
        for nom in ("game_settings_dialog", "bandeau_jeu", "settings_panel"):
            source = Path(f"src/ui/{nom}.py").read_text(encoding="utf-8")
            assert not re.search(r"^_LARGEUR_(RAIL|RUBRIQUES) = ", source, re.M), nom
            assert "setFixedWidth(LARGEUR_RAIL)" not in source, nom

    def test_filtre_a_hauteur_fixe(self, qtbot):
        petit, grand = composants.filtre("Tous"), composants.filtre("Folio", grand=True)
        for b in (petit, grand):
            qtbot.addWidget(b)
            assert b.objectName() == "filtre" and b.isCheckable()
        assert petit.maximumHeight() == composants.HAUTEUR_FILTRE
        assert grand.maximumHeight() == composants.HAUTEUR_FILTRE_GRAND
        assert grand.property("grand") is True and petit.property("grand") is False

    def test_la_hauteur_fixe_ne_rogne_pas_le_texte(self, qtbot):
        """La pastille est ronde parce que sa hauteur est fixe : celle-ci doit
        couvrir ce que le texte (et le pictogramme d'une rubrique) demandent."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon, QPixmap

        hote = QWidget()
        qtbot.addWidget(hote)
        hote.setStyleSheet(composants.feuille_de_style())
        icone = QPixmap(18, 18)
        icone.fill()
        for grand, hauteur in ((False, composants.HAUTEUR_FILTRE),
                               (True, composants.HAUTEUR_FILTRE_GRAND)):
            b = composants.filtre("Cinématiques", grand=grand)
            b.setParent(hote)
            if grand:
                b.setIcon(QIcon(icone))
                b.setIconSize(QSize(18, 18))
            b.setMinimumHeight(0)
            b.setMaximumHeight(16777215)
            b.ensurePolished()
            assert b.sizeHint().height() <= hauteur, (grand, b.sizeHint().height())   # rien de rogné
            # Avant la refonte, 5 px de remplissage au-dessus et au-dessous
            # (6 pour une rubrique) : la hauteur fixe garde au moins cet air
            # autour de ce qui SE VOIT (lettres, pictogramme) et du cadre de
            # 1 px. Pas autour de la boîte de ligne : FreeType arrondit montant
            # et descendant chacun vers le haut (17 px sous Linux, 16 sous
            # Windows, même Gelasio), la CI Linux tombait à 9 px d'air.
            air = 12 if grand else 10
            encre = max(b.fontMetrics().tightBoundingRect(b.text()).height(),
                        b.iconSize().height() if grand else 0)
            assert encre + 2 + air <= hauteur, (grand, encre)

    def test_les_pastilles_des_pages_passent_par_le_composant(self, qtbot):
        from src.ui import choix_jeux

        class Jeu:
            cover_image = ""
            name = "Harry Potter"

        b = choix_jeux.pastille(Jeu(), "I")
        qtbot.addWidget(b)
        assert b.objectName() == "filtre" and b.maximumHeight() == composants.HAUTEUR_FILTRE

    def test_la_pastille_a_jaquette_garde_son_air(self, qtbot, monkeypatch):
        """Relecture tra12 : une jaquette de 24 px dans le filtre de 28 px ne
        gardait qu'1 px d'air ; la pastille reprend ses 36 px d'avant la refonte."""
        from PyQt6.QtGui import QPixmap
        from src.ui import choix_jeux

        jaquette = QPixmap(60, 80)
        jaquette.fill()
        monkeypatch.setattr(choix_jeux, "_jaquette", lambda _chemin: jaquette)

        class Jeu:
            cover_image = "hp1.jpg"
            name = "Harry Potter"

        hote = QWidget()
        qtbot.addWidget(hote)
        hote.setStyleSheet(composants.feuille_de_style())
        b = choix_jeux.pastille(Jeu(), "I")
        b.setParent(hote)
        assert b.property("jaquette") is True
        hauteur = composants.HAUTEUR_FILTRE_JAQUETTE
        assert (b.minimumHeight(), b.maximumHeight()) == (hauteur, hauteur)
        b.setMinimumHeight(0)
        b.setMaximumHeight(16777215)
        b.ensurePolished()
        assert b.sizeHint().height() + 10 <= hauteur, b.sizeHint().height()
        assert f"border-radius: {rayon_pastille(hauteur)}px" in composants.feuille_de_style()


class TestRails:
    def test_pastilles_des_parametres(self, qtbot):
        """Les rubriques des Paramètres sont les pastilles des réglages d'un jeu (maquette A, 2026-11-15)."""
        from src.ui.settings_panel import _RUBRIQUES, _Pastilles
        rangee = _Pastilles(_RUBRIQUES)
        qtbot.addWidget(rangee)
        assert [b.objectName() for b in rangee.boutons] == ["filtre"] * len(_RUBRIQUES)
        assert {b.maximumHeight() for b in rangee.boutons} == {composants.HAUTEUR_FILTRE_GRAND}
        rangee.boutons[1].click()
        assert rangee.currentRow() == 1


class TestTitresDePage:
    def test_une_seule_fabrique(self, qtbot):
        """f76 : Cinzel Decorative 29 ou 32 px selon la page, au même endroit."""
        from PyQt6.QtCore import Qt
        titre = composants.titre_page("Galerie")
        qtbot.addWidget(titre)
        assert titre.font().pointSizeF() == 22 and titre.textFormat() == Qt.TextFormat.PlainText
        # Les réglages d'un jeu n'ont plus de grand titre (maquette B, 2026-11-15) : la pastille cochée le dit.
        for nom in ("galerie_page", "folio_page", "atelier_page", "versions_dialog", "nouveautes_page"):
            source = Path(f"src/ui/{nom}.py").read_text(encoding="utf-8")
            assert "titre_page(" in source, nom
        for nom in ("galerie_page", "folio_page", "atelier_page", "versions_dialog", "nouveautes_page",
                    "game_settings_dialog", "bandeau_jeu"):
            source = Path(f"src/ui/{nom}.py").read_text(encoding="utf-8")
            assert not re.search(r"cinzel_decorative\(2\d\)", source), f"{nom} : un titre à part"

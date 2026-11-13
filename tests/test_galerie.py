"""La galerie des captures : la liste, les mois, la page, le partage."""

import os
from datetime import datetime
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage

from src.core import captures, galerie
from src.core.game_data import GameData
from src.core.i18n import set_language


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


def _jeu(id_jeu: str, nom: str) -> GameData:
    return GameData.from_dict({
        "id": id_jeu, "name": nom, "year": 2005, "description": "d", "developer": "d",
        "executable": f"{id_jeu}/jeu.exe", "cover_image": "c.jpg"})


def _capture(jeu: GameData, nom: str, quand: datetime, taille=(64, 36)) -> Path:
    dossier = captures.dossier(jeu)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    image = QImage(*taille, QImage.Format.Format_RGB32)
    image.fill(QColor("steelblue"))
    assert image.save(str(chemin), "PNG")
    os.utime(chemin, (quand.timestamp(), quand.timestamp()))
    return chemin


HP4 = _jeu("hp4", "Harry Potter et la Coupe de Feu")
HP5 = _jeu("hp5", "Harry Potter et l'Ordre du Phénix")


class TestListe:
    def test_les_plus_recentes_d_abord_tous_jeux_confondus(self):
        _capture(HP4, "a.png", datetime(2026, 9, 3, 20, 0))
        _capture(HP5, "b.png", datetime(2026, 10, 14, 21, 3))
        _capture(HP4, "c.png", datetime(2026, 10, 1, 18, 0))
        liste = galerie.lister([HP4, HP5])
        assert [c.chemin.name for c in liste] == ["b.png", "c.png", "a.png"]

    def test_groupees_par_mois(self):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        _capture(HP4, "c.png", datetime(2026, 10, 1))
        groupes = galerie.par_mois(galerie.lister([HP4, HP5]))
        assert [(cle, len(liste)) for cle, liste in groupes] == [((2026, 10), 2), ((2026, 9), 1)]

    def test_compte_par_jeu(self):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP4, "b.png", datetime(2026, 9, 4))
        assert galerie.compte_par_jeu(galerie.lister([HP4, HP5])) == {"hp4": 2}

    def test_sans_dossier_rien(self):
        assert galerie.lister([HP4, HP5]) == []

    def test_un_dossier_partage_n_est_lu_qu_une_fois(self):
        jumeau = _jeu("hp4b", "Harry Potter et la Coupe de Feu")
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        assert len(galerie.lister([HP4, jumeau])) == 1


pytest.importorskip("pytestqt")


class TestTextes:
    @pytest.mark.parametrize("nom,court", [
        ("Harry Potter et la Coupe de Feu", "La Coupe de Feu"),
        ("Harry Potter and the Goblet of Fire", "The Goblet of Fire"),
        ("Harry Potter y el cáliz de fuego", "El cáliz de fuego"),
        ("Autre jeu", "Autre jeu"),
    ])
    def test_nom_court(self, nom, court):
        from src.ui.galerie_page import nom_court
        assert nom_court(nom) == court

    def test_le_mois_en_capitales(self):
        from src.ui.galerie_page import mois
        assert mois(2026, 10) == "OCTOBRE 2026"


class TestPage:
    def _page(self, qtbot, jeu=""):
        from src.ui.galerie_page import GaleriePage
        page = GaleriePage([HP4, HP5], jeu=jeu)
        qtbot.addWidget(page)
        return page

    def test_vide_elle_le_dit_et_ne_propose_rien(self, qtbot):
        from PyQt6.QtWidgets import QLabel
        page = self._page(qtbot)
        assert page.choisie is None
        assert not page._partager.isEnabled()
        textes = " ".join(lbl.text() for lbl in page.findChildren(QLabel))
        assert "Pas encore de capture" in textes
        assert "F12 en jeu." in textes
        assert "inutile de le signaler" not in textes, "F12 marche dans HP1 à HP3 : le catalogue le dit"
        assert not page._vide.isHidden() and page._cote_cadre.isHidden()

    def test_ouvre_sur_la_plus_recente(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        page = self._page(qtbot)
        assert page.choisie.chemin.name == "b.png"
        assert "2560" not in page._details.text() and "64 × 36" in page._details.text()

    def test_le_filtre_ne_garde_que_le_jeu(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        page = self._page(qtbot)
        page.filtrer("hp4")
        visibles = [v.capture.chemin.name for v in page._vignettes if not v.isHidden()]
        assert visibles == ["a.png"]
        assert page.choisie.chemin.name == "a.png", "la choisie cachée laisse place à une visible"
        page.filtrer("")
        assert len([v for v in page._vignettes if not v.isHidden()]) == 2

    def test_un_filtre_sans_capture_vide_l_apercu(self, qtbot):
        """L'aperçu et ses boutons gardaient la capture d'un autre jeu (audit du 2026-11-02)."""
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        page.filtrer("hp5")
        assert page.choisie is None and page._titre_jeu.text() == ""
        assert not page._partager.isEnabled()
        assert page._vide.text() == "Pas encore de capture pour ce jeu."
        assert not page._vide.isHidden() and page._cote_cadre.isHidden(), "ni aperçu vierge ni boutons éteints"
        page.filtrer("")
        assert page.choisie.chemin.name == "a.png" and page._partager.isEnabled()
        assert page._vide.isHidden() and not page._cote_cadre.isHidden()

    def test_les_commandes_sont_des_ronds_a_icone_seule(self, qtbot):
        from src.ui.icon_button import ICONES
        page = self._page(qtbot)
        assert "copier" in ICONES
        for commande, nom in ((page._ouvrir, "Ouvrir l'image"), (page._copier, "Copier l'image"),
                              (page._dossier, "Ouvrir le dossier")):
            assert commande.objectName() == "rond" and not commande.text()
            assert commande.accessibleName() == nom and commande.toolTip() == nom
        assert page._partager.text() == "Partager sur Discord" and not page._partager.icon().isNull()

    def test_un_clic_sur_l_apercu_ouvre_l_image(self, qtbot, monkeypatch):
        from PyQt6.QtCore import Qt
        ouverts = []
        monkeypatch.setattr("src.ui.galerie_page.open_local_path", ouverts.append)
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        qtbot.mouseClick(page._apercu, Qt.MouseButton.LeftButton)
        assert ouverts == [str(chemin)]

    def test_pastilles_sans_chiffre_le_nombre_en_infobulle(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP4, "b.png", datetime(2026, 9, 4))
        page = self._page(qtbot)
        hp4, hp5, tous = page._filtres["hp4"], page._filtres["hp5"], page._filtres[""]
        assert not any(c.isdigit() for b in (hp4, hp5, tous) for c in b.text())
        assert "2 captures" in hp4.toolTip() and "2 captures" in tous.toolTip()
        assert hp5.property("vide") is True and "0" not in hp5.toolTip()

    def test_le_filtre_resserre_les_vignettes(self, qtbot, mise_en_page_stable):
        """Captures de deux jeux mêlées dans un mois : filtrer ne laisse aucun
        trou noir à la place des cachées (Ludo, 2026-10-24)."""
        for i, jeu in enumerate((HP4, HP5, HP4, HP5, HP4)):
            _capture(jeu, f"{i}.png", datetime(2026, 10, 1 + i))
        page = self._page(qtbot)
        page.resize(1400, 900)
        page.show()
        qtbot.waitExposed(page)
        page.filtrer("hp4")
        mise_en_page_stable(page)
        visibles = sorted((v for v in page._vignettes if not v.isHidden()), key=lambda v: v.x())
        assert len(visibles) == 3
        assert {v.y() for v in visibles} == {visibles[0].y()}, "les trois sur la même rangée"
        assert visibles[1].x() == visibles[0].x() + visibles[0].width() + 10

    def test_ouverte_sur_un_jeu(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        _capture(HP5, "b.png", datetime(2026, 10, 14))
        assert self._page(qtbot, "hp4").choisie.chemin.name == "a.png"

    def test_les_vignettes_se_chargent_apres_l_ouverture(self, qtbot):
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        assert page._vignettes[0]._pix is None
        qtbot.waitUntil(lambda: page._vignettes[0]._pix is not None, timeout=2000)

    def test_partager_copie_puis_ouvre_le_discord(self, qtbot, monkeypatch):
        from PyQt6.QtGui import QGuiApplication
        from src.core.liens import DISCORD_MEDIAS_URL
        ouverts = []
        monkeypatch.setattr("src.ui.galerie_page.open_url", ouverts.append)
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        page._partager.click()
        assert ouverts == [DISCORD_MEDIAS_URL], "le salon des captures, pas l'invitation"
        assert QGuiApplication.clipboard().image().width() == 64
        assert "Ctrl+V" in page._confirmation.text() and not page._confirmation.isHidden()

    def test_ouvrir_l_image_la_donne_a_la_visionneuse(self, qtbot, monkeypatch):
        ouverts = []
        monkeypatch.setattr("src.ui.galerie_page.open_local_path", ouverts.append)
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        page._ouvrir.click()
        assert ouverts == [str(chemin)], "l'image elle-même, pas son dossier"

    def test_vide_ouvrir_l_image_est_eteint(self, qtbot):
        assert not self._page(qtbot)._ouvrir.isEnabled()

    def test_une_image_illisible_ne_promet_rien(self, qtbot, monkeypatch):
        ouverts = []
        monkeypatch.setattr("src.ui.galerie_page.open_url", ouverts.append)
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = self._page(qtbot)
        chemin.write_bytes(b"pas une image")
        page._partager.click()
        assert ouverts == [], "Discord ne s'ouvre pas pour une image qui n'est pas copiée"
        assert "ne se lit pas" in page._confirmation.text()


class TestClavier:
    """Constat tra2 : un arrêt par vignette, 113 appuis pour atteindre « Partager
    sur Discord », et ↓ qui menait à la voisine de droite."""

    @pytest.fixture
    def grille(self, qtbot, mise_en_page_stable):
        """Sept captures d'un même mois, à 1400 px : trois colonnes (3 + 3 + 1)."""
        from PyQt6.QtWidgets import QApplication
        from src.ui.galerie_page import GaleriePage
        for i in range(7):
            _capture(HP4, f"{i}.png", datetime(2026, 10, 20 - i))
        page = GaleriePage([HP4, HP5])
        qtbot.addWidget(page)
        page.resize(1400, 900)
        page.show()
        page.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is page)
        mise_en_page_stable(page)
        v = page._vignettes
        assert [x.capture.chemin.name for x in v] == [f"{i}.png" for i in range(7)]
        assert len({x.y() for x in v[:3]}) == 1 and v[3].y() > v[0].y() and v[6].y() > v[3].y()
        v[0].setFocus(Qt.FocusReason.TabFocusReason)
        qtbot.waitUntil(v[0].hasFocus)
        return page, v

    def test_seule_la_choisie_est_dans_la_chaine_tab(self, grille):
        page, v = grille
        dans_la_chaine = [x for x in v if x.focusPolicy() & Qt.FocusPolicy.TabFocus]
        assert dans_la_chaine == [v[0]]
        assert all(x.focusPolicy() & Qt.FocusPolicy.ClickFocus for x in v), "le clic garde le focus"
        v[4].setChecked(True)
        assert [x for x in v if x.focusPolicy() & Qt.FocusPolicy.TabFocus] == [v[4]]

    def test_tab_quitte_la_grille_d_un_seul_appui(self, qtbot, grille):
        page, v = grille
        qtbot.keyClick(v[0], Qt.Key.Key_Tab)
        assert page._partager.hasFocus(), "Partager sur Discord juste après la grille"

    def test_les_fleches_suivent_rangees_et_colonnes(self, qtbot, grille):
        from PyQt6.QtCore import QPoint, QRect
        from PyQt6.QtWidgets import QApplication
        from src.ui import focus_visible
        focus_visible.install(QApplication.instance())   # posé une fois, comme au démarrage
        page, v = grille
        qtbot.keyClick(v[0], Qt.Key.Key_Right)
        assert v[1].hasFocus() and v[1].isChecked() and page.choisie == v[1].capture
        qtbot.keyClick(v[1], Qt.Key.Key_Down)
        assert v[4].hasFocus() and page.choisie == v[4].capture, "la rangée du dessous, même colonne"
        assert v[4].property("focusClavier") is True, "l'anneau du clavier suit"
        # Et il se VOIT : la vignette choisie avait déjà le cadre or, le focus ne changeait
        # pas un pixel (audit UI, 2026-11-13). L'anneau unique l'entoure.
        anneau = v[4].window().findChild(focus_visible._Anneau)
        qtbot.waitUntil(lambda: anneau.isVisible()
                        and anneau.geometry().contains(QRect(v[4].mapTo(v[4].window(), QPoint(0, 0)), v[4].size())))
        qtbot.keyClick(v[4], Qt.Key.Key_Down)
        assert v[6].hasFocus(), "rangée incomplète : la vignette la plus proche"
        qtbot.keyClick(v[6], Qt.Key.Key_Up)
        assert v[3].hasFocus()
        qtbot.keyClick(v[3], Qt.Key.Key_Left)
        assert v[2].hasFocus(), "← passe à la fin de la rangée d'avant"

    def test_les_bords(self, qtbot, grille):
        page, v = grille
        qtbot.keyClick(v[0], Qt.Key.Key_Left)
        assert v[0].hasFocus() and v[0].isChecked(), "rien avant la première"
        qtbot.keyClick(v[0], Qt.Key.Key_Up)
        assert page.focusWidget() in page._filtres.values(), "↑ sur la première rangée : les filtres"
        v[6].setChecked(True)
        v[6].setFocus(Qt.FocusReason.TabFocusReason)
        qtbot.keyClick(v[6], Qt.Key.Key_Right)
        assert v[6].hasFocus(), "rien après la dernière"
        qtbot.keyClick(v[6], Qt.Key.Key_Down)
        assert page._partager.hasFocus(), "↓ sur la dernière rangée : les actions"

    def test_une_vignette_cachee_est_sautee(self, grille):
        page, v = grille
        assert page.voisine(v[0], Qt.Key.Key_Right) is v[1]
        v[1].hide()
        assert page.voisine(v[0], Qt.Key.Key_Right) is v[2]
        assert page.voisine(v[1], Qt.Key.Key_Right) is None, "une cachée ne mène nulle part"

    def test_la_manette_garde_ses_fleches_dans_la_grille(self, grille):
        from src.ui.manette_nav import GARDE_FLECHES
        _page, v = grille
        assert all(x.property(GARDE_FLECHES) is True for x in v)


class TestDansCollections:
    def test_integree_sans_retour_ni_titre(self, qtbot):
        """Rubrique Captures des Collections : la page porte déjà le retour et le titre."""
        from PyQt6.QtWidgets import QPushButton
        from src.ui.galerie_page import GaleriePage
        page = GaleriePage([], integree=True)
        qtbot.addWidget(page)
        assert not [b for b in page.findChildren(QPushButton) if b.objectName() == "retour"]
        seule = GaleriePage([])
        qtbot.addWidget(seule)
        assert [b for b in seule.findChildren(QPushButton) if b.objectName() == "retour"]


class TestVignettesEnCache:
    """Une capture de 10 Mo coûtait 155 ms à chaque ouverture (2026-10-14)."""

    def test_rangee_puis_relue_sans_redecoder(self, qtbot, monkeypatch):
        from src.ui import galerie_page
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3), taille=(1920, 1080))
        premiere = galerie_page._vignette(chemin)
        cache = galerie.chemin_vignette(chemin)
        assert cache is not None and cache.is_file()
        assert premiere.width() == galerie_page._VIGNETTE.width() * 2

        def interdit(*_a):
            raise AssertionError("la capture a été redécodée")
        monkeypatch.setattr(galerie_page, "_lire", interdit)
        assert not galerie_page._vignette(chemin).isNull()

    def test_une_capture_remplacee_a_une_autre_vignette(self):
        chemin = _capture(HP4, "a.png", datetime(2026, 9, 3))
        avant = galerie.chemin_vignette(chemin)
        _capture(HP4, "a.png", datetime(2026, 9, 4), taille=(80, 45))
        assert galerie.chemin_vignette(chemin) != avant

    def test_capture_disparue(self, tmp_path):
        assert galerie.chemin_vignette(tmp_path / "absente.png") is None

    def test_fermer_la_page_arrete_le_chargement(self, qtbot):
        from src.ui.galerie_page import GaleriePage
        _capture(HP4, "a.png", datetime(2026, 9, 3))
        page = GaleriePage([HP4])
        qtbot.addWidget(page)
        page.accept()
        assert not page._chargeur.isActive()

    def test_l_apercu_arrive_en_grand_apres_coup(self, qtbot):
        from src.ui.galerie_page import GaleriePage
        _capture(HP4, "a.png", datetime(2026, 9, 3), taille=(1920, 1080))
        page = GaleriePage([HP4])
        qtbot.addWidget(page)
        page.show()
        qtbot.waitUntil(lambda: page._apercu_attendu is None, timeout=3000)
        assert not page._apercu.pixmap().isNull()

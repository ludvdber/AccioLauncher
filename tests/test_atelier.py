"""L'atelier des artistes : le contenu embarqué, les besoins mesurés, la page, la pastille."""

import json

import pytest

from src.core import atelier
from src.core.config import ATELIER_PATH
from src.core.i18n import set_language

LIBELLES = {atelier.JAQUETTE: "Jaquette", atelier.FOND: "Fond d'écran",
            "carree": "Carrée aujourd'hui", "taille": "{} × {} aujourd'hui",
            "priorite": "en priorité"}


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


class TestContenuEmbarque:
    def test_sept_metiers_dont_un_mesure(self):
        data = json.loads(ATELIER_PATH.read_text(encoding="utf-8"))
        ids = [m["id"] for m in data["metiers"]]
        assert ids == ["jaquettes", "bandes-annonces", "cartes", "textures", "chargement",
                       "sauvegardes", "videos"]
        assert [m["id"] for m in data["metiers"] if m.get("auto")] == ["jaquettes"]

    @pytest.mark.parametrize("langue", ["fr", "en", "es"])
    def test_chaque_texte_existe_dans_chaque_langue(self, langue):
        """Le repli sur le français cacherait une traduction oubliée."""
        data = json.loads(ATELIER_PATH.read_text(encoding="utf-8"))
        for m in data["metiers"]:
            for champ in ("nom", "ou", "texte"):
                assert m[champ].get(langue), (m["id"], champ)
            for f in m["formats"]:
                assert f.get(langue), (m["id"], f)
            for b in m["besoins"]:
                assert b["quoi"].get(langue) and b["detail"].get(langue), b
                assert b["etat"] in atelier.ETATS, b

    def test_aucun_texte_a_trou(self):
        """La maquette portait des « [à inventorier] » : rien de tel ne part."""
        brut = ATELIER_PATH.read_text(encoding="utf-8")
        assert "[" not in brut.replace('"metiers": [', "").replace('"formats": [', "") \
            .replace('"besoins": [', "")


class TestBesoinsMesures:
    def test_toutes_les_images_les_petites_en_priorite(self):
        """Toutes, pas seulement les trop petites : le but est aussi de ne plus
        dépendre des images de Warner (Ludo, 2026-10-14)."""
        besoins = atelier.besoins_mesures(
            {"hp2": ((1024, 1024), (1920, 620)), "hp3": ((1080, 1500), (920, 430))}, LIBELLES)
        assert [(b.jeu, b.genre, b.detail, b.prioritaire) for b in besoins] == [
            ("HP2", atelier.JAQUETTE, "Carrée aujourd'hui · en priorité", True),
            ("HP2", atelier.FOND, "1920 × 620 aujourd'hui", False),
            ("HP3", atelier.JAQUETTE, "1080 × 1500 aujourd'hui", False),
            ("HP3", atelier.FOND, "920 × 430 aujourd'hui · en priorité", True)]

    def test_une_image_absente_n_a_pas_de_taille_a_dire(self):
        besoins = atelier.besoins_mesures({"hp9": ((0, 0), (0, 0))}, LIBELLES)
        assert [b.detail for b in besoins] == ["en priorité", "en priorité"]

    @pytest.mark.parametrize("id_jeu,court", [("hp1", "HP1"), ("hp7a", "HP7 · 1"),
                                              ("hp7b", "HP7 · 2"), ("bonus", "BONUS")])
    def test_nom_court(self, id_jeu, court):
        assert atelier.court(id_jeu) == court


class TestLecture:
    def test_le_metier_mesure_prend_les_mesures(self):
        mesure = atelier.Besoin("HP3", "Fond d'écran", "", atelier.CHERCHE, atelier.FOND)
        metiers = atelier.charger([mesure])
        assert metiers[0].id == "jaquettes" and metiers[0].besoins == (mesure,)

    def test_sans_mesure_le_metier_disparait(self):
        """Toutes les images à la hauteur : plus rien à proposer dans ce métier."""
        assert "jaquettes" not in [m.id for m in atelier.charger([])]

    def test_ouverts_ne_compte_que_ce_qui_cherche(self, tmp_path):
        chemin = tmp_path / "a.json"
        chemin.write_text(json.dumps({"metiers": [{"id": "x", "nom": "X", "besoins": [
            {"jeu": "HP1", "quoi": "a", "etat": "cherche"},
            {"jeu": "HP1", "quoi": "b", "etat": "cours"},
            {"jeu": "HP1", "quoi": "c", "etat": "fait"},
            {"jeu": "HP1", "quoi": "d", "etat": "inconnu"}]}]}), encoding="utf-8")
        (metier,) = atelier.charger([], "fr", chemin)
        assert len(metier.besoins) == 3 and metier.ouverts == 1

    @pytest.mark.parametrize("brut", ["", "{", "[]", '{"metiers": 3}'])
    def test_un_fichier_fautif_rend_une_liste_vide(self, tmp_path, brut):
        chemin = tmp_path / "a.json"
        chemin.write_text(brut, encoding="utf-8")
        assert atelier.charger([], "fr", chemin) == []

    def test_en_espagnol(self):
        noms = [m.nom for m in atelier.charger([], "es")]
        assert "Texturas del juego" in noms


pytest.importorskip("pytestqt")


class _Jeu:
    def __init__(self, id_jeu, jaquette="hp1_cover.jpg"):
        self.id = id_jeu
        self.cover_image = jaquette


class TestPage:
    def _page(self, qtbot, metier=""):
        from src.ui.atelier_page import AtelierPage
        page = AtelierPage([_Jeu("hp3")], metier=metier)
        qtbot.addWidget(page)
        return page

    def test_ouvre_sur_le_premier_metier(self, qtbot):
        page = self._page(qtbot)
        assert page.metier_affiche == page.metiers[0].id

    def test_ouvre_sur_le_metier_demande(self, qtbot):
        assert self._page(qtbot, "videos").metier_affiche == "videos"

    def test_chaque_besoin_a_sa_ligne(self, qtbot):
        from PyQt6.QtWidgets import QWidget
        page = self._page(qtbot)
        for m in page.metiers:
            page.choisir(m.id)
        lignes = [w for w in page.findChildren(QWidget) if w.objectName() == "besoin"]
        assert len(lignes) == sum(len(m.besoins) for m in page.metiers)

    def test_seul_le_metier_affiche_est_construit(self, qtbot):
        """Les sept pages d'avance coûtaient 550 ms d'ouverture (2026-10-14)."""
        page = self._page(qtbot)
        assert page._details.count() == 1
        page.choisir(page.metiers[1].id)
        page.choisir(page.metiers[0].id)
        assert page._details.count() == 2
        assert page.metier_affiche == page.metiers[0].id

    def test_choisir_un_metier_change_la_page(self, qtbot):
        page = self._page(qtbot)
        page.choisir("textures")
        assert page.metier_affiche == "textures"

    def test_ouvrir_le_discord(self, qtbot, monkeypatch):
        from PyQt6.QtWidgets import QPushButton
        from src.core.liens import DISCORD_URL
        ouverts = []
        monkeypatch.setattr("src.ui.atelier_page.open_url", ouverts.append)
        page = self._page(qtbot)
        next(b for b in page.findChildren(QPushButton) if b.text() == "Ouvrir le Discord").click()
        assert ouverts == [DISCORD_URL]

    def test_bibliotheque_ferme_la_page(self, qtbot):
        from PyQt6.QtWidgets import QPushButton
        page = self._page(qtbot)
        fermee = []
        page.finished.connect(fermee.append)
        page.findChild(QPushButton, "retour").click()
        assert fermee


def test_la_fiche_ne_porte_plus_de_pastille_d_atelier(make_window):
    """Ludo, 2026-11-02 : « Ce fond cherche un artiste » retiré de la fiche,
    l'atelier s'ouvre par « Contribuer »."""
    from PyQt6.QtWidgets import QPushButton
    win = make_window()
    assert not hasattr(win._detail, "_pastille_atelier")
    assert not any("cherche un artiste" in (b.text() or "") for b in win._detail.findChildren(QPushButton))

"""Nouveautés du launcher : le contenu embarqué, quand la page s'ouvre, ce qu'elle montre."""

import json

import pytest

from src.core import nouveautes
from src.core.config import APP_VERSION, NOUVEAUTES_PATH
from src.core.i18n import set_language


@pytest.fixture(autouse=True)
def _francais():
    set_language("fr")
    yield
    set_language("fr")


def _fichier(tmp_path, entree):
    chemin = tmp_path / "nouveautes.json"
    chemin.write_text(json.dumps({"versions": [entree]}, ensure_ascii=False), encoding="utf-8")
    return chemin


class TestContenuEmbarque:
    def test_la_version_courante_a_ses_nouveautes(self):
        """Une release sans sa page passerait sous silence tout ce qu'elle apporte."""
        contenu = nouveautes.charger()
        assert contenu is not None, f"aucune entrée pour {APP_VERSION} dans nouveautes.json"
        assert contenu.version == APP_VERSION
        assert contenu.points_forts and contenu.changements

    @pytest.mark.parametrize("langue", ["fr", "en", "es"])
    def test_chaque_texte_existe_dans_chaque_langue(self, langue):
        """Le repli sur le français cacherait une traduction oubliée."""
        data = json.loads(NOUVEAUTES_PATH.read_text(encoding="utf-8"))
        for entree in data["versions"]:
            for point in entree["points_forts"]:
                assert point["titre"].get(langue) and point["texte"].get(langue), point
            for changement in entree["changements"]:
                assert changement["texte"].get(langue), changement
            if "annonce" in entree:
                annonce = entree["annonce"]
                assert annonce["titre"].get(langue), annonce["titre"]
                for paragraphe in annonce["paragraphes"]:
                    assert paragraphe.get(langue), paragraphe
                if "appel" in annonce:
                    assert annonce["appel"].get(langue), annonce["appel"]

    def test_la_1_3_1_annonce_la_fin_des_jeux_livres(self):
        """Ludo, 2026-10-30 : prévenir dès la 1.3.1, et renvoyer vers le Discord.
        Jamais une source de jeux : seulement de l'aide."""
        annonce = nouveautes.charger("1.3.1", "fr").annonce
        assert annonce is not None and annonce.discord and "Discord" in annonce.appel
        tout = " ".join(annonce.paragraphes + (annonce.appel,))
        assert "votre copie" in tout and "Discord" in tout
        assert "télécharg" not in tout.lower()

    def test_les_icones_existent(self):
        from src.ui.icon_button import ICONES
        data = json.loads(NOUVEAUTES_PATH.read_text(encoding="utf-8"))
        for entree in data["versions"]:
            for point in entree["points_forts"]:
                assert point["icone"] in ICONES, point["icone"]

    def test_genres_connus(self):
        data = json.loads(NOUVEAUTES_PATH.read_text(encoding="utf-8"))
        for entree in data["versions"]:
            assert {c["genre"] for c in entree["changements"]} <= set(nouveautes.GENRES)


class TestLecture:
    def test_repli_sur_le_francais(self, tmp_path):
        chemin = _fichier(tmp_path, {"version": "9.0", "changements": [
            {"genre": "corrige", "texte": {"fr": "Réparé", "en": ""}}]})
        contenu = nouveautes.charger("9.0", "en", chemin)
        assert contenu.changements[0].texte == "Réparé"

    def test_rangees_nouveau_ameliore_corrige(self, tmp_path):
        chemin = _fichier(tmp_path, {"version": "9.0", "changements": [
            {"genre": "corrige", "texte": "c"}, {"genre": "nouveau", "texte": "n"},
            {"genre": "ameliore", "texte": "a"}, {"genre": "inconnu", "texte": "x"}]})
        contenu = nouveautes.charger("9.0", "fr", chemin)
        assert [c.genre for c in contenu.changements] == ["nouveau", "ameliore", "corrige"]

    @pytest.mark.parametrize("brut", ["", "{", "[]", '{"versions": 3}',
                                      '{"versions": [{"version": "9.0", "changements": 5}]}'])
    def test_un_fichier_fautif_rend_none(self, tmp_path, brut):
        chemin = tmp_path / "n.json"
        chemin.write_text(brut, encoding="utf-8")
        assert nouveautes.charger("9.0", "fr", chemin) is None

    def test_une_autre_version_rend_none(self, tmp_path):
        chemin = _fichier(tmp_path, {"version": "9.0", "changements": [{"genre": "nouveau", "texte": "n"}]})
        assert nouveautes.charger("9.1", "fr", chemin) is None

    def test_une_carte_sans_texte_est_ecartee(self, tmp_path):
        chemin = _fichier(tmp_path, {"version": "9.0", "points_forts": [
            {"icone": "ecran", "titre": "T", "texte": ""}],
            "changements": [{"genre": "nouveau", "texte": "n"}]})
        assert nouveautes.charger("9.0", "fr", chemin).points_forts == ()

    def test_le_nom_de_la_version(self, tmp_path):
        """Un nom commun à toutes les langues, ou traduit ; absent : vide."""
        entree = {"version": "9.0", "changements": [{"genre": "nouveau", "texte": "n"}]}
        assert nouveautes.charger("9.0", "en", _fichier(tmp_path, {**entree, "nom": "Lumos"})).nom == "Lumos"
        traduit = {**entree, "nom": {"fr": "Le Terrier", "en": "The Burrow"}}
        assert nouveautes.charger("9.0", "en", _fichier(tmp_path, traduit)).nom == "The Burrow"
        assert nouveautes.charger("9.0", "fr", _fichier(tmp_path, entree)).nom == ""

    def test_l_annonce(self, tmp_path):
        entree = {"version": "9.0", "annonce": {
            "titre": {"fr": "Titre", "en": "Title"},
            "paragraphes": [{"fr": "Un", "en": "One"}, {"fr": ""}, "Deux"], "discord": True}}
        annonce = nouveautes.charger("9.0", "en", _fichier(tmp_path, entree)).annonce
        assert annonce == nouveautes.Annonce("Title", ("One", "Deux"), True)

    @pytest.mark.parametrize("annonce", [
        None, "texte", {"titre": "T"}, {"titre": "", "paragraphes": ["p"]},
        {"titre": "T", "paragraphes": [""]}])
    def test_une_annonce_incomplete_est_ignoree(self, tmp_path, annonce):
        entree = {"version": "9.0", "annonce": annonce,
                  "changements": [{"genre": "nouveau", "texte": "n"}]}
        assert nouveautes.charger("9.0", "fr", _fichier(tmp_path, entree)).annonce is None

    def test_discord_seulement_si_vrai(self, tmp_path):
        entree = {"version": "9.0", "annonce": {"titre": "T", "paragraphes": ["p"], "discord": "oui"}}
        assert not nouveautes.charger("9.0", "fr", _fichier(tmp_path, entree)).annonce.discord


class TestQuandMontrer:
    def test_apres_une_mise_a_jour(self):
        assert nouveautes.a_montrer("1.1.5")

    def test_config_d_avant_la_1_1_6(self):
        assert nouveautes.a_montrer("")

    def test_pas_deux_fois(self):
        assert not nouveautes.a_montrer(APP_VERSION)

    def test_pas_en_revenant_a_une_version_plus_ancienne(self):
        assert not nouveautes.a_montrer("99.0.0")

    def test_pas_sans_contenu(self, monkeypatch):
        monkeypatch.setattr(nouveautes, "charger", lambda *a, **k: None)
        assert not nouveautes.a_montrer("1.1.5")


pytest.importorskip("pytestqt")


class TestPage:
    def _page(self, qtbot, apres=True):
        from src.ui.nouveautes_page import NouveautesPage
        page = NouveautesPage(nouveautes.charger(), apres_mise_a_jour=apres)
        qtbot.addWidget(page)
        return page

    def _textes(self, page):
        from PyQt6.QtWidgets import QLabel
        return [lbl.text() for lbl in page.findChildren(QLabel)]

    def test_apres_une_mise_a_jour_elle_le_dit(self, qtbot):
        textes = self._textes(self._page(qtbot))
        assert "MISE À JOUR INSTALLÉE" in textes
        assert not any("vos jeux et vos réglages sont là" in t for t in textes), "un état normal ne se dit pas"

    def test_rouverte_depuis_a_propos_elle_ne_le_redit_pas(self, qtbot):
        textes = self._textes(self._page(qtbot, apres=False))
        assert "NOUVEAUTÉS" in textes
        assert not any("vos jeux et vos réglages" in t for t in textes)

    def test_le_nom_de_la_version_sous_le_numero(self, qtbot):
        from PyQt6.QtWidgets import QLabel
        page = self._page(qtbot)
        # Le nom de la version COURANTE (« Revelio · Folio Magi » en 1.2.0) : écrit
        # en dur, le test cassait à chaque release.
        assert page.findChild(QLabel, "nomVersion").text() == nouveautes.charger().nom

    @pytest.mark.parametrize("largeur", [1000, 1280, 1920])
    def test_les_cartes_montrent_tout_leur_texte(self, qtbot, largeur):
        # Bornées à leur `sizeHint`, calculée pour une autre largeur, les cartes
        # coupaient leur dernière ligne (2026-10-26).
        from PyQt6.QtWidgets import QLabel
        from src.ui.nouveautes_page import _CartePointFort
        page = self._page(qtbot)
        page.resize(largeur, 900)
        page.show()
        qtbot.waitExposed(page)
        for carte in page.findChildren(_CartePointFort):
            for lbl in carte.findChildren(QLabel):
                if lbl.wordWrap():
                    assert lbl.height() >= lbl.heightForWidth(lbl.width()), lbl.text()[:40]

    def test_le_bas_se_fond_tant_qu_il_reste_a_lire(self, qtbot):
        """Les cartes du bas étaient coupées net par le pied (revue du 2026-11-01)."""
        from PyQt6.QtWidgets import QScrollArea
        page = self._page(qtbot)
        page.resize(1000, 520)
        page.show()
        qtbot.waitExposed(page)
        zone = page.findChild(QScrollArea)
        barre = zone.verticalScrollBar()
        assert barre.maximum() > 0, "la page doit déborder à 520 px de haut"
        assert page.fondu.isVisible()
        assert page.fondu.geometry().bottom() == zone.viewport().geometry().bottom()
        barre.setValue(barre.maximum())
        assert not page.fondu.isVisible(), "tout est lu : plus de fondu"
        page.resize(1000, 4000)
        qtbot.waitUntil(lambda: barre.maximum() == 0)
        assert not page.fondu.isVisible()

    def test_chaque_changement_a_sa_ligne(self, qtbot):
        from src.ui.nouveautes_page import _LigneChangement
        page = self._page(qtbot)
        assert len(page.findChildren(_LigneChangement)) == len(page.nouveautes.changements)

    def test_aller_a_la_bibliotheque_ferme_la_page(self, qtbot):
        from PyQt6.QtWidgets import QPushButton
        page = self._page(qtbot)
        fermee = []
        page.finished.connect(fermee.append)
        next(b for b in page.findChildren(QPushButton)
             if b.text() == "Aller à la bibliothèque").click()
        assert fermee

    def test_toutes_les_versions_mene_a_github(self, qtbot, monkeypatch):
        from PyQt6.QtWidgets import QLabel
        from src.core.liens import NOTES_VERSIONS_URL
        ouverts = []
        monkeypatch.setattr("src.ui.nouveautes_page.open_url", ouverts.append)
        page = self._page(qtbot)
        lien = page.findChild(QLabel, "toutesLesVersions")
        lien.linkActivated.emit(NOTES_VERSIONS_URL)
        assert ouverts == [NOTES_VERSIONS_URL]

    def test_l_annonce_avant_les_cartes_et_son_bouton_discord(self, qtbot, monkeypatch):
        from src.core.liens import DISCORD_URL
        from src.ui.nouveautes_page import _CarteAnnonce, _CartePointFort
        ouverts = []
        monkeypatch.setattr("src.ui.nouveautes_page.open_url", ouverts.append)
        page = self._page(qtbot)
        page.resize(1280, 900)
        page.show()
        qtbot.waitExposed(page)
        annonce = page.findChild(_CarteAnnonce)
        assert annonce is not None
        from PyQt6.QtWidgets import QLabel
        assert annonce.findChild(QLabel, "appelAnnonce").text() == page.nouveautes.annonce.appel
        premiere_carte = page.findChildren(_CartePointFort)[0]
        assert annonce.mapTo(page, annonce.rect().topLeft()).y() < \
            premiere_carte.mapTo(page, premiere_carte.rect().topLeft()).y()
        assert annonce.rejoindre.objectName() == "principal"
        annonce.rejoindre.click()
        assert ouverts == [DISCORD_URL]


class TestAProposOuvreLaPage:
    def test_le_numero_de_version_ouvre_les_nouveautes(self, qtbot, monkeypatch):
        from PyQt6.QtWidgets import QLabel
        from src.ui import about_page
        ouverts, demandes = [], []
        monkeypatch.setattr(about_page, "open_url", ouverts.append)
        page = about_page.construire([], ouvrir_nouveautes=lambda: demandes.append(1))
        qtbot.addWidget(page)
        version = page.findChild(QLabel, "versions")
        assert 'href="nouveautes"' in version.text()
        version.linkActivated.emit("nouveautes")
        assert demandes == [1] and ouverts == []

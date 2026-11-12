"""Paramètres refaits (2026-10-09) : rubriques à gauche, cartes, chemin coupé
au milieu, barre du disque, retour vers la bibliothèque."""

from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402

from src.core.config import Config  # noqa: E402
from src.core.game_manager import GameManager  # noqa: E402
from src.ui import composants  # noqa: E402
from src.ui.composants import Chemin as _Chemin  # noqa: E402
from src.ui.settings_panel import SettingsDialog  # noqa: E402


@pytest.fixture
def dialogue(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    cfg = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache", langue="fr")
    dlg = SettingsDialog(cfg, GameManager(cfg))
    qtbot.addWidget(dlg)
    yield dlg
    dlg._shutdown_scan()


class TestChemin:
    def test_coupe_au_milieu_et_garde_le_chemin_entier(self, qtbot):
        chemin = r"D:\Un dossier très long\encore plus long\et encore\AccioLauncher"
        lbl = _Chemin(chemin)
        qtbot.addWidget(lbl)
        lbl.show()   # règle 48 : un widget caché ne reçoit son resizeEvent qu'à l'affichage
        lbl.resize(160, 30)
        visible = super(_Chemin, lbl).text()
        assert "…" in visible
        assert visible.startswith("D:") and visible.endswith("Launcher")
        assert lbl.text() == chemin and lbl.toolTip() == chemin


class TestDialogue:
    def test_quatre_rubriques_et_quatre_pages(self, dialogue):
        assert dialogue._nav.count() == dialogue._pages.count() == 4

    def test_pas_de_retour_en_double(self, dialogue, qtbot):
        """L'onglet Bibliothèque du haut ferme la page : pas de second bouton."""
        from PyQt6.QtWidgets import QPushButton
        assert dialogue.findChild(QPushButton, "retour") is None

    def test_le_scan_remplit_la_ligne_et_la_legende(self, dialogue):
        dialogue._on_scan_done(3, 9_800_000_000)
        assert dialogue._installed_label.text().startswith("3 jeux installés, ")
        # Le poids est dit une fois, sur la ligne du dessus.
        assert not [lbl.text() for lbl in dialogue.findChildren(composants.QLabel)
                    if lbl.text().startswith("Vos jeux ·")]
        assert dialogue._barre_disque._jeux > 0

    def test_plus_de_phrase_de_methode_en_pied(self, dialogue):
        """« Échap pour revenir » doublait l'onglet du haut, et ne valait pas à la manette."""
        for rang in range(dialogue._nav.count()):
            dialogue._nav.setCurrentRow(rang)
        textes = [lbl.text() for lbl in dialogue.findChildren(composants.QLabel)]
        assert not [t for t in textes if "Échap" in t or "Appliqué immédiatement" in t]

    def test_la_ligne_de_redemarrage_attend_un_changement(self, dialogue, qtbot):
        dialogue.show()
        dialogue._nav.setCurrentRow(0)
        assert not dialogue._lang_hint.isVisible()
        autre = next(i for i in range(dialogue._lang_combo.count())
                     if dialogue._lang_combo.itemData(i) != "fr")
        dialogue._lang_combo.setCurrentIndex(autre)
        assert dialogue._lang_hint.isVisible() and dialogue._lang_restart.isVisible()

    def test_chaque_interrupteur_a_un_nom(self, dialogue):
        from src.ui.toggle_switch import ToggleSwitch
        for bascule in dialogue.findChildren(ToggleSwitch):
            assert bascule.accessibleName()


    def test_la_partie_sur_discord_suit_la_presence(self, dialogue):
        """« Montrer où j'en suis » n'a de sens qu'avec la carte Discord : grisée
        sans elle, sa valeur intacte, et enregistrée comme les autres cases."""
        dialogue.construire_rubrique(2)     # Intégrations, bâtie à sa visite
        ligne, case = dialogue._ligne_discord_partie, dialogue._tgl_discord_partie
        assert ligne.isEnabled() and case.isChecked()
        dialogue._tgl_discord._basculer()       # un clic (setChecked n'émet rien)
        assert not ligne.isEnabled() and ligne.graphicsEffect() is not None
        assert case.isChecked(), "griser ne change pas le choix"
        dialogue._tgl_discord._basculer()
        assert ligne.isEnabled() and ligne.graphicsEffect() is None
        case._basculer()
        assert dialogue.config.discord_partie is False
        assert Config.load().discord_partie is False

    def test_presence_eteinte_a_l_ouverture_la_case_est_grisee(self, qtbot, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        cfg = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache", langue="fr",
                     discord_presence=False)
        dlg = SettingsDialog(cfg, GameManager(cfg))
        qtbot.addWidget(dlg)
        try:
            dlg.construire_rubrique(2)
            assert not dlg._ligne_discord_partie.isEnabled()
        finally:
            dlg._shutdown_scan()

class TestComposants:
    def test_carte_pose_un_filet_entre_les_lignes(self, qtbot):
        carte = composants.Carte()
        qtbot.addWidget(carte)
        carte.ajouter(composants.LigneReglage("Un"))
        carte.ajouter(composants.LigneReglage("Deux"))
        filets = carte.findChildren(composants.QFrame, "separateur")
        assert len(filets) == 1

    def test_le_texte_n_est_jamais_interprete(self, qtbot):
        lbl = composants.texte("<b>x</b>")
        qtbot.addWidget(lbl)
        assert lbl.textFormat() == Qt.TextFormat.PlainText

    def test_description_vide_cachee(self, qtbot):
        ligne = composants.LigneReglage("Titre")
        qtbot.addWidget(ligne)
        ligne.show()
        assert not ligne.description.isVisible()
        ligne.decrire("Une phrase")
        assert ligne.description.isVisible()


def _un_jeu_installe(dialogue, monkeypatch, nombre=1):
    from types import SimpleNamespace
    from src.core.game_manager import GameState
    entrees = [SimpleNamespace(state=GameState.INSTALLED, game=SimpleNamespace(id=f"jeu{i}"))
               for i in range(nombre)]
    monkeypatch.setattr(dialogue, "manager", SimpleNamespace(
        get_games=lambda: entrees, get_game_path=lambda _id: None))


class TestChangerLeDossier:
    """Rien n'est déplacé : les jeux installés restent dans l'ancien dossier."""

    def test_le_bouton_n_est_pas_l_action_mise_en_avant(self, dialogue):
        from PyQt6.QtWidgets import QPushButton
        changer = next(b for b in dialogue.findChildren(QPushButton) if b.text() == "Changer…")
        assert changer.objectName() == "secondaire"

    def test_annuler_ne_change_rien(self, dialogue, monkeypatch, tmp_path):
        _un_jeu_installe(dialogue, monkeypatch, 8)
        vu = {}
        monkeypatch.setattr("src.ui.settings_panel.message",
                            lambda _p, _i, _t, contenu, choix, defaut: vu.update(
                                contenu=contenu, choix=choix, defaut=defaut) or 1)
        avant = dialogue.config.install_path
        ancien_scan = dialogue._scan_worker
        dialogue.changer_dossier(tmp_path / "ailleurs")
        assert dialogue.config.install_path == avant
        assert dialogue._scan_worker is ancien_scan
        assert "Vos 8 jeux" in vu["contenu"] and str(avant) in vu["contenu"]
        assert vu["choix"] == ("Changer", "Annuler") and vu["defaut"] == 1

    def test_confirmer_pose_le_dossier_et_relance_le_scan(self, dialogue, monkeypatch, tmp_path, qtbot):
        _un_jeu_installe(dialogue, monkeypatch)
        monkeypatch.setattr("src.ui.settings_panel.message", lambda *a, **k: 0)
        ancien_scan = dialogue._scan_worker
        with qtbot.waitSignal(dialogue.config_changed, timeout=1000):
            dialogue.changer_dossier(tmp_path / "ailleurs")
        assert dialogue.config.install_path == tmp_path / "ailleurs"
        assert dialogue._path_label.text() == str(tmp_path / "ailleurs")
        assert dialogue._scan_worker is not ancien_scan

    def test_sans_jeu_installe_aucune_question(self, dialogue, monkeypatch, tmp_path):
        def jamais(*_a, **_k):
            raise AssertionError("rien à perdre : pas de question")
        monkeypatch.setattr("src.ui.settings_panel.message", jamais)
        dialogue.changer_dossier(tmp_path / "ailleurs")
        assert dialogue.config.install_path == tmp_path / "ailleurs"

    def test_le_meme_dossier_ne_demande_rien(self, dialogue, monkeypatch):
        _un_jeu_installe(dialogue, monkeypatch)
        def jamais(*_a, **_k):
            raise AssertionError("rien ne change")
        monkeypatch.setattr("src.ui.settings_panel.message", jamais)
        dialogue.changer_dossier(dialogue.config.install_path)


class TestBandesAnnonces:
    @pytest.fixture
    def page(self, dialogue, monkeypatch):
        from types import SimpleNamespace
        from src.ui import settings_panel
        presentes = {"n": 3}
        monkeypatch.setattr(dialogue, "_trailers", lambda: (1, 2, 3))
        monkeypatch.setattr(settings_panel.trailer_store, "nombre_present", lambda _l: presentes["n"])
        monkeypatch.setattr(settings_panel.trailer_store, "poids_disque", lambda: 1_100_000_000)
        monkeypatch.setattr(settings_panel.trailer_store, "poids_a_telecharger", lambda _l: 400)
        dialogue.construire_rubrique(1)
        dialogue.supprimees = []
        dialogue._store = SimpleNamespace(
            is_busy=False, supprimer_tout=lambda: dialogue.supprimees.append(1), start=lambda _l: None)
        dialogue.presentes = presentes
        dialogue.config.trailers_optin = True
        return dialogue

    def test_supprimer_n_est_pas_le_bouton_or(self, page):
        page._refresh_trailers()
        assert page._btn_trailers.text() == "Supprimer"
        assert page._btn_trailers.objectName() == "secondaire"
        assert page._lbl_trailers.text().startswith("3 sur le disque (")
        page.presentes["n"] = 1
        page._refresh_trailers()
        assert page._btn_trailers.objectName() == "principal"
        assert page._lbl_trailers.text() == "1 sur 3"

    def test_annuler_garde_les_bandes_annonces(self, page, monkeypatch):
        vu = {}
        monkeypatch.setattr("src.ui.settings_panel.message",
                            lambda *a, **k: vu.update(k) or 1)
        page._on_trailers_clicked()
        assert page.supprimees == [] and page.config.trailers_optin is True
        assert vu["choix"] == ("Supprimer", "Annuler") and vu["defaut"] == 1

    def test_confirmer_supprime_et_dit_non(self, page, monkeypatch):
        monkeypatch.setattr("src.ui.settings_panel.message", lambda *a, **k: 0)
        page._on_trailers_clicked()
        assert page.supprimees == [1] and page.config.trailers_optin is False


class TestRevueDesParametres:
    def test_une_seule_fleche_sur_les_listes(self):
        """Sans `::drop-down`, le bouton natif restait sous le chevron peint."""
        from src.ui.settings_panel import _COMBO_STYLE
        assert "QComboBox::drop-down { border: none; width: 18px; }" in _COMBO_STYLE

    def test_la_rubrique_dit_qu_elle_porte_le_son(self):
        from src.ui.settings_panel import _RUBRIQUES
        assert _RUBRIQUES[1][0] == "Son et image"

    def test_une_carte_d_une_ligne_n_a_pas_de_surtitre(self, dialogue):
        textes = {lbl.text() for lbl in dialogue.findChildren(composants.QLabel)}
        assert "DOSSIER DES JEUX" in textes, "plusieurs lignes : le surtitre reste"
        assert not textes & {"LANGUE", "SAUVEGARDES", "DÉCOUVRIR", "DÉSINSTALLER"}

    def test_desinstaller_est_un_lien_discret(self, dialogue):
        from PyQt6.QtWidgets import QPushButton
        lien = next(b for b in dialogue.findChildren(QPushButton) if b.text() == "Désinstaller…")
        assert lien.objectName() == "lienDiscret"
        textes = {lbl.text() for lbl in dialogue.findChildren(composants.QLabel)}
        assert "Accio Launcher" in textes and "Désinstaller Accio Launcher" not in textes

    def test_revenir_a_une_copie_fond_dans_l_interrupteur(self, dialogue):
        textes = {lbl.text() for lbl in dialogue.findChildren(composants.QLabel)}
        assert "Revenir à une copie" not in textes
        assert ("Une copie de chaque sauvegarde qui a changé, à restaurer depuis les "
                "réglages du jeu.") in textes


class TestToutLeSonCoupe:
    """« Couper le son des vidéos » n'a plus d'effet quand tout est coupé."""

    @pytest.fixture
    def page(self, qtbot, tmp_path, monkeypatch):
        from PyQt6.QtCore import QObject, pyqtSignal

        class Fond(QObject):
            son_coupe_change = pyqtSignal(bool)
            son_coupe = True

            def basculer_son(self):
                self.son_coupe = not self.son_coupe
                self.son_coupe_change.emit(self.son_coupe)

        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        cfg = Config(install_path=tmp_path / "jeux", cache_path=tmp_path / "cache", langue="fr")
        dlg = SettingsDialog(cfg, GameManager(cfg), fond=Fond())
        qtbot.addWidget(dlg)
        dlg.construire_rubrique(1)
        yield dlg
        dlg._shutdown_scan()

    def test_grise_a_l_ouverture_et_valeur_intacte(self, page):
        assert not page._ligne_mute.isEnabled() and page._ligne_mute.graphicsEffect() is not None
        assert page._tgl_mute.isChecked() is page.config.mute_videos

    def test_l_interrupteur_rend_la_ligne(self, page):
        page._tgl_son._basculer()
        assert page._ligne_mute.isEnabled() and page._ligne_mute.graphicsEffect() is None

    def test_le_haut_parleur_de_la_barre_aussi(self, page):
        page._fond.basculer_son()
        assert page._ligne_mute.isEnabled()
        page._fond.basculer_son()
        assert not page._ligne_mute.isEnabled()


class TestQuatreRubriques:
    """Constat car11 (2026-11-12) : la rubrique Téléchargements tenait un
    interrupteur et deux boutons dont l'un incluait l'autre. L'interrupteur va
    sous le dossier des jeux, UN bouton va sous les numéros d'À propos."""

    def test_plus_de_rubrique_telechargements(self, dialogue):
        from src.ui.settings_panel import _RANG_A_PROPOS, _RUBRIQUES
        assert [libelle for libelle, _ in _RUBRIQUES] == [
            "Général", "Son et image", "Intégrations", "À propos"]
        assert _RANG_A_PROPOS == len(_RUBRIQUES) - 1
        assert [b.text() for b in dialogue._nav.boutons][-1] == "À propos"

    def test_les_archives_dans_la_carte_du_dossier(self, dialogue):
        from src.ui.composants import Carte
        assert dialogue._tgl_archives.isChecked() is dialogue.config.delete_archives
        carte = next(c for c in dialogue.findChildren(Carte)
                     if c.isAncestorOf(dialogue._installed_label))
        assert carte.isAncestorOf(dialogue._tgl_archives), "sous le dossier des jeux"
        dialogue._tgl_archives._basculer()
        assert Config.load().delete_archives is dialogue._tgl_archives.isChecked()

    def test_un_seul_bouton_sous_les_numeros(self, dialogue):
        from PyQt6.QtWidgets import QLabel, QPushButton
        from src.ui.settings_panel import _RANG_A_PROPOS
        dialogue._nav.setCurrentRow(_RANG_A_PROPOS)
        page = dialogue._pages.widget(_RANG_A_PROPOS)
        textes = [b.text() for b in dialogue.findChildren(QPushButton)]
        assert textes.count("Vérifier les mises à jour") == 1
        assert "Actualiser le catalogue" not in textes
        assert page.isAncestorOf(dialogue._btn_verifier)
        numeros = page.findChild(QLabel, "versions")
        assert numeros is dialogue._versions_label
        colonne = numeros.parentWidget().layout()
        bloc = dialogue._btn_verifier.parentWidget()
        assert colonne.indexOf(numeros) < colonne.indexOf(bloc) < colonne.count() - 1, (
            "juste sous les numéros, avant les tuiles")
        assert colonne.indexOf(bloc) - colonne.indexOf(numeros) == 2   # l'espace entre eux

    def test_le_clic_demande_une_verification(self, dialogue, qtbot):
        from src.ui.settings_panel import _RANG_A_PROPOS
        dialogue.construire_rubrique(_RANG_A_PROPOS)
        with qtbot.waitSignal(dialogue.verification_demandee, timeout=1000):
            dialogue._btn_verifier.click()
        assert dialogue._update_status.text() == "Vérification des mises à jour…"

    def test_un_catalogue_neuf_redit_le_numero(self, dialogue):
        dialogue.update_catalog_version("<b>9.99</b>")
        texte = dialogue._versions_label.text()
        assert "CATALOGUE &lt;B&gt;9.99&lt;/B&gt;" in texte, "numéro venu de l'extérieur : échappé"
        assert "<a href=" in texte, "le numéro de version reste un lien"

    def test_la_colonne_colle_au_rail(self, dialogue, qtbot):
        """Centrée, la colonne de 760 px flottait loin du rail sur un grand écran."""
        dialogue.resize(1600, 800)
        dialogue.show()
        qtbot.waitExposed(dialogue)
        page = dialogue._pages.currentWidget().widget().layout().itemAt(0).widget()
        assert page.width() == 760
        assert page.mapTo(dialogue._pages, page.rect().topLeft()).x() == 64

    def test_les_jeux_qui_attendent_leur_mise_a_jour_sont_comptes(self, dialogue, monkeypatch):
        """Ce que la vérification lit quand elle n'apporte rien (règle 108)."""
        assert dialogue.jeux_a_mettre_a_jour() == 0
        premier = dialogue.manager.get_games()[0].game.id
        # GameManager a des __slots__ : on remplace le gestionnaire du dialogue, pas sa classe (règle 12).
        vrai = dialogue.manager
        monkeypatch.setattr(dialogue, "manager", SimpleNamespace(
            get_games=vrai.get_games, has_update=lambda gid: gid == premier))
        assert dialogue.jeux_a_mettre_a_jour() == 1

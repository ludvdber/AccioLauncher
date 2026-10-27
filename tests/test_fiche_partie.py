"""La fiche montre la partie en cours au lieu de la description (resume_partie.py).

Décision de Ludo, 2026-10-15 : jamais joué ou pas installé, la description
reste ; une sauvegarde LISIBLE, elle passe dans « À propos du jeu » et la fiche
dit où l'on en était. Un jeu dont on ne lit rien garde sa description.
"""
from datetime import date, datetime

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import Qt  # noqa: E402

from src.core.i18n import set_language  # noqa: E402
from tests.test_folio import BLOC, MENU, _save  # noqa: E402


@pytest.fixture
def fiche(qtbot, tmp_path, monkeypatch):
    """Un panneau d'infos sur un HP1 installé ; rien du catalogue réel (règle 78)."""
    from src.core import sauvegardes
    from src.core.config import Config
    from src.core.game_data import GameData
    from src.core.game_manager import GameManager
    from src.ui.info_panel import InfoPanel
    set_language("fr")
    monkeypatch.setattr(sauvegardes, "racines", lambda: {"documents": tmp_path / "Docs"})
    installes = {"hp1"}
    monkeypatch.setattr(GameManager, "is_installed", lambda _self, gid: gid in installes)
    monkeypatch.setattr(GameManager, "get_playtime", lambda _self, _gid: 600)
    install = tmp_path / "Jeux"
    system = install / "HP1" / "System"
    system.mkdir(parents=True)
    (system / "HPmenu.fre").write_bytes(MENU.encode("cp1252"))
    commun = {"year": 2001, "developer": "KnowWonder", "cover_image": "c.jpg",
              "description": "Incarnez Harry Potter et découvrez Poudlard."}
    hp1 = GameData.from_dict({
        **commun, "id": "hp1", "name": "Harry Potter à l'École des Sorciers",
        "executable": "HP1/System/HP.exe",
        "saves": {"root": "documents", "folders": ["Harry Potter/Save"],
                  "files": "Save*.usa", "first": 0}})
    hp2 = GameData.from_dict({**commun, "id": "hp2", "name": "La Chambre des Secrets",
                              "executable": "HP2/System/Game.exe"})
    manager = GameManager(Config(install_path=install, cache_path=tmp_path / "c"))
    panel = InfoPanel(manager)
    qtbot.addWidget(panel)
    panel.resize(600, 500)
    saves = tmp_path / "Docs" / "Harry Potter" / "Save"

    def montrer(jeu):
        panel.apply_game(jeu)
        panel.rafraichir_indices(jeu)

    return panel, montrer, hp1, hp2, saves, installes


def _visibles(panel):
    return (panel._desc.isVisibleTo(panel), panel._derniere.isVisibleTo(panel),
            panel._bloc.isVisibleTo(panel))


class TestDeuxEtats:
    def test_une_partie_lisible_remplace_la_description(self, fiche):
        panel, montrer, hp1, _, saves, _ = fiche
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        montrer(hp1)
        assert _visibles(panel) == (False, True, True)
        assert "Parc de Poudlard" in panel._derniere.text()
        assert panel._bloc.texte_compte() == "3 cartes sur 25", "WizardCards[25] est hors du folio"
        assert panel._bloc.texte_detail() == "Serpentard mène", "le temps de jeu est près de l'engrenage"
        assert panel.partie_affichee()
        # « Folio › » est dans le bloc : la ligne d'indices porte la description rangée.
        assert 'href="a-propos"' in panel._indices.text()
        assert 'href="folio"' not in panel._indices.text()

    def test_jamais_joue_la_description_reste(self, fiche):
        panel, montrer, hp1, _, _, _ = fiche
        montrer(hp1)
        assert _visibles(panel) == (True, False, False)
        assert not panel.partie_affichee()

    def test_un_debut_de_jeu_illisible_garde_la_description(self, fiche):
        panel, montrer, hp1, _, saves, _ = fiche
        _save(saves, 0, b"rien", b"Lev_Tut1", datetime(2026, 10, 1))
        montrer(hp1)
        assert _visibles(panel) == (True, False, False)

    def test_desinstalle_la_description_revient(self, fiche):
        panel, montrer, hp1, _, saves, installes = fiche
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        installes.clear()
        montrer(hp1)
        assert _visibles(panel) == (True, False, False)

    def test_un_jeu_dont_on_ne_lit_rien_garde_sa_description(self, fiche):
        """Un jeu sans sauvegarde lisible (ici HP2, aucune partie écrite)."""
        panel, montrer, hp1, hp2, saves, installes = fiche
        installes.add("hp2")
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        montrer(hp1)
        montrer(hp2)
        assert _visibles(panel) == (True, False, False)

    def test_la_premiere_sauvegarde_bascule_au_retour_de_partie(self, fiche):
        panel, montrer, hp1, _, saves, _ = fiche
        montrer(hp1)
        assert not panel.partie_affichee()
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 10, 15))
        montrer(hp1)    # ce que fait `MainWindow._on_game_exited` (set_game même id)
        assert panel.partie_affichee()


class TestAvancementSansFolio:
    """HP5 dit son avancement (« 14 % ») : depuis le 2026-10-26 (maquette « Plan
    du launcher v2 », Ludo : « on doit afficher le folio des cartes ou autre
    s'il y a quelque chose »), il a son bloc comme HP1 à HP3, et la description
    passe derrière « À propos du jeu ». Elle restait jusque-là (2026-10-15)."""

    @pytest.fixture
    def hp5(self, fiche, tmp_path, monkeypatch):
        from src.core import sauvegardes
        from src.core.game_data import GameData
        from tests.test_sauvegardes import HPOOTP, _hpootp
        panel, montrer, _, _, _, installes = fiche
        monkeypatch.setattr(sauvegardes, "racines",
                            lambda: {"documents": tmp_path / "Docs", "localappdata": tmp_path / "App"})
        installes.add("hp5")
        jeu = GameData.from_dict({
            "id": "hp5", "name": "L'Ordre du Phénix", "year": 2007, "developer": "EA UK",
            "cover_image": "c.jpg", "description": "Dumbledore's Army.",
            "executable": "HP5/hp.exe",
            "saves": {"root": "localappdata",
                      "folders": ["Electronic Arts/Harry Potter*Ph*nix/HPOOTP"],
                      "files": "HPOOTP", "first": 1, "slots": "hp5"}})
        chemin = tmp_path / "App" / HPOOTP
        chemin.parent.mkdir(parents=True)
        return panel, montrer, jeu, chemin, _hpootp, installes

    def test_la_derniere_partie_et_son_pourcentage(self, hp5):
        panel, montrer, jeu, chemin, hpootp, _ = hp5
        chemin.write_bytes(hpootp(("Frontend", datetime(2026, 4, 29, 21, 5, 13), 1),
                                  ("Hogwarts", datetime(2026, 10, 1, 16, 8, 24), 14)))
        montrer(jeu)
        assert _visibles(panel) == (False, True, True), "le bloc, la description rangée"
        assert panel._bloc._compte.text() == "14 % terminé", "la plus récente, pas la première"
        assert panel.partie_affichee(), "les statistiques passent dans le bloc"
        assert 'href="a-propos"' in panel._indices.text()

    def test_sans_sauvegarde_rien_de_plus(self, hp5):
        panel, montrer, jeu, _, _, _ = hp5
        montrer(jeu)
        assert _visibles(panel) == (True, False, False)

    def test_desinstalle_la_ligne_s_en_va(self, hp5):
        panel, montrer, jeu, chemin, hpootp, installes = hp5
        chemin.write_bytes(hpootp(("Hogwarts", datetime(2026, 10, 1), 14)))
        installes.discard("hp5")
        montrer(jeu)
        assert _visibles(panel) == (True, False, False)


class TestAProposDuJeu:
    def test_la_description_se_relit_puis_se_range(self, fiche):
        panel, montrer, hp1, _, saves, _ = fiche
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        montrer(hp1)
        panel._on_meta_link("a-propos")
        assert _visibles(panel) == (True, False, True)
        assert "MA PARTIE" in panel._indices.text().replace(chr(160), " ")
        panel._on_meta_link("a-propos")
        assert _visibles(panel) == (False, True, True)

    def test_un_autre_jeu_repart_de_la_partie(self, fiche):
        panel, montrer, hp1, hp2, saves, _ = fiche
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        montrer(hp1)
        panel._on_meta_link("a-propos")
        montrer(hp2)
        montrer(hp1)
        assert _visibles(panel) == (False, True, True)


class TestLeBlocEstUnBouton:
    """Règle 119 : il a l'air d'un bouton, il répond comme un bouton."""

    def test_clic_et_clavier_ouvrent_le_folio(self, fiche, qtbot):
        panel, montrer, hp1, _, saves, _ = fiche
        _save(saves, 0, BLOC, b"LEV2_HOGFRONT", datetime(2026, 3, 8))
        montrer(hp1)
        ouvertures = []
        panel.folio_clicked.connect(lambda: ouvertures.append(1))
        bloc = panel._bloc
        qtbot.mouseClick(bloc, Qt.MouseButton.LeftButton)
        qtbot.keyClick(bloc, Qt.Key.Key_Return)
        qtbot.keyClick(bloc, Qt.Key.Key_Space)
        assert len(ouvertures) == 3
        assert bloc.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert bloc.accessibleName()


class TestPhrases:
    def test_date_relative_et_lieu_echappe(self):
        from src.ui.resume_partie import phrase_derniere_partie
        set_language("fr")
        texte = phrase_derniere_partie(datetime(2026, 10, 14, 20), "<b>Cachots</b>",
                                       today=date(2026, 10, 15))
        assert "Dernière partie hier" in texte
        assert "<b>" not in texte and "&lt;b&gt;Cachots" in texte

    def test_au_dela_d_un_mois_la_date(self):
        from src.ui.resume_partie import phrase_derniere_partie
        set_language("fr")
        texte = phrase_derniere_partie(datetime(2026, 3, 8), "", today=date(2026, 10, 15))
        assert "Dernière partie le 8 mars 2026" in texte

    def test_au_dela_d_un_mois_la_date_suit_la_langue(self):
        from src.ui.resume_partie import phrase_derniere_partie
        set_language("en")
        try:
            texte = phrase_derniere_partie(datetime(2026, 3, 8), "", today=date(2026, 10, 15))
        finally:
            set_language("fr")
        assert "08/03/2026" not in texte and "2026" in texte

    def test_une_seule_carte(self):
        from src.ui.resume_partie import phrase_cartes
        set_language("fr")
        assert phrase_cartes(1) == "1 carte sur 25"

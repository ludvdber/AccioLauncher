"""La page de statistiques — ce qu'elle affiche, et surtout ce qu'elle TAIT.

Deux regles de la maison se croisent ici et sont faciles a perdre de vue :

· **rien de normal ne s'affiche.** Une serie d'un seul jour, un compte de
  parties a zero ou une plage horaire sans donnee ne sont pas des informations,
  ce sont des cases vides qui apprennent a l'utilisateur a ne plus lire la page.
· **un `QLabel` en `wordWrap` pose dans un layout sans hauteur imposee** ne
  recoit qu'une ligne : son `sizeHint` est calcule a une largeur qui n'est pas
  la sienne. Le piege a ete paye quatre fois dans ce projet avant celui-ci.
"""

from datetime import datetime, timedelta

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtWidgets import QLabel  # noqa: E402

from src.core import stats  # noqa: E402
from src.core.config import Config  # noqa: E402
from src.core.game_manager import GameManager  # noqa: E402
from src.ui.stats_dialog import _Paragraphe, _Saga, StatsDialog  # noqa: E402


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
    return GameManager(conf)


def _remplir(manager, jours=12, jeux=("hp1", "hp2")):
    """Un historique realiste : deux jeux, des soirees, une serie en cours."""
    ids = [e.game.id for e in manager.get_games()][:len(jeux)]
    for d in range(jours, 0, -1):
        debut = (datetime.now() - timedelta(days=d - 1)).replace(
            hour=21, minute=0, second=0, microsecond=0)
        stats.enregistrer_session(ids[d % len(ids)], debut, 3600 + d * 60)
    return ids


def _labels(dlg) -> str:
    return "\n".join(lbl.text() for lbl in dlg.findChildren(QLabel))


class TestEtatVide:
    def test_le_premier_jour_la_page_n_a_pas_l_air_cassee(self, qtbot, manager):
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "cette page se remplit toute seule" in _labels(dlg)

    def test_aucun_chiffre_a_zero_n_est_affiche(self, qtbot, manager):
        """« 0 partie lancée » et « 0 jour de jeu » ne sont pas des
        statistiques : c'est du bruit qui apprend a ignorer la page."""
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        for interdit in ("parties lancées", "jours de jeu", "Habitudes",
                         "Temps par jeu", "par session en moyenne"):
            assert interdit not in rendu, interdit


class TestAvecDesParties:
    def test_le_bandeau_porte_les_quatre_chiffres(self, qtbot, manager):
        _remplir(manager)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        for attendu in ("de jeu au total", "parties lancées",
                        "par session en moyenne", "jours de jeu"):
            assert attendu in rendu, attendu

    def test_chaque_jeu_joue_a_sa_ligne(self, qtbot, manager):
        ids = _remplir(manager)
        noms = {e.game.id: e.game.name for e in manager.get_games()}
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        for gid in ids:
            assert noms[gid] in rendu

    def test_les_jeux_jamais_lances_sont_nommes(self, qtbot, manager):
        _remplir(manager)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "Jamais lancés" in _labels(dlg)

    def test_une_serie_d_un_seul_jour_ne_s_affiche_pas(self, qtbot, manager):
        """Jouer aujourd'hui n'est pas une serie — c'est l'etat normal."""
        gid = manager.get_games()[0].game.id
        stats.enregistrer_session(gid, datetime.now().replace(hour=21), 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "Série en cours" not in _labels(dlg)

    def test_un_jeu_sans_session_n_affiche_pas_zero_partie(self, qtbot, tmp_path,
                                                           monkeypatch):
        """Tout son temps est anterieur au journal : « 0 partie » a cote de six
        heures de jeu serait faux, et incomprehensible.

        Le cumul est pose AVANT la construction du manager : c'est lui qui
        amorce le journal, et `amorcer` ne repasse jamais (sans quoi le temps
        joue depuis serait recompte a chaque demarrage).
        """
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        from src.core.game_data import load_catalog
        gid = load_catalog().games[0].id
        conf.playtime_seconds[gid] = 21600
        manager = GameManager(conf)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "6 h" in rendu
        assert "0 parties" not in rendu


class TestSurfaceDuCatalogue:
    def test_le_balisage_d_un_nom_de_jeu_n_est_jamais_interprete(self, qtbot, manager,
                                                                 monkeypatch):
        """Ces noms viennent du catalogue DISTANT. Un `<img src="http://…">`
        ferait partir une requete a l'ouverture de la page — donc « qui joue a
        quoi » chez l'hebergeur de l'image."""
        import dataclasses
        jeux = manager.catalog.games
        piege = dataclasses.replace(jeux[0], name='<img src="http://pisteur/x.png">')
        manager._catalog = dataclasses.replace(manager.catalog,
                                               games=(piege,) + tuple(jeux[1:]))
        manager._games = manager._catalog.games
        manager._index[piege.id] = piege
        stats.enregistrer_session(piege.id, datetime.now().replace(hour=21), 3600)

        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        for lbl in dlg.findChildren(QLabel):
            from PyQt6.QtCore import Qt
            assert lbl.textFormat() != Qt.TextFormat.RichText, lbl.text()
        assert '<img' in _labels(dlg)  # affiché tel quel, donc inoffensif


class TestParagrapheMesure:
    def test_la_hauteur_suit_la_largeur_reelle(self, qtbot):
        """Le piege maison : sans mesure au `resizeEvent`, le layout n'accorde
        qu'UNE ligne et la liste des jeux jamais lances se coupe."""
        lbl = _Paragraphe(" · ".join(["Harry Potter et la Chambre des Secrets"] * 4))
        qtbot.addWidget(lbl)
        lbl.show()
        lbl.resize(300, 10)
        qtbot.wait(1)
        une_ligne = lbl.fontMetrics().height()
        assert lbl.minimumHeight() > une_ligne * 2, (
            f"hauteur {lbl.minimumHeight()} px pour un texte qui en demande plusieurs")

    def test_elle_se_recalcule_en_s_elargissant(self, qtbot):
        lbl = _Paragraphe(" · ".join(["Harry Potter et la Coupe de Feu"] * 4))
        qtbot.addWidget(lbl)
        lbl.show()
        lbl.resize(240, 10)
        qtbot.wait(1)
        etroit = lbl.minimumHeight()
        lbl.resize(900, 10)
        qtbot.wait(1)
        assert lbl.minimumHeight() < etroit, "la hauteur n'a pas suivi l'élargissement"


class TestSaga:
    @staticmethod
    def _survoler(w, entrees, indice):
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        pas = w.width() / len(entrees)
        pos = QPointF(pas * indice + pas / 2, 11.0)
        w.mouseMoveEvent(QMouseEvent(
            QMouseEvent.Type.MouseMove, pos, QPointF(pos),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))

    def test_le_balisage_n_atteint_pas_l_infobulle(self, qtbot, manager):
        """L'infobulle est le SEUL endroit de la page ou du balisage du
        catalogue serait interprete : `QToolTip` est un `QLabel` laisse en
        `AutoText`, alors que tout le reste est pose en `PlainText` a la
        construction. Le balayage de `TestSurfaceDuCatalogue` ne regarde que
        `findChildren(QLabel)` — il ne voyait pas ce chemin-la.

        Mesure faite avant d'ecrire ce test, parce que la raison ecrite dans
        CLAUDE.md etait fausse : un `QLabel` PyQt6 ne va PAS chercher une image
        distante (0 requete contre un serveur local, placeholder 16x16), alors
        qu'un `file:///` se charge bel et bien (64x64, la taille du PNG). Ce
        qu'on empeche ici n'est donc pas une fuite reseau mais l'interpretation
        du balisage — mise en page detournee, et lecture de fichiers LOCAUX.
        """
        import dataclasses
        entrees = manager.get_games()
        piege = dataclasses.replace(entrees[2].game, name='<img src="file:///C:/x.png">')
        entrees = list(entrees)
        # GameEntry est un NamedTuple, pas une dataclass : `_replace`.
        entrees[2] = entrees[2]._replace(game=piege)

        w = _Saga(entrees, set())
        qtbot.addWidget(w)
        w.resize(400, 22)
        self._survoler(w, entrees, 2)
        assert "<img" not in w.toolTip(), w.toolTip()
        assert "&lt;img" in w.toolTip()

    def test_le_nom_du_jeu_sous_le_curseur(self, qtbot, manager):
        """Sans ca, huit segments anonymes."""
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        entrees = manager.get_games()
        w = _Saga(entrees, set())
        qtbot.addWidget(w)
        w.resize(400, 22)
        pas = 400 / len(entrees)
        pos = QPointF(pas * 2 + pas / 2, 11.0)
        w.mouseMoveEvent(QMouseEvent(
            QMouseEvent.Type.MouseMove, pos, QPointF(pos),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))
        assert w.toolTip() == entrees[2].game.name


class TestBoutonDeFenetre:
    def test_la_fenetre_porte_une_commande_de_statistiques(self, qtbot, tmp_path,
                                                           monkeypatch):
        """Deux commandes cote a cote, et qui ne se recouvrent pas.

        Deux precautions, chacune payee ailleurs :

        · le bouton n'est PAS clique — `StatsDialog.exec()` bloquerait la suite
          indefiniment, comme `versions_clicked` l'avait deja fait ;
        · la fenetre n'est PAS fermee. `MainWindow.closeEvent` fait l'extinction
          des threads, `terminate()` compris : en production ca precede d'une
          seconde la sortie du processus, mais dans une session pytest le
          processus CONTINUE avec des verrous abandonnes, et la suite meurt
          plusieurs fichiers plus loin sur une violation d'acces, dans le
          `paintEvent` d'un widget qui n'y est pour rien (constate le
          2026-08-26 : 3 exécutions sur 3, sites de plantage variables). Aucun
          test du projet n'appelle `close()` — `qtbot.addWidget` suffit.
        """
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check",
                            lambda self: None)
        from src.core.config import Config as C
        C(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c").save()
        from src.ui.main_window import MainWindow

        win = MainWindow()
        qtbot.addWidget(win)
        win.show()   # c'est le redimensionnement qui pose les commandes en absolu
        qtbot.wait(10)
        assert win._btn_stats.isVisible()
        # Elles etaient posees au MEME x tant que le placement ne tenait compte
        # que de l'engrenage.
        assert not win._btn_stats.geometry().intersects(win._btn_settings.geometry())

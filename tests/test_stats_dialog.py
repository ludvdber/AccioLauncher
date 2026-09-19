"""La page de la saga — ce qu'elle affiche, et surtout ce qu'elle TAIT.

Trois regles de la maison se croisent ici et sont faciles a perdre de vue :

· **rien de normal ne s'affiche.** Un compte de parties a zero ou un jeu jamais
  lance ne sont pas des informations, ce sont des cases vides qui apprennent a
  l'utilisateur a ne plus lire la page.
· **le squelette ne depend jamais des donnees.** La frise fait huit cases,
  qu'on ait joue a zero jeu ou aux huit. C'est ce qui empeche la page d'avoir
  l'air cassee le premier jour, ce qui arrivait bien avant qu'elle n'ait l'air
  pauvre.
· **un `QLabel` en `wordWrap` pose dans un layout sans hauteur imposee** ne
  recoit qu'une ligne : son `sizeHint` est calcule a une largeur qui n'est pas
  la sienne. Le piege a ete paye cinq fois dans ce projet.
"""

from datetime import datetime, timedelta

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtWidgets import QLabel, QScrollArea  # noqa: E402

from src.core import stats  # noqa: E402
from src.core.config import Config  # noqa: E402
from src.core.game_manager import GameManager  # noqa: E402
from src.ui.stats_dialog import (  # noqa: E402
    _CarteSauvegarde, _Etagere, _Mois, _Paragraphe, StatsDialog)


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
    conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
    return GameManager(conf)


def _remplir(manager, jours=12, jeux=2):
    """Un historique realiste : deux jeux, des soirees, sur douze jours."""
    ids = [e.game.id for e in manager.get_games()][:jeux]
    for d in range(jours, 0, -1):
        debut = (datetime.now() - timedelta(days=d - 1)).replace(
            hour=21, minute=0, second=0, microsecond=0)
        stats.enregistrer_session(ids[d % len(ids)], debut, 3600 + d * 60)
    return ids


def _labels(dlg) -> str:
    return "\n".join(lbl.text() for lbl in dlg.findChildren(QLabel))


class TestLeSqueletteNeBougePas:
    """La frise fait huit cases quoi qu'il arrive.

    C'est le vrai correctif de l'ancienne page : chaque bloc y changeait de
    taille selon les donnees (quatre cartes puis une, huit segments dont six
    vides, six lignes de liste, puis 400 px de vide). Une page dont la
    structure varie a l'air cassee.
    """

    @pytest.mark.parametrize("avec_parties", [False, True])
    def test_toujours_autant_de_cases(self, qtbot, manager, avec_parties):
        if avec_parties:
            _remplir(manager)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        frises = dlg.findChildren(_Etagere)
        assert len(frises) == 1
        assert len(frises[0]._entrees) == len(manager.get_games()) == 8

    def test_la_frise_n_est_pas_dans_la_zone_defilante(self, qtbot, manager):
        """C'est le squelette : il ne doit jamais partir sous la ligne de
        flottaison quand le journal s'allonge."""
        _remplir(manager, jours=40)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        frise = dlg.findChildren(_Etagere)[0]
        assert not frise.findChildren(QScrollArea)
        parents = []
        w = frise.parentWidget()
        while w is not None:
            parents.append(type(w).__name__)
            w = w.parentWidget()
        assert "QScrollArea" not in parents


class TestEtatVide:
    """Une page ne se termine JAMAIS par du vide — dans TOUS ses etats.

    La hauteur est posee par `showEvent` : on AFFICHE, comme le fait `exec()`
    (piege « mesurer une hauteur pilotee par resizeEvent sans afficher »).
    """

    @staticmethod
    def _ouvrir(qtbot, manager) -> StatsDialog:
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        dlg.show()
        return dlg

    def test_premier_lancement_la_page_s_arrete_ou_le_contenu_s_arrete(
            self, qtbot, manager):
        vide = self._ouvrir(qtbot, manager)
        assert not vide.findChildren(QScrollArea)
        assert vide.height() < 420, f"{vide.height()} px pour une etagere et une phrase"
        _remplir(manager, jours=30)
        pleine = self._ouvrir(qtbot, manager)
        assert pleine.height() > vide.height()

    def test_le_premier_jour_la_page_n_a_pas_l_air_cassee(self, qtbot, manager):
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "cette page se remplira toute seule" in _labels(dlg)

    def test_un_contenu_court_ne_laisse_pas_de_vide(self, qtbot, manager):
        _remplir(manager, jours=2, jeux=1)
        dlg = self._ouvrir(qtbot, manager)
        zone = dlg.findChildren(QScrollArea)[0]
        reste = zone.viewport().height() - zone.widget().sizeHint().height()
        assert reste <= 2, f"{reste} px de vide au bas de la page"

    def test_la_hauteur_est_plafonnee_par_l_ecran(self, qtbot, manager):
        from src.ui.stats_dialog import _HAUTEUR_MAX, _hauteur_max
        _remplir(manager, jours=60, jeux=8)
        dlg = self._ouvrir(qtbot, manager)
        assert dlg.height() <= _hauteur_max(dlg) <= _HAUTEUR_MAX
        assert _hauteur_max(dlg) <= dlg.screen().availableGeometry().height()

    def test_aucun_zero_n_est_affiche(self, qtbot, manager):
        _remplir(manager, jours=3, jeux=1)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        textes = [lbl.text() for lbl in dlg.findChildren(QLabel)]
        assert "0" not in textes
        assert not any(t.startswith("0 ") for t in textes), textes


class TestEtagere:
    def test_le_dernier_jeu_joue_est_choisi_a_l_ouverture(self, qtbot, manager):
        ids = [e.game.id for e in manager.get_games()]
        stats.enregistrer_session(ids[0], datetime(2026, 8, 20, 21, 0), 3600)
        stats.enregistrer_session(ids[3], datetime(2026, 8, 25, 21, 0), 1800)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert dlg.findChildren(_Etagere)[0].choix == ids[3]

    def test_un_jeu_sans_rien_ne_se_choisit_pas(self, qtbot, manager):
        ids = [e.game.id for e in manager.get_games()]
        stats.enregistrer_session(ids[0], datetime(2026, 8, 20, 21, 0), 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        etagere = dlg.findChildren(_Etagere)[0]
        etagere.choisir(ids[5])
        assert etagere.choix == ids[0]

    def test_choisir_un_jeu_change_la_fiche(self, qtbot, manager):
        ids = _remplir(manager, jours=4, jeux=2)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        noms = {e.game.id: e.game.name for e in manager.get_games()}
        etagere = dlg.findChildren(_Etagere)[0]
        autre = ids[0] if etagere.choix == ids[1] else ids[1]
        etagere.choisir(autre)
        visibles = [lbl.text() for lbl in dlg._fiche.findChildren(QLabel)]
        assert noms[autre] in visibles

    def test_les_fleches_parcourent_les_jeux_choisissables(self, qtbot, manager):
        from PyQt6.QtCore import Qt
        ids = _remplir(manager, jours=4, jeux=2)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        etagere = dlg.findChildren(_Etagere)[0]
        qtbot.keyClick(etagere, Qt.Key.Key_Home)
        assert etagere.choix == ids[0]
        qtbot.keyClick(etagere, Qt.Key.Key_Right)
        assert etagere.choix == ids[1]


class TestSaga:
    def test_le_mois_l_annee_et_le_total(self, qtbot, manager):
        gid = manager.get_games()[0].game.id
        stats.enregistrer_session(gid, datetime.now().replace(microsecond=0), 2 * 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "Au total" in rendu
        assert f"En {datetime.now().year}" in rendu

    def test_la_plus_longue_partie_porte_sa_date(self, qtbot, manager):
        """Date, c'est un souvenir ; sans date, c'est un chiffre."""
        gid = manager.get_games()[0].game.id
        stats.enregistrer_session(gid, datetime(2026, 8, 12, 20, 0), 3 * 3600 + 1200)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "12/08/2026" in _labels(dlg)

    def test_le_temps_anterieur_au_journal_est_annonce(self, qtbot, tmp_path,
                                                       monkeypatch):
        """Sans cette ligne, l'annee et le mois ne se raccordent pas au total."""
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        from src.core.game_data import load_catalog
        conf.playtime_seconds[load_catalog().games[0].id] = 21600
        dlg = StatsDialog(GameManager(conf))
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "avant la mise en service du journal" in rendu
        assert "6 h" in rendu

    def test_les_douze_mois_n_apparaissent_qu_avec_des_parties(self, qtbot, manager):
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert not dlg.findChildren(_Mois)
        _remplir(manager, jours=3)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        (mois,) = dlg.findChildren(_Mois)
        assert len(mois._cases) == 12


class TestSauvegardesAffichees:
    @staticmethod
    def _save(nom, quand):
        import os
        from src.core import sauvegardes
        dossier = sauvegardes.racines()["documents"] / "Harry Potter" / "Save"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / nom
        chemin.write_bytes(b"x")
        os.utime(chemin, (quand.timestamp(), quand.timestamp()))

    def test_une_carte_par_sauvegarde(self, qtbot, manager):
        self._save("Save0.usa", datetime(2026, 3, 8))
        self._save("Save1.usa", datetime(2026, 4, 3))
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert dlg.findChildren(_Etagere)[0].choix == "hp1"
        assert len(dlg.findChildren(_CarteSauvegarde)) == 2
        rendu = _labels(dlg)
        assert "Emplacement 1" in rendu and "Emplacement 2" in rendu
        assert "03/04/2026" in rendu

    def test_le_temps_non_observe_n_est_pas_devine(self, qtbot, manager):
        self._save("Save0.usa", datetime(2026, 3, 8))
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "Temps compté à partir de la prochaine partie." in rendu
        assert "Tes sauvegardes sont là" in rendu

    def test_un_jeu_sans_sauvegarde_n_a_pas_de_section(self, qtbot, manager):
        _remplir(manager, jours=2, jeux=1)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "SAUVEGARDES" not in rendu


class TestSurfaceDuCatalogue:
    def test_le_balisage_d_un_nom_de_jeu_n_est_jamais_interprete(self, qtbot, manager,
                                                                 monkeypatch):
        """Ces noms viennent du catalogue DISTANT."""
        import dataclasses
        from PyQt6.QtCore import Qt
        jeux = manager.catalog.games
        piege = dataclasses.replace(jeux[0], name='<img src="file:///C:/x.png">')
        manager._catalog = dataclasses.replace(manager.catalog,
                                               games=(piege,) + tuple(jeux[1:]))
        manager._games = manager._catalog.games
        manager._index[piege.id] = piege
        stats.enregistrer_session(piege.id, datetime(2026, 8, 25, 21, 0), 3600)

        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        for lbl in dlg.findChildren(QLabel):
            assert lbl.textFormat() != Qt.TextFormat.RichText, lbl.text()
        assert '<img' in _labels(dlg)   # affiché tel quel, donc inoffensif

    def test_le_balisage_n_atteint_pas_l_infobulle(self, qtbot, manager):
        """L'infobulle est le SEUL endroit de la page ou du balisage serait
        interprete : `QToolTip` est un `QLabel` laisse en `AutoText`, alors que
        tout le reste est pose en `PlainText` a la construction."""
        import dataclasses
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        entrees = list(manager.get_games())
        piege = dataclasses.replace(entrees[2].game, name='<img src="file:///C:/x.png">')
        entrees[2] = entrees[2]._replace(game=piege)   # GameEntry est un NamedTuple

        w = _Etagere(entrees, {}, set())
        qtbot.addWidget(w)
        w.resize(800, 142)
        pas = 800 / len(entrees)
        pos = QPointF(pas * 2 + pas / 2, 60.0)
        w.mouseMoveEvent(QMouseEvent(
            QMouseEvent.Type.MouseMove, pos, QPointF(pos),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))
        assert "<img" not in w.toolTip(), w.toolTip()
        assert "&lt;img" in w.toolTip()


class TestFriseSeDessine:
    def test_de_l_encre_est_posee(self, qtbot, manager):
        """Les jaquettes sont peintes : un paintEvent muet passerait tous les
        autres tests sans qu'on voie rien a l'ecran."""
        from PyQt6.QtGui import QColor, QImage, QPainter
        entrees = manager.get_games()
        gid = entrees[0].game.id
        w = _Etagere(entrees, {gid: "1 h"}, {gid}, gid)
        qtbot.addWidget(w)
        w.resize(800, 142)
        img = QImage(800, 142, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        w.render(p)
        p.end()
        poses = sum(1 for y in range(0, 142, 2) for x in range(0, 800, 2)
                    if QColor.fromRgba(img.pixel(x, y)).alpha() > 0)
        assert poses > 5000, f"frise quasi vide : {poses} pixels"


class TestParagrapheMesure:
    def test_la_hauteur_suit_la_largeur_reelle(self, qtbot):
        lbl = _Paragraphe(" · ".join(["Harry Potter et la Chambre des Secrets"] * 4))
        qtbot.addWidget(lbl)
        lbl.show()
        lbl.resize(300, 10)
        qtbot.wait(1)
        assert lbl.minimumHeight() > lbl.fontMetrics().height() * 2

    def test_elle_se_recalcule_en_s_elargissant(self, qtbot):
        lbl = _Paragraphe(" · ".join(["Harry Potter et la Coupe de Feu"] * 4))
        qtbot.addWidget(lbl)
        lbl.show()
        lbl.resize(240, 10)
        qtbot.wait(1)
        etroit = lbl.minimumHeight()
        lbl.resize(900, 10)
        qtbot.wait(1)
        assert lbl.minimumHeight() < etroit


class TestBoutonDeFenetre:
    def test_la_fenetre_porte_une_commande_de_statistiques(self, qtbot, tmp_path,
                                                           monkeypatch):
        """Deux commandes cote a cote, et qui ne se recouvrent pas.

        Le bouton n'est PAS clique (`exec()` bloquerait la suite) et la fenetre
        n'est PAS fermee (`closeEvent` fait l'extinction des threads,
        `terminate()` compris — dans pytest le processus CONTINUE avec des
        verrous abandonnes et meurt plusieurs fichiers plus loin).
        """
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        monkeypatch.setattr("src.ui.main_window.MainWindow._start_update_check",
                            lambda self: None)
        Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c").save()
        from src.ui.main_window import MainWindow

        win = MainWindow()
        qtbot.addWidget(win)
        win.show()
        qtbot.wait(10)
        assert win._btn_stats.isVisible()
        assert not win._btn_stats.geometry().intersects(win._btn_settings.geometry())

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
from src.ui.stats_dialog import _Frise, _Paragraphe, StatsDialog  # noqa: E402


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
        frises = dlg.findChildren(_Frise)
        assert len(frises) == 1
        assert len(frises[0]._entrees) == len(manager.get_games()) == 8

    def test_la_frise_n_est_pas_dans_la_zone_defilante(self, qtbot, manager):
        """C'est le squelette : il ne doit jamais partir sous la ligne de
        flottaison quand le journal s'allonge."""
        _remplir(manager, jours=40)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        frise = dlg.findChildren(_Frise)[0]
        assert not frise.findChildren(QScrollArea)
        parents = []
        w = frise.parentWidget()
        while w is not None:
            parents.append(type(w).__name__)
            w = w.parentWidget()
        assert "QScrollArea" not in parents


class TestEtatVide:
    """Une page ne se termine JAMAIS par du vide — dans TOUS ses etats.

    La regle etait ecrite, testee, et pourtant fausse a l'ecran : la capture de
    Ludo du 2026-08-28 montrait 450 px de rien sous la frise. Deux erreurs
    superposees, et ce sont elles que cette classe garde :

    · le test ne couvrait que le premier lancement (zero session, zero temps
      herite), l'etat vide le plus RARE. L'etat reel de tout utilisateur actuel
      — du temps de jeu d'avant le journal, pas encore une partie enregistree —
      passait par la branche « pleine » et etirait la zone defilante ;
    · un journal COURT laissait le meme vide, la fenetre s'ouvrant a une
      hauteur fixe pendant que la zone defilante absorbait tout l'excedent.

    Et un piege d'outillage : la hauteur est posee par `showEvent`, comme celle
    de `_Frise` et de `_Paragraphe`. Une page qu'on ne montre pas garde sa
    taille de construction — c'est la regle deja ecrite dans CLAUDE.md pour les
    tests, et elle vaut ici aussi. On AFFICHE, comme le fait `exec()`.
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
        _remplir(manager, jours=30)
        pleine = self._ouvrir(qtbot, manager)
        assert vide.height() < 420, f"{vide.height()} px pour une frise et deux lignes"
        assert pleine.height() > vide.height()

    def test_du_temps_herite_sans_aucune_partie_ne_fait_pas_un_journal(
            self, qtbot, manager):
        """L'etat de la capture : 4 min heritees, zero session enregistree.

        Le temps d'avant le journal rendait `_journal()` vrai, donc la zone
        defilante existait pour porter UNE phrase — 388 px de vide mesures.
        """
        # Le temps herite est GELE par `amorcer`, que `GameManager.__init__`
        # appelle une fois pour toutes : le semer apres coup ne ferait rien
        # (la fonction est idempotente, c'est meme tout son interet). Il faut
        # donc un manager construit sur une config qui porte deja du temps.
        ids = [e.game.id for e in manager.get_games()]
        conf = Config(install_path=manager.config.install_path,
                      cache_path=manager.config.cache_path,
                      playtime_seconds={ids[0]: 40, ids[1]: 180})
        stats.chemin_journal().unlink(missing_ok=True)
        avec_herite = GameManager(conf)
        dlg = self._ouvrir(qtbot, avec_herite)
        assert not dlg.findChildren(QScrollArea), \
            "une seule phrase ne merite pas une zone defilante"
        assert dlg.height() < 420, f"{dlg.height()} px pour une frise et deux lignes"
        # Le total de l'en-tete doit rester raccordable : la phrase demeure.
        assert "Avant la mise en service du journal" in _labels(dlg)
        # Mais pas le titre d'une liste qui n'existe pas.
        assert "JOURNAL DES PARTIES" not in _labels(dlg)

    def test_un_journal_court_ne_laisse_pas_de_vide_non_plus(self, qtbot, manager):
        """La regle vaut aussi quand le journal existe mais tient en 4 lignes.

        La zone defilante prend tout l'excedent (`stretch=1`) : avec une
        hauteur d'ouverture fixe, le vide passait simplement DEDANS.
        """
        _remplir(manager, jours=4)
        dlg = self._ouvrir(qtbot, manager)
        zone = dlg.findChildren(QScrollArea)[0]
        reste = zone.viewport().height() - zone.widget().sizeHint().height()
        assert reste <= 2, f"{reste} px de vide au bas de la zone defilante"

    def test_un_journal_long_est_plafonne_et_defile(self, qtbot, manager):
        _remplir(manager, jours=60)
        dlg = self._ouvrir(qtbot, manager)
        assert dlg.height() <= 720
        zone = dlg.findChildren(QScrollArea)[0]
        assert zone.widget().sizeHint().height() > zone.viewport().height()

    def test_le_premier_jour_la_page_n_a_pas_l_air_cassee(self, qtbot, manager):
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "cette page se remplira toute seule" in _labels(dlg)

    def test_aucun_chiffre_a_zero_n_est_affiche(self, qtbot, manager):
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        for interdit in ("0 ", "Journal des parties", "Plus longue partie"):
            assert interdit not in rendu, interdit


class TestCeQuiAEteRetireNeRevientPas:
    """Chacune de ces sections a ete supprimee pour une raison ecrite dans
    l'en-tete du module. Les remettre annulerait le correctif."""

    INTERDITS = (
        "Jamais lanc",          # un catalogue de ce qu'on n'a pas fait
        "Série en cours",       # sa seule force est la peur de la rompre
        "record :",
        "Jour de prédilection",
        "entre",                # « Tu lances surtout une partie entre X h et Y h »
        "démarrages du launcher",
        "par session en moyenne",
        "jours de jeu",
        "Progression dans la saga",
        "Temps par jeu",
        "Habitudes",
    )

    @pytest.mark.parametrize("interdit", INTERDITS)
    def test_absent_avec_un_historique_fourni(self, qtbot, manager, interdit):
        _remplir(manager, jours=40)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert interdit not in _labels(dlg), interdit


class TestJournal:
    def test_la_derniere_partie_est_en_haut(self, qtbot, manager):
        ids = [e.game.id for e in manager.get_games()][:2]
        stats.enregistrer_session(ids[0], datetime(2026, 8, 20, 21, 0), 3600)
        stats.enregistrer_session(ids[1], datetime(2026, 8, 25, 21, 0), 1800)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        # Seul le journal porte date ET heure : la ligne « plus longue partie »
        # ne montre que la date, donc ce motif isole exactement les entrees.
        import re
        dates = re.findall(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}", _labels(dlg))
        assert dates == ["25/08/2026  21:00", "20/08/2026  21:00"]

    def test_un_jeu_jamais_lance_n_a_aucune_ligne(self, qtbot, manager):
        """La regle « rien de normal ne s'affiche » sort GRATUITEMENT du
        format : aucune condition n'a eu a etre ecrite pour ca."""
        entrees = manager.get_games()
        stats.enregistrer_session(entrees[0].game.id, datetime(2026, 8, 25, 21, 0), 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert entrees[0].game.name in rendu
        assert entrees[5].game.name not in rendu

    def test_le_temps_anterieur_au_journal_est_annonce(self, qtbot, tmp_path,
                                                       monkeypatch):
        """Sans cette ligne, la somme du journal ne colle pas avec le total de
        l'en-tete — et quelqu'un qui le remarque cesse de croire la page."""
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        from src.core.game_data import load_catalog
        conf.playtime_seconds[load_catalog().games[0].id] = 21600
        dlg = StatsDialog(GameManager(conf))
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "Avant la mise en service du journal" in rendu
        assert "6 h" in rendu


class TestFaitsMarquants:
    def test_la_plus_longue_partie_porte_sa_date(self, qtbot, manager):
        """Date, c'est un souvenir ; sans date, c'est un chiffre."""
        gid = manager.get_games()[0].game.id
        stats.enregistrer_session(gid, datetime(2026, 8, 12, 20, 0), 3 * 3600 + 1200)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "12/08/2026" in _labels(dlg)

    def test_un_jeu_delaisse_depuis_peu_ne_dit_rien(self, qtbot, manager):
        gid = manager.get_games()[0].game.id
        stats.enregistrer_session(gid, datetime.now() - timedelta(days=5), 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "pas relancé depuis" not in _labels(dlg)

    def test_un_jeu_delaisse_depuis_longtemps_est_rappele(self, qtbot, manager):
        gid = manager.get_games()[0].game.id
        stats.enregistrer_session(gid, datetime.now() - timedelta(days=200), 7200)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert "pas relancé depuis" in _labels(dlg)

    def test_un_jeu_sans_session_datee_n_est_jamais_dit_delaisse(self, qtbot, tmp_path,
                                                                  monkeypatch):
        """Le temps herite n'a pas de date : on ne sait pas depuis quand il
        n'est plus lance, donc on se tait. Garde STRUCTURELLE — `derniere_par_jeu`
        ne voit que les sessions."""
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        from src.core.game_data import load_catalog
        conf.playtime_seconds[load_catalog().games[0].id] = 360000
        dlg = StatsDialog(GameManager(conf))
        qtbot.addWidget(dlg)
        assert "pas relancé depuis" not in _labels(dlg)


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

        w = _Frise(entrees, {})
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
        w = _Frise(entrees, {entrees[0].game.id: 3600})
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

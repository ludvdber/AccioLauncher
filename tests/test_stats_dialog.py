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
from src.ui.stats_dialog import _Mois, _Paragraphe, StatsDialog  # noqa: E402
from src.ui.stats_widgets import _CarteSauvegarde  # noqa: E402
from src.ui.stats_releve import _Ligne, _Nom, _Releve  # noqa: E402


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
        frises = dlg.findChildren(_Releve)
        assert len(frises) == 1
        assert len(frises[0]._entrees) == len(manager.get_games()) == 8
        assert len(frises[0].findChildren(_Ligne)) == 8

    def test_a_la_taille_d_un_portable_tout_reste_atteignable(self, qtbot, manager):
        """Devenue une PAGE de hauteur fixe, la page gardait le relevé hors de la
        zone défilante : à 980 × 600 (portable 1366 × 768), la zone des
        sauvegardes tombait à 1 px et le relevé recevait 590 px pour 634, d'où
        « À …rs » (2026-10-14). Toute la page défile ; la saga passe dessous."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QBoxLayout
        _remplir(manager, jours=14)
        dlg = StatsDialog(manager)
        dlg.setWindowFlags(Qt.WindowType.Widget)
        dlg.setMinimumSize(0, 0)
        qtbot.addWidget(dlg)
        dlg.resize(980, 600)
        dlg.show()
        qtbot.waitUntil(lambda: dlg._haut.direction() == QBoxLayout.Direction.TopToBottom,
                        timeout=1000)
        dlg.layout().activate()
        releve = dlg.findChildren(_Releve)[0]
        assert releve.width() >= releve.minimumSizeHint().width()


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
        assert vide.height() < 720, f"{vide.height()} px pour un releve et une phrase"
        _remplir(manager, jours=30)
        pleine = self._ouvrir(qtbot, manager)
        # Sans les cartes de sauvegarde (parties dans le folio), la page pleine
        # tient aussi sous la hauteur d'un portable.
        assert pleine.height() < 720, f"{pleine.height()} px pour le relevé et la saga"

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


class TestReleve:
    def test_le_dernier_jeu_joue_est_choisi_a_l_ouverture(self, qtbot, manager):
        ids = [e.game.id for e in manager.get_games()]
        stats.enregistrer_session(ids[0], datetime(2026, 8, 20, 21, 0), 3600)
        stats.enregistrer_session(ids[3], datetime(2026, 8, 25, 21, 0), 1800)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert dlg.findChildren(_Releve)[0].choix == ids[3]

    def test_un_jeu_sans_rien_ne_se_choisit_pas(self, qtbot, manager):
        ids = [e.game.id for e in manager.get_games()]
        stats.enregistrer_session(ids[0], datetime(2026, 8, 20, 21, 0), 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        etagere = dlg.findChildren(_Releve)[0]
        etagere.choisir(ids[5])
        assert etagere.choix == ids[0]

    def test_une_ligne_ouverte_mene_au_folio(self, qtbot, manager):
        """Sauvegardes et succès vivent dans le folio (2026-10-24) : un clic ou
        Entrée y mène, les flèches ne font que déplacer le choix."""
        ids = _remplir(manager, jours=4, jeux=2)
        demandes = []
        dlg = StatsDialog(manager, folio=demandes.append)
        qtbot.addWidget(dlg)
        etagere = dlg.findChildren(_Releve)[0]
        autre = ids[0] if etagere.choix == ids[1] else ids[1]
        etagere.choisir(autre)
        assert demandes == []
        from PyQt6.QtCore import Qt
        qtbot.keyClick(etagere, Qt.Key.Key_Return)
        assert demandes == [autre]

    def test_les_fleches_parcourent_les_jeux_choisissables(self, qtbot, manager):
        from PyQt6.QtCore import Qt
        ids = _remplir(manager, jours=4, jeux=2)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        etagere = dlg.findChildren(_Releve)[0]
        qtbot.keyClick(etagere, Qt.Key.Key_Home)
        assert etagere.choix == ids[0]
        qtbot.keyClick(etagere, Qt.Key.Key_Right)
        assert etagere.choix == ids[1]


class TestSaga:
    def test_le_mois_l_annee_et_le_total(self, qtbot, manager):
        gid = manager.get_games()[0].game.id
        maintenant = datetime.now().replace(microsecond=0)
        stats.enregistrer_session(gid, maintenant, 2 * 3600)
        stats.enregistrer_session(gid, maintenant.replace(year=maintenant.year - 1, month=6, day=1), 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "Au total" in rendu
        assert f"En {maintenant.year}" in rendu

    def test_une_ligne_qui_redit_le_chiffre_du_dessus_ne_s_ecrit_pas(self, qtbot, manager):
        """« Au total 13 h 18 · En 2026 13 h 18 · En octobre 13 h 18 » : trois
        fois le même chiffre (Ludo, 2026-10-14). Tout joué ce mois-ci : le total seul."""
        gid = manager.get_games()[0].game.id
        stats.enregistrer_session(gid, datetime.now().replace(microsecond=0), 2 * 3600)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "Au total" in rendu
        # Ni l'année ni le mois : aucune ligne « En … ».
        assert not [ligne for ligne in rendu.splitlines() if ligne.startswith("En ")]

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
        assert "sans date" in rendu
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

    def test_aucun_nom_de_mois_n_est_rogne(self, qtbot):
        """« n… ja… fé… se… » sous les barres, vu avec les vraies polices le
        2026-10-14 : les abréviations ne tenaient pas dans une colonne sur douze."""
        from PyQt6.QtGui import QFont, QFontMetrics
        from src.ui.stats_dialog import _COLONNE_DROITE
        cases = [(2025 + (m + 10) // 12, (m + 10) % 12 + 1, 3600) for m in range(12)]
        mois = _Mois(cases)
        qtbot.addWidget(mois)
        mois.resize(_COLONNE_DROITE, mois.height())
        police = QFont()
        police.setPointSize(8)
        fm = QFontMetrics(police)
        noms = mois._noms(fm)
        assert len(noms) == 12
        assert all(fm.horizontalAdvance(n) <= mois._colonne(0).width() for n in noms), noms

    def test_le_chiffre_d_une_barre_n_est_pas_rogne(self, qtbot):
        """« 14… » au-dessus de septembre à toutes les tailles (Bazzite,
        2026-10-20) : le chiffre ne disposait que de la largeur de sa barre."""
        from PyQt6.QtGui import QFont, QFontMetrics
        from src.ui.stats_dialog import _COLONNE_DROITE
        cases = [(2026, m, 0) for m in range(1, 13)]
        cases[8] = (2026, 9, 14 * 3600)
        mois = _Mois(cases)
        qtbot.addWidget(mois)
        mois.resize(_COLONNE_DROITE, mois.height())
        police = QFont()
        police.setPointSize(8)
        gauche, droite = mois._place_valeur(8)
        assert QFontMetrics(police).horizontalAdvance("14 h") <= droite - gauche
        assert droite - gauche > mois._colonne(8).width()

    def test_le_dernier_mois_au_bord_n_est_pas_rogne(self, qtbot):
        """Octobre (2 h 53, la plus haute) collé au bord droit, septembre (1 h)
        à côté : « 3… » au Relevé de Ludo le 2026-10-24."""
        from PyQt6.QtGui import QFont, QFontMetrics
        from src.ui.stats_dialog import _COLONNE_DROITE
        cases = [(2025 + (m + 10) // 12, (m + 10) % 12 + 1, 0) for m in range(12)]
        cases[10] = (2026, 9, 3600)
        cases[11] = (2026, 10, 2 * 3600 + 53 * 60)
        mois = _Mois(cases)
        qtbot.addWidget(mois)
        mois.resize(_COLONNE_DROITE, mois.height())
        police = QFont()
        police.setPointSize(8)
        gauche, droite = mois._place_valeur(11)
        assert QFontMetrics(police).horizontalAdvance("3 h") <= droite - gauche

        class ArrondiA125:
            """La mesure arrondie (15) sous-estime le dessin (15,4) : ce qui
            se passait avec Gelasio à 125 %, et pas avec la police d'offscreen."""
            def horizontalAdvance(self, texte):
                return 15

            def elidedText(self, texte, _mode, largeur):
                return texte if largeur >= 15.4 else texte[0] + "…"
        assert mois._valeur(11, ArrondiA125())[2] == "3 h"

    def test_deux_chiffres_voisins_ne_se_chevauchent_pas(self, qtbot):
        cases = [(2026, m, 3600) for m in range(1, 13)]
        mois = _Mois(cases)
        qtbot.addWidget(mois)
        mois.resize(300, mois.height())
        assert mois._place_valeur(3)[1] <= mois._place_valeur(4)[0]


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

    def test_les_sauvegardes_vivent_dans_le_folio(self, qtbot, manager):
        self._save("Save0.usa", datetime(2026, 3, 8))
        self._save("Save1.usa", datetime(2026, 4, 3))
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        assert dlg.findChildren(_Releve)[0].choix == "hp1"
        assert not dlg.findChildren(_CarteSauvegarde)
        assert "Vos sauvegardes sont là" in _labels(dlg)

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
        entrees = list(manager.get_games())
        piege = dataclasses.replace(entrees[2].game, name='<img src="file:///C:/x.png">')
        entrees[2] = entrees[2]._replace(game=piege)   # GameEntry est un NamedTuple

        w = _Releve(entrees, {}, {}, {}, {}, set())
        qtbot.addWidget(w)
        bulles = [n.toolTip() for n in w.findChildren(_Nom)]
        assert "&lt;img" in " ".join(bulles)
        assert not any("<img" in b for b in bulles)


class TestReleveSeDessine:
    def test_de_l_encre_est_posee(self, qtbot, manager):
        """Jaquettes et barres sont peintes : un paintEvent muet passerait tous
        les autres tests sans qu'on voie rien a l'ecran."""
        from PyQt6.QtGui import QColor, QImage, QPainter
        entrees = manager.get_games()
        gid = entrees[0].game.id
        w = _Releve(entrees, {gid: 3600}, {gid: 2}, {}, {gid: "1 h"}, {gid}, gid)
        qtbot.addWidget(w)
        w.resize(900, w.sizeHint().height())
        img = QImage(w.size(), QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        w.render(p)
        p.end()
        poses = sum(1 for y in range(0, img.height(), 2) for x in range(0, img.width(), 2)
                    if QColor.fromRgba(img.pixel(x, y)).alpha() > 0)
        assert poses > 2000, f"releve quasi vide : {poses} pixels"

    def test_l_annee_sept_a_deux_lignes_et_un_seul_chiffre(self, qtbot, manager):
        w = _Releve(manager.get_games(), {}, {}, {}, {}, set())
        qtbot.addWidget(w)
        textes = [lbl.text() for lbl in w.findChildren(QLabel)]
        assert textes.count("VII") == 1
        septieme = [e.game.id for e in manager.get_games() if e.game.annee == 7]
        rattachees = [li.game_id for li in w.findChildren(_Ligne) if li._rattachee]
        assert len(septieme) == 2 and rattachees == septieme[1:]

    def test_hors_des_cours_seulement_s_il_y_a_un_tel_jeu(self, qtbot, manager):
        import dataclasses
        w = _Releve(manager.get_games(), {}, {}, {}, {}, set())
        qtbot.addWidget(w)
        assert "HORS DES COURS" not in [lbl.text() for lbl in w.findChildren(QLabel)]
        entrees = list(manager.get_games())
        entrees[0] = entrees[0]._replace(game=dataclasses.replace(entrees[0].game, annee=0))
        w = _Releve(entrees, {}, {}, {}, {}, set())
        qtbot.addWidget(w)
        assert "HORS DES COURS" in [lbl.text() for lbl in w.findChildren(QLabel)]


class TestParagrapheMesure:
    def test_la_hauteur_suit_la_largeur_reelle(self, qtbot, mise_en_page_stable):
        lbl = _Paragraphe(" · ".join(["Harry Potter et la Chambre des Secrets"] * 4))
        qtbot.addWidget(lbl)
        lbl.show()
        lbl.resize(300, 10)
        mise_en_page_stable(lbl)
        assert lbl.minimumHeight() > lbl.fontMetrics().height() * 2

    def test_elle_se_recalcule_en_s_elargissant(self, qtbot, mise_en_page_stable):
        lbl = _Paragraphe(" · ".join(["Harry Potter et la Coupe de Feu"] * 4))
        qtbot.addWidget(lbl)
        lbl.show()
        lbl.resize(240, 10)
        mise_en_page_stable(lbl)
        etroit = lbl.minimumHeight()
        lbl.resize(900, 10)
        mise_en_page_stable(lbl)
        assert lbl.minimumHeight() < etroit


class TestBoutonDeFenetre:
    def test_la_fenetre_porte_une_commande_de_statistiques(self, qtbot, tmp_path,
                                                           monkeypatch, mise_en_page_stable):
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
        mise_en_page_stable(win)
        assert win._btn_stats.isVisible()
        assert not win._btn_stats.geometry().intersects(win._btn_settings.geometry())


class TestRetoursDuDixNeufSeptembre:
    """Capture de Ludo du 2026-09-19 : un titre, un total dit deux fois, une
    legende « sauvegardes », et une colonne dont les chiffres ne s'additionnaient
    pas (46 au total, dont 43 cette annee et 4 d'avant)."""

    def test_le_total_n_est_plus_repete_en_tete(self, qtbot, manager):
        _remplir(manager, jours=3, jeux=2)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "jeux de la saga" not in rendu
        assert rendu.count("Au total") == 1

    def test_les_chiffres_affiches_s_additionnent(self, qtbot, tmp_path, monkeypatch):
        """46,5 min au total = 42,9 cette annee + 3,6 d'avant : arrondis un par
        un, 46 ≠ 43 + 4. Le total affiche doit etre la somme de ses parties."""
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        from src.core.game_data import load_catalog
        gid = load_catalog().games[0].id
        conf.playtime_seconds[gid] = 214
        man = GameManager(conf)
        stats.enregistrer_session(gid, datetime.now().replace(microsecond=0), 2576)
        dlg = StatsDialog(man)
        qtbot.addWidget(dlg)
        rendu = _labels(dlg)
        assert "47 min" in rendu
        assert "43 min" in rendu and "Dont 4 min" in rendu

    def test_une_jaquette_sans_temps_ne_dit_pas_sauvegardes(self, qtbot, manager):
        TestSauvegardesAffichees._save("Save0.usa", datetime(2026, 3, 8))
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        legendes = dlg.findChildren(_Releve)[0]._legendes
        assert legendes["hp1"] == "—"


    @staticmethod
    def _carte(qtbot, commencee, derniere):
        """La carte seule, a partir d'une `Vue` : le test ne depend plus de ce
        que le SYSTEME sait des fichiers. Sous Linux, un fichier n'a pas de
        date de creation lisible (pas de `st_birthtime`) — la version
        precedente de ce test la supposait, et n'echouait donc que sur la CI
        Linux."""
        from src.core.sauvegardes import Vue
        carte = _CarteSauvegarde(Vue("Save0.usa", 1, commencee, derniere, 0, None), 0)
        qtbot.addWidget(carte)
        return [lbl.text() for lbl in carte.findChildren(QLabel)]

    def test_une_seule_date_quand_elles_se_confondent(self, qtbot):
        from datetime import date
        textes = self._carte(qtbot, date(2026, 3, 8), date(2026, 3, 8))
        assert "Jouée le" in textes and "08/03/2026" in textes
        assert "Commencée" not in textes

    def test_deux_dates_quand_elles_different(self, qtbot):
        from datetime import date
        textes = self._carte(qtbot, date(2026, 3, 4), date(2026, 4, 6))
        assert "Commencée" in textes and "Dernière fois" in textes

    def test_sans_date_de_creation_seule_la_derniere_est_dite(self, qtbot):
        """Le cas Linux : on ne sait pas quand elle a commence, on ne le dit
        pas — ni « Jouée le », qui laisserait croire a une seule seance."""
        from datetime import date
        textes = self._carte(qtbot, None, date(2026, 3, 8))
        assert "Dernière fois" in textes
        assert "Commencée" not in textes and "Jouée le" not in textes


def test_la_barre_du_mois_et_la_colonne_disent_le_meme_chiffre():
    """38,5 min : 38 sur la barre (arrondi au pair), 39 dans la colonne."""
    from src.ui.stats_dialog import _duree_courte, _minutes
    assert _duree_courte(2310) == "39 min" and _minutes(2310) == 39


class TestCouleursDeLaMaison:
    def test_aucun_chiffre_ne_reste_en_or_poudlard(self, qtbot, manager):
        """« Au total », « dernière jouée » et le temps d'une sauvegarde étaient
        en `#d6a72c` écrit en dur (vérification du 2026-10-14)."""
        from src.ui.theme import set_theme
        set_theme("gryffondor")
        try:
            _remplir(manager)
            dlg = StatsDialog(manager)
            qtbot.addWidget(dlg)
            restes = [lbl.text() for lbl in dlg.findChildren(QLabel)
                      if "#d6a72c" in lbl.styleSheet().lower()]
            assert not restes, restes
        finally:
            set_theme("poudlard")


class TestPhraseDEntete:
    """« Élève de Serdaigle » sous le titre, et rien d'autre.

    Le compte des années et « Vous êtes en 7ᵉ année » sont partis le 2026-10-14
    (Ludo) : le relevé montre déjà ce qui est fait.
    """

    def test_la_maison_seule(self):
        from src.ui.theme import THEMES
        assert StatsDialog._phrase_entete(THEMES["serdaigle"]) == "Élève de Serdaigle"

    def test_sans_maison_rien_d_ecrit(self):
        from src.ui.theme import THEMES
        assert StatsDialog._phrase_entete(THEMES["poudlard"]) == ""

    def test_plus_aucun_compte_d_annees_sur_la_page(self, qtbot, manager):
        """Même quand des années sont commencées."""
        _remplir(manager)
        dlg = StatsDialog(manager)
        qtbot.addWidget(dlg)
        textes = _labels(dlg)
        assert "commencée" not in textes
        assert "Vous êtes en" not in textes
        assert "vous attend" not in textes


class TestGrilleSauvegardes:
    """Plein écran : quatre cartes côte à côte, plafonnées, au lieu de deux
    bandeaux de 980 px (capture de Ludo, 2026-10-16)."""

    @pytest.mark.parametrize(("largeur", "nombre", "colonnes"), [
        (500, 4, 1), (700, 4, 2), (1000, 4, 3), (1960, 4, 4), (1960, 3, 3), (1960, 9, 4)])
    def test_les_colonnes_suivent_la_largeur(self, largeur, nombre, colonnes):
        from src.ui.stats_widgets import _GrilleSauvegardes
        assert _GrilleSauvegardes.colonnes(largeur, nombre) == colonnes

    def test_une_carte_ne_s_etire_plus(self, qtbot):
        from PyQt6.QtWidgets import QFrame
        from src.ui.stats_widgets import _GrilleSauvegardes
        cartes = [QFrame() for _ in range(3)]
        grille = _GrilleSauvegardes(cartes)
        qtbot.addWidget(grille)
        grille.resize(1960, 200)
        grille.show()
        qtbot.waitUntil(lambda: grille._colonnes == 3)
        assert all(c.width() <= _GrilleSauvegardes.LARGEUR_MAX for c in cartes)


class TestJaquettes:
    def test_une_jaquette_n_est_decodee_qu_une_fois(self, qtbot):
        """Le Relevé et les pastilles des Collections la redemandaient à chaque visite."""
        from src.ui import stats_releve
        stats_releve._jaquette_decodee.cache_clear()
        premiere = stats_releve._jaquette("hp1_cover.jpg")
        seconde = stats_releve._jaquette("hp1_cover.jpg")
        assert premiere is not None and not premiere.isNull()
        assert seconde.size() == premiere.size() and seconde.height() <= 84
        assert stats_releve._jaquette_decodee.cache_info().hits == 1

    def test_une_jaquette_absente_ne_plante_pas(self, qtbot):
        from src.ui import stats_releve
        assert stats_releve._jaquette("personne.jpg") is None

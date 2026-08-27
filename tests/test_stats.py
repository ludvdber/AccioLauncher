"""Journal des sessions et statistiques derivees.

Le point de vigilance de ce module n'est pas un calcul, c'est une SEPARATION :
le temps joue avant la creation du journal (`herite`) compte dans les totaux —
il a reellement ete joue — mais ne doit entrer dans AUCUNE moyenne, serie ou
repartition horaire, faute d'avoir une date, une duree de session ou une heure.
Une seule fonction a le droit d'y toucher. `TestHeriteNEntreQueDansLesTotaux`
verifie exactement ca, et c'est le test a ne jamais assouplir.
"""

import json
from datetime import date, datetime, timedelta

import pytest

from src.core import stats
from src.core.formatting import format_duree_compacte


def _s(jeu, jour, heure=21, duree=3600):
    """Session d'essai : `jour` est un decalage NEGATIF en jours depuis aujourd'hui."""
    debut = (datetime.now() + timedelta(days=jour)).replace(
        hour=heure, minute=0, second=0, microsecond=0)
    return stats.Session(jeu=jeu, debut=debut, duree=duree)


def _hist(sessions=(), herite=None, **kw):
    return stats.Historique(tuple(sessions), dict(herite or {}), **kw)


@pytest.fixture
def journal(tmp_path):
    return tmp_path / "sessions.json"


class TestFichier:
    def test_aller_retour(self, journal):
        stats.amorcer({}, journal)
        stats.enregistrer_session("hp3", datetime(2026, 8, 20, 21, 30), 3600, journal)
        stats.enregistrer_session("hp2", datetime(2026, 8, 21, 19, 0), 1800, journal)
        hist = stats.charger(journal)
        assert [(s.jeu, s.duree) for s in hist.sessions] == [("hp3", 3600), ("hp2", 1800)]
        assert hist.sessions[0].debut == datetime(2026, 8, 20, 21, 30)

    def test_fichier_absent(self, journal):
        hist = stats.charger(journal)
        assert hist.vide and hist.sessions == () and hist.demarrages == 0

    def test_un_journal_illisible_est_mis_de_cote_et_non_ecrase(self, journal):
        """C'est un historique personnel : il ne se reconstruit pas.

        L'ecraser en silence sous la prochaine ecriture serait le pire des deux
        comportements possibles — on perd la donnee ET on ne le sait pas.
        """
        journal.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
        assert stats.charger(journal).vide
        assert journal.with_suffix(".corrompu").exists()

    def test_une_entree_fautive_ne_perd_pas_les_autres(self, journal):
        journal.write_text(json.dumps({"sessions": [
            {"jeu": "hp1", "debut": "2026-08-20T21:00:00", "duree": 3600},
            "pas un dict",
            {"jeu": "", "debut": "2026-08-20T21:00:00", "duree": 3600},
            {"jeu": "hp2", "debut": "pas une date", "duree": 3600},
            {"jeu": "hp3", "debut": "2026-08-20T21:00:00", "duree": "beaucoup"},
            {"jeu": "hp4", "debut": "2026-08-21T21:00:00", "duree": 1200},
        ]}), encoding="utf-8")
        assert [s.jeu for s in stats.charger(journal).sessions] == ["hp1", "hp4"]

    def test_les_sessions_sont_triees_par_date(self, journal):
        """Les series de jours et la premiere partie en dependent, et rien ne
        garantit l'ordre d'un fichier qu'on n'a pas ecrit soi-meme."""
        journal.write_text(json.dumps({"sessions": [
            {"jeu": "b", "debut": "2026-08-22T10:00:00", "duree": 600},
            {"jeu": "a", "debut": "2026-08-20T10:00:00", "duree": 600},
        ]}), encoding="utf-8")
        assert [s.jeu for s in stats.charger(journal).sessions] == ["a", "b"]

    def test_une_session_trop_courte_n_entre_pas(self, journal):
        """Un double-clic malheureux ou un jeu qui refuse de demarrer n'est pas
        une partie, et fausserait la duree moyenne vers le bas."""
        stats.enregistrer_session("hp1", datetime.now(), 3, journal)
        assert stats.charger(journal).sessions == ()

    def test_plafond_de_sessions(self, journal):
        """Borne ce qu'un fichier trafique peut charger en memoire."""
        trop = stats._MAX_SESSIONS + 50
        journal.write_text(json.dumps({"sessions": [
            {"jeu": "hp1", "debut": f"2026-01-01T{i % 24:02d}:00:00", "duree": 600}
            for i in range(trop)]}), encoding="utf-8")
        assert len(stats.charger(journal).sessions) == stats._MAX_SESSIONS

    def test_une_ecriture_impossible_ne_remonte_pas(self, journal, monkeypatch):
        """Perdre une statistique n'est pas une raison d'interrompre une partie
        qui vient de se terminer — l'appelant est `add_playtime`."""
        def _echec(*_a, **_k):
            raise OSError("disque plein")
        monkeypatch.setattr(stats, "_ecrire", _echec)
        stats.enregistrer_session("hp1", datetime.now(), 3600, journal)  # ne leve pas


class TestAmorcage:
    def test_gele_les_cumuls_deja_connus(self, journal):
        assert stats.amorcer({"hp2": 12000, "hp3": 0}, journal) is True
        hist = stats.charger(journal)
        assert hist.herite == {"hp2": 12000}  # un cumul nul n'est pas de l'historique

    def test_idempotent(self, journal):
        """Elle tourne a CHAQUE construction de GameManager : un deuxieme
        passage qui reprendrait les cumuls recompterait tout le temps joue
        depuis, a chaque demarrage."""
        stats.amorcer({"hp2": 12000}, journal)
        stats.enregistrer_session("hp2", datetime.now(), 3600, journal)
        assert stats.amorcer({"hp2": 15600}, journal) is False
        assert stats.charger(journal).herite == {"hp2": 12000}

    def test_survit_a_un_dossier_absent(self, tmp_path):
        assert stats.amorcer({"hp1": 60}, tmp_path / "pas" / "encore" / "s.json")


class TestHeriteNEntreQueDansLesTotaux:
    """L'invariant structurel du module — voir l'en-tete de ce fichier."""

    @pytest.fixture
    def que_de_l_herite(self):
        return _hist(herite={"hp2": 7200})

    def test_le_total_le_compte(self, que_de_l_herite):
        assert stats.temps_total(que_de_l_herite) == 7200
        assert stats.temps_par_jeu(que_de_l_herite) == {"hp2": 7200}

    def test_aucune_derivation_de_session_ne_le_voit(self, que_de_l_herite):
        h = que_de_l_herite
        assert stats.duree_moyenne(h) == 0
        assert stats.parties_par_jeu(h) == {}
        assert stats.plus_longue(h) is None
        assert stats.jours_joues(h) == []
        assert stats.serie_actuelle(h) == 0
        assert stats.meilleure_serie(h) == 0
        assert stats.par_heure(h) == [0] * 24
        assert stats.par_jour_semaine(h) == [0] * 7
        assert stats.plage_de_predilection(h) is None
        assert stats.jour_prefere(h) is None
        assert stats.premiere_session(h) is None

    def test_le_total_additionne_herite_et_sessions(self):
        h = _hist([_s("hp2", 0, duree=1800)], herite={"hp2": 7200})
        assert stats.temps_par_jeu(h) == {"hp2": 9000}


class TestSeries:
    def test_une_serie_qui_finit_aujourd_hui(self):
        h = _hist([_s("hp1", -2), _s("hp1", -1), _s("hp1", 0)])
        assert stats.serie_actuelle(h) == 3

    def test_hier_maintient_la_serie(self):
        """La journee n'est pas finie : annoncer la serie rompue avant minuit
        serait faux, et decourageant au moment precis ou elle tient encore."""
        h = _hist([_s("hp1", -2), _s("hp1", -1)])
        assert stats.serie_actuelle(h) == 2

    def test_avant_hier_la_rompt(self):
        assert stats.serie_actuelle(_hist([_s("hp1", -2)])) == 0

    def test_plusieurs_parties_le_meme_jour_comptent_pour_un_jour(self):
        h = _hist([_s("hp1", -1, heure=14), _s("hp1", -1, heure=21), _s("hp1", 0)])
        assert stats.serie_actuelle(h) == 2

    def test_le_record_survit_a_une_coupure(self):
        h = _hist([_s("hp1", -20), _s("hp1", -19), _s("hp1", -18), _s("hp1", -17),
                   _s("hp1", -1), _s("hp1", 0)])
        assert stats.meilleure_serie(h) == 4
        assert stats.serie_actuelle(h) == 2

    def test_aucune_session(self):
        assert stats.serie_actuelle(_hist()) == 0
        assert stats.meilleure_serie(_hist()) == 0

    def test_serie_calculee_a_une_date_donnee(self):
        """Sans injection possible, ce test ne passerait qu'un jour sur deux."""
        h = stats.Historique((
            stats.Session("hp1", datetime(2026, 8, 24, 21), 3600),
            stats.Session("hp1", datetime(2026, 8, 25, 21), 3600),
        ))
        assert stats.serie_actuelle(h, date(2026, 8, 25)) == 2
        assert stats.serie_actuelle(h, date(2026, 8, 26)) == 2  # hier : vivante
        assert stats.serie_actuelle(h, date(2026, 8, 27)) == 0  # rompue


class TestDerivations:
    def test_moyenne_et_plus_longue(self):
        h = _hist([_s("hp1", -3, duree=1200), _s("hp2", -2, duree=3600),
                   _s("hp1", -1, duree=2400)])
        assert stats.duree_moyenne(h) == 2400
        longue = stats.plus_longue(h)
        assert (longue.jeu, longue.duree) == ("hp2", 3600)

    def test_parties_et_derniere_par_jeu(self):
        h = _hist([_s("hp1", -5), _s("hp1", -1), _s("hp2", -3)])
        assert stats.parties_par_jeu(h) == {"hp1": 2, "hp2": 1}
        derniere = stats.derniere_par_jeu(h)
        assert derniere["hp1"] == (datetime.now() - timedelta(days=1)).date()

    def test_repartition_horaire(self):
        h = _hist([_s("hp1", -1, heure=21, duree=3600),
                   _s("hp1", -2, heure=21, duree=1800),
                   _s("hp1", -3, heure=9, duree=600)])
        cases = stats.par_heure(h)
        assert cases[21] == 5400 and cases[9] == 600 and sum(cases) == 6000

    def test_plage_de_predilection(self):
        h = _hist([_s("hp1", -i, heure=22, duree=3600) for i in range(1, 6)])
        debut, fin = stats.plage_de_predilection(h)
        assert debut <= 22 < debut + 3
        assert fin == (debut + 3) % 24

    def test_la_plage_boucle_sur_minuit(self):
        """23 h, minuit et 1 h forment une soiree, pas trois moments epars."""
        h = _hist([_s("hp1", -1, heure=23), _s("hp1", -2, heure=0),
                   _s("hp1", -3, heure=1)])
        assert stats.plage_de_predilection(h) == (23, 2)

    def test_jour_prefere(self):
        h = stats.Historique((
            stats.Session("hp1", datetime(2026, 8, 22, 21), 7200),  # samedi
            stats.Session("hp1", datetime(2026, 8, 24, 21), 600),   # lundi
        ))
        assert stats.jour_prefere(h) == 5  # 0 = lundi

    def test_premiere_session(self):
        h = _hist([_s("hp1", -10), _s("hp2", -1)])
        assert stats.premiere_session(h).date() == (
            datetime.now() - timedelta(days=10)).date()

    def test_vide(self):
        assert _hist().vide
        assert not _hist(herite={"hp1": 60}).vide
        assert not _hist([_s("hp1", 0)]).vide
        # Un cumul a zero n'est pas de l'historique : la page doit rester en
        # etat vide plutot que d'afficher « 0 min de jeu au total ».
        assert _hist(herite={"hp1": 0}).vide


class TestFormatage:
    @pytest.mark.parametrize("secondes,attendu", [
        (30, "moins d'une minute"),
        (90, "2 min"),
        (2880, "48 min"),
        (3600, "1 h"),
        (3720, "1 h 02 min"),   # minutes sur DEUX chiffres : « 1 h 2 min » se
                                # lit comme une coquille
        (9300, "2 h 35 min"),
        (50400, "14 h"),
    ])
    def test_duree_compacte(self, secondes, attendu):
        assert format_duree_compacte(secondes) == attendu


class TestCablage:
    """Le journal doit se remplir par le chemin REEL, pas seulement en test."""

    def test_add_playtime_journalise(self, tmp_path, monkeypatch):
        from src.core.config import Config
        from src.core.game_manager import GameManager

        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        conf = Config(install_path=tmp_path / "g", cache_path=tmp_path / "g" / "c")
        manager = GameManager(conf)
        gid = manager.get_games()[0].game.id

        manager.add_playtime(gid, 3600)
        hist = stats.charger(stats.chemin_journal())
        assert [(s.jeu, s.duree) for s in hist.sessions] == [(gid, 3600)]
        # L'heure de debut est reconstituee par soustraction : elle doit tomber
        # une heure avant maintenant, pas a l'instant de l'ecriture.
        ecart = (datetime.now() - hist.sessions[0].debut).total_seconds()
        assert 3595 < ecart < 3620

    def test_le_chemin_suit_config_file_path(self, tmp_path, monkeypatch):
        """C'est ce qui fait heriter le journal de la garde du conftest : sans
        ca, un test ecrirait dans les vraies statistiques de l'utilisateur —
        c'est deja arrive le 2026-08-18."""
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        assert stats.chemin_journal() == tmp_path / stats.JOURNAL_NAME


class TestCompteurs:
    """Les deux entiers du journal s'incrementent SANS relire les sessions.

    Le chemin rapide (`_muter_compteur`) reecrit le dictionnaire brut au lieu
    de reconstruire tout l'historique : il doit rendre exactement le meme
    fichier que l'ancien chemin, sessions et herite intacts. C'est la seule
    chose qui rende l'optimisation sans risque — mesure au passage :
    `enregistrer_demarrage` tombe de 105 a 45 ms au plafond de 20 000 sessions,
    et il est paye avant le premier rendu de la fenetre.
    """

    def test_demarrage_incremente_sans_toucher_au_reste(self, tmp_path):
        ch = tmp_path / "sessions.json"
        stats.amorcer({"hp1": 7200}, ch)
        stats.enregistrer_session("hp2", datetime(2026, 8, 20, 21, 0), 3600, ch)

        stats.enregistrer_demarrage(ch)
        stats.enregistrer_demarrage(ch)

        hist = stats.charger(ch)
        assert hist.demarrages == 2
        assert hist.herite == {"hp1": 7200}
        assert [(s.jeu, s.duree) for s in hist.sessions] == [("hp2", 3600)]

    def test_octets_se_cumulent(self, tmp_path):
        ch = tmp_path / "sessions.json"
        stats.amorcer({}, ch)
        stats.enregistrer_telechargement(1_000, ch)
        stats.enregistrer_telechargement(2_500, ch)
        stats.enregistrer_telechargement(0, ch)      # ignore
        stats.enregistrer_telechargement(-5, ch)     # ignore
        assert stats.charger(ch).octets_telecharges == 3_500

    def test_journal_absent_le_chemin_complet_prend_le_relais(self, tmp_path):
        """Le fichier n'existe pas encore : le compteur doit quand meme
        atterrir, exactement comme avant l'optimisation."""
        ch = tmp_path / "sessions.json"
        stats.enregistrer_demarrage(ch)
        assert ch.exists()
        assert stats.charger(ch).demarrages == 1

    def test_un_compteur_trafique_a_la_main_ne_fait_pas_planter(self, tmp_path):
        ch = tmp_path / "sessions.json"
        stats.amorcer({}, ch)
        data = json.loads(ch.read_text(encoding="utf-8"))
        data["demarrages"] = "beaucoup"
        ch.write_text(json.dumps(data), encoding="utf-8")
        stats.enregistrer_demarrage(ch)
        assert stats.charger(ch).demarrages == 1

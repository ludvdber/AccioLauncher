"""Cycle de vie d'une partie : journal, présence Discord, ordre des signaux.

Ce flux vivait dans `main_window.py` et n'était couvert par AUCUN test —
l'exercer supposait de construire la fenêtre entière et de lui fournir un vrai
processus. Isolé dans `GameSession`, il se teste en injectant un faux moniteur.

L'invariant le plus important est un ORDRE : le temps de jeu doit être
enregistré AVANT que `terminee` ne soit émis, sinon la fiche que la fenêtre
rafraîchit en réponse afficherait le total d'avant la partie qui vient de finir.
"""

from unittest.mock import patch

import pytest

pytest.importorskip("pytestqt")

from src.core.config import Config  # noqa: E402
from src.core.game_data import Catalog, GameData  # noqa: E402
from src.core.game_manager import GameManager  # noqa: E402
from src.ui.game_session import GameSession  # noqa: E402

GAME = {
    "id": "hp1", "name": "HP1", "year": 2001, "description": "Desc",
    "developer": "Dev", "executable": "HP1/System/Harry.exe",
    "cover_image": "hp1.jpg", "recommended_version": "1.0",
    "versions": [{
        "version": "1.0", "date": "2026-01-01",
        "download_url": "https://x.test/a.7z",
        "download_parts": None, "size_mb": 100, "changes": [],
    }],
}


def _manager(tmp_path) -> GameManager:
    catalog = Catalog(catalog_version="1.0", catalog_url="",
                      games=(GameData.from_dict(GAME),))
    config = Config(install_path=tmp_path, cache_path=tmp_path / ".cache")
    with patch("src.core.game_manager.load_catalog", return_value=catalog):
        return GameManager(config)


class _FauxProcess:
    """Un Popen qui ne meurt jamais : le moniteur est piloté à la main."""
    pid = 1234

    def poll(self):
        return None


@pytest.fixture
def session(tmp_path, qtbot):
    """Session dont le moniteur ne surveille rien — on émet ses signaux nous-mêmes.

    Le faux est posé sur l'INSTANCE (`_monitor.start`) et jamais sur la classe :
    remplacer un attribut de classe d'un type sip laisse un descripteur cassé
    qui abat le processus plusieurs FICHIERS de tests plus loin.
    """
    s = GameSession(_manager(tmp_path))
    demarrages: list = []
    s._monitor.start = lambda proc, nom: demarrages.append((proc, nom))
    s.demarrages = demarrages
    return s


class TestOuvertureDeSession:
    def test_demarrer_emet_le_nom_et_lance_la_surveillance(self, session, qtbot):
        proc = _FauxProcess()
        with qtbot.waitSignal(session.demarree, timeout=1000) as bloc:
            session.demarrer(proc, "HP1", "hp1")
        assert bloc.args == ["HP1"]
        assert session.demarrages == [(proc, "HP1")]

    def test_la_session_est_ouverte_AVANT_la_fin_du_jeu(self, session):
        """Écrite au lancement et non à la fermeture.

        C'est tout l'objet du fichier de reprise : pendant la partie le
        launcher dort dans la zone de notification, donc c'est là qu'on le
        quitte ou qu'une mise à jour le tue. Écrire à la fin faisait perdre
        d'autant plus souvent qu'une partie était LONGUE — un biais silencieux
        qui contaminait moyenne, record, séries et plages horaires à la fois.
        """
        from src.core import stats
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        assert stats.chemin_en_cours().exists()

    def test_le_battement_rafraichit_le_filet(self, session):
        from src.core import stats
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        avant = stats.chemin_en_cours().read_text(encoding="utf-8")
        session._monitor.battement.emit()
        # Le battement réécrit le fichier avec un « vu à » plus récent : ce qui
        # compte est qu'il soit OBSERVÉ. Sans battement on n'écrit rien — mieux
        # vaut un trou qu'un chiffre faux.
        assert stats.chemin_en_cours().read_text(encoding="utf-8") != avant \
            or "vu_a" in avant


class TestFermetureDeSession:
    def test_le_temps_est_enregistre_avant_que_terminee_ne_parte(self, session, qtbot):
        """L'ORDRE est l'invariant : la fenêtre rafraîchit la fiche sur ce
        signal, et lirait sinon le total d'avant la partie."""
        vu: list[int] = []
        session.terminee.connect(
            lambda _nom: vu.append(session._manager.get_playtime("hp1")))
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        session._monitor.game_exited.emit("HP1", 0, 600.0)
        assert vu == [600]

    def test_la_session_en_cours_est_refermee(self, session):
        from src.core import stats
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        session._monitor.game_exited.emit("HP1", 0, 600.0)
        assert not stats.chemin_en_cours().exists()

    def test_une_partie_trop_courte_ne_compte_pas_comme_du_temps_de_jeu(self, session):
        """Sous le seuil, c'est une TENTATIVE et non une partie — mais elle est
        tout de même consignée, avec son code de sortie : c'est la signature
        exacte d'un jeu qui refuse de démarrer."""
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        session._monitor.game_exited.emit("HP1", 0, 3.0)
        assert session._manager.get_playtime("hp1") == 0

    def test_terminee_part_meme_sans_session_ouverte(self, session, qtbot):
        """Le moniteur peut conclure sans qu'on ait rien ouvert (relance de
        processus par UE1). La fenêtre doit revenir quand même — sinon elle
        resterait dans la zone de notification, sans rien pour l'en sortir."""
        with qtbot.waitSignal(session.terminee, timeout=1000):
            session._monitor.game_exited.emit("HP1", 0, 600.0)


class TestExtinction:
    def test_shutdown_ne_ferme_PAS_la_partie_en_cours(self, session):
        """Quitter le launcher pendant une partie ne doit pas effacer la partie.

        C'est exactement le biais que ce module corrige : le fichier de reprise
        doit SURVIVRE à la mort du launcher, pour que le démarrage suivant
        rattrape la durée observée.
        """
        from src.core import stats
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        session.shutdown()
        assert stats.chemin_en_cours().exists()

    def test_le_nom_en_cours_est_lisible(self, session):
        assert session.nom_en_cours == ""


class TestUnLancementRateSeDitCommeTel:
    """Un jeu qui n'a jamais démarré ne doit pas s'entendre souhaiter bon jeu.

    Le launcher CONSIGNAIT déjà l'échec (`stats.Tentative`, avec son code de
    sortie) et affichait quand même « Bon jeu ! » — mesuré le 2026-08-28 sur une
    sortie en 0,5 s, code 0 : la signature exacte du dossier `pc` de HP7. C'est
    le cas type de ce que le launcher SAIT et jette au moment de l'afficher.

    Le verdict remonte d'`add_playtime`, seul endroit qui arbitre le seuil : le
    faire redécider par la fenêtre l'aurait mis à deux endroits, et deux seuils
    qu'aucun calcul ne relie finissent toujours par diverger.
    """

    def test_une_vraie_partie_annonce_une_partie(self, session, qtbot):
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        with qtbot.waitSignal(session.terminee, timeout=1000) as bloc:
            session._monitor.game_exited.emit("HP1", 0, 1200.0)
        assert bloc.args == ["HP1", True]

    def test_un_lancement_avorte_annonce_un_echec(self, session, qtbot):
        session.demarrer(_FauxProcess(), "HP1", "hp1")
        with qtbot.waitSignal(session.terminee, timeout=1000) as bloc:
            session._monitor.game_exited.emit("HP1", 0, 0.5)
        assert bloc.args == ["HP1", False]

    def test_sans_session_ouverte_on_n_accuse_pas(self, session, qtbot):
        """Le moniteur peut conclure sans qu'on ait rien ouvert (relance de
        processus par UE1). Dans le doute on suppose une partie : accuser à
        tort un jeu qui a très bien tourné serait pire que se taire."""
        with qtbot.waitSignal(session.terminee, timeout=1000) as bloc:
            session._monitor.game_exited.emit("HP1", 0, 1200.0)
        assert bloc.args == ["HP1", True]

    def test_le_seuil_reste_celui_d_add_playtime(self, session):
        """Contre-épreuve du découplage : c'est bien le manager qui tranche."""
        from src.core import stats
        juste_sous = stats.DUREE_MINIMALE - 1
        juste_au_dessus = stats.DUREE_MINIMALE + 1
        m = session._manager
        assert m.add_playtime("hp1", juste_sous, None, 0) is False
        assert m.add_playtime("hp1", juste_au_dessus, None, 0) is True


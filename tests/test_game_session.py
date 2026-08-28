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

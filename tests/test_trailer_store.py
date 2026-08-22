"""Enchaînement des téléchargements de bandes-annonces.

Le vrai `Downloader` est remplacé par un double qu'on pilote à la main : ce
qu'on veut vérifier ici, c'est l'ORDRE et la RÉSILIENCE de la file, pas le
réseau (couvert par `test_downloader_stream.py`).
"""

from unittest.mock import patch

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from src.core import trailers as store  # noqa: E402
from src.core.game_data import Trailer  # noqa: E402
from src.ui.trailer_store import TrailerStore  # noqa: E402


class FauxDownloader(QObject):
    """Même surface que `Downloader`, mais rien ne part sur le réseau."""

    progress = pyqtSignal(int, int)
    download_finished = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    crees: list["FauxDownloader"] = []

    def __init__(self, url=None, destination=None, parent=None, **_kw):
        super().__init__(parent)
        self.url = url
        self.destination = destination
        self.demarre = False
        self.annule = False
        self._fini = False
        FauxDownloader.crees.append(self)

    def start(self):
        self.demarre = True

    def cancel(self):
        self.annule = True

    # `arreter_a_la_fermeture` interroge le thread AVANT de le tuer : sans ces
    # trois-la, le double ne traverse pas le chemin d'extinction reel.
    def isRunning(self):
        return self.demarre and not self._fini

    def requestInterruption(self):
        self._fini = True

    def terminate(self):
        self._fini = True

    def wait(self, _ms=0):
        return True

    # ── pilotage depuis les tests ──
    def reussir(self):
        self.download_finished.emit(str(self.destination))

    def echouer(self, message="hors ligne"):
        self.error.emit(message)


class FauxOps:
    def __init__(self, busy=False):
        self.is_busy = busy


class FauxManager:
    def __init__(self, liste=()):
        self._liste = tuple(liste)

    def trailers(self):
        return self._liste

    def trailer_hash(self, _t):
        return None

    def trailer_size_mb(self, t):
        return t.size_mb


def _t(game_id="hp1", version="1.0", size_mb=10):
    return Trailer(game_id=game_id, version=version,
                   url=f"https://example.org/{game_id}_video.mp4", size_mb=size_mb)


@pytest.fixture
def dossier(tmp_path):
    with patch.object(store, "TRAILERS_DIR", tmp_path):
        yield tmp_path


@pytest.fixture
def faux_dl():
    FauxDownloader.crees.clear()
    with patch("src.ui.trailer_store.Downloader", FauxDownloader):
        yield FauxDownloader


class TestEnchainement:
    def test_telecharge_dans_l_ordre_du_catalogue(self, qtbot, dossier, faux_dl):
        liste = [_t("hp1"), _t("hp2"), _t("hp3")]
        s = TrailerStore(FauxManager(liste), FauxOps())
        s.start(liste)
        assert len(faux_dl.crees) == 1
        assert faux_dl.crees[0].url.endswith("hp1_video.mp4")

        faux_dl.crees[0].reussir()
        assert faux_dl.crees[1].url.endswith("hp2_video.mp4")
        faux_dl.crees[1].reussir()
        assert faux_dl.crees[2].url.endswith("hp3_video.mp4")

    def test_saute_ce_qui_est_deja_la(self, qtbot, dossier, faux_dl):
        liste = [_t("hp1"), _t("hp2")]
        (dossier / liste[0].filename).write_bytes(b"deja")
        s = TrailerStore(FauxManager(liste), FauxOps())
        s.start(liste)
        assert len(faux_dl.crees) == 1
        assert faux_dl.crees[0].url.endswith("hp2_video.mp4")

    def test_un_echec_n_arrete_pas_les_suivantes(self, qtbot, dossier, faux_dl):
        """Une bande-annonce indisponible n'est pas une raison d'abandonner
        les sept autres — c'est un ornement, pas une dépendance."""
        liste = [_t("hp1"), _t("hp2")]
        s = TrailerStore(FauxManager(liste), FauxOps())
        with qtbot.waitSignal(s.job_finished, timeout=1000) as bloc:
            s.start(liste)
            faux_dl.crees[0].echouer()
            faux_dl.crees[1].reussir()
        assert bloc.args == [1, 1]   # (téléchargées, échouées)

    def test_rien_a_faire_termine_tout_de_suite(self, qtbot, dossier, faux_dl):
        liste = [_t("hp1")]
        (dossier / liste[0].filename).write_bytes(b"deja")
        s = TrailerStore(FauxManager(liste), FauxOps())
        with qtbot.waitSignal(s.job_finished, timeout=1000) as bloc:
            s.start(liste)
        assert bloc.args == [0, 0]
        assert faux_dl.crees == []

    def test_destination_versionnee(self, qtbot, dossier, faux_dl):
        liste = [_t("hp1", version="2.0")]
        s = TrailerStore(FauxManager(liste), FauxOps())
        s.start(liste)
        assert faux_dl.crees[0].destination.name == "hp1_video_v2.0.mp4"


class TestPriorite:
    def test_attend_qu_un_jeu_finisse_de_se_telecharger(self, qtbot, dossier, faux_dl):
        """Au premier lancement, quelqu'un qui accepte les bandes-annonces va
        lancer un jeu de 4 Go dans la minute : se partager la bande passante
        ralentirait précisément ce qu'il attend."""
        liste = [_t("hp1")]
        s = TrailerStore(FauxManager(liste), FauxOps(busy=True))
        s.start(liste)
        assert faux_dl.crees == []      # rien n'est parti
        assert s.is_busy                 # mais le travail n'est pas perdu


class TestMenageEtAnnulation:
    def test_les_versions_perimees_partent_avant_de_telecharger(
            self, qtbot, dossier, faux_dl):
        (dossier / "hp1_video_v1.0.mp4").write_bytes(b"vieux")
        liste = [_t("hp1", version="2.0")]
        s = TrailerStore(FauxManager(liste), FauxOps())
        s.start(liste)
        assert not (dossier / "hp1_video_v1.0.mp4").exists()

    def test_annuler_vide_la_file(self, qtbot, dossier, faux_dl):
        liste = [_t("hp1"), _t("hp2"), _t("hp3")]
        s = TrailerStore(FauxManager(liste), FauxOps())
        s.start(liste)
        s.cancel()
        assert faux_dl.crees[0].annule
        assert s.is_busy is False
        assert s.restantes == 0

    def test_supprimer_tout(self, qtbot, dossier, faux_dl):
        liste = [_t("hp1")]
        (dossier / liste[0].filename).write_bytes(b"0123456789")
        s = TrailerStore(FauxManager(liste), FauxOps())
        assert s.supprimer_tout() == 10
        assert store.nombre_present(liste) == 0

    def test_start_ignore_si_deja_en_cours(self, qtbot, dossier, faux_dl):
        liste = [_t("hp1"), _t("hp2")]
        s = TrailerStore(FauxManager(liste), FauxOps())
        s.start(liste)
        s.start(liste)
        assert len(faux_dl.crees) == 1

    def test_shutdown_annule_sans_lever(self, qtbot, dossier, faux_dl):
        """Un thread laissé vivant est détruit avec son parent, ce qui abandonne
        le processus sans un mot (0xC0000409)."""
        liste = [_t("hp1")]
        s = TrailerStore(FauxManager(liste), FauxOps())
        s.start(liste)
        s.shutdown()
        assert faux_dl.crees[0].annule


class FauxConfig:
    def __init__(self, optin=True):
        self.trailers_optin = optin


class TestRattrapageApresCatalogue:
    """Une bande-annonce ajoutée ou révisée à distance doit arriver DANS la
    session qui reçoit le catalogue.

    Sans ce rappel il fallait deux lancements, et entre les deux la fiche
    perdait sa vidéo : `present()` cherche déjà le nom de la nouvelle version.
    """

    def test_telecharge_ce_que_le_nouveau_catalogue_ajoute(self, qtbot, dossier, faux_dl):
        manager = FauxManager([_t('hp1')])
        magasin = TrailerStore(manager, FauxOps())
        magasin.rattraper_apres_catalogue(FauxConfig(optin=True))
        assert [d.url for d in faux_dl.crees] == ['https://example.org/hp1_video.mp4']

    def test_ne_telecharge_rien_si_l_utilisateur_a_refuse(self, qtbot, dossier, faux_dl):
        """Le refus est un choix persisté, pas un report : une mise à jour du
        catalogue ne doit pas le contourner."""
        magasin = TrailerStore(FauxManager([_t('hp1')]), FauxOps())
        magasin.rattraper_apres_catalogue(FauxConfig(optin=False))
        assert faux_dl.crees == []

    def test_une_version_revisee_remplace_l_ancienne(self, qtbot, dossier, faux_dl):
        """Le fichier local porte la version : la 1.0 est périmée dès que le
        catalogue annonce la 2.0, et part AVANT le téléchargement."""
        ancienne = dossier / 'hp1_video_v1.0.mp4'
        ancienne.write_bytes(b'vieux')
        magasin = TrailerStore(FauxManager([_t('hp1', version='2.0')]), FauxOps())
        magasin.rattraper_apres_catalogue(FauxConfig(optin=True))
        assert not ancienne.exists(), "l'ancienne version n'a pas été nettoyée"
        assert faux_dl.crees[0].destination.name == 'hp1_video_v2.0.mp4'

    def test_ne_relance_rien_si_un_telechargement_court_deja(self, qtbot, dossier, faux_dl):
        magasin = TrailerStore(FauxManager([_t('hp1'), _t('hp2')]), FauxOps())
        magasin.rattraper_apres_catalogue(FauxConfig(optin=True))
        magasin.rattraper_apres_catalogue(FauxConfig(optin=True))
        assert len(faux_dl.crees) == 1

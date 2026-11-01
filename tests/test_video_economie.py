"""La bande-annonce ne coûte que ce qui se voit (2026-09-30).

Mesuré hors écran sur la bande-annonce de HP6 (1080p, 60 images/s) : 8 ms de
conversion par image, puis 2 à 8 ms de peinture du fond. En fond, une image
sur deux suffit ; en mode cinéma, toutes ; fenêtre réduite, aucune.
"""
import pytest

pytest.importorskip("pytestqt")

from src.ui.video_player import ECART_FOND_US, VideoPlayer  # noqa: E402

_60_IPS = 16_667


def _montees(lecteur: VideoPlayer, horodatages) -> list[int]:
    return [t for t in horodatages if lecteur.a_monter(t)]


def test_en_fond_une_image_sur_deux_d_une_source_a_60(qtbot):
    lecteur = VideoPlayer()
    montees = _montees(lecteur, [i * _60_IPS for i in range(60)])
    assert 29 <= len(montees) <= 31


def test_une_source_a_30_ou_25_garde_toutes_ses_images(qtbot):
    for pas in (33_333, 40_000):
        lecteur = VideoPlayer()
        assert len(_montees(lecteur, [i * pas for i in range(30)])) == 30
    assert 33_333 - 3_000 > ECART_FOND_US   # la gigue d'un 30 images/s ne fait rien sauter


def test_en_cinema_toutes_les_images(qtbot):
    lecteur = VideoPlayer()
    lecteur.set_plein_debit(True)
    assert len(_montees(lecteur, [i * _60_IPS for i in range(60)])) == 60


def test_un_retour_en_arriere_repart_de_la(qtbot):
    lecteur = VideoPlayer()
    assert lecteur.a_monter(5_000_000)
    assert lecteur.a_monter(0)          # la vidéo a repris au début
    assert not lecteur.a_monter(_60_IPS)


def test_horodatage_inconnu_toujours_monte(qtbot):
    lecteur = VideoPlayer()
    assert lecteur.a_monter(-1) and lecteur.a_monter(-1)


class _FauxLecteur:
    def __init__(self):
        self.appels = []

    def pause(self):
        self.appels.append("pause")

    def play(self):
        self.appels.append("play")


def test_reduite_suspend_puis_reprend(qtbot):
    lecteur = VideoPlayer()
    faux = _FauxLecteur()
    lecteur._player = faux
    lecteur.set_reduite(True)
    assert lecteur.paused and faux.appels == ["pause"]
    lecteur.set_reduite(False)
    assert not lecteur.paused and faux.appels == ["pause", "play"]
    lecteur._player = None


def test_une_pause_voulue_ne_reprend_pas_au_retour(qtbot):
    lecteur = VideoPlayer()
    faux = _FauxLecteur()
    lecteur._player = faux
    lecteur.pause()                     # l'utilisateur a mis en pause
    lecteur.set_reduite(True)
    lecteur.set_reduite(False)
    assert lecteur.paused and faux.appels == ["pause"]
    lecteur._player = None


class _Image:
    def __init__(self, us: int) -> None:
        self.us = us

    def isValid(self) -> bool:
        return True

    def startTime(self) -> int:
        return self.us


def test_vers_la_carte_graphique_une_image_sur_deux_en_fond_toutes_en_cinema(qtbot):
    """Branché tout droit sur le `VideoOutput`, le lecteur lui donnait ses 60 images/s :
    la fenêtre se recomposait 60 fois par seconde pour un fond (2026-11-01)."""
    recues = []
    lecteur = VideoPlayer()
    lecteur._relais = type("Recepteur", (), {"setVideoFrame": lambda _s, f: recues.append(f.us)})()
    for i in range(6):
        lecteur._relayer(_Image(i * _60_IPS))
    assert recues == [0, 2 * _60_IPS, 4 * _60_IPS]
    recues.clear()
    lecteur.set_plein_debit(True)
    for i in range(6, 9):
        lecteur._relayer(_Image(i * _60_IPS))
    assert len(recues) == 3


def test_la_scene_expose_le_recepteur_de_sa_sortie(qtbot):
    from src.ui import fond_gpu
    if not fond_gpu.QUICK_DISPONIBLE:
        pytest.skip("Qt Quick absent")
    from PyQt6.QtMultimedia import QVideoSink
    fond = fond_gpu.FondGPU()
    qtbot.addWidget(fond)
    assert isinstance(fond.sortie_video().property("videoSink"), QVideoSink)


def test_muette_la_lecture_n_a_pas_de_sortie_audio(qtbot):
    """Décoder et mixer un son que personne n'entend coûtait 3 à 4 points d'un cœur
    (2026-11-01) ; les bandes-annonces sont muettes par défaut."""
    from PyQt6.QtMultimedia import QAudioOutput
    branchee = []
    lecteur = VideoPlayer()
    lecteur._audio = QAudioOutput()
    lecteur._player = type("Lecteur", (), {"setAudioOutput": lambda _s, a: branchee.append(a)})()
    lecteur.set_muted(True)
    lecteur.set_muted(False)
    lecteur.toggle_mute()
    lecteur.set_volume(40)          # toucher au volume rallume le son
    assert branchee == [None, lecteur._audio, None, lecteur._audio]
    lecteur._player = None

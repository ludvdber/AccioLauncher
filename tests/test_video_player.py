"""Le lecteur vidéo (`src/ui/video_player.py`) sur une VRAIE vidéo.

`tests/data/rouge_06s.mp4` : 0,6 s d'image rouge en 64 × 36, piste son muette
(2,5 Ko, fabriquée par ffmpeg le 2026-10-24). Le lecteur des cinématiques et
des bandes-annonces n'était exercé que sur des objets simulés : ici l'image
arrive, la fin est signalée, les ressources sont rendues.
"""

from pathlib import Path

import pytest

from src.ui.video_player import MULTIMEDIA_DISPONIBLE, VideoPlayer

VIDEO = Path(__file__).parent / "data" / "rouge_06s.mp4"

pytestmark = pytest.mark.skipif(not MULTIMEDIA_DISPONIBLE, reason="PyQt6-Multimedia absent")


@pytest.fixture
def lecteur(qtbot):
    from PyQt6.QtWidgets import QWidget
    hote = QWidget()
    qtbot.addWidget(hote)
    lecteur = VideoPlayer(hote)
    lecteur.set_plein_debit(True)
    yield lecteur
    lecteur.stop()


class TestVraieLecture:
    def test_l_image_arrive_puis_la_fin_est_signalee(self, lecteur, qtbot):
        images = []
        lecteur.video_frame.connect(images.append)
        with qtbot.waitSignal(lecteur.playback_ended, timeout=10000):
            assert lecteur.play(str(VIDEO), muted=True)
            assert lecteur.is_playing
        assert images, "aucune image décodée"
        couleur = images[0].pixelColor(32, 18)
        assert couleur.red() > 180 and couleur.green() < 80, couleur.name()
        assert not lecteur.is_playing, "la fin rend les ressources"

    def test_relancer_remplace_la_lecture_en_cours(self, lecteur, qtbot):
        assert lecteur.play(str(VIDEO), muted=True)
        premier = lecteur._player
        assert lecteur.play(str(VIDEO), muted=True)
        assert lecteur._player is not premier

    def test_pause_et_reprise_sans_perdre_la_source(self, lecteur, qtbot):
        assert lecteur.play(str(VIDEO), muted=True)
        lecteur.pause()
        assert lecteur.paused and lecteur.is_playing
        lecteur.resume()
        assert not lecteur.paused

    def test_fenetre_reduite_puis_rendue(self, lecteur):
        assert lecteur.play(str(VIDEO), muted=True)
        lecteur.set_reduite(True)
        assert lecteur.paused
        lecteur.set_reduite(False)
        assert not lecteur.paused
        lecteur.pause()
        lecteur.set_reduite(True)
        lecteur.set_reduite(False)
        assert lecteur.paused, "une pause voulue ne reprend pas d'elle-même"


class TestSon:
    def test_sans_lecture_couper_ne_fait_rien(self, lecteur):
        assert lecteur.toggle_mute() is False
        lecteur.set_volume(50)
        lecteur.set_muted(True)
        assert lecteur.muted

    def test_monter_le_volume_rend_le_son(self, lecteur):
        assert lecteur.play(str(VIDEO), muted=True)
        assert lecteur.muted and lecteur._audio.isMuted()
        lecteur.set_volume(40)
        assert not lecteur.muted and not lecteur._audio.isMuted()
        assert lecteur._audio.volume() == pytest.approx(0.4)
        assert lecteur.toggle_mute() is True and lecteur._audio.isMuted()

"""Les cinématiques des Collections sur la carte graphique (`ecran_video_gpu`).

Le lecteur relaie ses `QVideoFrame` à un `VideoOutput`, sans `toImage()` : 134 % d'un
cœur par `toImage`, 28 % par `VideoOutput` (mesuré en vraie fenêtre, bande-annonce).
Les parcours dans la vraie page sont dans `test_mediatheque.py`.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QObject, QPoint, Qt  # noqa: E402
from PyQt6.QtGui import QColor  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from src.ui import ecran_video_gpu, fond_gpu  # noqa: E402
from src.ui.video_player import MULTIMEDIA_DISPONIBLE, VideoPlayer  # noqa: E402

VIDEO = Path(__file__).parent / "data" / "rouge_06s.mp4"

pytestmark = pytest.mark.skipif(not (fond_gpu.QUICK_DISPONIBLE and MULTIMEDIA_DISPONIBLE),
                                reason="Qt Quick ou Multimedia absent")


@pytest.fixture
def allume(monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.setenv("ACCIO_MEDIA_GPU", "1")


@pytest.fixture
def hote(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(480, 270)
    return widget


def test_les_tests_gardent_la_scene_eteinte():
    """Une scène Qt Quick par fenêtre de test fait tomber un travailleur de xdist."""
    assert os.environ["ACCIO_MEDIA_GPU"] == "0"
    assert not ecran_video_gpu.actif()


def test_suit_le_fond_et_s_eteint_par_son_interrupteur(monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.delenv("ACCIO_MEDIA_GPU", raising=False)
    assert ecran_video_gpu.actif(), "allumé avec le fond"
    monkeypatch.setenv("ACCIO_MEDIA_GPU", "0")
    assert not ecran_video_gpu.actif(), "l'interrupteur éteint"
    monkeypatch.delenv("ACCIO_MEDIA_GPU")
    monkeypatch.setenv("ACCIO_FOND_GPU", "0")
    assert not ecran_video_gpu.actif(), "pas sans le fond sur la carte graphique"


def test_eteint_aucune_scene(hote):
    assert ecran_video_gpu.creer(hote) is None


def test_scene_qui_ne_charge_pas_rend_le_chemin_qpainter(allume, hote, tmp_path, monkeypatch):
    casse = tmp_path / "EcranVideo.qml"
    casse.write_text("import QtQuick\nItem { pas du qml", encoding="utf-8")
    monkeypatch.setattr(ecran_video_gpu, "_QML", casse)
    assert ecran_video_gpu.creer(hote) is None
    assert not hote.findChildren(ecran_video_gpu.EcranVideoGPU), "la scène ratée ne reste pas posée"


def test_la_scene_ne_prend_ni_le_focus_ni_la_souris(allume, hote):
    """Espace et les flèches restent à la page, le double-clic au widget dessous."""
    ecran = ecran_video_gpu.creer(hote)
    assert ecran is not None
    assert not ecran.errors()
    assert ecran.focusPolicy() == Qt.FocusPolicy.NoFocus
    ecran.setGeometry(hote.rect())
    assert hote.childAt(QPoint(50, 50)) is None, "la souris passe au travers"


def test_les_coins_prennent_la_couleur_de_la_page(allume, hote, qtbot):
    ecran = ecran_video_gpu.creer(hote, coin=8, fond=QColor(255, 0, 255))
    ecran.setGeometry(hote.rect())
    hote.show()

    def rendu():
        image = ecran.grabFramebuffer()
        assert image.pixelColor(0, 0).red() > 200 and image.pixelColor(0, 0).blue() > 200
        assert image.pixelColor(240, 135).red() < 20
    qtbot.waitUntil(rendu, timeout=5000)


class _Sortie:
    """Un `VideoOutput` réduit à son récepteur."""

    def __init__(self) -> None:
        self.recepteur = MagicMock()

    def property(self, nom: str):
        assert nom == "videoSink"
        return self.recepteur


class _Image:
    def __init__(self, ms: int) -> None:
        self.ms = ms
        self.converties = 0

    def isValid(self) -> bool:
        return True

    def startTime(self) -> int:
        return self.ms * 1000

    def toImage(self):
        self.converties += 1
        image = MagicMock()
        image.isNull.return_value = False
        return image


@pytest.fixture
def lecteur(hote):
    lecteur = VideoPlayer(hote)
    lecteur.set_plein_debit(True)
    return lecteur


class TestAvanceRapide:
    """Le commentaire d'avant : « une cinématique d'EA a besoin de voir passer les
    images, elle garde le chemin QPainter ». Elles passent aussi par le relais."""

    def test_une_cinematique_d_ea_part_vers_la_carte_graphique(self, lecteur):
        sortie = _Sortie()
        lecteur.set_sortie(sortie)
        lecteur._index = object()              # ce qui distingue une cinématique d'EA
        lecteur._sink = None
        lecteur._ouvrir(str(VIDEO), True, 0.25)
        try:
            assert lecteur._relais is sortie.recepteur
        finally:
            lecteur.stop()

    def test_rien_n_est_relaye_avant_le_point_voulu(self, lecteur):
        lecteur._relais = MagicMock()
        lecteur._player = MagicMock()
        lecteur._decalage, lecteur._cible = 400, 750
        avant, arrivee = _Image(200), _Image(350)    # 600 et 750 ms dans la vidéo
        lecteur._on_frame(avant)
        lecteur._relais.setVideoFrame.assert_not_called()
        assert lecteur._cible == 750, "toujours en avance rapide"
        lecteur._on_frame(arrivee)
        lecteur._relais.setVideoFrame.assert_called_once_with(arrivee)
        assert lecteur._cible == -1
        lecteur._player.setPlaybackRate.assert_called_once_with(1.0)
        assert avant.converties == arrivee.converties == 0, "aucun toImage"
        lecteur._player = None
        lecteur._relais = None

    def test_la_pause_du_saut_attend_le_point_voulu_aussi_par_le_relais(self, lecteur):
        lecteur._relais = MagicMock()
        lecteur._player = MagicMock()
        lecteur._cible, lecteur._pause_apres_saut, lecteur._paused = 300, True, True
        lecteur._on_frame(_Image(300))
        lecteur._player.pause.assert_called_once()
        assert lecteur.paused
        lecteur._player = None
        lecteur._relais = None


class TestSortieVivante:
    def test_sans_sortie_les_images_restent_en_qimage(self, lecteur):
        images = []
        lecteur.video_frame.connect(images.append)
        frame = _Image(10)
        lecteur._on_frame(frame)
        assert frame.converties == 1 and len(images) == 1

    def test_changer_d_ecran_en_lecture_emporte_l_image(self, lecteur):
        page, plein = _Sortie(), _Sortie()
        lecteur.set_sortie(page)
        lecteur._player = MagicMock()
        lecteur._relais = page.recepteur
        lecteur.set_sortie(plein)
        assert lecteur._relais is plein.recepteur
        plein.recepteur.setVideoFrame.assert_called_once_with(page.recepteur.videoFrame())
        lecteur._player = None
        lecteur._relais = None

    def test_retirer_la_sortie_en_lecture_rend_les_qimage(self, lecteur):
        lecteur.set_sortie(_Sortie())
        lecteur._player = MagicMock()
        lecteur._relais = object()
        lecteur.set_sortie(None)
        assert lecteur._relais is None
        lecteur._player = None

    @pytest.mark.parametrize("garder, appels", [(False, 1), (True, 0)])
    def test_l_arret_ne_garde_l_image_que_si_on_le_demande(self, lecteur, garder, appels):
        """Saut de HP7 (6 s d'avance rapide), narration de HP5 après la fin de l'image :
        l'écran garde la dernière image, comme le chemin QPainter."""
        recepteur = MagicMock()
        lecteur.set_garder_image(garder)
        lecteur._player, lecteur._sink, lecteur._audio = MagicMock(), MagicMock(), MagicMock()
        lecteur._relais = recepteur
        lecteur._liberer()
        assert recepteur.setVideoFrame.call_count == appels
        assert lecteur._relais is None


def test_une_vraie_video_arrive_dans_la_scene_sans_toimage(allume, hote, lecteur, qtbot):
    ecran = ecran_video_gpu.creer(hote)
    assert ecran is not None
    ecran.setGeometry(hote.rect())
    hote.show()
    sortie = ecran.sortie_video()
    assert isinstance(sortie, QObject)
    images = []
    lecteur.video_frame.connect(images.append)
    lecteur.set_garder_image(True)
    lecteur.set_sortie(sortie)
    with qtbot.waitSignal(lecteur.playback_ended, timeout=10000):
        assert lecteur.play(str(VIDEO), muted=True)
    assert images == [], "le signal des QImage ne part plus"
    assert sortie.property("videoSink").videoFrame().isValid(), "la dernière image reste"
    ecran.vider()
    assert not sortie.property("videoSink").videoFrame().isValid()


def test_une_pause_voulue_tient_pendant_le_rattrapage_d_un_saut(qtbot, monkeypatch):
    """`paused` reste vrai entre l'arrivée de la copie et l'image visée."""
    hote = QWidget()
    qtbot.addWidget(hote)
    lecteur = VideoPlayer(hote)
    lecteur._paused = True
    lecteur._demandes = 1
    lecteur._attente = 5_000

    def ouvrir(*_a):
        lecteur._paused = False
        lecteur._player = MagicMock()

    monkeypatch.setattr(lecteur, "_liberer", lambda: None)
    monkeypatch.setattr(lecteur, "_ouvrir", ouvrir)
    monkeypatch.setattr(lecteur, "_jeter", lambda _c: None)
    lecteur._poser_saut(1, (b"", "copie.vp6", 1_000))
    assert lecteur._cible == 5_000
    assert lecteur.paused
    lecteur._player = None

"""Arrêter un lecteur média sans garder le GIL (règle 135).

`QMediaPlayer.stop()` est appelé par PyQt SANS relâcher le GIL, et le
greffon FFmpeg y attend un verrou de Qt. Le fil audio de FFmpeg (`AudioR`),
qui tient ce verrou en détruisant ses objets, passe par le `disconnectNotify`
d'une `QAudioOutput` créée par Python, donc attend le GIL : interblocage,
le launcher fige. Pris sous gdb le 2026-10-29 (suite entière sous xdist,
démontage de `test_video_player.py`). `setSource(QUrl())` arrête aussi et
relâche le GIL (`/ReleaseGIL/` dans `qmediaplayer.sip`).

Le gel est rare (un passage de la suite sur ~17) : on vérifie ici que les
chemins d'arrêt ne passent plus par `stop()`. L'espion est posé sur
l'INSTANCE, jamais sur la classe (règle 12).
"""

from pathlib import Path

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QWidget

from src.ui.video_player import MULTIMEDIA_DISPONIBLE, VideoPlayer

VIDEO = Path(__file__).parent / "data" / "rouge_06s.mp4"

pytestmark = pytest.mark.skipif(not MULTIMEDIA_DISPONIBLE, reason="PyQt6-Multimedia absent")


def _espionner_stop(lecteur, monkeypatch) -> list[bool]:
    appels: list[bool] = []
    monkeypatch.setattr(lecteur, "stop", lambda: appels.append(True))
    return appels


def test_la_video_s_arrete_sans_stop(qtbot, monkeypatch):
    hote = QWidget()
    qtbot.addWidget(hote)
    video = VideoPlayer(hote)
    assert video.play(str(VIDEO), muted=True)
    lecteur = video._player
    appels = _espionner_stop(lecteur, monkeypatch)
    video.stop()
    assert not appels, "QMediaPlayer.stop() garde le GIL : setSource(QUrl())"
    assert lecteur.source().isEmpty() and video._player is None


def test_la_musique_de_fond_s_arrete_sans_stop(qtbot, tmp_path, monkeypatch):
    from src.core.config import Config
    from src.ui.fond_sonore import FondSonore
    fenetre = QWidget()
    qtbot.addWidget(fenetre)
    fond = FondSonore(Config(install_path=tmp_path), lambda _jeu: None, lambda: tmp_path, fenetre)
    lecteur = fond._preparer()
    lecteur.setSource(QUrl.fromLocalFile(str(VIDEO)))
    appels = _espionner_stop(lecteur, monkeypatch)
    fond.arreter()
    assert not appels, "QMediaPlayer.stop() garde le GIL : setSource(QUrl())"
    assert lecteur.source().isEmpty()


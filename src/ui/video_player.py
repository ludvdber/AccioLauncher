"""Lecteur vidéo basé sur QVideoSink — frames peintes via BackgroundWidget."""

import logging

from PyQt6.QtCore import QUrl, pyqtSignal, QObject
from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)


class VideoPlayer(QObject):
    """Gère la lecture vidéo (QMediaPlayer + QVideoSink + QAudioOutput).

    Émet des frames QImage pour un rendu custom dans un QPainter,
    au lieu d'utiliser QVideoWidget (incompatible avec les overlays Qt).
    """

    video_frame = pyqtSignal(object)  # QImage
    playback_ended = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._player = None
        self._sink = None
        self._audio = None
        self._muted = False

    @property
    def is_playing(self) -> bool:
        return self._player is not None

    @property
    def muted(self) -> bool:
        return self._muted

    def play(self, video_path: str, *, muted: bool = False, volume: float = 0.25) -> bool:
        """Lance la lecture d'une vidéo. Retourne False si Multimedia non disponible."""
        self.stop()
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
        except ImportError:
            log.debug("PyQt6-Multimedia non disponible")
            return False

        parent_widget = self.parent()

        self._sink = QVideoSink(parent_widget)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._audio = QAudioOutput(parent_widget)
        self._audio.setVolume(volume)
        self._audio.setMuted(muted)
        self._muted = muted
        self._player = QMediaPlayer(parent_widget)
        self._player.setVideoOutput(self._sink)
        self._player.setAudioOutput(self._audio)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        self._player.setSource(QUrl.fromLocalFile(video_path))
        self._player.play()
        return True

    def stop(self) -> None:
        """Arrête la lecture et libère toutes les ressources média."""
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
            self._player.mediaStatusChanged.disconnect(self._on_media_status)
            self._sink.videoFrameChanged.disconnect(self._on_frame)
            self._player.deleteLater()
            self._sink.deleteLater()
            self._audio.deleteLater()
            self._player = None
            self._sink = None
            self._audio = None

    def toggle_mute(self) -> bool:
        """Inverse l'état mute. Retourne le nouvel état."""
        if self._audio is None:
            return self._muted
        self._muted = not self._muted
        self._audio.setMuted(self._muted)
        return self._muted

    def set_volume(self, value_0_100: int) -> None:
        """Définit le volume (0-100). Unmute automatiquement si muté."""
        if self._audio is None:
            return
        if self._muted:
            self._muted = False
            self._audio.setMuted(False)
        self._audio.setVolume(value_0_100 / 100.0)

    # ── Slots internes ──

    def _on_frame(self, frame) -> None:
        if frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.video_frame.emit(image)

    def _on_media_status(self, status) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stop()
            self.playback_ended.emit()

"""Lecteur vidéo basé sur QVideoSink — frames peintes via BackgroundWidget."""

import logging

from PyQt6.QtCore import QUrl, pyqtSignal, QObject
from PyQt6.QtWidgets import QWidget

# Import AU CHARGEMENT DU MODULE, pas au premier trailer.
#
# Le try/except est là pour dégrader proprement si PyQt6-Multimedia manque —
# ce comportement est conservé à l'identique, `play()` renvoie toujours False.
# Ce qui change, c'est le MOMENT : créer un module d'extension Qt en pleine
# session, alors que le ramasse-miettes peut passer sur des objets Qt vivants,
# provoque un « access violation » aléatoire (constaté sur QtNetwork pendant un
# build, voir tests/conftest.py). Ici la création se faisait au premier
# démarrage de vidéo, donc chez l'utilisateur, fenêtre pleine.
# Coût mesuré : +6 ms au démarrage, sur ~2 000. Rien à arbitrer.
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
    MULTIMEDIA_DISPONIBLE = True
except ImportError:                                   # pragma: no cover
    QAudioOutput = QMediaPlayer = QVideoSink = None   # type: ignore[assignment]
    MULTIMEDIA_DISPONIBLE = False

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
        self._paused = False

    @property
    def is_playing(self) -> bool:
        return self._player is not None

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        """Suspend la lecture SANS libérer la source (reprise instantanée)."""
        if self._player is not None and not self._paused:
            self._player.pause()
            self._paused = True

    def resume(self) -> None:
        if self._player is not None and self._paused:
            self._player.play()
            self._paused = False

    def play(self, video_path: str, *, muted: bool = False, volume: float = 0.25) -> bool:
        """Lance la lecture d'une vidéo. Retourne False si Multimedia non disponible."""
        self.stop()
        if not MULTIMEDIA_DISPONIBLE:
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
        self._paused = False
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

    def set_muted(self, muted: bool) -> None:
        """Force l'état mute (réglage « Couper le son » appliqué en direct)."""
        self._muted = muted
        if self._audio is not None:
            self._audio.setMuted(muted)

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
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stop()
            self.playback_ended.emit()

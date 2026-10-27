"""Lecteur vidéo basé sur QVideoSink — frames peintes via BackgroundWidget."""

import logging
import tempfile
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal, QObject
from PyQt6.QtWidgets import QWidget

from src.core import vp6_ea

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

# Écart minimal entre deux images montées en fond, en microsecondes. Les
# bandes-annonces sont en 1080p à 60 images/s, et CHAQUE image coûtait sa
# conversion en QImage (8 ms, décodage logiciel) puis une peinture de toute la
# fenêtre (2 à 8 ms selon la taille) : environ 60 % d'un cœur de bureau pour un
# fond d'écran, bien plus sur le portable de Ludo (« le launcher consomme
# beaucoup », 2026-09-30). Le reste de l'interface vit à 30 images/s (Ticker) :
# une image sur deux suffit. 25 ms et non 33 : une source à 30 ou 25 images/s
# garde toutes les siennes malgré la gigue des horodatages.
ECART_FOND_US = 25_000

# Vitesse de l'avance rapide invisible qui rattrape le point voulu après un
# saut dans une cinématique d'EA (`vp6_ea`) : 4 s d'écart au pire chez HP5 et
# HP6, rattrapées en une demi-seconde (mesuré le 2026-10-27).
_RATTRAPAGE = 8.0


class VideoPlayer(QObject):
    """Gère la lecture vidéo (QMediaPlayer + QVideoSink + QAudioOutput).

    Émet des frames QImage pour un rendu custom dans un QPainter,
    au lieu d'utiliser QVideoWidget (incompatible avec les overlays Qt).
    """

    video_frame = pyqtSignal(object)  # QImage
    playback_ended = pyqtSignal()
    # Millisecondes, pour une barre de lecture (Médiathèque) : une cinématique
    # dure au plus quelques minutes, loin de la limite d'un int (règle 32).
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._player = None
        self._sink = None
        self._audio = None
        self._muted = False
        self._paused = False
        self._image_vide_signalee = False
        # Toutes les images (mode cinéma : la vidéo est ce qu'on regarde), ou
        # une sur deux au plus (`ECART_FOND_US`) quand elle n'est qu'un fond.
        self._plein_debit = False
        self._derniere_us = -1
        # Mise en pause par la fenêtre réduite, pas par l'utilisateur : seule
        # celle-là reprend d'elle-même au retour.
        self._pause_reduite = False
        # Une position demandée avant que la vidéo soit chargée (relance depuis
        # la barre de lecture) : posée dès que le média l'accepte.
        self._position_en_attente = -1
        # Cinématique d'EA : on n'y saute pas, on rejoue une copie qui part
        # de l'image complète d'avant (`vp6_ea`), décalée de `_decalage` ms,
        # en avance rapide sans rien montrer jusqu'à `_cible`.
        self._volume = 0.25
        self._source = ""
        self._index: vp6_ea.Index | None = None
        self._decalage = 0
        self._cible = -1
        self._pause_apres_saut = False
        self._copies = 0

    def set_plein_debit(self, oui: bool) -> None:
        self._plein_debit = oui

    def set_reduite(self, oui: bool) -> None:
        """Fenêtre réduite : rien ne se voit, inutile de décoder. La position est gardée."""
        if oui and self._player is not None and not self._paused:
            self.pause()
            self._pause_reduite = True
        elif not oui and self._pause_reduite:
            self._pause_reduite = False
            self.resume()

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

    @property
    def position(self) -> int:
        """Où en est la vidéo, en millisecondes (0 sans vidéo)."""
        if self._player is None:
            return 0
        return self._cible if self._cible >= 0 else self._player.position() + self._decalage

    @property
    def duration(self) -> int:
        if self._index is not None:
            return self._index.duree_ms
        return self._player.duration() if self._player is not None else 0

    def seek(self, ms: int) -> None:
        """Va à `ms` dans la vidéo, en pause comme en lecture."""
        if self._player is None:
            return
        if self._index is not None:
            self._sauter(self._index, max(0, ms), self._paused)
        else:
            self._player.setPosition(max(0, ms))

    def _sauter(self, index: vp6_ea.Index, ms: int, pause: bool) -> bool:
        """Rejoue la cinématique d'EA depuis son image complète d'avant `ms`.
        Un saut direct décodait des pavés de couleur jusqu'à la fin (Ludo,
        2026-10-27, HP6)."""
        copie = Path(tempfile.gettempdir()) / f"accio_cinematique_{self._copies % 2}.vp6"
        self._copies += 1
        try:
            copie.unlink(missing_ok=True)
            debut = vp6_ea.copie_depuis(self._source, index, ms, copie)
        except OSError as e:
            log.warning("Cinématique : copie pour le saut impossible (%s)", e)
            return False
        self._liberer()
        self._ouvrir(str(copie), self._muted, self._volume)
        self._decalage = debut
        self._cible = ms if ms - debut > 40 else -1
        self._pause_apres_saut = pause
        if self._cible >= 0:
            self._player.setPlaybackRate(_RATTRAPAGE)
        elif pause:
            self.pause()
        return True

    def play(self, video_path: str, *, muted: bool = False, volume: float = 0.25,
             debut_ms: int = 0) -> bool:
        """Lance la lecture d'une vidéo. Retourne False si Multimedia non disponible."""
        self.stop()
        if not MULTIMEDIA_DISPONIBLE:
            log.debug("PyQt6-Multimedia non disponible")
            return False
        self._source = video_path
        self._muted, self._volume = muted, volume
        if video_path.lower().endswith(".vp6"):
            self._index = vp6_ea.indexer(video_path)
            if self._index is not None and debut_ms > 0 and self._sauter(self._index, debut_ms, False):
                return True
        self._ouvrir(video_path, muted, volume)
        self._position_en_attente = debut_ms if debut_ms > 0 else -1
        return True

    def _ouvrir(self, video_path: str, muted: bool, volume: float) -> None:
        parent_widget = self.parent()

        self._sink = QVideoSink(parent_widget)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._audio = QAudioOutput(parent_widget)
        self._audio.setVolume(volume)
        self._audio.setMuted(muted)
        self._muted = muted
        self._volume = volume
        self._player = QMediaPlayer(parent_widget)
        self._player.setVideoOutput(self._sink)
        self._player.setAudioOutput(self._audio)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        # Relayés par des méthodes : un signal qint64 ne se branche pas sur un
        # signal int (« connect() failed », vu au premier vrai lancement).
        self._player.positionChanged.connect(self._sur_position)
        self._player.durationChanged.connect(self._sur_duree)

        self._player.setSource(QUrl.fromLocalFile(video_path))
        self._player.play()
        self._paused = False
        self._pause_reduite = False
        self._derniere_us = -1

    def stop(self) -> None:
        """Arrête la lecture et libère toutes les ressources média."""
        self._liberer()
        self._source, self._index = "", None
        self._decalage, self._cible = 0, -1

    def _liberer(self) -> None:
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
            self._player.mediaStatusChanged.disconnect(self._on_media_status)
            self._player.positionChanged.disconnect(self._sur_position)
            self._player.durationChanged.disconnect(self._sur_duree)
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

    def a_monter(self, debut_us: int) -> bool:
        """Cette image (horodatée en µs) doit-elle être convertie et peinte ?"""
        if self._plein_debit or debut_us < 0:
            return True
        ecart = debut_us - self._derniere_us
        if self._derniere_us >= 0 and 0 <= ecart < ECART_FOND_US:
            return False
        # Premier plan, ou retour en arrière (reprise, boucle) : on repart d'ici.
        self._derniere_us = debut_us
        return True

    def _on_frame(self, frame) -> None:
        if self._cible >= 0 and frame.isValid():
            # Avance rapide après un saut : rien à montrer avant le point voulu.
            if frame.startTime() // 1000 + self._decalage < self._cible:
                return
            self._cible = -1
            self._player.setPlaybackRate(1.0)
            if self._pause_apres_saut:
                self.pause()
        if frame.isValid() and self.a_monter(frame.startTime()):
            image = frame.toImage()
            if not image.isNull():
                self.video_frame.emit(image)
            elif not self._image_vide_signalee:
                # Le seul symptôme serait « le son sans l'image » : on le dit au
                # journal une fois, avec ce qui permet d'en trouver la cause.
                self._image_vide_signalee = True
                log.warning("Vidéo : image reçue mais non convertible (format %s, support %s)",
                            frame.pixelFormat(), frame.handleType())

    def _sur_position(self, ms: int) -> None:
        if self._cible < 0:
            self.position_changed.emit(int(ms) + self._decalage)

    def _sur_duree(self, ms: int) -> None:
        self.duration_changed.emit(self._index.duree_ms if self._index is not None else int(ms))

    def _on_media_status(self, status) -> None:
        if self._position_en_attente >= 0 and status in (
                QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._player.setPosition(self._position_en_attente)
            self._position_en_attente = -1
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stop()
            self.playback_ended.emit()

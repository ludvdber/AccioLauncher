"""Lecteur vidéo sur QVideoSink : QImage par `video_frame` (chemin QPainter), ou
QVideoFrame relayées à un VideoOutput de la carte graphique (`set_sortie`)."""

import logging
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal, QObject
from PyQt6.QtWidgets import QWidget

from src.core import vp6_ea
from src.ui.utils import apres_le_fil

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
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
    MULTIMEDIA_DISPONIBLE = True
except ImportError:                                   # pragma: no cover
    QAudioOutput = QMediaPlayer = QVideoFrame = QVideoSink = None   # type: ignore[assignment,misc]
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
# saut dans une cinématique d'EA (`vp6_ea`) : 4 s d'écart au pire chez HP5,
# HP6 et HP8, rattrapées en une demi-seconde (mesuré le 2026-10-27). Chez HP7
# (jusqu'à 49 s entre deux images complètes), le rattrapage peut durer 6 s.
_RATTRAPAGE = 8.0


def dossier_des_copies() -> Path:
    """Où poser la copie d'une cinématique d'EA pour un saut : dans les données
    du launcher, résolu À L'APPEL (les tests redirigent la config).

    Plus dans le /tmp partagé sous un nom fixe : sous Linux, un autre compte
    pouvait y poser le fichier avant nous (saut cassé) ou, sans
    `fs.protected_symlinks`, un lien vers un fichier de la victime, écrasé
    entre l'`unlink` et l'`open` (audit du 2026-10-29). Toujours deux noms qui
    alternent : la place reste bornée.
    """
    from src.core.config import CONFIG_FILE_PATH
    return CONFIG_FILE_PATH.parent / "cache" / "cinematiques_saut"


class VideoPlayer(QObject):
    """Gère la lecture vidéo (QMediaPlayer + QVideoSink + QAudioOutput).

    Pas de QVideoWidget (incompatible avec les overlays Qt) : images par
    `video_frame`, ou relais à la carte graphique (`set_sortie`).
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
        # en avance rapide sans rien montrer jusqu'à `_cible`. `_index` : son
        # en-tête (la durée) ; `_complet` : ses images complètes, lues au
        # premier saut, sur le fil qui prépare la copie.
        self._volume = 0.25
        self._source = ""
        self._index: vp6_ea.Index | None = None
        self._complet: vp6_ea.Index | None = None
        self._decalage = 0
        self._cible = -1
        self._pause_apres_saut = False
        # Le saut en préparation : sa position voulue (-1 : aucun), le numéro
        # de la dernière demande (une plus ancienne qui arrive est jetée), et
        # la copie jouée en ce moment.
        self._attente = -1
        self._demandes = 0
        self._copie: Path | None = None
        # Une sortie vidéo de la carte graphique (`VideoOutput` de Qt Quick, voir
        # `fond_gpu`) : les images y vont directement, sans `toImage()` (8 ms
        # par image en 1080p) ni peinture de la fenêtre. None : le chemin QPainter.
        self._sortie: QObject | None = None
        # Le récepteur de cette sortie pendant une lecture : les images y sont
        # RELAYÉES, une sur deux en fond (`_relayer`).
        self._relais = None
        # La dernière image reste à l'arrêt : c'est au propriétaire de la sortie de
        # la retirer. Le mode cinéma en a besoin (voir `_liberer`).
        self._garder_image = False

    @staticmethod
    def _recepteur(sortie: QObject | None):
        return sortie.property("videoSink") if sortie is not None else None

    def set_sortie(self, sortie: QObject | None) -> None:
        """Envoie les images à une sortie de la carte graphique au lieu du signal
        `video_frame`. Avant `play()`, ou en pleine lecture pour changer d'écran
        (plein écran) : l'image du moment suit, sinon rien tant qu'on est en pause."""
        ancien, nouveau = self._recepteur(self._sortie), self._recepteur(sortie)
        self._sortie = sortie
        if ancien is not None and nouveau is not None and ancien is not nouveau:
            nouveau.setVideoFrame(ancien.videoFrame())
        if self._player is not None:
            self._relais = nouveau

    def image_courante(self):
        """L'image affichée par la sortie, en QImage (None sans sortie ni image)."""
        recepteur = self._recepteur(self._sortie)
        if recepteur is None:
            return None
        image = recepteur.videoFrame().toImage()
        return None if image.isNull() else image

    def set_garder_image(self, oui: bool) -> None:
        self._garder_image = oui

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
        return self._player is not None or self._attente >= 0

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        """Suspend la lecture SANS libérer la source (reprise instantanée).

        Pendant l'avance rapide d'un saut, la pause attend le point voulu :
        posée tout de suite, elle figeait l'image d'avant, et la bonne
        n'apparaissait qu'à la reprise (audit du 2026-11-02).
        """
        if self._player is not None and self._cible >= 0:
            self._pause_apres_saut = self._paused = True
        elif self._player is not None and not self._paused:
            self._player.pause()
            self._paused = True
        elif self._player is None and self._attente >= 0:
            self._paused = True          # posée à l'arrivée du saut

    def resume(self) -> None:
        if self._player is not None and self._cible >= 0:
            self._pause_apres_saut = self._paused = False
        elif self._player is not None and self._paused:
            self._player.play()
            self._paused = False
        elif self._player is None and self._attente >= 0:
            self._paused = False

    @property
    def position(self) -> int:
        """Où en est la vidéo, en millisecondes (0 sans vidéo)."""
        if self._attente >= 0:
            return self._attente
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
        if self._index is not None and self.is_playing:
            self._demander_saut(max(0, ms))
        elif self._player is not None:
            self._player.setPosition(max(0, ms))

    def _demander_saut(self, ms: int) -> None:
        """Rejoue la cinématique d'EA depuis son image complète d'avant `ms`.
        Un saut direct décodait des pavés de couleur jusqu'à la fin (Ludo,
        2026-10-27, HP6).

        L'index et la copie se préparent sur un fil à part : dans celui de
        l'interface, une cinématique de HP8 la figeait 0,45 s au premier saut
        puis 0,2 s à chacun (grand audit du 2026-11-02). Avant la deuxième
        image complète, aucune copie : le fichier lui-même, depuis le début."""
        self._demandes += 1
        numero, source, complet = self._demandes, self._source, self._complet
        self._attente = ms
        copie = dossier_des_copies() / f"saut_{numero}.vp6"

        def preparer() -> object:
            try:
                index = complet or vp6_ea.indexer(source)
                if index is not None and vp6_ea.sans_copie(index, ms):
                    return (index, source, 0)
                if index is not None:
                    copie.parent.mkdir(parents=True, exist_ok=True)
                    return (index, str(copie), vp6_ea.copie_depuis(source, index, ms, copie))
            except OSError as e:
                log.warning("Cinématique : copie pour le saut impossible (%s)", e)
            return None
        apres_le_fil(self, preparer, lambda resultat: self._poser_saut(numero, resultat),
                     "cinematique-saut")

    def _poser_saut(self, numero: int, resultat: object) -> None:
        if numero != self._demandes:     # un saut plus récent suit, ou l'arrêt
            if isinstance(resultat, tuple):
                self._jeter(resultat[1])
            return
        ms, self._attente = self._attente, -1
        if not isinstance(resultat, tuple):
            # Ni index ni copie : depuis le début, comme un lecteur ordinaire.
            if self._player is None:
                self._ouvrir(self._source, self._muted, self._volume)
            return
        index, chemin, debut = resultat
        self._complet = index
        pause, precedente = self._paused, self._copie
        self._liberer()
        self._ouvrir(chemin, self._muted, self._volume)
        self._copie = Path(chemin) if chemin != self._source else None
        if precedente is not None and precedente != self._copie:
            self._jeter(str(precedente))
        self._decalage = debut
        self._cible = ms if ms - debut > 40 else -1
        self._pause_apres_saut = pause
        if self._cible >= 0:
            self._player.setPlaybackRate(_RATTRAPAGE)
        elif pause:
            self.pause()

    def _jeter(self, chemin: str) -> None:
        """Efface une copie de saut (jamais la cinématique elle-même)."""
        if chemin != self._source and Path(chemin).parent == dossier_des_copies():
            try:
                Path(chemin).unlink(missing_ok=True)
            except OSError:              # encore ouverte : effacée au prochain arrêt
                pass

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
            self._index = vp6_ea.lire_entete(video_path)
            if self._index is not None and debut_ms > 0:
                self._demander_saut(debut_ms)
                return True
        self._ouvrir(video_path, muted, volume)
        self._position_en_attente = debut_ms if debut_ms > 0 else -1
        return True

    def _ouvrir(self, video_path: str, muted: bool, volume: float) -> None:
        parent_widget = self.parent()

        self._sink = QVideoSink(parent_widget)
        # Vers la carte graphique, les images passent quand même par notre récepteur :
        # branché tout droit sur la sortie, le lecteur lui donnait ses 60 images/s et la
        # fenêtre se recomposait 60 fois par seconde pour un fond (mesuré le 2026-11-01 :
        # 21-26 % d'un cœur, 18-19 % en relayant une image sur deux). Relayer ne copie
        # rien : la `QVideoFrame` reste dans la carte graphique. C'est aussi ce qui
        # rend l'avance rapide d'une cinématique d'EA possible ici : son horodatage
        # se lit sans convertir l'image (`_en_avance_rapide`).
        self._relais = self._recepteur(self._sortie)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._audio = QAudioOutput(parent_widget)
        self._audio.setVolume(volume)
        self._audio.setMuted(muted)
        self._muted = muted
        self._volume = volume
        self._player = QMediaPlayer(parent_widget)
        self._player.setVideoOutput(self._sink)
        self._brancher_son()
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
        self._demandes += 1              # un saut en préparation n'aboutira plus
        self._attente = -1
        self._copie = None
        self._effacer_copies()
        self._source, self._index, self._complet = "", None, None
        self._decalage, self._cible = 0, -1

    @staticmethod
    def _effacer_copies() -> None:
        """Les copies des sauts (jusqu'à 329 Mo chacune pour HP8) ne restent
        pas dans le cache fixe après la lecture (grand audit du 2026-11-02)."""
        dossier = dossier_des_copies()
        if not dossier.is_dir():
            return
        for copie in dossier.glob("saut_*.vp6"):
            try:
                copie.unlink()
            except OSError:      # encore ouverte ou en cours d'écriture : au prochain arrêt
                pass

    def _liberer(self) -> None:
        if self._player is not None:
            # Jamais `stop()` : il garde le GIL ; `setSource(QUrl())` arrête
            # aussi, et le relâche (règle 135).
            self._player.setSource(QUrl())
            self._player.mediaStatusChanged.disconnect(self._on_media_status)
            self._player.positionChanged.disconnect(self._sur_position)
            self._player.durationChanged.disconnect(self._sur_duree)
            self._sink.videoFrameChanged.disconnect(self._on_frame)
            if self._relais is not None:
                # La dernière image resterait affichée au début de la lecture suivante.
                # Sauf au cinéma, où l'écran la garde comme le chemin QPainter : pendant
                # l'avance rapide d'un saut (jusqu'à 6 s pour HP7), et pendant qu'une
                # narration finit sa phrase après la fin de l'image (HP5).
                if not self._garder_image:
                    self._relais.setVideoFrame(QVideoFrame())
                self._relais = None
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
        self._brancher_son()
        return self._muted

    def set_muted(self, muted: bool) -> None:
        """Force l'état mute (réglage « Couper le son » appliqué en direct)."""
        self._muted = muted
        if self._audio is not None:
            self._audio.setMuted(muted)
            self._brancher_son()

    def set_volume(self, value_0_100: int) -> None:
        """Définit le volume (0-100). Unmute automatiquement si muté."""
        if self._audio is None:
            return
        if self._muted:
            self._muted = False
            self._audio.setMuted(False)
            self._brancher_son()
        self._audio.setVolume(value_0_100 / 100.0)

    def _brancher_son(self) -> None:
        """Muette, la lecture n'a pas de sortie audio : décoder et mixer un son que
        personne n'entend coûtait 3 à 4 points d'un cœur (mesuré le 2026-11-01), et
        les bandes-annonces sont muettes par défaut (`Config.mute_videos`)."""
        if self._player is not None:
            self._player.setAudioOutput(None if self._muted else self._audio)

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

    def _relayer(self, frame) -> None:
        if self._relais is not None and frame.isValid() and self.a_monter(frame.startTime()):
            self._relais.setVideoFrame(frame)

    def _en_avance_rapide(self, frame) -> bool:
        """Après un saut : rien à montrer avant le point voulu, puis vitesse normale."""
        if self._cible < 0 or not frame.isValid():
            return False
        if frame.startTime() // 1000 + self._decalage < self._cible:
            return True
        self._cible = -1
        self._player.setPlaybackRate(1.0)
        if self._pause_apres_saut:
            self._pause_apres_saut = self._paused = False
            self.pause()
        return False

    def _on_frame(self, frame) -> None:
        if self._en_avance_rapide(frame):
            return
        if self._relais is not None:
            self._relayer(frame)
        elif frame.isValid() and self.a_monter(frame.startTime()):
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

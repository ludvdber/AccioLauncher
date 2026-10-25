"""La musique de fond du launcher, et le haut-parleur qui coupe tout.

Demandé par Ludo le 2026-10-24 : choisir un morceau des jeux comme fond
sonore, le faire cohabiter avec les bandes-annonces, et pouvoir couper le son
« sans devoir toucher à 15 menus ».

**Un seul lecteur, des raisons de se taire.** La musique joue quand un morceau
est choisi, que le son n'est pas coupé et qu'AUCUNE raison ne la suspend :
`BANDE_ANNONCE` (une bande-annonce joue avec le son), `JEU` (une partie est en
cours), `FENETRE` (le launcher est caché dans la zone de notification),
`CINEMATIQUE` (une cinématique de la Médiathèque joue). Chaque
raison se pose et se retire seule ; la musique reprend quand il n'en reste
aucune. Une écoute depuis la Médiathèque (`ecouter`) passe devant le fond, se met
en pause sur place (`basculer_pause`) et continue hors de la page : le
mini-lecteur de la barre du bas la montre. Elle rend la main au fond quand
on l'arrête (`arreter_ecoute`).

**Le son coupé** (`Config.son_coupe`) vaut pour tout le launcher : la fenêtre
l'applique aussi aux bandes-annonces (`son_coupe_change`).

Les morceaux se trouvent par `phonographe` (copie du joueur, HP1 extrait dans
le cache) ; un morceau introuvable (jeu désinstallé) se tait sans erreur.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget

from src.core import discographie, phonographe
from src.core.config import Config

# Au chargement du module, comme `video_player` (règle 5).
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    MULTIMEDIA_DISPONIBLE = True
except ImportError:                                   # pragma: no cover
    QAudioOutput = QMediaPlayer = None                # type: ignore[assignment,misc]
    MULTIMEDIA_DISPONIBLE = False

log = logging.getLogger(__name__)

BANDE_ANNONCE = "bande_annonce"
JEU = "jeu"
FENETRE = "fenetre"
CINEMATIQUE = "cinematique"


def cle(jeu: str, fichier: str) -> str:
    return f"{jeu}/{fichier}"


def decouper(cle_morceau: str) -> tuple[str, str] | None:
    jeu, sep, fichier = cle_morceau.partition("/")
    return (jeu, fichier) if sep and jeu and fichier else None


class FondSonore(QObject):
    """Le lecteur de fond ; la barre du bas et la page Musique ne font que l'appeler."""

    change = pyqtSignal()
    son_coupe_change = pyqtSignal(bool)

    def __init__(self, config: Config, dossier_jeu: Callable[[str], Path | None],
                 cache: Callable[[], Path], fenetre: QWidget) -> None:
        super().__init__(fenetre)
        self._config = config
        self._dossier_jeu = dossier_jeu
        self._cache = cache
        self._raisons: set[str] = set()
        self._ecoute = ""              # morceau écouté depuis la page, devant le fond
        self._en_pause = False         # l'écoute arrêtée sur place, prête à reprendre
        self._courant = ""             # morceau chargé dans le lecteur
        # Les morceaux, pas leurs titres : le titre se lit dans la langue du moment.
        self._morceaux = {cle(j, m.fichier): m
                          for j, morceaux in discographie.charger().items() for m in morceaux}
        self._lecteur: QMediaPlayer | None = None
        self._sortie: QAudioOutput | None = None
        fenetre.installEventFilter(self)

    # ── État ──

    @property
    def disponible(self) -> bool:
        return MULTIMEDIA_DISPONIBLE

    @property
    def son_coupe(self) -> bool:
        return self._config.son_coupe

    @property
    def fond(self) -> str:
        return self._config.musique_fond

    @property
    def ecoute(self) -> str:
        return self._ecoute

    @property
    def en_pause(self) -> bool:
        return bool(self._ecoute) and self._en_pause

    @property
    def morceau(self) -> str:
        """Ce que la platine montre : l'écoute de la page, sinon le fond."""
        return self._ecoute or self._config.musique_fond

    def titre(self, cle_morceau: str) -> str:
        morceau = self._morceaux.get(cle_morceau)
        return morceau.titre if morceau is not None else ""

    @property
    def en_lecture(self) -> bool:
        lecteur = self._lecteur
        return (lecteur is not None and bool(self._courant)
                and lecteur.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    # ── Ce que la page et la barre demandent ──

    def demarrer(self) -> None:
        """Ouverture du launcher : le fond choisi la dernière fois reprend."""
        self._appliquer()

    def choisir_fond(self, cle_morceau: str) -> None:
        """Ce morceau devient le fond (vide = aucun), enregistré aussitôt."""
        self._config.musique_fond = cle_morceau
        self._config.save()
        self._appliquer()

    def ecouter(self, cle_morceau: str) -> None:
        """Une écoute depuis la page : passe devant le fond, même son coupé
        (un clic sur « écouter » est une demande explicite de son)."""
        self._ecoute = cle_morceau
        self._en_pause = False
        if self._config.son_coupe:
            self._config.son_coupe = False
            self._config.save()
            self.son_coupe_change.emit(False)
        self._appliquer()

    def basculer_pause(self) -> None:
        """Pause ou reprise de ce que montre la platine. Sans écoute, le fond
        devient l'écoute : en lecture il se met en pause, muet il repart."""
        if not self._ecoute:
            if not self._config.musique_fond:
                return
            self._en_pause = self.en_lecture
            self._ecoute = self._config.musique_fond
        else:
            self._en_pause = not self._en_pause
        if not self._en_pause and self._config.son_coupe:
            self._config.son_coupe = False
            self._config.save()
            self.son_coupe_change.emit(False)
        self._appliquer()

    def arreter_ecoute(self) -> None:
        self._ecoute = ""
        self._en_pause = False
        self._appliquer()

    def basculer_son(self) -> None:
        self._config.son_coupe = not self._config.son_coupe
        self._config.save()
        self.son_coupe_change.emit(self._config.son_coupe)
        self._appliquer()

    def regler_volume(self, valeur: int, enregistrer: bool = True) -> None:
        """`enregistrer=False` pendant qu'on glisse le curseur : une écriture au lâcher."""
        self._config.volume_musique = max(0, min(100, valeur))
        if enregistrer:
            self._config.save()
        if self._sortie is not None:
            self._sortie.setVolume(self._config.volume_musique / 100.0)

    # ── Raisons de se taire ──

    def suspendre(self, raison: str) -> None:
        if raison not in self._raisons:
            self._raisons.add(raison)
            self._appliquer()

    def reprendre(self, raison: str) -> None:
        if raison in self._raisons:
            self._raisons.discard(raison)
            self._appliquer()

    def bande_annonce_sonore(self, oui: bool) -> None:
        (self.suspendre if oui else self.reprendre)(BANDE_ANNONCE)

    def eventFilter(self, obj, event) -> bool:
        # Cachée dans la zone de notification : la musique se tait avec elle.
        if event.type() == QEvent.Type.Hide:
            self.suspendre(FENETRE)
        elif event.type() == QEvent.Type.Show:
            self.reprendre(FENETRE)
        return False

    # ── Lecture ──

    def _voulu(self) -> str:
        """Le morceau qui devrait jouer maintenant, vide pour le silence."""
        if self._ecoute:
            # L'écoute de la page ne cède qu'à sa pause, à une partie lancée, à la
            # fenêtre cachée ou à une cinématique.
            if self._en_pause or self._raisons & {JEU, FENETRE, CINEMATIQUE}:
                return ""
            return self._ecoute
        if self._config.son_coupe or self._raisons:
            return ""
        return self._config.musique_fond

    def fichier(self, cle_morceau: str) -> Path | None:
        """Le fichier lisible d'un morceau (HP1 : extrait dans le cache), ou None."""
        morceau = decouper(cle_morceau)
        if morceau is None:
            return None
        jeu, fichier = morceau
        for piste in phonographe.pistes(jeu, self._dossier_jeu(jeu)):
            if piste.identifiant == fichier:
                return phonographe.fichier_lisible(piste, self._cache())
        return None

    def _appliquer(self) -> None:
        voulu = self._voulu()
        if not voulu or not MULTIMEDIA_DISPONIBLE:
            if self._lecteur is not None:
                self._lecteur.pause()
            self.change.emit()
            return
        if voulu != self._courant:
            chemin = self.fichier(voulu)
            if chemin is None:
                log.info("Musique de fond introuvable : %s", voulu)
                if self._lecteur is not None:
                    self._lecteur.stop()
                self._courant = ""
                self.change.emit()
                return
            lecteur = self._preparer()
            lecteur.setSource(QUrl.fromLocalFile(str(chemin)))
            self._courant = voulu
        if self._lecteur is not None:
            self._lecteur.play()
        self.change.emit()

    def _preparer(self) -> QMediaPlayer:
        """Le lecteur, créé au premier morceau : rien à l'ouverture pour qui n'en choisit pas."""
        if self._lecteur is None:
            self._sortie = QAudioOutput(self)
            self._sortie.setVolume(self._config.volume_musique / 100.0)
            self._lecteur = QMediaPlayer(self)
            self._lecteur.setAudioOutput(self._sortie)
            self._lecteur.setLoops(QMediaPlayer.Loops.Infinite)
            # `play()` est asynchrone : l'état lu juste après valait encore
            # « arrêté », et le disque de la page ne tournait pas (Ludo, 2026-10-24).
            self._lecteur.playbackStateChanged.connect(self._etat_change)
        return self._lecteur

    def _etat_change(self, _etat) -> None:
        self.change.emit()

    def arreter(self) -> None:
        """Fermeture du launcher : le lecteur s'arrête et lâche son fichier."""
        if self._lecteur is not None:
            self._lecteur.stop()
            self._lecteur.setSource(QUrl())
        self._courant = ""

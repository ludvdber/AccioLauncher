"""La musique de fond du launcher, et le haut-parleur qui coupe tout.

Demandé par Ludo le 2026-10-24 : choisir un morceau des jeux comme fond
sonore, le faire cohabiter avec les bandes-annonces, et pouvoir couper le son
« sans devoir toucher à 15 menus ».

**Un seul lecteur, des raisons de se taire.** La musique joue quand un morceau
est choisi, que le son n'est pas coupé et qu'AUCUNE raison ne la suspend :
`BANDE_ANNONCE` (une bande-annonce joue avec le son), `JEU` (une partie est en
cours), `FENETRE` (le launcher est caché dans la zone de notification). Chaque
raison se pose et se retire seule ; la musique reprend quand il n'en reste
aucune. Une écoute depuis la page Musique (`ecouter`) passe devant le fond et
le rend à la sortie de la page (`fin_ecoute`).

**Le son coupé** (`Config.son_coupe`) vaut pour tout le launcher : la fenêtre
l'applique aussi aux bandes-annonces (`son_coupe_change`).

Les morceaux se trouvent par `phonographe` (copie du joueur, HP1 extrait dans
le cache) ; un morceau introuvable (jeu désinstallé) se tait sans erreur.
"""

from __future__ import annotations

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
        self._courant = ""             # morceau chargé dans le lecteur
        self._titres = {cle(j, m.fichier): m.titre
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

    def titre(self, cle_morceau: str) -> str:
        return self._titres.get(cle_morceau, "")

    @property
    def en_lecture(self) -> bool:
        lecteur = self._lecteur
        return (lecteur is not None and bool(self._courant)
                and lecteur.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    # ── Ce que la page et la barre demandent ──

    def choisir_fond(self, cle_morceau: str) -> None:
        """Ce morceau devient le fond (vide = aucun), enregistré aussitôt."""
        self._config.musique_fond = cle_morceau
        self._config.save()
        self._appliquer()

    def ecouter(self, cle_morceau: str) -> None:
        """Une écoute depuis la page : passe devant le fond, même son coupé
        (un clic sur « écouter » est une demande explicite de son)."""
        self._ecoute = cle_morceau
        if self._config.son_coupe:
            self._config.son_coupe = False
            self._config.save()
            self.son_coupe_change.emit(False)
        self._appliquer()

    def arreter_ecoute(self) -> None:
        self._ecoute = ""
        self._appliquer()

    def fin_ecoute(self) -> None:
        """La page se ferme : le fond reprend sa place."""
        if self._ecoute:
            self.arreter_ecoute()

    def basculer_son(self) -> None:
        self._config.son_coupe = not self._config.son_coupe
        self._config.save()
        self.son_coupe_change.emit(self._config.son_coupe)
        self._appliquer()

    def regler_volume(self, valeur: int) -> None:
        self._config.volume_musique = max(0, min(100, valeur))
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
            # L'écoute de la page ne cède qu'à une partie lancée ou à la fenêtre cachée.
            return "" if self._raisons & {JEU, FENETRE} else self._ecoute
        if self._config.son_coupe or self._raisons:
            return ""
        return self._config.musique_fond

    def _fichier(self, cle_morceau: str) -> Path | None:
        morceau = decouper(cle_morceau)
        if morceau is None:
            return None
        jeu, fichier = morceau
        for piste in phonographe.pistes(jeu, self._dossier_jeu(jeu)):
            if piste.source.stem == fichier:
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
            chemin = self._fichier(voulu)
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
        return self._lecteur

    def arreter(self) -> None:
        """Fermeture du launcher : le lecteur s'arrête et lâche son fichier."""
        if self._lecteur is not None:
            self._lecteur.stop()
            self._lecteur.setSource(QUrl())
        self._courant = ""

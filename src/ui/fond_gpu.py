"""FondGPU — le fond de l'accueil dessiné par la carte graphique (Qt Quick).

Même interface que `BackgroundWidget`, qu'il remplace quand Qt Quick est là et
que l'interrupteur est mis (`actif()`). Ce que ça change :

- la bande-annonce passe de `QMediaPlayer` à un `VideoOutput` sans détour : ni
  `toImage()` (8 ms par image en 1080p), ni peinture de toute la fenêtre ;
- l'illustration, son zoom, sa parallaxe et le fondu enchaîné sont des
  transformations de texture, plus des mises à l'échelle lissées au processeur.

Le zoom et la parallaxe restent cadencés par le `Ticker` (même pas, même
inertie, même pause fenêtre inactive) : seule la valeur part vers la scène.
Le bandeau étendu ne passe plus par un flou : il se prolonge dans la couleur
dominante de son propre bas (`_ambiance`).
"""

import functools
import logging
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import QObject, QRect, QRectF, QSize, Qt, QUrl, pyqtProperty
from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget

from src.core.config import ASSETS_DIR
from src.core.season import profil as profil_de
from src.ui import theme
from src.ui.background_widget import (
    _VOILE_ALPHA, _ZOOM_MAX, _ZOOM_MIN, _ZOOM_STEP, BackgroundWidget, construire_voiles,
)
from src.ui.particles import _FORMES, _Particle
from src.ui.ticker import TICK_MS, Ticker

try:
    from PyQt6.QtQuick import QQuickImageProvider
    from PyQt6.QtQuickWidgets import QQuickWidget
    QUICK_DISPONIBLE = True
except ImportError:                                    # pragma: no cover
    QQuickImageProvider = QQuickWidget = None          # type: ignore[assignment,misc]
    QUICK_DISPONIBLE = False

log = logging.getLogger(__name__)

_QML = ASSETS_DIR / "qml" / "FondAccueil.qml"
_ETENDU_RATIO = 1.2


def actif() -> bool:
    """Le fond passe-t-il par la carte graphique ?

    Oui par défaut sous Windows (mesuré en vraie fenêtre le 2026-11-01 : repos
    22 → 11 % d'un cœur, bande-annonce 90 → 28 %, mode cinéma 125 → 15 %).
    Pas encore sous Linux, où Qt Quick passe par OpenGL et n'a pas été essayé
    sous Wine ni dans l'AppImage. `ACCIO_FOND_GPU=0` ou `=1` force l'un ou l'autre.
    """
    if not QUICK_DISPONIBLE or not _QML.exists():
        return False
    force = os.environ.get("ACCIO_FOND_GPU")
    if force in ("0", "1"):
        return force == "1"
    return sys.platform == "win32"


@functools.cache
def _ambiance(chemin: Path) -> QColor:
    """La couleur dominante du bas d'une image, assombrie : le prolongement du bandeau.
    Gardée par chemin : la calculer décodait le JPEG, 10 ms à chaque changement de jeu."""
    img = QImage(str(chemin))
    if img.isNull():
        return theme.bg_qcolor(255)
    bas = img.copy(0, img.height() * 2 // 3, img.width(), img.height() // 3).scaled(16, 4)
    # La plus saturée des cases, pas la moyenne : une moyenne tire vers un gris boueux.
    meilleure = max((bas.pixelColor(x, y) for x in range(16) for y in range(4)),
                    key=lambda c: c.hsvSaturationF() * (0.3 + c.valueF()))
    h, s, _, _ = meilleure.getHsvF()
    return QColor.fromHsvF(max(0.0, h), min(1.0, s * 1.1), 0.18)


# Les formes des particules sont peintes une fois, agrandies de ce facteur, puis
# posées à leur taille : nettes jusqu'à l'échelle 200 % sans repeindre.
_SUREECHELLE = 4


def _image_voiles(ident: str) -> QImage:
    # ident = « l×h/dpr/n » ; n change avec la taille ou le thème pour vider le cache.
    dims, dpr, _ = ident.split("/")
    w, h = (int(v) for v in dims.split("x"))
    echelle = float(dpr)
    # Peintes en pixels logiques puis agrandies : ce ne sont que des dégradés.
    image = construire_voiles(w, h).toImage()
    if echelle != 1.0:
        image = image.scaled(math.ceil(w * echelle), math.ceil(h * echelle))
    return image


def _image_halo(rgb: str) -> QImage:
    """Le halo d'une particule : le même dégradé radial que `ParticleOverlay._halo`."""
    r, g, b = (int(v) for v in rgb.split(","))
    cote = 64
    image = QImage(cote, cote, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QRadialGradient(cote / 2, cote / 2, cote / 2)
    grad.setColorAt(0, QColor(r, g, b, 255))
    grad.setColorAt(1, QColor(r, g, b, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(QRectF(0, 0, cote, cote))
    p.end()
    return image


def _image_forme(ident: str) -> QImage:
    """Flocon, lettre ou flamme, peints par les gestes de `ParticleOverlay`."""
    forme, rgb, taille = ident.split("/")
    r, g, b = (int(v) for v in rgb.split(","))
    size = float(taille)
    cote = math.ceil(size * 2.4 * _SUREECHELLE)
    image = QImage(max(cote, 1), max(cote, 1), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    peintre = _FORMES.get(forme)
    if peintre is not None:
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(_SUREECHELLE, _SUREECHELLE)
        modele = SimpleNamespace(x=size * 1.2, y=size * 1.2, size=size, rotation=0.0)
        peintre(p, modele, QColor(r, g, b, 255))
        p.end()
    return image


if QUICK_DISPONIBLE:
    class _Voiles(QQuickImageProvider):
        """Sert à la scène les images peintes par Python : voiles fixes, halos, formes."""

        def __init__(self) -> None:
            super().__init__(QQuickImageProvider.ImageType.Image)

        def requestImage(self, ident: str, voulue: QSize):
            genre, _, reste = ident.partition("/")
            image = (_image_voiles(reste) if genre == "voiles"
                     else _image_halo(reste) if genre == "halo"
                     else _image_forme(reste))
            return image, image.size()


class FondGPU(QQuickWidget if QUICK_DISPONIBLE else QWidget):  # type: ignore[misc]
    """Le fond de l'accueil sur la carte graphique, interface de `BackgroundWidget`."""

    PARALLAX_MAX_X = BackgroundWidget.PARALLAX_MAX_X
    PARALLAX_MAX_Y = BackgroundWidget.PARALLAX_MAX_Y
    MAX_SCALE = BackgroundWidget.MAX_SCALE

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._opacity = 1.0
        self._source = ""
        self._taille_image = QSize()
        self._voiles_n = 0
        self._zoom = 1.0
        self._zoom_phase = 0.0
        self._zoom_ticking = False
        self._zoom_running = False
        self._parallax_tx = self._parallax_ty = 0.0
        self._parallax_cx = self._parallax_cy = 0.0
        self._parallax_ticking = False
        self._cinema = False
        self._semees = False
        # Les particules de la fenêtre, quand elles vivent ici (`ParticulesGPU`).
        self.particules: ParticulesGPU | None = None
        # Gardé par Python : sans référence, le ramasse-miettes le détruit et la
        # scène reçoit « Failed to get image from provider ».
        self._fournisseur = _Voiles()
        self.engine().addImageProvider("accio", self._fournisseur)
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setClearColor(theme.bg_qcolor(255))
        self.setSource(QUrl.fromLocalFile(str(_QML)))
        for erreur in self.errors():
            log.warning("Fond sur la carte graphique : %s", erreur.toString())
        self._racine = self.rootObject()
        if self._racine is not None:
            self._racine.setProperty("fond", theme.bg_qcolor(255))
            self._racine.setProperty("voileAlpha", _VOILE_ALPHA / 255)
            self._racine.setProperty("parallaxeMaxY", self.PARALLAX_MAX_Y)
            log.info("Fond de l'accueil sur la carte graphique (%s)",
                     self.quickWindow().rendererInterface().graphicsApi().name)

    def _poser(self, nom: str, valeur: object) -> None:
        if self._racine is not None:
            self._racine.setProperty(nom, valeur)

    # ── Particules (pilotées par `ParticulesGPU`) ──

    def poser_particules(self, liste: list[dict[str, object]]) -> None:
        self._semees = bool(liste)
        self._poser("temps", 0)
        self._poser("particules", liste)

    def particules_semees(self) -> bool:
        return self._semees

    def poser_temps(self, pas: int) -> None:
        self._poser("temps", pas)

    def poser_particules_visibles(self, oui: bool) -> None:
        self._poser("particulesVisibles", oui)

    def poser_particules_secondes(self, secondes: float) -> None:
        self._poser("secondesParPas", secondes)

    def valide(self) -> bool:
        """La scène a-t-elle chargé ? Sinon (greffon QML absent, pilote refusé),
        la vue retombe sur `BackgroundWidget`."""
        return self._racine is not None and self.sortie_video() is not None

    def sortie_video(self) -> QObject | None:
        """Le `VideoOutput` de la scène, pour `VideoPlayer.set_sortie`."""
        # Par son nom : la propriété alias revient en pointeur nu (`sip.voidptr`).
        return self._racine.findChild(QObject, "sortieVideo") if self._racine is not None else None

    # ── Interface de BackgroundWidget ──

    def _get_bg_opacity(self) -> float:
        return self._opacity

    def _set_bg_opacity(self, value: float) -> None:
        self._opacity = value
        self._poser("opacite", value)

    bg_opacity = pyqtProperty(float, _get_bg_opacity, _set_bg_opacity)

    def start_zoom_loop(self) -> None:
        self._zoom, self._zoom_phase, self._zoom_running = _ZOOM_MIN, 0.0, True
        self._set_zoom_ticking(True)

    def _set_zoom_ticking(self, on: bool) -> None:
        if on and not self._zoom_ticking:
            Ticker.instance().tick.connect(self._advance_zoom)
            self._zoom_ticking = True
        elif not on and self._zoom_ticking:
            Ticker.detach(self._advance_zoom)
            self._zoom_ticking = False

    def _advance_zoom(self) -> None:
        # Même courbe et même pas que `BackgroundWidget._advance_zoom` : un seul aller.
        self._zoom_phase = min(1.0, self._zoom_phase + _ZOOM_STEP)
        eased = 0.5 - 0.5 * math.cos(math.pi * self._zoom_phase)
        self._zoom = _ZOOM_MIN + (_ZOOM_MAX - _ZOOM_MIN) * eased
        self._poser("zoom", self._zoom)
        if self._zoom_phase >= 1.0:
            self._zoom_running = False
            self._set_zoom_ticking(False)

    def set_parallax_target(self, mouse_x: float, mouse_y: float, win_w: float, win_h: float) -> None:
        if win_w <= 0 or win_h <= 0:
            return
        self._parallax_tx = -(mouse_x - win_w / 2) / win_w * self.PARALLAX_MAX_X
        self._parallax_ty = -(mouse_y - win_h / 2) / win_h * self.PARALLAX_MAX_Y
        self._set_parallax_ticking(True)

    def _set_parallax_ticking(self, on: bool) -> None:
        if on and not self._parallax_ticking:
            Ticker.instance().tick.connect(self._update_parallax)
            self._parallax_ticking = True
        elif not on and self._parallax_ticking:
            Ticker.detach(self._update_parallax)
            self._parallax_ticking = False

    def _update_parallax(self) -> None:
        dx = self._parallax_tx - self._parallax_cx
        dy = self._parallax_ty - self._parallax_cy
        if abs(dx) < 0.05 and abs(dy) < 0.05:
            self._set_parallax_ticking(False)
            return
        self._parallax_cx += dx * 0.10
        self._parallax_cy += dy * 0.10
        # Le chemin QPainter déplace la zone LUE de l'image : l'image, elle, va à l'opposé.
        self._poser("parallaxeX", -self._parallax_cx)
        self._poser("parallaxeY", -self._parallax_cy)

    def pause(self) -> None:
        self._set_parallax_ticking(False)
        self._set_zoom_ticking(False)

    def resume(self) -> None:
        if self._zoom_running:
            self._set_zoom_ticking(True)
        if abs(self._parallax_tx - self._parallax_cx) >= 0.05 or abs(self._parallax_ty - self._parallax_cy) >= 0.05:
            self._set_parallax_ticking(True)

    def invalidate_cache(self) -> None:
        """La taille a changé : les voiles fixes et le cadrage étendu sont à refaire."""
        self._voiles_n += 1
        w, h = self.width(), self.height()
        if w > 0 and h > 0:
            self._poser("voiles", f"image://accio/voiles/{w}x{h}/{self.devicePixelRatioF():g}/{self._voiles_n}")
        self._poser("etendu", self._doit_etendre(w, h))
        if self.particules is not None:
            self.particules.resemer_si_taille()

    def begin_crossfade(self) -> None:
        self._poser("ancienne", QUrl.fromLocalFile(self._source) if self._source else QUrl())

    def cinema(self) -> bool:
        return self._cinema

    def set_cinema(self, actif_: bool) -> None:
        self._cinema = actif_
        self._poser("cinema", actif_)

    def set_video_frame(self, image: QImage | None) -> None:
        """Les images arrivent par `sortie_video()` : ce signal ne sert qu'à dire « vidéo »."""
        self._poser("video", image is not None)

    def debut_video(self) -> None:
        self._poser("video", True)

    def clear_video(self) -> None:
        self._poser("video", False)

    def set_image(self, path: Path | None) -> None:
        self._source = str(path) if path and path.exists() else ""
        self._taille_image = QImageReader(self._source).size() if self._source else QSize()
        self._poser("ambiance", _ambiance(Path(self._source)) if self._source else theme.bg_qcolor(255))
        self._poser("etendu", self._doit_etendre(self.width(), self.height()))
        self._poser("source", QUrl.fromLocalFile(self._source) if self._source else QUrl())

    def _doit_etendre(self, w: int, h: int) -> bool:
        """Même règle que `BackgroundWidget._doit_etendre`."""
        iw, ih = self._taille_image.width(), self._taille_image.height()
        if iw <= 0 or ih <= 0 or w <= 0 or h <= 0 or iw / ih < (w / h) * _ETENDU_RATIO:
            return False
        return h * self.devicePixelRatioF() * self.MAX_SCALE > ih


class ParticulesGPU:
    """Les particules de l'Almanach dans la scène du fond, interface de `ParticleOverlay`.

    Les paramètres de chaque particule sont tirés par le MÊME constructeur
    (`particles._Particle`, donc les mêmes ambiances de `season.py`) ; la scène
    calcule ensuite chaque position comme une fonction du temps. Python ne fait
    qu'avancer un compteur de pas au rythme du Ticker : rien n'est peint par le
    processeur, et la fenêtre de widgets n'est plus repeinte sous les particules.
    Elles vivent dans la zone du fond, sous la fiche ; plus devant les jaquettes.
    """

    def __init__(self, fond: FondGPU) -> None:
        self._fond = fond
        self._profil = profil_de("aucune")
        self._season = "aucune"
        self._temps = 0
        self._ticking = False
        self._visible = True
        self._fond.poser_particules_secondes(TICK_MS / 1000.0)
        # Objet Python simple : PyQt ne le débranche pas du Ticker à la mort du fond,
        # et le pas suivant visait une scène détruite (« wrapped C/C++ object… deleted »).
        self._fond.destroyed.connect(self._fond_detruit)
        self.resume()

    def _fond_detruit(self) -> None:
        self.pause()
        self._visible = False

    def _semer(self) -> None:
        w, h = self._fond.width(), self._fond.height()
        liste = []
        for _ in range(self._profil.nombre):
            pt = _Particle(w, h, self._profil)
            liste.append({
                "x0": pt.x, "y0": pt.y, "vx": pt.speed_x, "vy": pt.speed_y, "sway": pt.sway,
                "phase0": pt.phase, "ps": pt.phase_speed, "rot0": pt.rotation, "rs": pt.rot_speed,
                "flicker": pt.flicker, "base": pt.base_opacity, "variation": pt.opacity_variation,
                "size": pt.size, "glow": pt.glow_size if pt.has_glow else 0.0, "forme": pt.shape,
                # Deux écritures : « r,g,b » pour nommer l'image d'un halo ou d'une
                # forme, et 0..1 pour `Qt.rgba` (QML ne lit pas « rgb(…) »).
                "rgb": ",".join(str(c) for c in pt.color_rgb),
                "r": pt.color_rgb[0] / 255, "g": pt.color_rgb[1] / 255, "b": pt.color_rgb[2] / 255,
            })
        self._temps = 0
        self._fond.poser_particules(liste)

    def apply_season(self, season: str) -> None:
        if season == self._season and self._fond.particules_semees():
            return
        self._season = season
        self._profil = profil_de(season)
        self._semer()

    def masquer(self, zones) -> None:
        """Rien à masquer : la scène s'arrête au bord du fond, au-dessus des jaquettes."""

    def _avancer(self) -> None:
        self._temps += 1
        self._fond.poser_temps(self._temps)

    def pause(self) -> None:
        if self._ticking:
            Ticker.detach(self._avancer)
            self._ticking = False

    def resume(self) -> None:
        if not self._ticking and self._visible:
            Ticker.instance().tick.connect(self._avancer)
            self._ticking = True

    def setVisible(self, oui: bool) -> None:
        self._visible = oui
        self._fond.poser_particules_visibles(oui)
        if oui:
            self.resume()
        else:
            self.pause()

    def show(self) -> None:
        self.setVisible(True)

    def hide(self) -> None:
        self.setVisible(False)

    def isVisible(self) -> bool:
        return self._visible

    def raise_(self) -> None:
        """La scène est sous la fiche : rien à monter."""

    def setGeometry(self, *_args) -> None:
        """La zone est celle du fond."""

    def geometry(self) -> QRect:
        return self._fond.geometry()

    def resemer_si_taille(self) -> None:
        """Première taille connue, ou fenêtre redimensionnée : re-semer sur toute la zone."""
        if self._fond.width() > 0 and self._fond.height() > 0:
            self._semer()


_QML_ETOILES = ASSETS_DIR / "qml" / "EtoilesCarrousel.qml"


class EtoilesGPU(QQuickWidget if QUICK_DISPONIBLE else QWidget):  # type: ignore[misc]
    """Le fond étoilé du carrousel sur la carte graphique (`Carousel`).

    Posé SOUS les jaquettes, à la taille de la bande. Ses images partent dans
    la même composition que celles du fond de l'accueil : 0,2 point d'un cœur
    au repos, contre 6 quand le processeur repeignait les étoiles.
    """

    def __init__(self, etoiles: list[tuple[float, float, float, int, bool, float]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setClearColor(theme.bg_qcolor(255))
        self.setSource(QUrl.fromLocalFile(str(_QML_ETOILES)))
        for erreur in self.errors():
            log.warning("Étoiles du carrousel sur la carte graphique : %s", erreur.toString())
        self._racine = self.rootObject()
        if self._racine is not None:
            self._racine.setProperty("fond", theme.bg_qcolor(255))
            self._racine.setProperty("accent", theme.accent_qcolor(255))
            self._racine.setProperty("etoiles", [list(e) for e in etoiles])

    def valide(self) -> bool:
        return self._racine is not None

    def poser_phase(self, phase: float) -> None:
        if self._racine is not None:
            self._racine.setProperty("phase", phase)

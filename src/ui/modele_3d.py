"""Un modèle 3D du jeu qu'on fait tourner à la souris, comme les skins sur NameMC.

Demande de Ludo (2026-10-26) : voir les personnages et les créatures en vrai
relief, qu'on tourne et qu'on fait bouger. Le modèle vient de la copie du
joueur (`maillages_ue1`), en pose de référence.

Les personnages sont modélisés bras en croix : les os des bras sont tournés
vers le bas (`maillages_ue1.bras_baisses`) et les points recalculés à chaque
image, ce qui donne aussi la respiration.

Rendu par QPainter, sans OpenGL : chaque face est un triangle rempli par sa
texture (une brosse dont la transformation envoie les UV sur le triangle à
l'écran), du plus loin au plus proche, avec un ombrage plat. Un modèle de HP1
compte environ mille faces : quelques millisecondes par image, et le même rendu
partout (Windows, Linux, plateforme `offscreen` des tests).

Glisser : tourner. Molette : zoom. Double-clic : vue de face. Lâché, le modèle
garde un peu d'élan ; au repos il tourne lentement et respire. Le minuteur ne
vit que si le widget est visible.

Les mouvements du jeu (`maillages_ue1.Animation`, demande de Ludo du
2026-10-27 : « un bouton pour animer les modèles ») se rejouent en boucle par
`animer(nom)` ; les bras baissés et la respiration ne valent que pour la pose
de référence.
"""

import math
import time

from PyQt6.QtCore import QPointF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QGuiApplication,
    QBrush,
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QShowEvent,
    QHideEvent,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import QWidget

from src.core import maillages_ue1
from src.core.maillages_ue1 import Animation, Maillage, Mouvement

LACET_DEPART = 20.0      # degrés : trois quarts, le relief se voit tout de suite
# Le mouvement montré d'abord : une attente qui boucle bien, par ordre de préférence.
_REPOS = ("breath", "idle", "stand", "fidget", "look", "wait", "hover", "fly", "walk")
TANGAGE_MAX = 35.0       # degrés, vers le haut comme vers le bas
_ZOOM = (0.6, 2.5)
_ROTATION_REPOS = 0.35   # degrés par image quand personne ne touche au modèle
_ATTENTE_REPOS = 120     # images (~2 s) après un geste avant de reprendre la rotation
_FREIN = 0.92            # part de l'élan gardée à chaque image
_DISTANCE = 3.2          # distance de la caméra, en hauteurs du modèle
_BRAS = 74.0             # degrés sous l'horizontale pour un modèle posé en croix
_LUMIERE = (0.55, -0.35, 0.75)   # vers la lumière : devant, à gauche, en haut


def _norme(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return v[0] / n, v[1] / n, v[2] / n


_L = _norme(_LUMIERE)


def transformation_affine(source: tuple[QPointF, QPointF, QPointF],
                          cible: tuple[QPointF, QPointF, QPointF]) -> QTransform | None:
    """La transformation qui envoie le triangle `source` sur `cible` ; None si
    `source` est plat (deux UV confondus)."""
    s0, s1, s2 = source
    d0, d1, d2 = cible
    e1x, e1y, e2x, e2y = s1.x() - s0.x(), s1.y() - s0.y(), s2.x() - s0.x(), s2.y() - s0.y()
    f1x, f1y, f2x, f2y = d1.x() - d0.x(), d1.y() - d0.y(), d2.x() - d0.x(), d2.y() - d0.y()
    det = e1x * e2y - e2x * e1y
    if abs(det) < 1e-9:
        return None
    a11 = (f1x * e2y - f2x * e1y) / det
    a12 = (f2x * e1x - f1x * e2x) / det
    a21 = (f1y * e2y - f2y * e1y) / det
    a22 = (f2y * e1x - f1y * e2x) / det
    dx = d0.x() - a11 * s0.x() - a12 * s0.y()
    dy = d0.y() - a21 * s0.x() - a22 * s0.y()
    return QTransform(a11, a21, a12, a22, dx, dy)


def mouvement_de_repos(animation: Animation) -> str | None:
    """Le mouvement à montrer d'abord : une attente (« breath », « Idle »…),
    sinon le premier qui dure plus d'une image, sinon le premier ; None sans
    mouvement."""
    noms = [m.nom for m in animation.mouvements]
    if not noms:
        return None
    for prefixe in _REPOS:
        for nom in noms:
            if nom.lower().startswith(prefixe):
                return nom
    return next((m.nom for m in animation.mouvements if m.images > 1), noms[0])


def _application_active() -> bool:
    return QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive


class Modele3D(QWidget):
    """Un modèle posé, vu de face au départ, qu'on fait tourner."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modele: Maillage | None = None
        self._pix: dict[str, QPixmap] = {}
        self._centre = (0.0, 0.0, 0.0)
        self._taille = 1.0
        self.lacet, self.tangage, self.zoom = LACET_DEPART, 8.0, 1.0
        self._elan = (0.0, 0.0)
        self._repos = 0
        self._phase = 0.0
        self._prise: QPointF | None = None
        self._bras = False
        self._face: maillages_ue1.Quat | None = None
        self._animation: Animation | None = None
        self._mouvement: Mouvement | None = None
        self._depart = 0.0              # `time.monotonic()` au lancement du mouvement
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(16)
        # PRÉCIS : le minuteur grossier de Windows tombe sur sa grille de
        # 15,6 ms, et une image sur deux arrivait 31 ms après la précédente.
        # Le modèle tournait par saccades (Ludo, 2026-10-27 : « encore pas
        # fluide »), comme le minuteur commun des particules (`ticker.py`).
        self._minuteur.setTimerType(Qt.TimerType.PreciseTimer)
        self._minuteur.timeout.connect(self._avancer)
        # Le launcher passé derrière une autre fenêtre : plus rien ne tourne.
        # Sans cela, la rotation au repos occupait un cœur entier (98 % mesurés)
        # tant que l'Encyclopédie restait ouverte (audit du 2026-10-29) ; le
        # Ticker des particules se met en pause de la même façon.
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._sur_etat_application)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    @property
    def modele(self) -> Maillage | None:
        return self._modele

    def poser(self, modele: Maillage | None, textures: dict[str, QImage] | None = None,
              animation: Animation | None = None) -> None:
        self._modele = modele
        self._pix = {nom: QPixmap.fromImage(img) for nom, img in (textures or {}).items()}
        self._bras = modele is not None and bool(maillages_ue1.bras_baisses(modele))
        self._face = maillages_ue1.face(modele) if modele is not None else None
        self._animation = animation if modele is not None else None
        self._mouvement = None
        points = self.points_du_moment()
        if points:
            # Cadré sur la pose montrée, pas sur la croix : sinon les bras tendus
            # rapetissent le personnage.
            bornes = [(min(p[k] for p in points), max(p[k] for p in points)) for k in range(3)]
            self._centre = ((bornes[0][0] + bornes[0][1]) / 2, (bornes[1][0] + bornes[1][1]) / 2,
                            (bornes[2][0] + bornes[2][1]) / 2)
            self._taille = max(b - a for a, b in bornes) or 1.0
        self.vue_de_face()
        self._mettre_en_route()

    def vue_de_face(self) -> None:
        """De trois quarts, un peu d'en haut, comme NameMC au chargement."""
        self.lacet, self.tangage, self.zoom = LACET_DEPART, 8.0, 1.0
        self._elan = (0.0, 0.0)
        self._repos = 0
        self.update()

    # --- Mouvements du jeu ---------------------------------------------------------

    def mouvements(self) -> list[str]:
        """Les mouvements que le modèle posé sait jouer, dans l'ordre du jeu."""
        return [m.nom for m in self._animation.mouvements] if self._animation is not None else []

    @property
    def mouvement(self) -> str | None:
        """Le mouvement en cours, None quand le modèle est en pose de référence."""
        return self._mouvement.nom if self._mouvement is not None else None

    def animer(self, nom: str | None) -> bool:
        """Rejoue `nom` en boucle depuis son début ; None rend la pose de
        référence. Faux si le modèle ne connaît pas ce mouvement."""
        if nom is None:
            self._mouvement = None
            self.update()
            return True
        if self._animation is None:
            return False
        mouvement = next((m for m in self._animation.mouvements if m.nom == nom), None)
        if mouvement is None:
            return False
        self._mouvement = mouvement
        self._depart = time.monotonic()
        self._repos = 0
        self.update()
        return True

    def instant(self) -> float:
        """Secondes écoulées depuis le lancement du mouvement."""
        return time.monotonic() - self._depart

    # --- Animation -------------------------------------------------------------

    def _mettre_en_route(self) -> None:
        if self._modele is not None and self.isVisible() and _application_active():
            self._minuteur.start()
        else:
            self._minuteur.stop()

    def _sur_etat_application(self, _etat: Qt.ApplicationState) -> None:
        self._mettre_en_route()

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        self._mettre_en_route()

    def hideEvent(self, event: QHideEvent | None) -> None:
        super().hideEvent(event)
        self._minuteur.stop()

    def _avancer(self) -> None:
        self._phase += 0.035
        if self._prise is None:
            dl, dt = self._elan
            if abs(dl) > 0.05 or abs(dt) > 0.05:
                self.tourner(dl, dt)
                self._elan = (dl * _FREIN, dt * _FREIN)
            elif self._repos >= _ATTENTE_REPOS:
                self.lacet = (self.lacet + _ROTATION_REPOS) % 360
            else:
                self._repos += 1
        self.update()

    def tourner(self, d_lacet: float, d_tangage: float) -> None:
        self.lacet = (self.lacet + d_lacet) % 360
        self.tangage = max(-TANGAGE_MAX, min(TANGAGE_MAX, self.tangage + d_tangage))

    # --- Souris ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._prise = event.position()
            self._elan = (0.0, 0.0)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None or self._prise is None:
            return
        pos = event.position()
        d = pos - self._prise
        self._prise = pos
        self._elan = (d.x() * 0.5, d.y() * 0.3)
        self.tourner(*self._elan)
        self._repos = 0
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        self._prise = None
        self._repos = 0
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        self.vue_de_face()

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is None:
            return
        pas = event.angleDelta().y() / 120
        self.zoom = max(_ZOOM[0], min(_ZOOM[1], self.zoom * (1.1 ** pas)))
        self._repos = 0
        self.update()

    # --- Rendu -------------------------------------------------------------------

    def points_du_moment(self) -> tuple[tuple[float, float, float], ...]:
        """Les points posés : bras baissés s'il était en croix, et un léger
        balancement des bras au rythme de la respiration."""
        m = self._modele
        if m is None:
            return ()
        points = m.points
        if self._mouvement is not None:
            # La clé de la racine porte déjà l'orientation du personnage : la
            # correction `face` (déduite du squelette de référence) s'y
            # ajouterait et montrerait Rogue, Malefoy ou le troll de profil.
            return maillages_ue1.pose(m, self._mouvement, self.instant())
        if self._bras:
            retouches = maillages_ue1.bras_baisses(m, _BRAS + 2.5 * math.sin(self._phase))
            points = maillages_ue1.poser(m, retouches)
        if self._face is not None:
            q = self._face
            points = tuple(maillages_ue1.tourner_point(q, p) for p in points)
        return points

    def projeter(self) -> list[tuple[float, float, float]]:
        """Chaque point : (x écran, y écran, profondeur vers la caméra)."""
        m = self._modele
        if m is None:
            return []
        cl, sl = math.cos(math.radians(self.lacet)), math.sin(math.radians(self.lacet))
        ct, st = math.cos(math.radians(self.tangage)), math.sin(math.radians(self.tangage))
        cx, cy, cz = self._centre
        k = 1.0 / self._taille
        # Respiration : le modèle monte et descend d'un rien.
        souffle = 0.008 * math.sin(self._phase)
        distance = _DISTANCE
        # 0,82 de la hauteur : dans la grande visionneuse (plus large que haute),
        # les pieds du gnome touchaient le bord (2026-10-27).
        focale = min(self.width(), self.height() * 0.82) * distance * 0.95 * self.zoom
        ox, oy = self.width() / 2, self.height() * 0.52
        sortie = []
        for x, y, z in self.points_du_moment():
            x, y, z = (x - cx) * k, (y - cy) * k, (z - cz) * k + souffle
            # Unreal : X devant le modèle, Y à sa gauche vu de face, Z en haut.
            xa, ya = x * cl - y * sl, x * sl + y * cl
            za, xb = z * ct + xa * st, xa * ct - z * st
            s = focale / (distance - xb)
            sortie.append((ox + ya * s, oy - za * s, xb))
        return sortie

    def paintEvent(self, event: object) -> None:
        if self._modele is None:
            return
        p = QPainter(self)
        self._peindre(p)
        p.end()

    def rendu(self, taille: QSize, dpr: float) -> QImage:
        """Une image du modèle sur fond transparent (les vignettes des fiches)."""
        self.resize(taille)
        image = QImage(round(taille.width() * dpr), round(taille.height() * dpr),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        if self._modele is not None:
            p = QPainter(image)
            self._peindre(p)
            p.end()
        return image

    def _peindre(self, p: QPainter) -> None:
        m = self._modele
        if m is None:
            return
        self._ombre_au_sol(p)
        ecran = self.projeter()
        faces = []
        for f in m.faces:
            a, b, c = (ecran[i] for i in f.sommets)
            aire = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
            mat = m.materiaux[f.materiau]
            dos = aire <= 0
            if dos and not mat.drapeaux & maillages_ue1.PF_DEUX_FACES:
                continue
            # L'envers d'une face à deux côtés (l'intérieur d'une robe) passe
            # avant tout l'endroit : jamais par-dessus le tissu qui le cache.
            faces.append((not dos, (a[2] + b[2] + c[2]) / 3, f, a, b, c))
        faces.sort(key=lambda t: (t[0], t[1]))
        p.setPen(Qt.PenStyle.NoPen)
        for _, _, f, a, b, c in faces:
            mat = m.materiaux[f.materiau]
            poly = QPolygonF([QPointF(a[0], a[1]), QPointF(b[0], b[1]), QPointF(c[0], c[1])])
            brosse = self._brosse(mat.texture, f.uv, poly)
            translucide = bool(mat.drapeaux & maillages_ue1.PF_TRANSLUCIDE)
            p.setOpacity(0.55 if translucide else 1.0)
            # Un trait de la même brosse bouche les fentes entre deux faces.
            p.setPen(QPen(brosse, 0.9))
            p.setBrush(brosse)
            p.drawPolygon(poly)
            # Pas d'ombre sur un matériau masqué : posée sur tout le triangle,
            # elle grisait ses parties transparentes (les mèches de HP3).
            ombre = 0 if mat.drapeaux & maillages_ue1.PF_MASQUE else self._ombre(a, b, c)
            if ombre > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, ombre))
                p.drawPolygon(poly)

    def _brosse(self, texture: str, uv: tuple[maillages_ue1.UV, maillages_ue1.UV, maillages_ue1.UV],
                poly: QPolygonF) -> QBrush:
        pix = self._pix.get(texture)
        if pix is None:
            return QBrush(QColor(150, 140, 125))
        w, h = pix.width(), pix.height()
        (u0, v0), (u1, v1), (u2, v2) = uv
        source = (QPointF(u0 * w, v0 * h), QPointF(u1 * w, v1 * h), QPointF(u2 * w, v2 * h))
        t = transformation_affine(source, (poly[0], poly[1], poly[2]))
        if t is None:
            image = pix.toImage()
            u, v = uv[0]
            return QBrush(image.pixelColor(min(w - 1, int(u * w)), min(h - 1, int(v * h))))
        brosse = QBrush(pix)
        brosse.setTransform(t)
        return brosse

    @staticmethod
    def _ombre(a: tuple[float, float, float], b: tuple[float, float, float],
               c: tuple[float, float, float]) -> int:
        """L'assombrissement d'une face (0 à 255) selon son angle à la lumière,
        sa normale prise sur le triangle à l'écran (x, -y, profondeur)."""
        u = (b[0] - a[0], a[1] - b[1], b[2] - a[2])
        v = (c[0] - a[0], a[1] - c[1], c[2] - a[2])
        n = _norme((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))
        # Vers la caméra = profondeur ; lumière : (droite écran, haut, vers la caméra).
        eclairage = abs(n[0] * _L[1] * -1 + n[1] * _L[2] + n[2] * _L[0])
        return int(150 * (1 - min(1.0, 0.35 + 0.75 * eclairage)))

    def _ombre_au_sol(self, p: QPainter) -> None:
        cx, cy = self.width() / 2, self.height() * 0.52 + self.height() * 0.30 * self.zoom
        r = self.width() * 0.22 * self.zoom
        g = QRadialGradient(QPointF(cx, cy), r)
        g.setColorAt(0, QColor(0, 0, 0, 90))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.save()
        p.translate(cx, cy)
        p.scale(1.0, 0.22)
        p.translate(-cx, -cy)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.restore()

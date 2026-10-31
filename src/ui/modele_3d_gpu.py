"""Le rendu des modèles 3D sur la carte graphique (OpenGL), hors écran.

Ludo, 2026-10-31 : « la carte graphique travaille pas trop pour les animations
3D, mais surtout le processeur ». Mesuré le même jour : le rendu QPainter
(`modele_3d.Modele3D._peindre`, une brosse par triangle) prenait 22 à 66 ms
par image pour une image toutes les 16 ms (Harry de HP3 : 1 984 faces,
~15 images/s, un cœur plein) ; poser les os n'en prenait que 1,5 à 4.

Ici, les triangles, leurs textures et la projection passent par OpenGL : le
processeur ne fait plus que poser les os et envoyer les points. Le dessin se
fait dans une image HORS ÉCRAN (contexte partagé, `QOffscreenSurface`, FBO
multiéchantillonné), relue puis posée par le `paintEvent` du widget habituel :
pas de `QOpenGLWidget`, qui change la façon dont toute la fenêtre se compose
(fenêtre native recréée au premier affichage, transparence et effets
d'opacité à part).

Repli sur QPainter, en silence, quand OpenGL 2.1 ne s'ouvre pas (machine
virtuelle sans pilote : l'exe n'embarque pas le Mesa logiciel, règle 94), sur
les plateformes `offscreen` et `minimal` (les tests), ou après la moindre
erreur de dessin. Le rendu reste celui de QPainter (même projection, même
ombrage plat, mêmes drapeaux de matériau) ; l'image y gagne un anticrénelage
4× et le filtrage des textures.
"""

import logging
from array import array
from itertools import chain

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QGuiApplication, QImage, QOffscreenSurface, QOpenGLContext, QSurfaceFormat

from src.core import maillages_ue1
from src.core.maillages_ue1 import Maillage

log = logging.getLogger(__name__)

# Les constantes OpenGL dont on a besoin (PyQt6 ne les expose pas).
_GL_FLOAT = 0x1406
_GL_TRIANGLES = 0x0004
_GL_DEPTH_TEST = 0x0B71
_GL_CULL_FACE = 0x0B44
_GL_BLEND = 0x0BE2
_GL_MULTISAMPLE = 0x809D
_GL_COLOR_BUFFER_BIT = 0x4000
_GL_DEPTH_BUFFER_BIT = 0x0100
_GL_ONE = 1
_GL_ONE_MINUS_SRC_ALPHA = 0x0303
_GL_BACK = 0x0405
_GL_CW = 0x0900
_GL_LEQUAL = 0x0203

_SANS_TEXTURE = (150 / 255, 140 / 255, 125 / 255, 1.0)

_SOMMETS = """#version 120
attribute vec3 a_pos;
attribute vec2 a_uv;
uniform vec4 u_rot;      // cos et sin du lacet, cos et sin du tangage
uniform vec3 u_centre;
uniform vec4 u_cadre;    // échelle, souffle, distance, focale
uniform vec4 u_ecran;    // centre x, centre y, largeur, hauteur (pixels logiques)
varying vec2 v_uv;
varying vec3 v_vue;
void main() {
    vec3 p = (a_pos - u_centre) * u_cadre.x;
    p.z += u_cadre.y;
    float xa = p.x * u_rot.x - p.y * u_rot.y;
    float ya = p.x * u_rot.y + p.y * u_rot.x;
    float za = p.z * u_rot.z + xa * u_rot.w;
    float xb = xa * u_rot.z - p.z * u_rot.w;
    float w = u_cadre.z - xb;
    float sx = u_ecran.x + ya * u_cadre.w / w;
    float sy = u_ecran.y - za * u_cadre.w / w;
    vec2 ndc = vec2(sx / u_ecran.z * 2.0 - 1.0, 1.0 - sy / u_ecran.w * 2.0);
    gl_Position = vec4(ndc * w, -xb * 0.3 * w, w);
    v_uv = a_uv;
    // Le repère de l'ombrage de QPainter : x et y écran, profondeur.
    v_vue = vec3(sx, -sy, xb);
}
"""

_PIXELS = """#version 120
uniform sampler2D u_tex;
uniform vec4 u_couleur;  // sans texture
uniform vec4 u_mode;     // texture, masque, ombrage, opacité
uniform vec3 u_lumiere;
varying vec2 v_uv;
varying vec3 v_vue;
void main() {
    vec4 c = u_mode.x > 0.5 ? texture2D(u_tex, v_uv) : u_couleur;
    if (u_mode.y > 0.5 && c.a < 0.5) discard;
    vec3 n = normalize(cross(dFdx(v_vue), dFdy(v_vue)));
    float e = abs(-n.x * u_lumiere.y + n.y * u_lumiere.z + n.z * u_lumiere.x);
    float ombre = 150.0 * (1.0 - min(1.0, 0.35 + 0.75 * e)) / 255.0;
    vec3 rgb = c.rgb * (1.0 - ombre * u_mode.z);
    float a = (u_mode.y > 0.5 ? 1.0 : c.a) * u_mode.w;
    gl_FragColor = vec4(rgb * a, a);
}
"""


class _Contexte:
    """Le contexte OpenGL du launcher, partagé par toutes les visionneuses."""

    def __init__(self) -> None:
        self.ctx = QOpenGLContext()
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setDepthBufferSize(24)
        self.ctx.setFormat(fmt)
        if not self.ctx.create() or self.ctx.isOpenGLES():
            raise RuntimeError("pas de contexte OpenGL de bureau")
        self.surface = QOffscreenSurface()
        self.surface.setFormat(self.ctx.format())
        self.surface.create()
        if not self.surface.isValid() or not self.ctx.makeCurrent(self.surface):
            raise RuntimeError("surface hors écran refusée")
        from PyQt6.QtOpenGL import QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile
        profil = QOpenGLVersionProfile()
        profil.setVersion(2, 1)
        self.f = QOpenGLVersionFunctionsFactory.get(profil, self.ctx)
        if self.f is None or not self.f.initializeOpenGLFunctions():
            self.ctx.doneCurrent()
            raise RuntimeError("OpenGL 2.1 absent")
        log.info("Modèles 3D sur la carte graphique : %s", self.f.glGetString(0x1F01))
        self.ctx.doneCurrent()


_CONTEXTE: _Contexte | None = None
_ESSAYE = False


def _contexte() -> _Contexte | None:
    global _CONTEXTE, _ESSAYE
    if not _ESSAYE:
        _ESSAYE = True
        if QGuiApplication.platformName() in ("offscreen", "minimal"):
            return None
        try:
            _CONTEXTE = _Contexte()
        except (RuntimeError, ImportError, AttributeError) as exc:
            log.info("Modèles 3D sur le processeur : %s", exc)
    return _CONTEXTE


class RenduGPU:
    """Les triangles d'UN modèle sur la carte graphique, pour une visionneuse.

    Chaque coin de triangle est un sommet à part (ses UV diffèrent d'une face
    à l'autre) : les UV partent une fois, les points à chaque image."""

    def __init__(self, contexte: _Contexte) -> None:
        self._c = contexte
        self._modele: Maillage | None = None
        self._textures_source: dict[str, QImage] = {}
        self._pret = False
        self._programme = None
        self._uv = None
        self._points = None
        self._textures: dict[str, object] = {}
        self._groupes: list[tuple[int, int, int]] = []   # (matériau, premier coin, nombre)
        self._coins = array("i")
        self._envoyes: object = None      # les derniers points envoyés
        self._fbo = None
        self._loc: dict[str, int] = {}

    @classmethod
    def creer(cls) -> RenduGPU | None:
        contexte = _contexte()
        return cls(contexte) if contexte is not None else None

    def poser(self, modele: Maillage | None, textures: dict[str, QImage]) -> None:
        """Un nouveau modèle : ses tampons partiront au prochain dessin."""
        self.liberer()
        self._modele = modele
        self._textures_source = dict(textures)

    def liberer(self) -> None:
        if not (self._pret or self._fbo is not None):
            return
        if self._c.ctx.makeCurrent(self._c.surface):
            for objet in (self._uv, self._points):
                if objet is not None:
                    objet.destroy()
            for texture in self._textures.values():
                texture.destroy()
            self._fbo = None
            self._c.ctx.doneCurrent()
        self._uv = self._points = None
        self._textures = {}
        self._envoyes = None
        self._pret = False

    # ── Préparer (contexte courant) ──

    def _preparer(self, modele: Maillage) -> None:
        from PyQt6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture
        if self._programme is None:
            programme = QOpenGLShaderProgram()
            if not (programme.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _SOMMETS)
                    and programme.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _PIXELS)
                    and programme.link()):
                raise RuntimeError(f"shaders refusés : {programme.log()}")
            self._programme = programme
            self._loc = {nom: programme.uniformLocation(nom) for nom in
                         ("u_rot", "u_centre", "u_cadre", "u_ecran", "u_tex", "u_couleur", "u_mode", "u_lumiere")}
            self._loc["a_pos"] = programme.attributeLocation("a_pos")
            self._loc["a_uv"] = programme.attributeLocation("a_uv")
        # Opaques d'abord, translucides ensuite (sans écrire la profondeur).
        par_materiau: dict[int, list[maillages_ue1.Face]] = {}
        for face in modele.faces:
            par_materiau.setdefault(face.materiau, []).append(face)
        ordre = sorted(par_materiau, key=lambda m: bool(modele.materiaux[m].drapeaux & maillages_ue1.PF_TRANSLUCIDE))
        coins, uv, self._groupes = array("i"), array("f"), []
        for m in ordre:
            faces = par_materiau[m]
            self._groupes.append((m, len(coins), 3 * len(faces)))
            for face in faces:
                coins.extend(face.sommets)
                for u, v in face.uv:
                    uv.extend((u, v))
        self._coins = coins
        self._uv = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._uv.create()
        self._uv.bind()
        self._uv.allocate(uv, len(uv) * 4)
        self._points = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._points.setUsagePattern(QOpenGLBuffer.UsagePattern.StreamDraw)
        self._points.create()
        self._points.bind()
        self._points.allocate(len(coins) * 3 * 4)
        self._points.release()
        for nom, image in self._textures_source.items():
            texture = QOpenGLTexture(image.convertToFormat(QImage.Format.Format_RGBA8888))
            texture.setMinMagFilters(QOpenGLTexture.Filter.LinearMipMapLinear, QOpenGLTexture.Filter.Linear)
            texture.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
            self._textures[nom] = texture
        self._pret = True

    def _cadre(self, taille: QSize) -> None:
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        if self._fbo is not None and self._fbo.size() == taille:
            return
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        fmt.setSamples(4)
        self._fbo = QOpenGLFramebufferObject(taille, fmt)

    # ── Dessiner ──

    def image(self, points: tuple[maillages_ue1.Point, ...], camera, largeur: int, hauteur: int,
              dpr: float, lumiere: tuple[float, float, float]) -> QImage | None:
        """Le modèle posé sur fond transparent, ou None (rien à montrer)."""
        modele = self._modele
        if modele is None or largeur <= 0 or hauteur <= 0:
            return None
        c = self._c
        if not c.ctx.makeCurrent(c.surface):
            raise RuntimeError("contexte OpenGL perdu")
        try:
            if not self._pret:
                self._preparer(modele)
            taille = QSize(max(1, round(largeur * dpr)), max(1, round(hauteur * dpr)))
            self._cadre(taille)
            self._fbo.bind()
            self._dessiner(modele, points, camera, largeur, hauteur, taille, lumiere)
            self._fbo.release()
            image = self._fbo.toImage()
        finally:
            c.ctx.doneCurrent()
        image.setDevicePixelRatio(dpr)
        return image

    def _dessiner(self, modele: Maillage, points, camera, largeur: int, hauteur: int,
                  taille: QSize, lumiere) -> None:
        f, p, loc = self._c.f, self._programme, self._loc
        f.glViewport(0, 0, taille.width(), taille.height())
        f.glClearColor(0.0, 0.0, 0.0, 0.0)
        f.glClear(_GL_COLOR_BUFFER_BIT | _GL_DEPTH_BUFFER_BIT)
        f.glEnable(_GL_DEPTH_TEST)
        f.glDepthFunc(_GL_LEQUAL)
        f.glEnable(_GL_MULTISAMPLE)
        f.glEnable(_GL_BLEND)
        f.glBlendFunc(_GL_ONE, _GL_ONE_MINUS_SRC_ALPHA)
        # L'écran a l'axe y vers le bas : une face vue de face y tourne dans le
        # sens horaire (l'aire positive de `_peindre`).
        f.glFrontFace(_GL_CW)
        f.glCullFace(_GL_BACK)
        p.bind()
        self._points.bind()
        # Les mêmes points qu'à l'image d'avant (un modèle de HP5-HP6, sans
        # mouvement) : rien à renvoyer.
        if points is not self._envoyes:
            sommets = array("f", chain.from_iterable(points[i] for i in self._coins))
            self._points.write(0, sommets, len(sommets) * 4)
            self._envoyes = points
        p.enableAttributeArray(loc["a_pos"])
        p.setAttributeBuffer(loc["a_pos"], _GL_FLOAT, 0, 3)
        self._uv.bind()
        p.enableAttributeArray(loc["a_uv"])
        p.setAttributeBuffer(loc["a_uv"], _GL_FLOAT, 0, 2)
        p.setUniformValue(loc["u_rot"], camera.cl, camera.sl, camera.ct, camera.st)
        p.setUniformValue(loc["u_centre"], *camera.centre)
        p.setUniformValue(loc["u_cadre"], camera.k, camera.souffle, camera.distance, camera.focale)
        p.setUniformValue(loc["u_ecran"], camera.ox, camera.oy, float(largeur), float(hauteur))
        p.setUniformValue(loc["u_lumiere"], *lumiere)
        p.setUniformValue(loc["u_tex"], 0)
        p.setUniformValue(loc["u_couleur"], *_SANS_TEXTURE)
        for m, premier, nombre in self._groupes:
            mat = modele.materiaux[m]
            texture = self._textures.get(mat.texture)
            translucide = bool(mat.drapeaux & maillages_ue1.PF_TRANSLUCIDE)
            masque = bool(mat.drapeaux & maillages_ue1.PF_MASQUE)
            if mat.drapeaux & maillages_ue1.PF_DEUX_FACES:
                f.glDisable(_GL_CULL_FACE)
            else:
                f.glEnable(_GL_CULL_FACE)
            f.glDepthMask(0 if translucide else 1)
            if texture is not None:
                texture.bind(0)
            p.setUniformValue(loc["u_mode"], 1.0 if texture is not None else 0.0, 1.0 if masque else 0.0,
                              0.0 if masque else 1.0, 0.55 if translucide else 1.0)
            f.glDrawArrays(_GL_TRIANGLES, premier, nombre)
            if texture is not None:
                texture.release()
        f.glDepthMask(1)
        p.disableAttributeArray(loc["a_pos"])
        p.disableAttributeArray(loc["a_uv"])
        self._uv.release()
        p.release()

"""La visionneuse de modèles 3D des Personnages et du Bestiaire."""

import pytest

pytest.importorskip("pytestqt")

from PyQt6.QtCore import QPointF, QSize  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402

from src.core import maillages_ue1 as mu  # noqa: E402
from src.ui.modele_3d import (  # noqa: E402
    LACET_DEPART, TANGAGE_MAX, Modele3D, mouvement_de_repos, transformation_affine,
)


def _carre() -> mu.Maillage:
    """Les deux faces avant d'un carré debout, face à la caméra (+X), à deux côtés."""
    points = ((0.0, -10.0, 0.0), (0.0, 10.0, 0.0), (0.0, 10.0, 20.0), (0.0, -10.0, 20.0))
    uv = ((0.0, 1.0), (1.0, 1.0), (1.0, 0.0))
    faces = (mu.Face((0, 1, 2), uv, 0), mu.Face((0, 2, 3), ((0.0, 1.0), (1.0, 0.0), (0.0, 0.0)), 0))
    return mu.Maillage(points, faces, (mu.Materiau("rouge", mu.PF_DEUX_FACES),))


def _rouge() -> QImage:
    img = QImage(4, 4, QImage.Format.Format_ARGB32)
    img.fill(QColor(200, 0, 0))
    return img


def test_transformation_affine():
    source = (QPointF(0, 0), QPointF(1, 0), QPointF(0, 1))
    cible = (QPointF(10, 10), QPointF(30, 10), QPointF(10, 50))
    t = transformation_affine(source, cible)
    assert t is not None
    for s, c in zip(source, cible, strict=True):
        assert t.map(s) == c
    assert transformation_affine((QPointF(0, 0),) * 3, cible) is None


def test_le_modele_se_dessine_texture(qtbot):
    v = Modele3D()
    qtbot.addWidget(v)
    v.poser(_carre(), {"rouge": _rouge()})
    image = v.rendu(QSize(120, 160), 1.0)
    couleurs = {image.pixelColor(x, y).name() for x in range(0, 120, 4) for y in range(0, 160, 4)}
    assert any(c[1:3] > "60" and c[3:] < "202020" for c in couleurs), couleurs   # du rouge, ombré
    assert image.pixelColor(0, 0).alpha() == 0                                  # fond transparent


def test_sans_modele_rien_ne_tourne(qtbot, monkeypatch):
    from src.ui import modele_3d
    # Offscreen, l'application n'est pas toujours déjà « active » au premier show.
    monkeypatch.setattr(modele_3d, "_application_active", lambda: True)
    v = Modele3D()
    qtbot.addWidget(v)
    v.show()
    v.poser(None)
    assert not v._minuteur.isActive()
    v.poser(_carre())
    assert v._minuteur.isActive()
    v.hide()
    assert not v._minuteur.isActive()


def test_animer_rejoue_un_mouvement_du_jeu(qtbot):
    from tests.test_maillages_ue1 import _Paquet, animation_brute, modele_brut
    p = _Paquet(modele_brut(), animation_brute())
    m, a = mu.lire(p, "x"), mu.lire_animation(p, "x")
    v = Modele3D()
    qtbot.addWidget(v)
    v.poser(m, {}, a)
    assert v.mouvements() == ["walk"] and v.mouvement is None
    assert not v.animer("inconnu") and v.mouvement is None
    assert v.animer("walk") and v.mouvement == "walk"
    v._depart -= 0.1                                 # trois images plus tard : le quart de tour
    assert v.points_du_moment()[2] == pytest.approx((0, -10, 0), abs=1e-3)
    assert v.animer(None) and v.mouvement is None
    assert v.points_du_moment()[2] == pytest.approx(m.points[2])
    v.poser(_carre())                                # un modèle sans mouvement
    assert v.mouvements() == [] and not v.animer("walk")


def test_mouvement_de_repos():
    def mouvement(nom: str, images: int) -> mu.Mouvement:
        return mu.Mouvement(nom, "None", images / 30, images, (), ())
    assert mouvement_de_repos(mu.Animation("a", ())) is None
    assert mouvement_de_repos(mu.Animation("a", (mouvement("Jump", 9), mouvement("Idle", 90)))) == "Idle"
    assert mouvement_de_repos(mu.Animation("a", (mouvement("eye_pos", 1), mouvement("roar", 20)))) == "roar"
    assert mouvement_de_repos(mu.Animation("a", (mouvement("eye_pos", 1),))) == "eye_pos"


def test_tourner_borne_le_tangage_et_double_clic_revient(qtbot):
    v = Modele3D()
    qtbot.addWidget(v)
    v.poser(_carre())
    v.tourner(400, 90)
    assert v.lacet == pytest.approx((LACET_DEPART + 400) % 360)
    assert v.tangage == TANGAGE_MAX
    v.mouseDoubleClickEvent(None)
    assert (v.tangage, v.zoom) == (8.0, 1.0)


def test_rien_ne_tourne_quand_le_launcher_n_est_plus_actif(qtbot, monkeypatch):
    """Audit du 2026-10-29 : un QTimer de 16 ms tournait tant que la page était
    visible, launcher passé derrière une autre fenêtre compris (98 % d'un cœur).
    L'état est simulé dans le MODULE, jamais sur la classe Qt (règle 12)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication

    from src.ui import modele_3d
    v = Modele3D()
    qtbot.addWidget(v)
    v.show()
    v.poser(_carre())
    assert v._minuteur.isActive()
    monkeypatch.setattr(modele_3d, "_application_active", lambda: False)
    QGuiApplication.instance().applicationStateChanged.emit(Qt.ApplicationState.ApplicationInactive)
    assert not v._minuteur.isActive()
    monkeypatch.setattr(modele_3d, "_application_active", lambda: True)
    QGuiApplication.instance().applicationStateChanged.emit(Qt.ApplicationState.ApplicationActive)
    assert v._minuteur.isActive()


# ─── La carte graphique (2026-10-31) ───

def test_offscreen_dessine_sur_le_processeur(qtbot):
    """Les tests tournent offscreen : pas d'OpenGL, le rendu QPainter, sans erreur."""
    from src.ui import modele_3d_gpu
    assert modele_3d_gpu.RenduGPU.creer() is None
    v = Modele3D()
    qtbot.addWidget(v)
    v.resize(120, 160)
    v.poser(_carre(), {"rouge": _rouge()})
    v.grab()
    assert v._gpu is None and v._gpu_essaye


class _GpuQuiCasse:
    def __init__(self):
        self.poses, self.libere = [], False

    def poser(self, modele, textures):
        self.poses.append(modele)

    def image(self, *args):
        raise RuntimeError("pilote perdu")

    def liberer(self):
        self.libere = True


def test_une_erreur_de_la_carte_graphique_rend_la_main_au_processeur(qtbot, monkeypatch):
    from src.ui import modele_3d_gpu
    gpu = _GpuQuiCasse()
    monkeypatch.setattr(modele_3d_gpu.RenduGPU, "creer", classmethod(lambda cls: gpu))
    v = Modele3D()
    qtbot.addWidget(v)
    v.resize(120, 160)
    v.poser(_carre(), {"rouge": _rouge()})
    image = v.grab().toImage()
    assert gpu.poses and gpu.libere and v._gpu is None, "QPainter pour de bon"
    assert any(image.pixelColor(x, y).red() > 60 and image.pixelColor(x, y).green() < 40
               for x in range(0, 120, 4) for y in range(0, 160, 4)), "le modèle est quand même dessiné"


def test_la_carte_graphique_recoit_chaque_nouveau_modele(qtbot, monkeypatch):
    from src.ui import modele_3d_gpu
    gpu = _GpuQuiCasse()
    gpu.image = lambda *args: None          # rien à montrer : QPainter dessine
    monkeypatch.setattr(modele_3d_gpu.RenduGPU, "creer", classmethod(lambda cls: gpu))
    v = Modele3D()
    qtbot.addWidget(v)
    v.poser(_carre())
    v.grab()
    v.poser(None)
    assert gpu.poses[-1] is None and v._gpu is gpu


def test_au_repos_la_rotation_passe_a_30_images(qtbot):
    """Audit du 2026-10-31 : la visionneuse ouverte prenait la moitié d'un cœur.
    Au repos, 30 images/s à la même vitesse ; un geste rend les 60."""
    from src.ui import modele_3d
    v = Modele3D()
    qtbot.addWidget(v)
    v.poser(_carre())
    v._repos = modele_3d._ATTENTE_REPOS
    avant = v.lacet
    v._avancer()
    assert v._minuteur.interval() == 2 * modele_3d._INTERVALLE
    assert v.lacet == pytest.approx((avant + 2 * modele_3d._ROTATION_REPOS) % 360)
    v._elan = (3.0, 0.0)
    v._avancer()
    assert v._minuteur.interval() == modele_3d._INTERVALLE

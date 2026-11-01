"""Le fond de l'accueil sur la carte graphique (`fond_gpu`), derrière son interrupteur."""

import pytest
from PyQt6.QtCore import QSize

from src.core.config import ASSETS_DIR
from src.ui import fond_gpu

pytestmark = pytest.mark.skipif(not fond_gpu.QUICK_DISPONIBLE, reason="Qt Quick absent")


def test_allume_par_defaut_sous_windows_seulement(monkeypatch):
    monkeypatch.delenv("ACCIO_FOND_GPU", raising=False)
    monkeypatch.setattr(fond_gpu.sys, "platform", "win32")
    assert fond_gpu.actif()
    monkeypatch.setattr(fond_gpu.sys, "platform", "linux")
    assert not fond_gpu.actif()
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    assert fond_gpu.actif()
    monkeypatch.setattr(fond_gpu.sys, "platform", "win32")
    monkeypatch.setenv("ACCIO_FOND_GPU", "0")
    assert not fond_gpu.actif()


def test_une_fenetre_avec_le_fond_gpu(make_window, monkeypatch):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    win = make_window()
    assert isinstance(win._detail._bg, fond_gpu.FondGPU)
    assert isinstance(win._particles, fond_gpu.ParticulesGPU)
    assert isinstance(win._carousel._gpu, fond_gpu.EtoilesGPU)
    win._carousel.select_next()
    win._particles.apply_season("noel")


def test_la_scene_charge_et_expose_sa_sortie_video(qtbot):
    fond = fond_gpu.FondGPU()
    qtbot.addWidget(fond)
    assert not fond.errors()
    assert fond.sortie_video() is not None


def test_les_voiles_viennent_du_fournisseur(qtbot):
    fond = fond_gpu.FondGPU()
    qtbot.addWidget(fond)
    fond.resize(800, 500)
    fond.invalidate_cache()
    ident = fond._racine.property("voiles").toString().removeprefix("image://accio/")
    image, taille = fond._fournisseur.requestImage(ident, QSize())
    assert not image.isNull() and taille.width() >= 800


def test_un_bandeau_trop_petit_est_etendu_une_illustration_16_9_non(qtbot, tmp_path):
    from PyQt6.QtGui import QColor, QImage
    petit = QImage(1920, 620, QImage.Format.Format_RGB32)
    petit.fill(QColor(0, 0, 255))
    petit.save(str(tmp_path / "bandeau.png"))
    fond = fond_gpu.FondGPU()
    qtbot.addWidget(fond)
    fond.resize(1400, 860)
    fond.set_image(tmp_path / "bandeau.png")
    assert fond._racine.property("etendu")
    fond.set_image(ASSETS_DIR / "backgrounds" / "hp4_bg.jpg")
    assert not fond._racine.property("etendu")


@pytest.mark.parametrize("jeu", ["hp1", "hp2", "hp3", "hp4", "hp5", "hp6", "hp7a", "hp7b"])
@pytest.mark.parametrize(("w", "h", "dpr"), [(1400, 620, 1.25), (1920, 820, 1.0), (2560, 1100, 1.0)])
def test_les_fonds_du_depot_gardent_le_cadrage_d_origine(jeu, w, h, dpr):
    """Ludo, 2026-11-02 : en étendu, l'image remontait et laissait du noir dessous.
    Agrandis, les huit fonds couvrent la fiche au cadrage centré de la 1.3.1,
    de la fenêtre par défaut à 125 % jusqu'à un écran 2560 × 1440 plein."""
    from PyQt6.QtGui import QImageReader

    from src.ui.background_widget import BackgroundWidget, doit_etendre
    taille = QImageReader(str(ASSETS_DIR / "backgrounds" / f"{jeu}_bg.jpg")).size()
    assert not doit_etendre(taille.width(), taille.height(), w, h, dpr, BackgroundWidget.MAX_SCALE)


def test_l_etendu_prolonge_l_image_dans_son_flou_pas_dans_du_noir(qtbot, tmp_path):
    """Sous le bandeau, la copie floue de l'image, plus une couleur unie : l'image
    est verte à gauche et bleue à droite, une couleur unie ne garderait pas les deux."""
    from PyQt6.QtGui import QColor, QImage, QPainter
    petit = QImage(1920, 620, QImage.Format.Format_RGB32)
    petit.fill(QColor(0, 0, 255))
    p = QPainter(petit)
    p.fillRect(0, 0, 960, 620, QColor(0, 255, 0))
    p.end()
    petit.save(str(tmp_path / "bandeau.png"))
    fond = fond_gpu.FondGPU()
    qtbot.addWidget(fond)
    fond.resize(1400, 860)
    fond.invalidate_cache()
    fond.set_image(tmp_path / "bandeau.png")
    fond.show()
    assert fond._racine.property("etendu")
    qtbot.waitUntil(lambda: fond.grabFramebuffer().pixelColor(1000, 300).blue() > 60, timeout=5000)
    rendu = fond.grabFramebuffer()
    # Les voiles assombrissent la gauche (sous le texte) : on compare les teintes, pas les niveaux.
    gauche, droite = rendu.pixelColor(400, 600), rendu.pixelColor(1100, 600)
    assert (gauche.green() - gauche.blue()) > (droite.green() - droite.blue()) + 15, (gauche.name(), droite.name())


def test_meme_interface_que_l_ancien_fond(qtbot):
    from src.ui.background_widget import BackgroundWidget
    publiques = {n for n in vars(BackgroundWidget) if not n.startswith("_") and n not in ("paintEvent",)}
    manquantes = {n for n in publiques if not hasattr(fond_gpu.FondGPU, n)}
    assert not manquantes


def test_les_particules_vivent_dans_la_scene(qtbot):
    from src.core.season import profil
    fond = fond_gpu.FondGPU()
    qtbot.addWidget(fond)
    fond.resize(800, 500)
    particules = fond_gpu.ParticulesGPU(fond)
    particules.apply_season("noel")
    liste = fond._racine.property("particules")
    assert len(liste) == profil("noel").nombre
    assert {p["forme"] for p in liste} >= {"flocon", "point"}
    particules.hide()
    assert not fond._racine.property("particulesVisibles")


def test_les_formes_sont_peintes_par_les_gestes_de_l_almanach():
    for forme in ("flocon", "enveloppe", "flamme"):
        image = fond_gpu._image_forme(f"{forme}/240,220,180/6.00")
        assert not image.isNull()
        assert any(image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height()))


def test_les_etoiles_du_carrousel_avancent_sans_repeindre_la_bande(qtbot, monkeypatch):
    from src.ui.carousel import Carousel
    from tests.test_carousel import _FakeManager, _make_game
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    c = Carousel([_make_game("a"), _make_game("b")], _FakeManager())
    qtbot.addWidget(c)
    c.resize(900, 192)
    c.show()
    assert c._gpu is not None and not c._gpu.errors()
    assert c._gpu.geometry() == c.rect()
    assert len(c._gpu._racine.property("etoiles")) == len(c._stars)
    repeint = []
    monkeypatch.setattr(c, "update", lambda *a: repeint.append(a))
    c._tick_stars()
    c._tick_stars()
    assert c._star_phase > 0
    assert c._gpu._racine.property("phase") == pytest.approx(c._star_phase)
    assert not repeint


def test_sans_la_scene_les_etoiles_restent_peintes_par_le_carrousel(qtbot, monkeypatch):
    from src.ui.carousel import Carousel
    from tests.test_carousel import _FakeManager, _make_game
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    monkeypatch.setattr(fond_gpu.EtoilesGPU, "valide", lambda self: False)
    c = Carousel([_make_game("a")], _FakeManager())
    qtbot.addWidget(c)
    assert c._gpu is None

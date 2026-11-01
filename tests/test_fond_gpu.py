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


def test_un_bandeau_trop_petit_est_etendu_une_illustration_16_9_non(qtbot):
    fond = fond_gpu.FondGPU()
    qtbot.addWidget(fond)
    fond.resize(1400, 860)
    fond.set_image(ASSETS_DIR / "backgrounds" / "hp1_bg.jpg")     # 1920 × 620
    assert fond._racine.property("etendu")
    fond.set_image(ASSETS_DIR / "backgrounds" / "hp4_bg.jpg")     # 1500 × 844
    assert not fond._racine.property("etendu")


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

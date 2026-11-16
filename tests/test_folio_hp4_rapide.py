"""Le folio de HP4 sous la demi-seconde (2026-11-16) : la carte décodée à la taille montrée, la
palette et le rognage sans boucle Python sur les pixels."""

import random
import struct

import pytest

from src.core import folio_hp4, images_ea


def test_la_palette_passe_par_des_tables_memes_octets():
    """`image_7b` : 14 ms par carte en joignant pixel par pixel, mêmes octets par `translate`."""
    hasard = random.Random(4)
    largeur, hauteur, nombre = 16, 8, 200
    indices = bytes(hasard.randrange(nombre) for _ in range(largeur * hauteur))
    palette = hasard.randbytes(4 * nombre)
    tete = bytes([0x7B]) + (16 + len(indices)).to_bytes(3, "little") + struct.pack("<HH", largeur, hauteur) + bytes(8)
    bloc_palette = bytes([0x2A, 0, 0, 0]) + struct.pack("<H", nombre) + bytes(10) + palette
    lue = folio_hp4.image_7b(tete + indices + bloc_palette, 0)
    assert lue == (largeur, hauteur, b"".join(palette[4 * i:4 * i + 4] for i in indices))


def test_une_vignette_ne_decode_pas_la_carte_entiere(monkeypatch, tmp_path):
    """Une case de 60 px décodait les 512 px de la carte (et la mémoire n'en gardait que 8)."""
    demandes = []
    monkeypatch.setattr(folio_hp4, "_flux_cartes", lambda system, flux: (b"flux", {"carte_01": 0, "carte_02": 4}))
    monkeypatch.setattr(images_ea, "image", lambda donnees, q, cote_max=128: demandes.append((q, cote_max)) or
                        (cote_max, cote_max, bytes(4)))
    folio_hp4._image_carte.cache_clear()
    jeu = folio_hp4.JeuCartes((1, "Jeu {}"), "carte", "f", (0, 1), 2)
    assert folio_hp4.image_carte(tmp_path, jeu, 0, 64) == (64, 64, bytes(4))
    folio_hp4.image_carte(tmp_path, jeu, 0, 64)
    folio_hp4.image_carte(tmp_path, jeu, 1, 64)
    folio_hp4.image_carte(tmp_path, jeu, 0)
    assert demandes == [(0, 64), (4, 64), (0, 512)], "à la taille demandée, une fois par taille"
    folio_hp4._image_carte.cache_clear()


pytest.importorskip("pytestqt")


def test_le_rognage_rend_le_cadre_du_calcul_pixel_par_pixel(qapp):
    from src.ui.folio_page import _cadre_opaque
    hasard = random.Random(9)
    for _ in range(60):
        largeur, hauteur = hasard.randrange(1, 24), hasard.randrange(1, 24)
        alphas = [hasard.choice((0, 0, 0, 16, 17, 255)) for _ in range(largeur * hauteur)]
        pixels = b"".join(bytes((1, 2, 3, a)) for a in alphas)
        gauche = hasard.randrange(largeur)
        droite = hasard.randrange(gauche, largeur + 1)
        opaques = [(i % largeur, i // largeur) for i in range(largeur * hauteur)
                   if alphas[i] > 16 and gauche <= i % largeur < droite]
        attendu = None
        if opaques:
            xs, ys = [p[0] for p in opaques], [p[1] for p in opaques]
            attendu = (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
        assert _cadre_opaque(pixels, largeur, hauteur, gauche, droite) == attendu


def test_l_embleme_d_une_fiche_se_peint_une_fois(qapp, monkeypatch):
    from PyQt6.QtCore import QSize

    from src.core import encyclopedie
    from src.ui import encyclopedie_page
    peints = []
    vrai = encyclopedie_page.pixmap_icone
    monkeypatch.setattr(encyclopedie_page, "pixmap_icone", lambda *a, **k: peints.append(a) or vrai(*a, **k))
    encyclopedie_page._embleme.cache_clear()
    for _ in range(26):
        encyclopedie_page.embleme(encyclopedie.PERSONNAGES, QSize(52, 64), 1.0)
    assert len(peints) == 1
    encyclopedie_page._embleme.cache_clear()

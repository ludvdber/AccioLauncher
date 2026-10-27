"""Cinématiques d'EA : l'index des images complètes et la copie qui part de la bonne."""

import struct

from src.core import vp6_ea


def _bloc(nom: bytes, contenu: bytes) -> bytes:
    return nom + struct.pack("<I", 8 + len(contenu)) + contenu


def _cinematique(tmp_path, images: str):
    """`images` : K pour une image complète, F pour une partielle ; 10 images/s."""
    entete = _bloc(b"MVhd", b"vp60" + struct.pack("<HHIIII", 64, 64, len(images), 99, 10, 1))
    corps = b"".join(_bloc(b"MV0K" if c == "K" else b"MV0F", bytes([i]) * 4)
                     for i, c in enumerate(images))
    chemin = tmp_path / "clip.vp6"
    chemin.write_bytes(entete + corps)
    return chemin, len(entete)


def test_index_des_images_completes(tmp_path):
    chemin, entete = _cinematique(tmp_path, "KFFFKFFFFK")
    index = vp6_ea.indexer(chemin)
    assert index is not None
    assert index.nombre == 10 and index.duree_ms == 1000
    assert [n for n, _ in index.completes] == [0, 4, 9]
    assert index.completes[0][1] == entete


def test_la_copie_part_de_l_image_complete_d_avant(tmp_path):
    chemin, _ = _cinematique(tmp_path, "KFFFKFFFFK")
    index = vp6_ea.indexer(chemin)
    copie = tmp_path / "copie.vp6"
    assert vp6_ea.copie_depuis(chemin, index, 750, copie) == 400
    lue = vp6_ea.indexer(copie)
    assert lue is not None and lue.nombre == 6, "l'en-tête compte les images restantes"
    assert [n for n, _ in lue.completes] == [0, 5]


def test_une_seule_image_complete_repart_du_debut(tmp_path):
    """HP7 et HP8 : une image complète, la première."""
    chemin, _ = _cinematique(tmp_path, "KFFFF")
    index = vp6_ea.indexer(chemin)
    assert vp6_ea.copie_depuis(chemin, index, 300, tmp_path / "copie.vp6") == 0


def test_autre_chose_qu_un_vp6_d_ea(tmp_path):
    autre = tmp_path / "x.vp6"
    autre.write_bytes(b"RIFF" + bytes(60))
    assert vp6_ea.indexer(autre) is None
    assert vp6_ea.indexer(tmp_path / "absent.vp6") is None

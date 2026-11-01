"""Les noms lisibles des mouvements des modèles 3D (`core/mouvements.py`)."""

import pytest

from src.core import mouvements


@pytest.mark.parametrize(("nom", "fr", "es", "en"), [
    ("breath", "Respirer", "Respirar", "Breath"),
    ("TalkLeft2", "Parler à gauche 2", "Hablar a la izquierda 2", "Talk left 2"),
    ("talkleft", "Parler à gauche", "Hablar a la izquierda", "Talk left"),
    ("Look_UpL45", "Regarder en haut à gauche 45°", "Mirar arriba a la izquierda 45°", "Look up left 45°"),
    ("WandCastFlipendoPerfect", "Lancer Flipendo parfait", "Lanzar Flipendo perfecto", "Cast Flipendo perfect"),
    ("land2run", "Atterrir puis courir", "Aterrizar y luego correr", "Land to run"),
    ("climb32NoTrans", "Grimper 32 sans transition", "Trepar 32 sin transición", "Climb 32 no transition"),
    ("RonPickupRat", "Ron ramasser rat", "Ron recoger rata", "Ron pickup rat"),
])
def test_traduit_mot_a_mot(nom, fr, es, en):
    assert mouvements.libelle(nom, "fr") == fr
    assert mouvements.libelle(nom, "es") == es
    assert mouvements.libelle(nom, "en") == en


@pytest.mark.parametrize("nom", ["mouth_rest", "eye_blink", "BrowLeftUp", "BlinkRight", "mbp", "Joy", "L"])
def test_le_visage_n_est_pas_un_mouvement(nom):
    assert mouvements.libelle(nom, "fr") is None


def test_un_mot_inconnu_reste_tel_quel():
    assert mouvements.libelle("Zorglub", "fr") == "Zorglub"
    assert mouvements.libelle("trot", "fr") == "Trotter", "pas de découpe en lettres seules"


def test_une_langue_sans_glossaire_garde_l_anglais():
    assert mouvements.libelle("StrafeRight", "de") == "Strafe right"

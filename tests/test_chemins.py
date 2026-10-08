"""Tests pour src/core/chemins.py : la barrière unique « chemin relatif sûr »."""

import pytest

from src.core.chemins import chemin_relatif_sur, est_peripherique, refus_de_chemin


class TestCheminsAcceptes:
    @pytest.mark.parametrize("chemin", [
        "HP1/System/Game.exe",
        "HP1\\System\\Game.exe",
        "game.exe",
        "Game/./data.txt",
        "Game/..bizarre/x",              # « .. » en tête d'un vrai nom
        "Game/System/",                  # dossier d'une archive zip
        "HP3/music/rescue_Cue86_SM_PoA_BuckbeakNightFlightS_Orch_edit.ogg",
        "Console/x.ini",                 # commence par « con » sans l'être
        "x" * 260,
    ])
    def test_accepte(self, chemin):
        assert refus_de_chemin(chemin) is None
        assert chemin_relatif_sur(chemin) is True


class TestCheminsRefuses:
    """Chaque refus vient d'une des quatre anciennes gardes (ACT-007) : toutes
    les appliquent désormais."""

    @pytest.mark.parametrize("chemin, raison", [
        ("", "vide"),
        ("HP1/x\x00.exe", "octet nul"),
        ("x" * 261, "trop long (261 caractères)"),
        ("C:\\Windows\\evil.exe", "deux-points"),
        ("D:/data/x", "deux-points"),
        ("a/C:x", "deux-points"),
        ("HP.exe:flux", "deux-points"),
        ("/etc/passwd", "absolu"),
        ("\\\\serveur\\partage\\x.dll", "absolu"),
        ("../evil.exe", "remontée"),
        ("..\\..\\Windows\\evil.dll", "remontée"),
        ("HP1/../../evil.exe", "remontée"),
        (".. /evil.dll", "remontée"),    # Windows retire l'espace finale
        ("a/... /x", "remontée"),
        (" ./x", "remontée"),
        ("   ", "remontée"),
        ("HP1/CON", "nom réservé"),
        ("HP1/nul.txt", "nom réservé"),
        ("COM1/x", "nom réservé"),
    ])
    def test_refuse(self, chemin, raison):
        assert refus_de_chemin(chemin) == raison
        assert chemin_relatif_sur(chemin) is False


def test_peripheriques():
    assert est_peripherique("CON") and est_peripherique("aux.int") and est_peripherique("Lpt9")
    assert not est_peripherique("Console") and not est_peripherique("com0")

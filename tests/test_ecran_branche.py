"""L'écran branché sur la puce du processeur alors qu'une vraie carte est là (1.3.6-beta.1).

Cas réel (2026-11-18) : GTX 970 + Intel HD 530, le câble sur la carte mère,
HP1/HP2 à 5 images/s. La décision se teste sans DXGI, sur des cartes fabriquées.
"""

import pytest

from src.core import ecran_branche
from src.core.ecran_branche import Carte, decider

GO = 1024 ** 3
INTEL = Carte("Intel(R) HD Graphics 530", 128 * 1024 ** 2, 1)
INTEL_SANS = Carte("Intel(R) HD Graphics 530", 128 * 1024 ** 2, 0)
GTX = Carte("NVIDIA GeForce GTX 970", 4 * GO, 0)
GTX_ECRAN = Carte("NVIDIA GeForce GTX 970", 4 * GO, 1)
BASIQUE = Carte("Microsoft Basic Render Driver", 0, 0, logicielle=True)
PARSEC = Carte("Parsec Virtual Display Adapter", 0, 1)


class TestDecision:
    def test_bureau_ecran_sur_la_puce_integree(self):
        assert decider([INTEL, GTX, BASIQUE], portable=False) == GTX

    def test_ecran_sur_la_carte_dediee(self):
        assert decider([INTEL_SANS, GTX_ECRAN, BASIQUE], portable=False) is None

    def test_un_ecran_sur_chaque_carte(self):
        assert decider([INTEL, GTX_ECRAN], portable=False) is None

    def test_portable(self):
        assert decider([INTEL, GTX], portable=True) is None

    def test_parsec_ignore(self):
        """Parsec porte un écran virtuel : il ne compte ni comme puce ni comme écran."""
        assert decider([PARSEC, GTX_ECRAN], portable=False) is None
        assert decider([PARSEC, INTEL, GTX], portable=False) == GTX

    def test_une_seule_carte(self):
        assert decider([INTEL], portable=False) is None
        assert decider([GTX_ECRAN, BASIQUE], portable=False) is None

    def test_une_carte_logicielle_n_est_pas_une_carte_dediee(self):
        assert decider([INTEL, Carte("Rendu", 8 * GO, 0, logicielle=True)], False) is None

    def test_la_liste_des_virtuelles_est_celle_des_deux_cartes(self):
        from src.core import diagnostic
        assert not diagnostic.plusieurs_cartes(
            ["NVIDIA GeForce GTX 970 · pilote 1", "Parsec Virtual Display Adapter · pilote 2"])
        assert diagnostic.carte_virtuelle(BASIQUE.nom) and diagnostic.carte_virtuelle(PARSEC.nom)

    def test_rien_hors_windows(self, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(ecran_branche, "_fil", None)
        ecran_branche.lancer()
        assert ecran_branche._fil is None


pytest.importorskip("pytestqt")

from tests.test_action_alerts import _disque, _prepare, panel  # noqa: E402,F401
from src.core.game_manager import GameState  # noqa: E402


class TestBandeau:
    @pytest.fixture
    def mal_branche(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.core.config.CONFIG_FILE_PATH", tmp_path / "config.json")
        monkeypatch.setattr(ecran_branche, "_resultat", GTX)
        monkeypatch.setattr(ecran_branche, "_fini", True)

    def test_l_alerte_nomme_la_carte_et_se_ferme(self, panel, monkeypatch, mal_branche):  # noqa: F811 (fixture importée)
        _disque(monkeypatch, 900_000)
        widget, manager, _game = _prepare(panel, GameState.INSTALLED)
        texte = widget._alert.text()
        assert not widget._alert.isHidden()
        assert "puce graphique du processeur" in texte and "GTX 970" in texte
        assert 'href="ecran_ignore"' in texte
        widget._alert._on_lien("ecran_ignore")
        assert manager.config.ecran_ignore == "NVIDIA GeForce GTX 970"
        assert "puce graphique" not in widget._alert.text()
        widget.refresh()
        assert "puce graphique" not in widget._alert.text(), "elle ne revient pas"

    def test_elle_revient_si_la_situation_change(self, panel, monkeypatch, mal_branche):  # noqa: F811 (fixture importée)
        _disque(monkeypatch, 900_000)
        widget, manager, _game = _prepare(panel, GameState.INSTALLED)
        manager.config.ecran_ignore = "AMD Radeon RX 580"
        widget.refresh()
        assert "GTX 970" in widget._alert.text()

    def test_rien_sur_un_pc_normal(self, panel, monkeypatch, mal_branche):  # noqa: F811 (fixture importée)
        _disque(monkeypatch, 900_000)
        monkeypatch.setattr(ecran_branche, "_resultat", None)
        widget, manager, _game = _prepare(panel, GameState.INSTALLED)
        manager.config.ecran_ignore = "NVIDIA GeForce GTX 970"
        widget.refresh()
        assert widget._alert.isHidden()
        assert manager.config.ecran_ignore == "", "réglé depuis : un prochain cas se redira"

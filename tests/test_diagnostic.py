"""Informations de diagnostic : journal, bouton de l'À propos, rapport de plantage.

Le launcher circule de main en main et l'aide passe par le Discord ; la première
question y est toujours « quelle version, quel Windows, quel jeu ? ».
"""

import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import diagnostic
from src.core.config import APP_VERSION
from src.core.game_manager import GameState
from src.core.stats import Tentative


def _faux_manager(install_path: Path):
    etats = {"hp1": GameState.INSTALLED, "hp2": GameState.NOT_INSTALLED}
    return SimpleNamespace(
        config=SimpleNamespace(install_path=install_path, langue="fr", theme="poudlard"),
        catalog=SimpleNamespace(catalog_version="0.24",
                                games=[SimpleNamespace(id="hp1"), SimpleNamespace(id="hp2")]),
        get_state=lambda gid: etats[gid],
        installed_version=lambda gid: "1.1" if gid == "hp1" else None,
        get_playtime=lambda gid: 3600 if gid == "hp1" else 0,
    )


class TestIdentite:
    def test_porte_la_version_et_le_systeme(self):
        ligne = diagnostic.identite()
        assert APP_VERSION in ligne
        assert "Python" in ligne
        assert diagnostic.systeme() in ligne


class TestEcran:
    def test_pixels_physiques(self):
        assert diagnostic.ecran(2048, 1152, 1.25) == "2560×1440 à 125 %"


class TestMateriel:
    """Processeur, carte graphique, pilote : la première question devant un
    écran noir. Demandé par Ludo le 2026-09-19."""

    def test_pilote_nvidia_au_numero_public(self):
        assert diagnostic.version_pilote_publique(
            "NVIDIA GeForce RTX 2060 SUPER", "32.0.16.1074") == "610.74"
        assert diagnostic.version_pilote_publique(
            "NVIDIA", "31.0.15.3623") == "536.23"

    def test_pilote_amd_au_numero_adrenalin(self):
        assert diagnostic.version_pilote_publique(
            "Advanced Micro Devices, Inc. AMD Radeon RX 6700", "31.0.24033.1003",
            "25.8.1") == "25.8.1"

    def test_pilote_intel_tel_quel(self):
        assert diagnostic.version_pilote_publique(
            "Intel Corporation Intel(R) UHD Graphics", "31.0.101.5186") == "31.0.101.5186"

    def test_ligne_de_carte(self):
        ligne = diagnostic.carte_graphique({
            "DriverDesc": "NVIDIA GeForce RTX 2060 SUPER", "ProviderName": "NVIDIA",
            "DriverVersion": "32.0.16.1074", "DriverDate": "7-2-2026",
            "HardwareInformation.qwMemorySize": 8 * 1024 ** 3,
            "MatchingDeviceId": r"pci\ven_10de&dev_1f06"})
        assert ligne == "NVIDIA GeForce RTX 2060 SUPER · pilote 610.74 · du 2026-07-02 · 8 Go"

    def test_un_adaptateur_virtuel_est_signale(self):
        ligne = diagnostic.carte_graphique({
            "DriverDesc": "Parsec Virtual Display Adapter", "DriverVersion": "0.45.0.0",
            "MatchingDeviceId": r"Root\Parsec\VDA"})
        assert ligne.endswith("virtuel")

    def test_le_rapport_porte_le_materiel(self):
        from tests.test_diagnostic import TestRapport
        texte = TestRapport()._rapport(tentatives=(),
                                       machine=["Processeur : Ryzen (16 threads)"])
        assert "Processeur : Ryzen (16 threads)" in texte

    def test_le_dossier_documents_est_dans_le_rapport(self, tmp_path, monkeypatch):
        """Chez l'utilisateur du 2026-09-20, il a fallu DÉDUIRE d'un
        avertissement du journal que Documents était inaccessible."""
        from tests.test_diagnostic import TestRapport
        texte = TestRapport()._rapport(tentatives=(), machine=[],
                                       documents=r"D:\Docs — INACCESSIBLE")
        assert "Documents : D:" in texte and "INACCESSIBLE" in texte

    def test_le_materiel_se_lit_sans_lever(self):
        assert diagnostic.materiel()[0].startswith("Processeur : ")


class TestRapport:
    def _rapport(self, **kw):
        return diagnostic.rapport(
            _faux_manager(Path.home() / "Games" / "AccioLauncher"),
            prerequis={"vcredist_x86": True, "vcredist2005_x86": False}, **kw)

    def test_le_dossier_personnel_n_en_sort_pas(self):
        texte = self._rapport(tentatives=())
        assert str(Path.home()) not in texte
        assert "~" in texte

    def test_seuls_les_jeux_installes_sont_listes(self):
        texte = self._rapport(tentatives=())
        assert "hp1 v1.1" in texte and "60 min de jeu" in texte
        assert "hp2" not in texte

    def test_prerequis_manquants_nommes(self):
        texte = self._rapport(tentatives=())
        assert "vcredist2005_x86 MANQUANT" in texte
        assert "vcredist_x86 OK" in texte

    def test_les_lancements_rates_y_figurent(self):
        t = Tentative(jeu="hp7a", debut=datetime(2026, 9, 17, 18, 0), duree=1, code=0)
        assert "hp7a le 2026-09-17 18:00 — 1 s, code 0" in self._rapport(tentatives=(t,))

    def test_du_journal_seuls_avertissements_et_erreurs(self):
        journal = ("2026 [x] INFO: tout va bien\n"
                   "2026 [x] WARNING: attention\n"
                   "2026 [x] DEBUG: détail\n"
                   "2026 [x] ERROR: panne\n")
        texte = self._rapport(tentatives=(), journal=journal)
        assert "attention" in texte and "panne" in texte
        assert "tout va bien" not in texte and "détail" not in texte

    def test_les_avertissements_sont_bornes(self):
        journal = "\n".join(f"[x] WARNING: n{i}" for i in range(50))
        assert len(diagnostic.lignes_notables(journal)) == 12
        assert diagnostic.lignes_notables(journal)[-1].endswith("n49")


class TestEnteteDuJournal:
    """Hors ligne, la version n'apparaissait JAMAIS dans le journal."""

    def test_la_premiere_ligne_porte_la_version(self, tmp_path, monkeypatch):
        import main
        monkeypatch.setattr(main, "LOG_DIR", tmp_path)
        monkeypatch.setattr(main, "LOG_FILE", tmp_path / "accio.log")
        racine = logging.getLogger()
        avant = list(racine.handlers)
        niveau = racine.level
        try:
            main._setup_logging()
        finally:
            for h in racine.handlers[:]:
                if h not in avant:
                    h.close()
                    racine.removeHandler(h)
            racine.setLevel(niveau)
        premiere = (tmp_path / "accio.log").read_text(encoding="utf-8").splitlines()[0]
        assert APP_VERSION in premiere and "Python" in premiere

    @pytest.mark.parametrize("gele, env, attendu", [
        (True, "", logging.INFO),
        (True, "debug", logging.DEBUG),
        (False, "", logging.DEBUG),
    ])
    def test_niveau_du_fichier(self, tmp_path, monkeypatch, gele, env, attendu):
        import main
        monkeypatch.setattr(main, "LOG_DIR", tmp_path)
        monkeypatch.setattr(main, "LOG_FILE", tmp_path / "accio.log")
        monkeypatch.setattr(main.sys, "frozen", gele, raising=False)
        monkeypatch.setenv("ACCIO_JOURNAL", env)
        racine = logging.getLogger()
        avant = list(racine.handlers)
        niveau = racine.level
        try:
            main._setup_logging()
            fichiers = [h for h in racine.handlers
                        if h not in avant and isinstance(h, logging.FileHandler)]
            assert fichiers[0].level == attendu
        finally:
            for h in racine.handlers[:]:
                if h not in avant:
                    h.close()
                    racine.removeHandler(h)
            racine.setLevel(niveau)


class TestBoutonDiagnostic:
    def test_copie_puis_confirme(self, qtbot, tmp_path, monkeypatch):
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtWidgets import QPushButton

        from src.ui import about_page
        monkeypatch.setattr(about_page, "LOG_DIR", tmp_path)
        page = about_page.construire((), manager=_faux_manager(tmp_path))
        qtbot.addWidget(page)
        monkeypatch.setattr(about_page.diagnostic, "rapport",
                            lambda manager, **kw: "DIAGNOSTIC-TEST")
        btn = next(b for b in page.findChildren(QPushButton)
                   if "diagnostic" in b.text())
        largeur = btn.minimumWidth()
        btn.click()
        assert QGuiApplication.clipboard().text() == "DIAGNOSTIC-TEST"
        assert "Discord" in btn.text()
        assert btn.minimumWidth() == largeur

    def test_absent_sans_manager(self, qtbot):
        from PyQt6.QtWidgets import QPushButton

        from src.ui import about_page
        page = about_page.construire(())
        qtbot.addWidget(page)
        assert not [b for b in page.findChildren(QPushButton) if "diagnostic" in b.text()]


class TestSortieSansFinalisation:
    """`sys.exit(app.exec())` laissait sip détruire les objets C++ pendant la
    finalisation de l'interpréteur : violation d'accès à 2 fermetures sur 8
    (2026-09-18). La sortie passe par `os._exit`, APRÈS `logging.shutdown()`."""

    def test_main_sort_par_os_exit_apres_avoir_vide_le_journal(self):
        source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        assert "sys.exit(app.exec())" not in source
        assert source.index("logging.shutdown()") < source.index("os._exit(code)")

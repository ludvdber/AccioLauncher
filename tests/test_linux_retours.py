"""Retours de Ludo sur Bazzite (2026-09-30) : avancement de la préparation de Wine,
fenêtre qui attend le jeu, umu sans réseau."""

import sys
from pathlib import Path
from types import SimpleNamespace

from src.core import compat
from src.core.preparation_wine import derniere_ligne


class TestDerniereLigne:
    def test_la_derniere_ligne_non_vide(self, tmp_path):
        j = tmp_path / "wine.log"
        j.write_bytes(b"===== 2026 : umu-run winetricks vcrun2022\nExecuting cd /tmp\n"
                      b"Downloading vc_redist.x86.exe  12%\r"
                      b"Downloading vc_redist.x86.exe  58%\r\n\n")
        assert derniere_ligne(j) == "Downloading vc_redist.x86.exe  58%"

    def test_couleurs_retirees_et_ligne_coupee(self, tmp_path):
        j = tmp_path / "wine.log"
        j.write_bytes(b"\x1b[1;32m" + b"x" * 300 + b"\x1b[0m\n")
        ligne = derniere_ligne(j)
        assert "\x1b" not in ligne and len(ligne) <= 110 and ligne.endswith("…")

    def test_rien_ou_absent(self, tmp_path):
        assert derniere_ligne(tmp_path / "absent.log") == ""
        (tmp_path / "vide.log").write_bytes(b"===== en-tete\n")
        assert derniere_ligne(tmp_path / "vide.log") == ""


class TestUmuHorsLigne:
    def test_la_mise_a_jour_du_runtime_sautee_hors_ligne(self, monkeypatch, tmp_path):
        lanceur = SimpleNamespace(famille="umu", proton="", executable="/usr/bin/umu-run", winetricks="")
        try:
            compat.signaler_reseau(False)
            assert compat.environnement(lanceur, tmp_path, base={})["UMU_RUNTIME_UPDATE"] == "0"
            compat.signaler_reseau(True)
            assert "UMU_RUNTIME_UPDATE" not in compat.environnement(lanceur, tmp_path, base={})
        finally:
            compat.signaler_reseau(True)


def _runtime_installe(dossier: Path, variante: str = "steamrt3") -> None:
    racine = dossier / variante if variante else dossier
    (racine / "pressure-vessel").mkdir(parents=True)
    (racine / "sniper_platform_3.0.20260914.260626").mkdir()


class TestRuntimeUmuUneFoisParSemaine:
    """En ligne, umu retéléchargeait 195 Mo de runtime avant chaque partie (17 s au lieu de 4,5)."""

    LANCEUR = SimpleNamespace(famille="umu", proton="", executable="/usr/bin/umu-run", winetricks="")

    def test_detection_du_runtime(self, tmp_path):
        assert compat.runtime_umu_installe(tmp_path) is False
        (tmp_path / "steamrt3" / "pressure-vessel").mkdir(parents=True)
        assert compat.runtime_umu_installe(tmp_path) is False     # incomplet
        (tmp_path / "steamrt3" / "sniper_platform_3.0").mkdir()
        assert compat.runtime_umu_installe(tmp_path) is True

    def test_l_ancienne_disposition_a_la_racine(self, tmp_path):
        _runtime_installe(tmp_path, variante="")
        assert compat.runtime_umu_installe(tmp_path) is True

    def test_pas_installe_umu_doit_pouvoir_l_installer(self, tmp_path):
        assert "UMU_RUNTIME_UPDATE" not in compat.environnement(self.LANCEUR, tmp_path, base={})

    def test_une_verification_par_semaine(self, monkeypatch, tmp_path):
        umu = tmp_path / "umu"
        _runtime_installe(umu)
        monkeypatch.setattr(compat, "dossier_umu", lambda: umu)
        t0 = 1_800_000_000.0
        assert compat.mise_a_jour_runtime_permise(t0) is True
        assert compat.mise_a_jour_runtime_permise(t0 + 60) is False
        assert compat.mise_a_jour_runtime_permise(t0 + compat.INTERVALLE_RUNTIME_S - 1) is False
        assert compat.mise_a_jour_runtime_permise(t0 + compat.INTERVALLE_RUNTIME_S + 1) is True
        assert compat.mise_a_jour_runtime_permise(t0 + compat.INTERVALLE_RUNTIME_S + 2) is False

    def test_l_environnement_de_la_partie_suivante(self, monkeypatch, tmp_path):
        umu = tmp_path / "umu"
        _runtime_installe(umu)
        monkeypatch.setattr(compat, "dossier_umu", lambda: umu)
        assert "UMU_RUNTIME_UPDATE" not in compat.environnement(self.LANCEUR, tmp_path, base={})
        assert compat.environnement(self.LANCEUR, tmp_path, base={})["UMU_RUNTIME_UPDATE"] == "0"

    def test_une_date_dans_le_futur_ne_bloque_pas_pour_toujours(self, monkeypatch, tmp_path):
        """Une horloge remise à l'heure : la marque ne doit pas geler le runtime."""
        umu = tmp_path / "umu"
        _runtime_installe(umu)
        monkeypatch.setattr(compat, "dossier_umu", lambda: umu)
        assert compat.mise_a_jour_runtime_permise(2_000_000_000.0) is True
        assert compat.mise_a_jour_runtime_permise(1_900_000_000.0) is True

    def test_la_valeur_de_l_utilisateur_reste_la_sienne(self, monkeypatch, tmp_path):
        umu = tmp_path / "umu"
        _runtime_installe(umu)
        monkeypatch.setattr(compat, "dossier_umu", lambda: umu)
        compat.mise_a_jour_runtime_permise()
        env = compat.environnement(self.LANCEUR, tmp_path, base={"UMU_RUNTIME_UPDATE": "1"})
        assert env["UMU_RUNTIME_UPDATE"] == "1"

    def test_un_import_de_registre_ne_prend_pas_la_verification_de_la_semaine(
            self, monkeypatch, tmp_path):
        """Revue du 2026-09-30 : l'import d'un .reg (changer la langue d'un jeu)
        consommait la vérification de la semaine sans la faire — UMU_RUNTIME_UPDATE=0
        posé juste après —, et la partie suivante n'en avait plus pour sept jours."""
        from src.core import game_registry
        umu = tmp_path / "umu"
        _runtime_installe(umu)
        monkeypatch.setattr(compat, "dossier_umu", lambda: umu)
        lanceur = compat.Lanceur("umu", "/nonexistent/accio-test/umu-run")
        monkeypatch.setattr(compat, "lanceur", lambda: lanceur)
        pfx = compat.prefixe("umu")
        (pfx / "drive_c").mkdir(parents=True)
        (pfx / "system.reg").write_text("WINE REGISTRY Version 2\n\n#arch=win64\n",
                                        encoding="utf-8")
        vus = []
        monkeypatch.setattr(game_registry.subprocess, "run",
                            lambda commande, **kw: vus.append(kw["env"]))
        assert game_registry._ecrire_par_wine(
            "HKLM", "SOFTWARE\\Electronic Arts\\HP7", {"Locale": "fr"}, 32) is True
        game_registry._nettoyer_reg()
        assert vus[0]["UMU_RUNTIME_UPDATE"] == "0"       # la fenêtre attend regedit
        assert "UMU_RUNTIME_UPDATE" not in compat.environnement(lanceur, pfx, base={})


class TestRetraitDiffere:
    def test_sous_linux_la_fenetre_attend_le_jeu(self, qtbot, monkeypatch):
        from src.ui.retrait_differe import RetraitDiffere
        monkeypatch.setattr(sys, "platform", "linux")
        retraits = []
        r = RetraitDiffere(lambda: retraits.append(1))
        assert r.differer("HP6", fenetre_active=True) and r.attend
        assert not retraits
        r.desactivee()   # le jeu prend la main
        assert retraits == [1] and not r.attend

    def test_sous_windows_ou_fenetre_inactive_retrait_immediat(self, qtbot, monkeypatch):
        from src.ui.retrait_differe import RetraitDiffere
        r = RetraitDiffere(lambda: None)
        monkeypatch.setattr(sys, "platform", "win32")
        assert not r.differer("HP6", fenetre_active=True)
        monkeypatch.setattr(sys, "platform", "linux")
        assert not r.differer("HP6", fenetre_active=False)

    def test_jeu_ferme_avant_d_avoir_pris_la_main(self, qtbot, monkeypatch):
        from src.ui.retrait_differe import RetraitDiffere
        monkeypatch.setattr(sys, "platform", "linux")
        retraits = []
        r = RetraitDiffere(lambda: retraits.append(1))
        r.differer("HP1", fenetre_active=True)
        r.oublier()
        r.desactivee()
        assert not retraits


class TestBarreDePreparation:
    def test_la_barre_montre_l_etape_et_annule_la_preparation(self, qtbot):
        from src.core.game_data import GameData
        from src.ui.download_bar import DownloadBar
        barre = DownloadBar()
        qtbot.addWidget(barre)
        jeu = GameData.from_dict({"id": "hp6", "name": "HP6", "year": 2009, "description": "d",
                                  "developer": "d", "executable": "HP6/hp6.exe", "cover_image": "c.jpg"})
        annule, telechargement = [], []
        barre.preparation_cancel_clicked.connect(lambda: annule.append(1))
        barre.cancel_clicked.connect(lambda: telechargement.append(1))
        barre.show_preparation(jeu)
        barre.set_preparation("Installation de Visual C++ 2015-2022", "Downloading vc_redist 58%")
        assert barre.en_preparation and barre._progress.maximum() == 0
        assert barre._status.text() == "Downloading vc_redist 58%"
        assert barre._phase_label.text().startswith("Installation de Visual C++ 2015-2022 · 0:0")
        barre._btn_cancel.click()
        assert annule == [1] and not telechargement
        barre.hide_bar()
        assert not barre.en_preparation

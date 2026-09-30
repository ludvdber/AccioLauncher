"""Retours de Ludo sur Bazzite (2026-09-30) : avancement de la préparation de Wine,
fenêtre qui attend le jeu, umu sans réseau."""

import sys
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

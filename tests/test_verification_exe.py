"""`--verifier-exe` : depuis les sources, la vérification de l'exe passe et dit ce qu'elle a vu.

La CI la lance sur l'exe et l'AppImage construits (tests.yml, job `exe`) ; ici, on
s'assure qu'elle ne crie pas au loup sur un dépôt sain, et qu'elle voit un vrai trou.
"""
import re

import pytest

pytest.importorskip("pytestqt")

from src.ui import verification_exe as ve  # noqa: E402


def test_le_drapeau_donne_le_chemin_du_rapport(tmp_path):
    assert ve.demande(["accio"]) is None
    assert ve.demande(["accio", ve.DRAPEAU, str(tmp_path / "r.txt")]) == tmp_path / "r.txt"


def test_un_depot_sain_passe(qtbot, tmp_path):
    rapport = tmp_path / "r.txt"
    assert ve.executer(rapport) == 0, rapport.read_text(encoding="utf-8")
    texte = rapport.read_text(encoding="utf-8")
    assert "ÉCHEC" not in texte and texte.rstrip().endswith("== OK")
    assert re.search(r"^catalogue : [1-9]\d* jeux$", texte, re.MULTILINE)
    assert re.search(r"^modules : \d{3} importés$", texte, re.MULTILINE)


def test_un_module_qui_ne_s_importe_pas_est_dit(qtbot, tmp_path, monkeypatch):
    vrai = ve.importlib.import_module

    def casse(nom):
        if nom == "src.core.chemins":
            raise ModuleNotFoundError("No module named 'src.core.chemins'")
        return vrai(nom)
    monkeypatch.setattr(ve.importlib, "import_module", casse)
    rapport = tmp_path / "r.txt"
    assert ve.executer(rapport) == 1
    assert "ÉCHEC import src.core.chemins" in rapport.read_text(encoding="utf-8")

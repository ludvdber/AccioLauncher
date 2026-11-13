"""Trouver un fichier du jeu sans casse et sans relister le dossier (`src/core/sans_casse.py`).

Banc de rapidité, 2026-11-13 : `HP3/textures` listé 234 fois sur un parcours (une fois
par carte du folio). Mesure : le nombre de `iterdir` réels. Contre-épreuve : l'ancien
`encyclopedie.trouver` listait à chaque appel.
"""

import os
from pathlib import Path

from src.core import encyclopedie, sans_casse


def _jeu(tmp_path: Path) -> Path:
    (tmp_path / "Textures").mkdir()
    (tmp_path / "Textures" / "HP3_Menu.utx").write_bytes(b"x")
    return tmp_path


def test_cent_cartes_un_seul_listage(tmp_path, monkeypatch):
    jeu = _jeu(tmp_path)
    listages = []
    vrai = Path.iterdir

    def compter(self):
        listages.append(self.name)
        return vrai(self)
    monkeypatch.setattr(Path, "iterdir", compter)
    for _ in range(100):
        assert encyclopedie.trouver(jeu, "textures/hp3_menu.utx") == jeu / "Textures" / "HP3_Menu.utx"
    assert sorted(listages) == sorted([jeu.name, "Textures"])


def test_un_fichier_ajoute_se_trouve(tmp_path):
    jeu = _jeu(tmp_path)
    assert sans_casse.trouver(jeu, "textures/nouveau.utx") is None
    dossier = jeu / "Textures"
    (dossier / "Nouveau.utx").write_bytes(b"y")
    etat = dossier.stat()     # au cas où le système garde la même date à la nanoseconde
    os.utime(dossier, ns=(etat.st_atime_ns, etat.st_mtime_ns + 1_000_000_000))
    assert sans_casse.trouver(jeu, "textures/nouveau.utx") == dossier / "Nouveau.utx"


def test_absent_ou_illisible(tmp_path):
    assert sans_casse.trouver(tmp_path / "rien", "a/b") is None
    assert sans_casse.entrees(tmp_path / "rien") == {}

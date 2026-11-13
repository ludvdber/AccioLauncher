"""Un seul lien dans le launcher (audit UI v57, Ludo 2026-11-13) : or et souligné, ou gris discret.

Onze présentations différentes coexistaient, dont des liens or sans soulignement que Ludo ne
reconnaissait pas comme des liens (ASTeam, 2026-10-14). Le lien vit dans `composants`
(`lien`, `html_lien`) ; seul le bandeau d'avertissement garde le sien, ambre et appuyé, mesuré
pour ne pas tirer un trait orange sous sa ligne.
"""

import re
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

_EXCEPTIONS = {"composants.py", "alert_banner.py"}


def test_aucun_style_de_lien_local():
    fautifs = []
    for fichier in sorted(Path("src/ui").glob("*.py")):
        if fichier.name in _EXCEPTIONS:
            continue
        texte = fichier.read_text(encoding="utf-8")
        for motif in (r"<a href=[^>]*style=", r"QPushButton#lien", r"text-decoration:\s*underline"):
            if re.search(motif, texte):
                fautifs.append(f"{fichier.name} : {motif}")
    assert fautifs == []


def test_le_lien_est_souligne_et_suit_la_maison(qtbot):
    from src.ui.composants import html_lien, lien
    from src.ui.theme import current, set_theme
    set_theme("gryffondor")
    try:
        assert f"color:{current().accent}; text-decoration:underline;" in html_lien("x", "Lien")
        assert 'href="a&amp;b"' in html_lien("a&b", "Lien")
    finally:
        set_theme("poudlard")
    assert lien("Ouvrir").objectName() == "lien"
    assert lien("Désinstaller…", discret=True).objectName() == "lienDiscret"

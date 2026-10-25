"""Toute sortie de programme lue en texte nomme son encodage.

`text=True` seul décode avec l'encodage par défaut : la page ANSI sous Windows
jusqu'à 3.14, UTF-8 à partir de 3.15 (PEP 686), et ni l'un ni l'autre n'est
celui de 7-Zip (page OEM de la console). La liste des archives rendait ainsi
« Ph‚nix » pour « Phénix » à la barrière Zip Slip (2026-10-25).
"""
import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
APPELS = {"run", "Popen", "check_output", "check_call", "call"}


def _appels_texte_sans_encodage(source: str) -> list[int]:
    lignes = []
    for noeud in ast.walk(ast.parse(source)):
        if not isinstance(noeud, ast.Call):
            continue
        nom = noeud.func.attr if isinstance(noeud.func, ast.Attribute) else getattr(noeud.func, "id", "")
        if nom not in APPELS:
            continue
        mots = {k.arg: k.value for k in noeud.keywords}
        texte = any(isinstance(mots.get(c), ast.Constant) and mots[c].value is True
                    for c in ("text", "universal_newlines"))
        if texte and "encoding" not in mots:
            lignes.append(noeud.lineno)
    return lignes


def test_aucune_sortie_de_programme_decodee_au_hasard():
    fautifs = []
    for fichier in [*RACINE.joinpath("src").rglob("*.py"), RACINE / "main.py",
                    *RACINE.joinpath("tools").rglob("*.py")]:
        for ligne in _appels_texte_sans_encodage(fichier.read_text(encoding="utf-8")):
            fautifs.append(f"{fichier.relative_to(RACINE)}:{ligne}")
    assert fautifs == [], fautifs


def test_le_garde_fou_voit_un_appel_fautif():
    assert _appels_texte_sans_encodage("subprocess.run(['x'], text=True)") == [1]
    assert _appels_texte_sans_encodage("subprocess.run(['x'], text=True, encoding='oem')") == []

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


def _fichiers_texte_sans_encodage(source: str) -> list[int]:
    """`open()` en mode texte, `read_text`, `write_text` sans `encoding=`.

    L'audit du 2026-10-29 a trouvé le dépôt propre, mais rien ne le gardait :
    le test ne surveillait que les sorties de programme."""
    lignes = []
    for noeud in ast.walk(ast.parse(source)):
        if not isinstance(noeud, ast.Call):
            continue
        nom = noeud.func.attr if isinstance(noeud.func, ast.Attribute) else getattr(noeud.func, "id", "")
        mots = {k.arg for k in noeud.keywords}
        if "encoding" in mots:
            continue
        if nom in ("read_text", "write_text"):
            lignes.append(noeud.lineno)
        elif nom == "open":
            # `open(chemin, mode)` / `Path.open(mode)` : le mode est le 2e argument
            # de la fonction, le 1er de la méthode.
            positionnels = noeud.args[1:] if isinstance(noeud.func, ast.Name) else noeud.args
            mode = next((k.value for k in noeud.keywords if k.arg == "mode"),
                        positionnels[0] if positionnels else None)
            if mode is None or (isinstance(mode, ast.Constant) and isinstance(mode.value, str)
                                and "b" not in mode.value):
                lignes.append(noeud.lineno)
    return lignes


def _sources():
    # build/ et fuzz/ aussi : un outil de build qui décode au hasard publie
    # un exe faux (audit du 2026-10-29 : `build/linux/dependances.py`).
    return [*RACINE.joinpath("src").rglob("*.py"), RACINE / "main.py",
            *RACINE.joinpath("tools").rglob("*.py"), *RACINE.joinpath("build").rglob("*.py"),
            *RACINE.joinpath("fuzz").rglob("*.py")]


def test_aucune_sortie_de_programme_decodee_au_hasard():
    fautifs = []
    for fichier in _sources():
        for ligne in _appels_texte_sans_encodage(fichier.read_text(encoding="utf-8")):
            fautifs.append(f"{fichier.relative_to(RACINE)}:{ligne}")
    assert fautifs == [], fautifs


def test_aucun_fichier_texte_ouvert_au_hasard():
    fautifs = []
    for fichier in _sources():
        for ligne in _fichiers_texte_sans_encodage(fichier.read_text(encoding="utf-8")):
            fautifs.append(f"{fichier.relative_to(RACINE)}:{ligne}")
    assert fautifs == [], fautifs


def test_le_garde_fou_voit_un_fichier_fautif():
    assert _fichiers_texte_sans_encodage("open(p)") == [1]
    assert _fichiers_texte_sans_encodage("open(p, 'w')") == [1]
    assert _fichiers_texte_sans_encodage("open(p, 'rb')") == []
    assert _fichiers_texte_sans_encodage("p.open('rb')") == []
    assert _fichiers_texte_sans_encodage("p.open()") == [1]
    assert _fichiers_texte_sans_encodage("p.read_text()") == [1]
    assert _fichiers_texte_sans_encodage("p.write_text(t, encoding='utf-8')") == []


def test_le_garde_fou_voit_un_appel_fautif():
    assert _appels_texte_sans_encodage("subprocess.run(['x'], text=True)") == [1]
    assert _appels_texte_sans_encodage("subprocess.run(['x'], text=True, encoding='oem')") == []

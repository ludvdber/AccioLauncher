"""Les modules d'extension Qt doivent être créés TÔT, jamais en pleine session.

Créer un module d'extension C alors que l'application tourne — donc pendant que
le ramasse-miettes peut passer sur des objets Qt vivants — provoque un
« Windows fatal exception: access violation ». C'est arrivé pendant un build le
2026-08-20 : `QtNetwork` était importé depuis un fixture de test, et le
plantage s'est produit dans `enum.py` au moment de la création du module.

Le plantage est ALÉATOIRE — il dépend de l'instant où le GC se déclenche — donc
il casse un build au hasard, ce qui est bien pire qu'une erreur franche.

`QtCore`, `QtGui` et `QtWidgets` ne sont pas concernés : ils sont importés en
tête de presque tous les modules, donc un import différé n'est plus qu'une
recherche dans `sys.modules`. Seuls comptent les modules qu'un import tardif
pourrait CRÉER pour la première fois.
"""

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
A_CHARGER_TOT = ("PyQt6.QtNetwork", "PyQt6.QtMultimedia", "PyQt6.QtSql",
                 "PyQt6.QtPrintSupport", "PyQt6.QtSvg")


def _imports_differes(arbre: ast.AST) -> list[tuple[str, int]]:
    """Imports des modules à risque situés DANS une fonction ou une méthode."""
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for interne in ast.walk(noeud):
            if isinstance(interne, ast.ImportFrom) and interne.module:
                nom = interne.module
            elif isinstance(interne, ast.Import):
                nom = interne.names[0].name
            else:
                continue
            if any(nom.startswith(risque) for risque in A_CHARGER_TOT):
                trouves.append((nom, interne.lineno))
    return trouves


def test_aucun_module_qt_a_risque_importe_dans_une_fonction():
    fautifs = []
    for chemin in sorted((RACINE / "src").rglob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), str(chemin))
        for nom, ligne in _imports_differes(arbre):
            fautifs.append(f"{chemin.relative_to(RACINE).as_posix()}:{ligne} → {nom}")
    assert not fautifs, (
        "import différé d'un module d'extension Qt (plantage aléatoire au "
        "premier usage, voir l'en-tête de ce fichier) :\n  " + "\n  ".join(fautifs))


def test_le_lecteur_video_degrade_toujours_proprement():
    """L'import a été remonté en tête : la dégradation doit survivre.

    `play()` doit encore renvoyer False si PyQt6-Multimedia manque — c'était
    tout l'intérêt du try/except qu'on a déplacé.
    """
    import src.ui.video_player as vp

    assert hasattr(vp, "MULTIMEDIA_DISPONIBLE")
    source = Path(vp.__file__).read_text(encoding="utf-8")
    assert "except ImportError" in source, "la dégradation gracieuse a disparu"
    assert "if not MULTIMEDIA_DISPONIBLE" in source

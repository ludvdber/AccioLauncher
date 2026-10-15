"""Un nom importé sous `if TYPE_CHECKING` n'existe pas à l'exécution.

Python 3.14 évalue les annotations paresseusement : une signature qui le cite
passe en local et casse l'import en 3.12 et 3.13 (la CI). Un `httpx.Response`
dans `downloader.py` a fait tomber 10 fichiers de tests en 3.12. Tout module qui
s'en sert dans une annotation évaluée doit porter `from __future__ import annotations`.
"""
import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _noms_sous_type_checking(arbre: ast.Module) -> set[str]:
    noms: set[str] = set()
    for noeud in arbre.body:
        if isinstance(noeud, ast.If) and ast.unparse(noeud.test).endswith("TYPE_CHECKING"):
            for imp in ast.walk(noeud):
                if isinstance(imp, (ast.Import, ast.ImportFrom)):
                    noms.update((a.asname or a.name).split(".")[0] for a in imp.names)
    return noms


def _annotations_evaluees(arbre: ast.Module) -> list[ast.expr]:
    """Signatures de fonctions et annotations de module ou de classe ; celles
    du corps d'une fonction ne sont jamais évaluées."""
    vues: list[ast.expr] = []

    def parcourir(corps: list[ast.stmt]) -> None:
        for n in corps:
            if isinstance(n, ast.AnnAssign):
                vues.append(n.annotation)
            elif isinstance(n, ast.ClassDef):
                parcourir(n.body)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = n.args
                for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg]:
                    if arg is not None and arg.annotation is not None:
                        vues.append(arg.annotation)
                if n.returns is not None:
                    vues.append(n.returns)
                parcourir([c for c in n.body if isinstance(c, ast.ClassDef)])
    parcourir(arbre.body)
    return vues


def test_aucun_nom_de_type_checking_dans_une_annotation_evaluee():
    fautifs = []
    for fichier in [*RACINE.joinpath("src").rglob("*.py"), RACINE / "main.py"]:
        source = fichier.read_text(encoding="utf-8")
        if "from __future__ import annotations" in source:
            continue
        arbre = ast.parse(source)
        caches = _noms_sous_type_checking(arbre)
        if not caches:
            continue
        for ann in _annotations_evaluees(arbre):
            if isinstance(ann, ast.Constant):
                continue  # annotation entre guillemets : jamais évaluée
            utilises = {n.id for n in ast.walk(ann) if isinstance(n, ast.Name)}
            for nom in utilises & caches:
                fautifs.append(f"{fichier.relative_to(RACINE)}:{ann.lineno} {nom}")
    assert fautifs == [], fautifs

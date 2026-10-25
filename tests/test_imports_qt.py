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


def test_tout_module_d_extension_qt_est_precharge():
    """Avec les imports paresseux (3.15), un module qui importe `QtMultimedia` en
    tête ne s'exécute plus qu'à son premier usage : seul le préchargement de
    `imports_paresseux` garde la création au démarrage."""
    from src.ui.imports_paresseux import MODULES_QT_A_CHARGER_TOT

    importes = set()
    for chemin in (RACINE / "src").rglob("*.py"):
        for noeud in ast.walk(ast.parse(chemin.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.ImportFrom) and noeud.module:
                noms = [noeud.module] + ([f"PyQt6.{a.name}" for a in noeud.names]
                                         if noeud.module == "PyQt6" else [])
            elif isinstance(noeud, ast.Import):
                noms = [a.name for a in noeud.names]
            else:
                continue
            importes |= {n for n in noms if n.startswith(A_CHARGER_TOT)}
    assert importes, "le balayage ne voit plus aucun import Qt d'extension"
    assert importes <= set(MODULES_QT_A_CHARGER_TOT), importes - set(MODULES_QT_A_CHARGER_TOT)


def test_la_paresse_ne_vise_que_le_launcher():
    import sys

    from src.ui.imports_paresseux import seulement_le_launcher

    assert seulement_le_launcher("main", "src.ui.about_page")
    assert not seulement_le_launcher("src.core.config", "json")
    assert not seulement_le_launcher("src.ui.mediatheque", "PyQt6.QtMultimedia")
    if hasattr(sys, "get_lazy_imports"):   # posé par conftest, comme main.main
        assert sys.get_lazy_imports() == "all"
        assert sys.get_lazy_imports_filter() is seulement_le_launcher


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

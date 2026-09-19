"""Les objets Qt qui vivent aussi longtemps que leur fenêtre ont un PARENT.

Sans parent, un objet Qt n'appartient qu'à Python : il survit au widget qu'il
sert et n'est détruit que lorsque le ramasse-miettes passe sur les cycles de
références de la fenêtre, à un instant quelconque — y compris pendant qu'une
autre fenêtre se peint. Relevé le 2026-09-19 en cherchant le plantage de la
CI Windows : six animations (fondu de la fiche, vignettes du carrousel, toast,
interrupteurs) et le menu de l'icône de notification, un `QMenu()` étant une
fenêtre à part entière. Avec un parent, ils meurent avec leur widget, dans
l'ordre de Qt.
"""

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Nombre d'arguments positionnels à partir duquel le parent est passé.
_POSITION_DU_PARENT = {
    "QPropertyAnimation": 3,          # (cible, propriété, parent)
    "QVariantAnimation": 1,
    "QSequentialAnimationGroup": 1,
    "QParallelAnimationGroup": 1,
    "QMenu": 1,                       # QMenu(parent) ou QMenu(titre, parent) : voir plus bas
}


def _nom(appel: ast.Call) -> str:
    f = appel.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _sans_parent(appel: ast.Call) -> bool:
    nom = _nom(appel)
    if any(k.arg == "parent" for k in appel.keywords):
        return False
    if nom == "QMenu" and len(appel.args) == 1:
        # QMenu("Titre") n'a pas de parent ; QMenu(widget) en a un.
        seul = appel.args[0]
        return isinstance(seul, ast.Constant) and isinstance(seul.value, str)
    return len(appel.args) < _POSITION_DU_PARENT[nom]


def test_aucun_objet_qt_durable_sans_parent():
    fautifs = []
    for chemin in sorted((RACINE / "src").rglob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), str(chemin))
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Call) and _nom(noeud) in _POSITION_DU_PARENT
                    and _sans_parent(noeud)):
                fautifs.append(f"{chemin.relative_to(RACINE).as_posix()}:{noeud.lineno}"
                               f" {_nom(noeud)}")
    assert not fautifs, "objet Qt sans parent :\n  " + "\n  ".join(fautifs)

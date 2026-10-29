"""Règles de REGLES.md vérifiables dans le texte du code, sur tout `src/`.

Relevé le 2026-10-25 en rejouant les règles : la 63 n'était gardée que pour le
Discord (deux adresses de GitHub écrites en dur avaient échappé), la 6 pas du
tout (quatre constantes `subprocess.CREATE_*` nommées dans des fonctions).
"""

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCES = [*RACINE.joinpath("src").rglob("*.py"), RACINE / "main.py"]
DRAPEAUX = {"CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP", "CREATE_NEW_CONSOLE",
            "DETACHED_PROCESS", "CREATE_BREAKAWAY_FROM_JOB"}
ADRESSES = ("https://github.com/ludvdber/AccioLauncher", "https://acciolauncher.be",
            "https://discord.gg/", "https://ko-fi.com/")


def _drapeaux_dans_une_fonction(source: str) -> list[int]:
    lignes = []
    for fonction in ast.walk(ast.parse(source)):
        if isinstance(fonction, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fonction):
                if (isinstance(n, ast.Attribute) and n.attr in DRAPEAUX
                        and isinstance(n.value, ast.Name) and n.value.id == "subprocess"):
                    lignes.append(n.lineno)
    return lignes


def test_regle_6_drapeaux_windows_nommes_a_l_import():
    fautifs = [f"{f.relative_to(RACINE)}:{n}" for f in SOURCES
               for n in _drapeaux_dans_une_fonction(f.read_text(encoding="utf-8"))]
    assert fautifs == [], fautifs


def test_regle_6_le_garde_fou_voit_un_drapeau_dans_une_fonction():
    assert _drapeaux_dans_une_fonction("def f():\n    return subprocess.CREATE_NO_WINDOW\n") == [2]
    assert _drapeaux_dans_une_fonction("X = subprocess.CREATE_NO_WINDOW\n") == []


def test_regle_12_aucun_faux_pose_sur_la_classe_d_un_objet_qt():
    """`monkeypatch.setattr(type(objet), …)` vise la CLASSE : sur un QObject, le
    rétablissement laisse un descripteur collé. Poser le faux sur l'instance."""
    fautifs = []
    for f in RACINE.joinpath("tests").glob("test_*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "setattr"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "monkeypatch"
                    and n.args and isinstance(n.args[0], ast.Call)
                    and isinstance(n.args[0].func, ast.Name) and n.args[0].func.id == "type"):
                fautifs.append(f"{f.relative_to(RACINE)}:{n.lineno}")
    assert fautifs == [], fautifs


def test_regle_63_adresses_du_projet_seulement_dans_liens():
    fautifs = []
    for f in SOURCES:
        if f.name == "liens.py":
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and any(
                    a in n.value for a in ADRESSES):
                fautifs.append(f"{f.relative_to(RACINE)}:{n.lineno}")
    assert fautifs == [], fautifs


LECTEURS_MEDIA = {"player", "_player", "lecteur", "_lecteur", "voix", "_voix"}


def _stop_sur_un_lecteur(source: str) -> list[int]:
    lignes = []
    for n in ast.walk(ast.parse(source)):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "stop"
                and not n.args):
            cible = n.func.value
            nom = cible.attr if isinstance(cible, ast.Attribute) else getattr(cible, "id", "")
            if nom in LECTEURS_MEDIA:
                lignes.append(n.lineno)
    return lignes


def test_regle_135_aucun_stop_sur_un_qmediaplayer():
    """`QMediaPlayer.stop()` garde le GIL et peut figer contre le fil audio de
    FFmpeg : `setSource(QUrl())` arrête aussi, et relâche le GIL."""
    fautifs = [f"{f.relative_to(RACINE)}:{n}" for f in SOURCES
               if "QMediaPlayer" in (texte := f.read_text(encoding="utf-8"))
               for n in _stop_sur_un_lecteur(texte)]
    assert fautifs == [], fautifs


def test_regle_135_le_garde_fou_voit_un_stop():
    assert _stop_sur_un_lecteur("self._player.stop()\nlecteur.stop()\n") == [1, 2]
    assert _stop_sur_un_lecteur("self._chargeur.stop()\nself.stop()\n") == []

"""`pyproject.toml` est la source de vérité des dépendances ; `requirements*.txt` n'en sont que le miroir.

Le plancher de ruff y disait `>=0.16` d'un côté et `>=0.16.10` de l'autre : un `pip install .[dev]` et un
`pip install -r requirements-dev.txt` ne posaient donc pas le même outil (ACT-013).
"""
import re
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def _lire_requirements(nom: str) -> dict[str, str]:
    """Nom → contrainte, sans commentaires ni lignes `-r`."""
    deps = {}
    for ligne in (RACINE / nom).read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if not ligne or ligne.startswith("-"):
            continue
        deps[_nom(ligne)] = ligne
    return deps


def _nom(spec: str) -> str:
    return re.split(r"[<>=!~\[ ]", spec, maxsplit=1)[0].lower()


def _pyproject() -> dict:
    return tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))


def _normaliser(specs: list[str]) -> dict[str, str]:
    return {_nom(s): s.replace(" ", "") for s in specs}


class TestMiroirs:
    def test_requirements_miroite_les_dependances(self):
        attendu = _normaliser(_pyproject()["project"]["dependencies"])
        lu = {nom: spec.replace(" ", "") for nom, spec in _lire_requirements("requirements.txt").items()}
        assert lu == attendu

    def test_requirements_dev_miroite_l_extra_dev(self):
        attendu = _normaliser(_pyproject()["project"]["optional-dependencies"]["dev"])
        lu = {nom: spec.replace(" ", "") for nom, spec in _lire_requirements("requirements-dev.txt").items()}
        assert lu == attendu

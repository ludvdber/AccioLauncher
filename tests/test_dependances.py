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


def _figees() -> dict[str, str]:
    """Nom normalisé → version épinglée de `.github/requirements/tests.txt`."""
    from packaging.utils import canonicalize_name
    figees = {}
    for ligne in (RACINE / ".github" / "requirements" / "tests.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^ ;\\]+)", ligne)
        if m:
            figees[canonicalize_name(m.group(1))] = m.group(2)
    return figees


class TestLesPaquetsFigesSatisfontLesPlanchers:
    """La release installe `tests.txt` (empreintes vérifiées) AVANT build.sh / build.bat.

    Un plancher de `requirements-dev.txt` plus haut que la version figée, et le
    `pip install -r requirements-dev.txt` du build allait chercher sur PyPI,
    SANS empreinte, de quoi le satisfaire : ruff 0.17.5 par-dessus 0.17.3
    (commit 1adad44, relevé par l'audit Linux du 2026-11-17, C1).
    """

    def test_chaque_plancher_est_satisfait(self):
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
        figees = _figees()
        manquants, insatisfaits = [], []
        for fichier in ("requirements.txt", "requirements-dev.txt"):
            for spec in _lire_requirements(fichier).values():
                req = Requirement(spec)
                version = figees.get(canonicalize_name(req.name))
                if version is None:
                    manquants.append(f"{fichier} : {req.name}")
                elif not req.specifier.contains(version, prereleases=True):
                    insatisfaits.append(f"{fichier} : {spec} contre {version} figé")
        assert not manquants, manquants
        assert not insatisfaits, insatisfaits

    def test_contre_epreuve_l_ancien_ruff_ne_passait_pas(self):
        from packaging.requirements import Requirement
        assert not Requirement("ruff>=0.17.4").specifier.contains("0.17.3")


class TestLeBuildDeReleaseNeReinstallePas:
    """Avec ACCIO_PY (posé par release.yml), build.sh / build.bat n'installent rien."""

    def test_build_sh(self):
        texte = (RACINE / "build.sh").read_text(encoding="utf-8")
        garde = texte.index('if [ -z "${ACCIO_PY:-}" ]; then')
        installation = texte.index("pip install -r requirements-dev.txt")
        fin = texte.index("\nfi\n", garde)
        assert garde < installation < fin

    def test_build_bat(self):
        texte = (RACINE / "build.bat").read_text(encoding="utf-8")
        garde = texte.index("if defined ACCIO_PY goto deps_faites")
        installation = texte.index("pip install -r requirements-dev.txt")
        etiquette = texte.index(":deps_faites")
        assert garde < installation < etiquette

"""Résumé d'un rapport JUnit de pytest dans la page du run GitHub (`$GITHUB_STEP_SUMMARY`).

    python tools/resume_junit.py rapport-tests.xml [titre]

Le journal d'un run fait des milliers de lignes ; un échec s'y cherchait à la main
(audit des tests, 2026-11-15). Ici : le compte, puis chaque échec avec sa première
ligne d'erreur, en haut de la page du run. Sans la variable (en local), sur la sortie.
"""
import os
import sys
import xml.etree.ElementTree as ET  # noqa: S405 — notre propre rapport, écrit par pytest dans ce run
from pathlib import Path


def resumer(chemin: Path, titre: str) -> str:
    racine = ET.parse(chemin).getroot()  # noqa: S314 — idem
    suites = [racine] if racine.tag == "testsuite" else list(racine)
    total = sum(int(s.get("tests", 0)) for s in suites)
    sautes = sum(int(s.get("skipped", 0)) for s in suites)
    echecs = []
    for cas in racine.iter("testcase"):
        for genre in ("failure", "error"):
            e = cas.find(genre)
            if e is not None:
                message = (e.get("message") or e.text or "").strip().splitlines()
                echecs.append((f"{cas.get('classname', '')}::{cas.get('name', '')}", genre,
                               message[0][:200] if message else ""))
    lignes = [f"### {titre}", "",
              f"**{total - sautes - len(echecs)} réussis, {len(echecs)} en échec, {sautes} sautés**", ""]
    if echecs:
        lignes += ["| Test | Erreur |", "|---|---|"]
        lignes += [f"| `{nom}` | {genre} : {msg.replace('|', '\\|')} |" for nom, genre, msg in echecs[:50]]
        if len(echecs) > 50:
            lignes.append(f"\n… et {len(echecs) - 50} autres")
    return "\n".join(lignes) + "\n"


def main() -> None:
    chemin = Path(sys.argv[1])
    if not chemin.exists():
        print(f"pas de rapport {chemin} : la suite n'a pas fini (voir le journal)")
        return
    texte = resumer(chemin, sys.argv[2] if len(sys.argv) > 2 else "Tests")
    cible = os.environ.get("GITHUB_STEP_SUMMARY")
    if cible:
        with open(cible, "a", encoding="utf-8") as f:
            f.write(texte)
    else:
        sys.stdout.write(texte)


if __name__ == "__main__":
    main()

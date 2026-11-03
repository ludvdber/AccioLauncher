#!/usr/bin/env python
"""Liste les textes d'un games.json qui n'ont pas leur traduction. N'écrit RIEN.

Le catalogue porte ses propres traductions (blocs `i18n`, résolus par
`catalogue_blocs._loc`) : c'est lui la source, on les y corrige à la main. Ce
script ne fait que dire ce qui manque, langue par langue, pour chaque champ que
`_loc` traduit : `name`, `description`, `warning`, `controller_note` des jeux,
`changes` des versions, `role` des contributeurs (un nom propre ne se traduit
pas). Les langues sont celles de l'interface (`src/data/i18n/*.json`).

Usage :
    python tools/verifier_i18n_catalogue.py src/data/games.json
    python tools/verifier_i18n_catalogue.py ../accio-launcher-games/games.json

Code 0 : tout est traduit ; 1 : il manque des traductions (listées) ; 2 : usage.
"""

import json
import sys
from pathlib import Path
from typing import Any

_I18N = Path(__file__).resolve().parent.parent / "src" / "data" / "i18n"
LANGUES = tuple(sorted(p.stem for p in _I18N.glob("*.json")))

_CHAMPS_JEU = ("name", "description", "warning", "controller_note")


def _manque(bloc: dict[str, Any], champ: str, langue: str) -> bool:
    """Le champ a un texte français, et `langue` n'en a pas de traduction."""
    valeur = bloc.get(champ)
    if not valeur:
        return False
    traductions = bloc.get("i18n")
    entree = traductions.get(langue) if isinstance(traductions, dict) else None
    traduit = entree.get(champ) if isinstance(entree, dict) else None
    if isinstance(valeur, list):
        return not (isinstance(traduit, list) and len(traduit) == len(valeur))
    return not (isinstance(traduit, str) and traduit.strip())


def manquants(catalogue: dict[str, Any], langues: tuple[str, ...] = LANGUES) -> list[str]:
    """Une ligne lisible par traduction manquante, dans l'ordre du catalogue."""
    lignes: list[str] = []
    for jeu in catalogue.get("games", []):
        if not isinstance(jeu, dict):
            continue
        gid = jeu.get("id", "?")
        for langue in langues:
            lignes += [f"{langue} · {gid} · {champ}" for champ in _CHAMPS_JEU if _manque(jeu, champ, langue)]
            for version in jeu.get("versions", []):
                if isinstance(version, dict) and _manque(version, "changes", langue):
                    lignes.append(f"{langue} · {gid} v{version.get('version', '?')} · changes")
    for contributeur in catalogue.get("contributors", []):
        if isinstance(contributeur, dict):
            lignes += [f"{langue} · contributeur {contributeur.get('name', '?')} · role"
                       for langue in langues if _manque(contributeur, "role", langue)]
    return lignes


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    chemin = Path(argv[1])
    catalogue = json.loads(chemin.read_text(encoding="utf-8"))
    absents = manquants(catalogue)
    if not absents:
        print(f"{chemin} : tout est traduit ({', '.join(LANGUES)}).")
        return 0
    print(f"{chemin} : {len(absents)} traduction(s) manquante(s) — à ajouter dans les blocs `i18n` :")
    for ligne in absents:
        print(f"  · {ligne}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Fuzzing de l'analyse du catalogue distant (Atheris, Linux).

    mkdir corpus && cp src/data/games.json corpus/
    python fuzz/fuzz_catalogue.py corpus -max_total_time=300

Le corpus de départ est le vrai `games.json` (cf. fuzz.yml) : les mutations
partent d'un catalogue valide, donc atteignent les validations au lieu de
s'arrêter au premier caractère JSON invalide.
"""

import json
import logging
import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.CRITICAL)   # un avertissement par jeu rejeté ralentirait tout

with atheris.instrument_imports():
    from fuzz import invariants


def test_un(data: bytes) -> None:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return      # pas du JSON : `load_catalog` le rattrape avant l'analyse
    invariants.catalogue(raw)


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_un)
    atheris.Fuzz()

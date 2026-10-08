"""Fuzzing du garde-fou anti-Zip-Slip des archives de jeu (Atheris, Linux).

    python fuzz/fuzz_archive.py -max_total_time=300
"""

import logging
import sys
import tempfile
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.CRITICAL)

with atheris.instrument_imports():
    from fuzz import invariants

# Un vrai dossier, créé une fois : `resolve()` suit les liens symboliques, et
# une destination inexistante ne l'exercerait pas comme à l'extraction.
_DESTINATION = Path(tempfile.mkdtemp()) / "jeu"
_DESTINATION.mkdir()


def test_un(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    nom = fdp.ConsumeUnicodeNoSurrogates(300)
    invariants.entree_archive(_DESTINATION, nom)
    invariants.meme_verdict(nom)


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_un)
    atheris.Fuzz()

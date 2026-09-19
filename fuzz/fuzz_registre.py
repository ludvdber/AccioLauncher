"""Fuzzing du .reg importé par un regedit ADMINISTRATEUR (Atheris, Linux).

    python fuzz/fuzz_registre.py -max_total_time=300

Pure fabrication de texte : rien n'est écrit dans aucun registre.
"""

import logging
import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.CRITICAL)

with atheris.instrument_imports():
    from fuzz import invariants


def test_un(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    ruche = fdp.PickValueInList(["HKCU", "HKLM", "HKCR", ""])
    # Un préfixe plausible de temps en temps, sinon presque tout s'arrête
    # au premier refus (« hors de Software ») et le reste n'est jamais exercé.
    prefixe = fdp.PickValueInList(["", "Software\\Editeur\\", "SOFTWARE/Electronic Arts/"])
    cle = prefixe + fdp.ConsumeUnicodeNoSurrogates(40)
    valeurs: dict = {}
    for _ in range(fdp.ConsumeIntInRange(0, 4)):
        nom = fdp.ConsumeUnicodeNoSurrogates(12)
        if fdp.ConsumeBool():
            valeurs[nom] = fdp.ConsumeUnicodeNoSurrogates(40)
        else:
            valeurs[nom] = fdp.ConsumeIntInRange(-2, 2**33)
    invariants.registre_ecrit(ruche, cle, valeurs, fdp.PickValueInList([32, 64]))


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_un)
    atheris.Fuzz()

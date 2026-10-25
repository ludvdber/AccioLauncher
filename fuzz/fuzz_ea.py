"""Fuzzing des archives EA de HP4 à HP6 lues par la Médiathèque (Atheris, Linux).

    python fuzz/fuzz_ea.py -max_total_time=300

Les archives viennent du dossier du jeu, qu'un mod ou une copie abîmée peut
avoir changé : leur lecture ne doit ni lever, ni sortir du fichier, ni tourner
sans fin. Rien n'est écrit ailleurs que dans un fichier temporaire.
"""

import logging
import struct
import sys
import tempfile
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.CRITICAL)

with atheris.instrument_imports():
    from fuzz import invariants

_FICHIER = Path(tempfile.mkdtemp()) / "music.big"


def _archive(fdp: atheris.FuzzedDataProvider) -> bytes:
    if fdp.ConsumeBool():
        return fdp.ConsumeBytes(fdp.remaining_bytes())
    # Une archive plausible, sinon presque tout s'arrête au premier octet : en-tête
    # BIGF, quelques entrées, puis des blocs SC.. aux tailles parfois fausses.
    corps = bytearray()
    for _ in range(fdp.ConsumeIntInRange(0, 12)):
        etiquette = fdp.PickValueInList([b"SCHl", b"SCCl", b"SCDl", b"SCEl", b"\0\0\0\0"])
        n = fdp.ConsumeIntInRange(0, 64)
        annonce = fdp.PickValueInList([n + 8, n, 0, 7, 2**32 - 1])
        corps += etiquette + struct.pack("<I", annonce) + fdp.ConsumeBytes(n)
    noms = [fdp.ConsumeBytes(12).replace(b"\0", b"") + b"\0" for _ in range(fdp.ConsumeIntInRange(0, 4))]
    taille_tete = 16 + sum(8 + len(nom) for nom in noms)
    entrees = b"".join(
        struct.pack(">II", fdp.ConsumeIntInRange(0, taille_tete + len(corps) + 8),
                    fdp.ConsumeIntInRange(0, len(corps) + 8)) + nom
        for nom in noms)
    nombre = fdp.PickValueInList([len(noms), len(noms) + 1, 2**31])
    tete = (fdp.PickValueInList([b"BIGF", b"BIG4"]) + struct.pack("<I", taille_tete + len(corps))
            + struct.pack(">II", nombre, taille_tete))
    return tete + entrees + bytes(corps)


def test_un(data: bytes) -> None:
    _FICHIER.write_bytes(_archive(atheris.FuzzedDataProvider(data)))
    invariants.archive_ea(_FICHIER)


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_un)
    atheris.Fuzz()

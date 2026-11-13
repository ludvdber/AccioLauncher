"""Une date de fichier ne se fie qu'une fois passée (`src/core/signature.py`).

CI Windows, 2026-11-13 : « SSAAFactor=1.5 » réécrit en « SSAAFactor=2.0 » (même taille, même
tic d'horloge) gardait sa signature et se relisait 1.5. Contre-épreuve : avec l'ancienne
signature (date, taille), `test_meme_taille_meme_date` échoue dans les quatre caches.
"""

import json
import os
import time

import pytest

from src.core import images_ea, json_garde, sans_casse, signature


def _a_la_date(chemin, ns):
    os.utime(chemin, ns=(ns, ns))


def test_fiable_seulement_une_fois_passee(tmp_path):
    f = tmp_path / "a.ini"
    f.write_bytes(b"x")
    assert signature.fiable(f.stat()) is None                       # vient d'être écrit
    _a_la_date(f, time.time_ns() + 60_000_000_000)
    assert signature.fiable(f.stat()) is None                       # date dans le futur
    _a_la_date(f, time.time_ns() - 10_000_000_000)
    etat = f.stat()
    assert signature.fiable(etat) == (etat.st_mtime_ns, etat.st_size)


@pytest.mark.parametrize("cache", ["json", "dossier", "archive"])
def test_meme_taille_meme_date(tmp_path, cache):
    """Écrit, lu, réécrit de même taille à la même date : la seconde lecture voit le neuf."""
    maintenant = time.time_ns()
    if cache == "json":
        f = tmp_path / "d.json"
        f.write_text(json.dumps({"v": 1}), encoding="utf-8")
        _a_la_date(f, maintenant)
        assert json_garde.lire(f) == {"v": 1}
        f.write_text(json.dumps({"v": 2}), encoding="utf-8")
        _a_la_date(f, maintenant)
        assert json_garde.lire(f) == {"v": 2}
    elif cache == "dossier":
        (tmp_path / "A.utx").write_bytes(b"")
        _a_la_date(tmp_path, maintenant)
        assert sans_casse.trouver(tmp_path, "b.utx") is None
        (tmp_path / "B.utx").write_bytes(b"")
        _a_la_date(tmp_path, maintenant)
        assert sans_casse.trouver(tmp_path, "b.utx") == tmp_path / "B.utx"
    else:
        import struct

        def archive(nom: bytes) -> bytes:
            tete = 16 + 8 + len(nom)
            return (b"BIGF" + struct.pack("<I", 0) + struct.pack(">II", 1, tete)
                    + struct.pack(">II", tete, 2) + nom + b"ok")
        f = tmp_path / "data.big"
        f.write_bytes(archive(b"a.str\0"))
        _a_la_date(f, maintenant)
        assert images_ea.entree_big(f, "a.str") == b"ok"
        f.write_bytes(archive(b"b.str\0"))
        _a_la_date(f, maintenant)
        assert images_ea.entree_big(f, "b.str") == b"ok"

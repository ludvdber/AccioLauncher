"""Une taille en octets ne traverse jamais un signal Qt en `int`.

Côté Qt, un `int` fait 32 bits. La page Paramètres affichait « 6 jeu(x)
installé(s) — 147 Mo utilisés » pour 12,2 Go réels : 13 039 361 350 octets
arrivaient en 154 459 462, le modulo 2³² exact (mesuré le 2026-09-24).
Au-delà de 2 Gio, un slot reçoit même des valeurs NÉGATIVES.

Aucun test ne pouvait le voir : il faut plus de 4 Gio de fichiers pour que
le total déborde. On vérifie donc la DÉCLARATION, dans le méta-objet Qt, et
on fait passer un vrai total de 13 Go par le signal du scan disque.
"""

import pytest

from src.core.downloader import Downloader
from src.ui.disk_scan_worker import DiskScanWorker
from src.ui.game_operations import GameOperations
from src.ui.trailer_store import TrailerStore

TREIZE_GO = 13_039_361_350      # le total réel de la machine où c'est arrivé


def _types(classe, signal: str) -> list[str]:
    meta = classe.staticMetaObject
    for i in range(meta.methodCount()):
        methode = meta.method(i)
        if bytes(methode.name()).decode() == signal:
            return [bytes(t).decode() for t in methode.parameterTypes()]
    raise AssertionError(f"{classe.__name__}.{signal} introuvable")


# (classe, signal, rangs des paramètres qui portent des OCTETS)
SIGNAUX_EN_OCTETS = [
    (DiskScanWorker, "result", [1]),
    (Downloader, "progress", [0, 1]),
    (GameOperations, "download_progress", [0, 1]),
    (TrailerStore, "progress", [2, 3]),
]


@pytest.mark.parametrize("classe, signal, rangs", SIGNAUX_EN_OCTETS,
                         ids=[f"{c.__name__}.{s}" for c, s, _ in SIGNAUX_EN_OCTETS])
def test_les_octets_voyagent_en_64_bits(classe, signal, rangs):
    types = _types(classe, signal)
    for rang in rangs:
        assert types[rang] == "qlonglong", (
            f"{classe.__name__}.{signal} porte des octets en {types[rang]} : "
            f"tronqué au-delà de 4 Gio, négatif au-delà de 2 Gio")


def test_le_total_du_disque_arrive_intact(qtbot):
    worker = DiskScanWorker([])
    recus = []
    worker.result.connect(lambda n, octets: recus.append(octets))
    worker.result.emit(6, TREIZE_GO)
    assert recus == [TREIZE_GO]

"""Temporaire (retiré après usage) : la fenêtre entière, fond sur la carte graphique, pour chaque jeu."""
import os
from pathlib import Path


def test_capture(make_window, monkeypatch, qtbot):
    monkeypatch.setenv("ACCIO_FOND_GPU", "1")
    sortie = Path(os.environ["ACCIO_CAPTURES"])
    sortie.mkdir(parents=True, exist_ok=True)
    win = make_window(musique_fond="", son_coupe=True)
    win.resize(1400, 860)
    win.show()
    qtbot.wait(800)
    for i in range(8):
        win._carousel.select(i)
        qtbot.wait(1800)
        win.grab().save(str(sortie / f"{i + 1}.png"))

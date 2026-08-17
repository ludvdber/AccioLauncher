"""Le dialogue de crash ne doit s'ouvrir qu'UNE FOIS.

Sans garde, une exception dans un slot rappelé en boucle (paintEvent, tick du
Ticker à ~30 FPS) empilait une modale par répétition : l'utilisateur devait tuer
le process sans jamais pouvoir copier le rapport — l'exact contraire du but.
"""

import sys

import pytest

pytest.importorskip("pytestqt")  # QApplication requis par le hook

from src.ui import crash_dialog  # noqa: E402


@pytest.fixture
def hooked(qapp, monkeypatch):
    """Installe l'excepthook avec un dialogue factice, et restaure après le test."""
    shown: list[str] = []
    monkeypatch.setattr(crash_dialog, "_show_crash_dialog", lambda report: shown.append(report))
    original = sys.excepthook
    crash_dialog.reset_crash_state()
    crash_dialog.install_excepthook()
    yield shown
    sys.excepthook = original
    crash_dialog.reset_crash_state()


def _boom(message: str = "boom") -> tuple:
    try:
        raise ValueError(message)
    except ValueError:
        return sys.exc_info()


class TestDialogueUneSeuleFois:
    def test_premiere_exception_ouvre_le_dialogue(self, hooked):
        sys.excepthook(*_boom())
        assert len(hooked) == 1
        assert "ValueError: boom" in hooked[0]

    def test_repetitions_ne_reouvrent_pas(self, hooked):
        for _ in range(50):  # simule un paintEvent qui lève en boucle
            sys.excepthook(*_boom())
        assert len(hooked) == 1, "une seule modale, quelle que soit la répétition"

    def test_exception_differente_nouvre_pas_non_plus(self, hooked):
        sys.excepthook(*_boom("première"))
        sys.excepthook(*_boom("deuxième"))
        assert len(hooked) == 1
        assert "première" in hooked[0]


class TestReentrance:
    def test_exception_pendant_le_dialogue_ne_recurse_pas(self, qapp, monkeypatch):
        """Si le dialogue lui-même lève, on ne doit pas rouvrir un dialogue."""
        calls: list[str] = []

        def _reentrant(report: str) -> None:
            calls.append(report)
            # Le dialogue crashe → le hook est rappelé pendant son propre exec()
            sys.excepthook(*_boom("pendant le dialogue"))

        monkeypatch.setattr(crash_dialog, "_show_crash_dialog", _reentrant)
        original = sys.excepthook
        crash_dialog.reset_crash_state()
        crash_dialog.install_excepthook()
        try:
            sys.excepthook(*_boom())
            assert len(calls) == 1, "pas de récursion dans le handler de crash"
        finally:
            sys.excepthook = original
            crash_dialog.reset_crash_state()


class TestComportementsPreserves:
    def test_keyboard_interrupt_garde_le_comportement_standard(self, hooked, monkeypatch):
        seen: list[type] = []
        monkeypatch.setattr(sys, "__excepthook__", lambda t, v, tb: seen.append(t))
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            sys.excepthook(*sys.exc_info())
        assert seen == [KeyboardInterrupt]
        assert hooked == [], "Ctrl+C n'est pas un crash"

    def test_reset_rearme_le_dialogue(self, hooked):
        sys.excepthook(*_boom())
        crash_dialog.reset_crash_state()
        sys.excepthook(*_boom())
        assert len(hooked) == 2
